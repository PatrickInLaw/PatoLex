"""Precision spot-check: sample N FORM-A (joined, the NEW recoveries) act records
from parsed_acts_early.json and print their header/title line so a human can judge
real-act-start vs false-positive. Deterministic stride sample for reproducibility.
  python _diag_early_precision.py <label> [N]
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
ROOT = Path(config.path_for("data_root"))

label = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 30
p = ROOT / ("production-" + label) / "parsed_acts_early.json"
data = json.loads(p.read_text(encoding="utf-8"))
acts = data["flagged_acts"]
form_a = [a for a in acts if a.get("form") == "A"]
form_b = [a for a in acts if a.get("form") == "B"]
print(f"{label}: total kept={len(acts)} (A={len(form_a)} B={len(form_b)})")
pool = form_a if form_a else acts
stride = max(1, len(pool) // N)
sample = pool[::stride][:N]
print(f"-- precision sample of {len(sample)} FORM-{'A' if form_a else '(all)'} starts --")
for a in sample:
    t = a["title"][:92]
    print(f"  pg{a['source_page']:>4} ord{a['in_act_order']:>4} ch~{a['chapter_int']:<5}| {t}")
