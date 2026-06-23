"""dump_lostheader.py -- print recovered + needs_reocr from a volume's
parsed_acts_lostheader.json for spot-checking.
  python dump_lostheader.py <production-label> [--needs]
"""
import sys, json
from pathlib import Path
import importlib.util
REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("config", str(REPO / "pipeline" / "config.py"))
config = importlib.util.module_from_spec(spec); spec.loader.exec_module(config)
ROOT = Path(config.path_for("data_root"))

label = sys.argv[1]
needs = "--needs" in sys.argv
p = ROOT / ("production-" + label) / "parsed_acts_lostheader.json"
d = json.loads(p.read_text(encoding="utf-8"))
print("=== recovered (%d) ===" % len(d["recovered_acts"]))
for r in d["recovered_acts"]:
    print(f"  ch {r['chapter_int']:>4} | printed={r['printed_numeral']:>5} | p{r['source_page']} "
          f"| anchors {r['lo_anchor']}-{r['hi_anchor']} | appr={int(r['has_approval'])} "
          f"| {r['title'][:72]}")
if needs:
    print("\n=== needs_reocr (%d) ===" % len(d["needs_reocr"]))
    for n in d["needs_reocr"]:
        print(f"  p{n['source_page']} pnum={n['printed_numeral']} slots={n['open_slots']} "
              f"ncand={n['n_candidates']} reason={n['reason']} | {n['title'][:60]}")
