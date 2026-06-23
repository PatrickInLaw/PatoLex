"""lostheader_stats.py -- aggregate stats across all parsed_acts_lostheader.json:
distribution of gap_open_slots for recovered acts, and the needs_reocr reason split.
  python lostheader_stats.py
"""
import json
from pathlib import Path
from collections import Counter
import importlib.util
REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("config", str(REPO / "pipeline" / "config.py"))
config = importlib.util.module_from_spec(spec); spec.loader.exec_module(config)
ROOT = Path(config.path_for("data_root"))

slot_dist = Counter()
reason = Counter()
nrec = nneed = 0
appr_only = enact_only = both = 0
printed_mismatch = printed_match = 0
for f in ROOT.glob("production-*/parsed_acts_lostheader.json"):
    d = json.loads(f.read_text(encoding="utf-8"))
    for r in d["recovered_acts"]:
        nrec += 1
        slot_dist[r["gap_open_slots"]] += 1
        if r.get("printed_numeral") == r["chapter_int"]:
            printed_match += 1
        else:
            printed_mismatch += 1
        a = r.get("has_approval"); e = r.get("has_enact")
        if a and e: both += 1
        elif a: appr_only += 1
        elif e: enact_only += 1
    for n in d["needs_reocr"]:
        nneed += 1
        reason[n["reason"]] += 1

print("recovered total:", nrec)
print("  gap_open_slots distribution:", dict(slot_dist))
print("  printed_numeral matched slot:", printed_match, " mismatched (true lost-header):", printed_mismatch)
print("  witness: approval+enact=%d approval_only=%d enact_only=%d" % (both, appr_only, enact_only))
print("needs_reocr total:", nneed, " reasons:", dict(reason))
