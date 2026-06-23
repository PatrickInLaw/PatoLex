"""dump_multislot.py -- show every recovered act with gap_open_slots>1 for adversarial
spot-check (these are the multi-candidate==multi-slot positional pairings, the riskier
subclass vs the dominant single-slot case).
"""
import json
from pathlib import Path
import importlib.util
REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("config", str(REPO / "pipeline" / "config.py"))
config = importlib.util.module_from_spec(spec); spec.loader.exec_module(config)
ROOT = Path(config.path_for("data_root"))
n = 0
for f in sorted(ROOT.glob("production-*/parsed_acts_lostheader.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    ms = [r for r in d["recovered_acts"] if r["gap_open_slots"] > 1]
    if not ms:
        continue
    print("---", f.parent.name)
    for r in ms:
        corro = "MATCH" if r["printed_numeral"] == r["chapter_int"] else "POS-ONLY"
        print(f"   ch {r['chapter_int']:>4} slots={r['gap_open_slots']} printed={r['printed_numeral']:>5} "
              f"[{corro}] p{r['source_page']} anch {r['lo_anchor']}-{r['hi_anchor']} | {r['title'][:60]}")
        n += 1
print("total multi-slot:", n)
