"""READ-ONLY: dump the OCR region between two emitted chapters to see what a 'missing'
chapter actually looks like in the text. Usage: python _diag_gap_region.py <label> <chA> <chB>
Shows all lines from the source_page of chA's act to chB's act."""
import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config, importlib.util
_RC = Path(__file__).resolve().parents[1] / "ingest" / "recover_chaptered.py"
spec = importlib.util.spec_from_file_location("rc", str(_RC)); rc = importlib.util.module_from_spec(spec); spec.loader.exec_module(rc)

label = sys.argv[1]; chA = int(sys.argv[2]); chB = int(sys.argv[3])
lines = rc.load_lines(label)
conf, flag, meta = rc.process_label(label)
byn = {a["chapter_int"]: a for a in conf}
pA = byn.get(chA, {}).get("source_page"); pB = byn.get(chB, {}).get("source_page")
print(f"ch{chA} page={pA}  ch{chB} page={pB}")
if pA is None or pB is None:
    print("one endpoint not emitted"); sys.exit()
# find the line index range covering pages pA..pB
idxs = [i for i, (p, ln, k) in enumerate(lines) if pA - 1 <= p <= pB]
for i in idxs:
    p, ln, k = lines[i]
    print(f"{p:>5} {repr(ln)[:120]}")
