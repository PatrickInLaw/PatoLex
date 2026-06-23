"""spotcheck_lostheader.py -- adversarial spot-check of recovered lost-header acts.
For a stratified sample (single-slot + multi-slot, MATCH + POS-ONLY), pull the OCR page
the act was recovered from and print the header region + a confirmation that the page sits
between the anchor pages and the assigned number is the open slot.
  python spotcheck_lostheader.py [N]
"""
import sys, json, random
from pathlib import Path
import importlib.util
REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("config", str(REPO / "pipeline" / "config.py"))
config = importlib.util.module_from_spec(spec); spec.loader.exec_module(config)
ROOT = Path(config.path_for("data_root"))

K = int(sys.argv[1]) if len(sys.argv) > 1 else 20

recs = []
for f in sorted(ROOT.glob("production-*/parsed_acts_lostheader.json")):
    label = f.parent.name[len("production-"):]
    d = json.loads(f.read_text(encoding="utf-8"))
    for r in d["recovered_acts"]:
        r["_label"] = label
        recs.append(r)

random.seed(42)
# stratify: ensure we include POS-ONLY and multi-slot
pos_only = [r for r in recs if r["printed_numeral"] != r["chapter_int"]]
multi = [r for r in recs if r["gap_open_slots"] > 1]
match = [r for r in recs if r["printed_numeral"] == r["chapter_int"]]
sample = []
random.shuffle(pos_only); random.shuffle(match); random.shuffle(multi)
sample += pos_only[:10] + match[:6] + multi[:4]
# dedup
seen = set(); uniq = []
for r in sample:
    k = (r["_label"], r["source_page"], r["chapter_int"])
    if k in seen: continue
    seen.add(k); uniq.append(r)
sample = uniq[:K]

_page_cache = {}
def page_text(label, pg1):
    if label not in _page_cache:
        ocr = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
        _page_cache[label] = json.loads(ocr.read_text(encoding="utf-8"))
    return _page_cache[label].get(str(pg1 - 1), {}).get("consensus_text", "")

import re as _re
HDR = _re.compile(r"^[^A-Za-z0-9]{0,4}C[Hh][A-Za-z]{0,5}\.?[.,\s]+[0-9]", _re.M)
for i, r in enumerate(sample, 1):
    corro = "MATCH" if r["printed_numeral"] == r["chapter_int"] else "POS-ONLY"
    print(f"\n[{i}] {r['_label']} ch {r['chapter_int']} (printed {r['printed_numeral']}, {corro}) "
          f"slots={r['gap_open_slots']} anchors {r['lo_anchor']}-{r['hi_anchor']} p{r['source_page']}")
    txt = page_text(r["_label"], r["source_page"])
    lines = txt.split("\n")
    # locate the CHAPTER header line on this page; print a window starting there
    start = 0
    for k, l in enumerate(lines):
        if HDR.match(l.strip()):
            start = k; break
    win = [l.strip() for l in lines[start:start + 9] if l.strip()]
    for l in win:
        print("    |", l[:100])
