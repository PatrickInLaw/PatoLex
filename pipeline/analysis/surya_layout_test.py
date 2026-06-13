"""
surya_layout_test.py -- can Surya's LAYOUT model tell statute BODY from non-body (roster/TOC/index)?

Runs the (already-installed) Surya 0.13 LayoutPredictor on the 7 ground-truth spot pages and scores it.
Surya emits structural region labels (Text / Table / List-item / Section-header / Title / Page-header ...);
it does NOT have a semantic "TOC" or "roster" label, so we test the decision that actually matters for
ingestion: BODY (ingest) vs NON-BODY (exclude). Mapping: a page whose region AREA is dominated by Text =>
BODY; dominated by Table/List-item/Page-header (or mostly Title/Section-header with little Text) => NON-BODY.

Run with the surya venv python:
  C:\Users\patolex\PatoLex-scratch\ocr-engines\surya-venv\Scripts\python.exe <thisfile> [spot_dir]
"""
import os, sys
from collections import defaultdict
from PIL import Image

SPOT = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\patolex\_spot"

# ground truth from the blind Sonnet visual pass + controls
GT = {
    "s1_1913_1405.png":      ("BODY",     "appropriations act"),
    "s2_186364_74.png":      ("NONBODY",  "reprinted-proclamation divider"),
    "s3_186970_847.png":     ("BODY",     "metes-and-bounds survey act"),
    "s4_1862_9.png":         ("NONBODY",  "CONTENTS table"),
    "s5_1863_26.png":        ("NONBODY",  "TABLE OF ACTS"),
    "c1_1862_34.png":        ("NONBODY",  "member roster"),
    "c2_187374code_485.png": ("NONBODY",  "INDEX TO POLITICAL CODE"),
}

NONBODY_LABELS = {"Table", "List-item", "List", "Page-header", "Page-footer", "Table-of-contents"}
STRUCT_TITLE   = {"Title", "Section-header", "Caption"}

def classify(layout_result, page_area):
    area = defaultdict(float)
    for b in layout_result.bboxes:
        x1, y1, x2, y2 = b.bbox
        a = max(0.0, (x2 - x1)) * max(0.0, (y2 - y1))
        area[b.label] += a
    if not area:
        return "NONBODY", {}, "no regions"
    text_a   = area.get("Text", 0.0)
    nonb_a   = sum(area.get(l, 0.0) for l in NONBODY_LABELS)
    title_a  = sum(area.get(l, 0.0) for l in STRUCT_TITLE)
    total    = sum(area.values()) or 1.0
    dist = {k: round(v / total, 3) for k, v in sorted(area.items(), key=lambda kv: -kv[1])}
    # decision: dominated by table/list/headers => NONBODY; mostly title with little text => NONBODY (divider);
    # else if Text is the plurality => BODY
    if nonb_a > text_a:
        return "NONBODY", dist, "table/list/header-dominant"
    if text_a < 0.15 * total and title_a > text_a:
        return "NONBODY", dist, "title/divider, little text"
    return "BODY", dist, "text-dominant"

def main():
    from surya.layout import LayoutPredictor
    print("loading Surya LayoutPredictor (downloads layout weights on first run)...", flush=True)
    predictor = LayoutPredictor()
    correct = 0; n = 0
    print(f"\n{'file':<24}{'truth':<9}{'surya':<9}{'ok':<4} reason | region-area-dist")
    for fn, (truth, desc) in GT.items():
        fp = os.path.join(SPOT, fn)
        if not os.path.exists(fp):
            print(f"{fn:<24} MISSING {fp}"); continue
        img = Image.open(fp).convert("RGB")
        res = predictor([img])[0]
        verdict, dist, reason = classify(res, img.size[0] * img.size[1])
        ok = (verdict == truth); correct += ok; n += 1
        print(f"{fn:<24}{truth:<9}{verdict:<9}{'Y' if ok else 'N':<4} {reason}  | {dist}   ({desc})")
    print(f"\nSURYA-LAYOUT body/non-body accuracy: {correct}/{n}")

if __name__ == "__main__":
    main()
