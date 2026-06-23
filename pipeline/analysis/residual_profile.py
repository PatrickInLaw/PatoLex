"""residual_profile.py -- classify post-cert residual by SHAPE so we can tell
'interior numeral loss' (a few garbled headers inside a dense, mostly-complete run)
from 'whole-volume-unparsed' sessions (compl% very low -> a different problem).

Reads _residual_after_certify.json and buckets sessions, and for the interior-loss
candidates reports how many residual slots are INTERIOR (have a confident anchor on
BOTH sides within a small window) vs trailing/leading/block gaps.
"""
import json, sys
from pathlib import Path
import importlib.util

REPO = Path(__file__).resolve().parents[2]
def _load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path)); m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); return m
sys.path.insert(0, str(REPO / "pipeline")); sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
import config  # noqa
ROOT = Path(config.path_for("data_root"))

rep = json.loads((ROOT / "_residual_after_certify.json").read_text(encoding="utf-8"))

def interior_count(present_sorted, residual_set, N):
    """count residual chapters that sit between two PRESENT confident numbers
    (i.e. there exists a present number < c and a present number > c)."""
    if not present_sorted:
        return 0
    lo = present_sorted[0]; hi = present_sorted[-1]
    return sum(1 for c in residual_set if lo < c < hi)

buckets = {"dense_>=85": [], "mid_50_85": [], "sparse_<50": []}
interior_total = 0
sessions = rep["sessions"]
for s in sessions:
    N = s["N"]; pct = s["compl_pct"]
    residual = set(s["residual"])
    present = sorted(set(range(1, N + 1)) - residual)
    ic = interior_count(present, residual, N)
    s["_interior"] = ic
    interior_total += ic
    b = "dense_>=85" if pct >= 85 else ("mid_50_85" if pct >= 50 else "sparse_<50")
    buckets[b].append(s)

print("INTERIOR residual (between present anchors) across ALL sessions:", interior_total)
for b, ss in buckets.items():
    tot_int = sum(x["_interior"] for x in ss)
    tot_miss = sum(x["missing"] for x in ss)
    print(f"\n=== {b}: {len(ss)} sessions, total missing={tot_miss}, interior={tot_int} ===")
    for s in sorted(ss, key=lambda x: -x["_interior"])[:15]:
        print(f"  {s['session']:<30} N={s['N']:>4} have={s['have']:>4} "
              f"miss={s['missing']:>4} ({s['compl_pct']}%) interior={s['_interior']:>4}")
