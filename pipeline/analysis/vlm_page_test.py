"""
vlm_page_test.py -- is a local 7B VLM (Qwen2-VL-7B-Instruct) smart enough to classify degraded
19th/20th-c. session-law page images: statute BODY vs MEMBER ROSTER vs INDEX/TOC vs REPRINT/divider?

Runs on the surya venv (torch 2.7+cu128, transformers 4.45 -> Qwen2-VL supported). Downloads the ~16GB
model on first run. Scores against the same 7 ground-truth pages as the Surya test (fine label + the
binary BODY-vs-exclude decision that matters for ingestion).

Run with the surya venv python:
  C:/Users/patolex/PatoLex-scratch/ocr-engines/surya-venv/Scripts/python.exe <thisfile> [spot_dir]
"""
import os, sys, re
from PIL import Image

SPOT  = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\patolex\_spot"
MODEL = os.environ.get("VLM_MODEL", "Qwen/Qwen2-VL-7B-Instruct")

GT = {
    "s1_1913_1405.png":      ("BODY",      "appropriations act"),
    "s2_186364_74.png":      ("REPRINT",   "reprinted-proclamation divider"),
    "s3_186970_847.png":     ("BODY",      "metes-and-bounds survey act"),
    "s4_1862_9.png":         ("INDEX_TOC", "CONTENTS table"),
    "s5_1863_26.png":        ("INDEX_TOC", "TABLE OF ACTS"),
    "c1_1862_34.png":        ("ROSTER",    "member roster"),
    "c2_187374code_485.png": ("INDEX_TOC", "INDEX TO POLITICAL CODE"),
}

PROMPT = (
    "This is a scanned page from a 19th/early-20th-century California session-laws volume. "
    "The scan/OCR may be degraded. Classify the PAGE into exactly ONE category:\n"
    "- BODY: the actual text of an act/statute/code section (including appropriations acts with dollar "
    "line-items, and acts containing land/street survey 'metes and bounds' descriptions).\n"
    "- ROSTER: a list/table of people -- legislators/officers/members, with columns like Name / County / Residence.\n"
    "- INDEX_TOC: a table of contents, alphabetical index, or 'table of acts' (entries with page numbers), "
    "or a code section index with Amended/Repealed/Added annotations. NOT statute text.\n"
    "- REPRINT: a reprinted external document or proclamation, a title page, or a section divider.\n"
    "- OTHER: blank, illustration, or none of the above.\n"
    "Look at the page LAYOUT and headings. Answer with ONLY the category word on the first line, then a "
    "short reason."
)
LABELS = ["BODY", "ROSTER", "INDEX_TOC", "REPRINT", "OTHER"]

def parse_label(txt):
    up = txt.upper()
    for lab in LABELS:                      # first label token that appears
        m = re.search(r"\b" + re.escape(lab) + r"\b", up)
        if m:
            return lab, m.start()
    return "OTHER", 1 << 30

def main():
    import torch
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
    print(f"loading {MODEL} (downloads ~16GB on first run)...", flush=True)
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        MODEL, torch_dtype=torch.bfloat16, device_map="cuda")
    processor = AutoProcessor.from_pretrained(MODEL)
    model.eval()

    fine_ok = 0; bin_ok = 0; n = 0
    print(f"\n{'file':<24}{'truth':<11}{'vlm':<11}{'fine':<6}{'binОК':<7} reason")
    for fn, (truth, desc) in GT.items():
        fp = os.path.join(SPOT, fn)
        if not os.path.exists(fp):
            print(f"{fn:<24} MISSING {fp}"); continue
        img = Image.open(fp).convert("RGB")
        messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": PROMPT}]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[img], return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=80, do_sample=False)
        gen = out[0][inputs.input_ids.shape[1]:]
        resp = processor.decode(gen, skip_special_tokens=True).strip()
        pred, _ = parse_label(resp)
        fine = (pred == truth)
        binp = "BODY" if pred == "BODY" else "NONBODY"
        bint = "BODY" if truth == "BODY" else "NONBODY"
        bok = (binp == bint)
        fine_ok += fine; bin_ok += bok; n += 1
        reason = resp.replace("\n", " ")[:70]
        print(f"{fn:<24}{truth:<11}{pred:<11}{'Y' if fine else 'N':<6}{'Y' if bok else 'N':<7} {reason}  ({desc})")
    print(f"\nVLM fine-label accuracy:      {fine_ok}/{n}")
    print(f"VLM BODY-vs-exclude accuracy: {bin_ok}/{n}")

if __name__ == "__main__":
    main()
