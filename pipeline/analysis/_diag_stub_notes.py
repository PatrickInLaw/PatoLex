"""READ-ONLY: find short redirect-stub acts: a line-head CHAPTER + An Act + approval
footer but NO enacting clause. Dump the trailing note line so we can see the real
'see Stats' phrasing. Usage: python _diag_stub_notes.py <label>"""
import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config, importlib.util
_RC = Path(__file__).resolve().parents[1] / "ingest" / "recover_chaptered.py"
spec = importlib.util.spec_from_file_location("rc", str(_RC)); rc = importlib.util.module_from_spec(spec); spec.loader.exec_module(rc)

label = sys.argv[1]
lines = rc.load_lines(label)
headers = rc.detect_headers(lines)
n_stub = 0
samples = []
for k, (si, num, raw) in enumerate(headers):
    ei = headers[k + 1][0] if k + 1 < len(headers) else len(lines)
    rec = rc.build_act(lines, si, ei, num, raw, 1933, label)
    if not rec["has_an_act"]:
        continue
    if rec["has_enact"]:
        continue
    if not rec["has_approval"]:
        continue
    # short act, no enact clause, has approval -> redirect-stub candidate
    n_stub += 1
    if len(samples) < 25:
        buf = [lines[j][1] for j in range(si, min(ei, si + 9))]
        samples.append((num, buf))
print(f"{label}: stub-candidates (An Act + approval + NO enact): {n_stub}")
for num, buf in samples:
    print(f"--- ch {num}")
    for b in buf:
        print("   ", repr(b)[:110])
