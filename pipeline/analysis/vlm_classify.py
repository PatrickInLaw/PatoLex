"""
vlm_classify.py -- run the local Qwen2-VL-7B over a directory of page images and print one category per file.
Used as the TIEBREAKER check: does the local 7B agree with the strong model on disputed page-type calls?

  <surya-venv-python> vlm_classify.py --dir <pngdir> [--vram-frac 0.85]
Prints: <file>\t<CATEGORY>\t<reason>.  Categories: BODY | ROSTER | INDEX_TOC | REPRINT | OTHER.
"""
import argparse, os, sys, glob, re
from PIL import Image

MODEL = os.environ.get("VLM_MODEL", "Qwen/Qwen2-VL-7B-Instruct")
PROMPT = (
    "This is a scanned page from a 19th/early-20th-century California session-laws volume; the scan may be "
    "degraded. Classify the PAGE into exactly ONE category:\n"
    "- BODY: actual text of an act/statute/code section (INCLUDING appropriations acts that are lists of "
    "items with dollar amounts, and acts with land/street metes-and-bounds descriptions).\n"
    "- ROSTER: a list/table of PEOPLE (legislators/officers/members), columns like Name / County / Residence.\n"
    "- INDEX_TOC: a table of contents, alphabetical index, 'table of acts' (act titles + page numbers), or a "
    "code section index with Amended/Repealed/Added annotations. NOT statute text.\n"
    "- REPRINT: a reprinted external document/proclamation, a title page, or a section divider.\n"
    "- OTHER: blank, illustration, illegible.\n"
    "Distinguish an appropriations ACT (BODY: prose 'Be it enacted', running head 'STATUTES OF CALIFORNIA', "
    "section numbers, money for a purpose) from an INDEX/TOC (entries that point to page numbers). "
    "Answer with ONLY the category word on the first line, then a short reason."
)
LABELS = ["BODY", "ROSTER", "INDEX_TOC", "REPRINT", "OTHER"]

def parse_label(txt):
    up = txt.upper()
    for lab in LABELS:
        if re.search(r"\b" + re.escape(lab) + r"\b", up):
            return lab
    return "OTHER"

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--vram-frac", type=float, default=0.0, help="optional hard cap on this proc's GPU memory")
    a = ap.parse_args()

    import torch
    if a.vram_frac and torch.cuda.is_available():
        torch.cuda.set_per_process_memory_fraction(a.vram_frac, 0)
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
    print(f"loading {MODEL} ...", flush=True)
    model = Qwen2VLForConditionalGeneration.from_pretrained(MODEL, torch_dtype=torch.bfloat16)
    model.to("cuda"); model.eval()
    processor = AutoProcessor.from_pretrained(MODEL)

    for fp in sorted(glob.glob(os.path.join(a.dir, "*.png"))):
        img = Image.open(fp).convert("RGB")
        msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": PROMPT}]}]
        text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[img], return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=80, do_sample=False)
        resp = processor.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        print(f"{os.path.basename(fp)}\t{parse_label(resp)}\t{resp.replace(chr(10),' ')[:90]}", flush=True)

if __name__ == "__main__":
    main()
