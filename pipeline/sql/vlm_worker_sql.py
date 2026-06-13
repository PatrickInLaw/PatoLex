"""
vlm_worker_sql.py -- the VLM TIEBREAKER worker (5090). Loads the local Qwen2-VL-7B ONCE and drains dbo.vlm_queue
(the ambiguous pages routed by the reconcile pass), reading each page's PERSISTED render PNG and recording a
per-page verdict. SELF-GATES: it will not load the model until the shape run is finished (no shape pending/working)
so it never contends with the shape workers for VRAM.

  vlm_worker_sql.py <worker_id> --render-root <dir> [--vram-frac 0.85] [--exit-when-drained]
PATOLEX_QUEUE_DSN from env.
"""
import argparse, os, re, sys, time
import pyodbc
from PIL import Image

MODEL = os.environ.get("VLM_MODEL", "Qwen/Qwen2-VL-7B-Instruct")
LABELS = ["BODY", "ROSTER", "INDEX_TOC", "REPRINT", "OTHER"]
PROMPT = (
    "This is a scanned page from a 19th/early-20th-century California session-laws volume; the scan may be "
    "degraded. Classify the PAGE into exactly ONE category:\n"
    "- BODY: actual text of an act/statute/code section (INCLUDING appropriations acts that are lists of items "
    "with dollar amounts, and acts with land/street metes-and-bounds descriptions).\n"
    "- ROSTER: a list/table of PEOPLE (legislators/officers/members), columns like Name / County / Residence.\n"
    "- INDEX_TOC: a table of contents, alphabetical index, 'table of acts' (act titles + page numbers), or a "
    "code section index with Amended/Repealed/Added annotations. NOT statute text.\n"
    "- REPRINT: a reprinted external document/proclamation, a title page, or a section divider.\n"
    "- OTHER: blank, illustration, illegible.\n"
    "Answer with ONLY the category word on the first line."
)

def parse_label(t):
    up = t.upper()
    for lab in LABELS:
        if re.search(r"\b" + re.escape(lab) + r"\b", up):
            return lab
    return "OTHER"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def connect():
    return pyodbc.connect(os.environ["PATOLEX_QUEUE_DSN"], autocommit=True)

def shape_busy(cx):
    return cx.execute("SELECT COUNT(*) FROM dbo.ocr_queue WHERE shape_state IN ('pending','working')").fetchone()[0]

def reconcile_busy(cx):
    return cx.execute("SELECT COUNT(*) FROM dbo.ocr_queue WHERE reconcile_state IN ('pending','working')").fetchone()[0]

CLAIM = """SET NOCOUNT ON;
UPDATE q SET state='working', lease_token=NEWID(), lease_expires_at=DATEADD(minute,15,sysutcdatetime()),
             claimed_by=?, heartbeat_at=sysutcdatetime()
 OUTPUT inserted.id, inserted.label, inserted.pdf, inserted.pidx, inserted.lease_token
  FROM dbo.vlm_queue AS q WITH (UPDLOCK, ROWLOCK)
 WHERE q.id = (SELECT TOP (1) q2.id FROM dbo.vlm_queue AS q2 WITH (READPAST, UPDLOCK, ROWLOCK)
               WHERE q2.state='pending' OR (q2.state='working' AND q2.lease_expires_at < sysutcdatetime())
               ORDER BY q2.id);"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("worker_id")
    ap.add_argument("--render-root", required=True)
    ap.add_argument("--vram-frac", type=float, default=0.85)
    ap.add_argument("--exit-when-drained", action="store_true")
    a = ap.parse_args()

    cx = connect()
    log(f"{a.worker_id} online role=vlm; waiting for shape run to finish before loading the model...")
    while shape_busy(cx) > 0:
        time.sleep(30)
    log("shape run complete -> loading the 7B (GPU now free)")

    import torch
    if a.vram_frac and torch.cuda.is_available():
        torch.cuda.set_per_process_memory_fraction(a.vram_frac, 0)
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
    model = Qwen2VLForConditionalGeneration.from_pretrained(MODEL, torch_dtype=torch.bfloat16)
    model.to("cuda"); model.eval()
    processor = AutoProcessor.from_pretrained(MODEL)
    log("model loaded; draining vlm_queue")

    empty = 0
    while True:
        row = cx.execute(CLAIM, a.worker_id).fetchone()
        if not row:
            if a.exit_when_drained and reconcile_busy(cx) == 0:
                log("vlm_queue drained and reconcile done -> exit"); return
            empty += 1
            if empty % 10 == 1:
                log("no pending pages; idling (reconcile may still be feeding)")
            time.sleep(20); continue
        empty = 0
        vid, label, pdf, pidx, token = row
        pdfbase = os.path.splitext(pdf)[0]
        png = os.path.join(a.render_root, pdfbase, f"{pidx:04d}.png")
        try:
            if not os.path.exists(png):
                cx.execute("UPDATE dbo.vlm_queue SET state='failed', attempts=attempts+1, error=? WHERE id=? AND lease_token=?",
                           f"no render: {png}"[:400], vid, token)
                continue
            img = Image.open(png).convert("RGB")
            msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": PROMPT}]}]
            text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            inputs = processor(text=[text], images=[img], return_tensors="pt").to(model.device)
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=24, do_sample=False)
            resp = processor.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
            verdict = parse_label(resp)
            cx.execute("UPDATE dbo.vlm_queue SET state='done', verdict=?, done_at=sysutcdatetime() WHERE id=? AND lease_token=?",
                       verdict, vid, token)
        except Exception as e:  # noqa: BLE001
            cx.execute("UPDATE dbo.vlm_queue SET state='failed', attempts=attempts+1, error=? WHERE id=? AND lease_token=?",
                       str(e)[:400], vid, token)

if __name__ == "__main__":
    main()
