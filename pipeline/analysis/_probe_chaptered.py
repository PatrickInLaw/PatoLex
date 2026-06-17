"""Quick READ-ONLY probe of chaptered-era OCR: dump CHAPTER-header context windows
so we can eyeball the redirect-stub / stacked-header / resolution layouts before
building the detector. Writes nothing. Usage: python _probe_chaptered.py <label> [n]"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config

ROOT = Path(config.path_for("data_root"))
label = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 30

ocr = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
raw = json.loads(ocr.read_text(encoding="utf-8"))
pages = {int(k): v for k, v in raw.items()}
lines = []
for pidx in sorted(pages):
    for k, ln in enumerate(pages[pidx].get("consensus_text", "").split("\n")):
        lines.append((pidx, ln, k))

HEAD = re.compile(r"^\s*CHAP(?:TER|T\.?|\.)?\s*([0-9IVXLCDMivxlcdm]{1,6})", re.I)
shown = 0
for i, (p, ln, k) in enumerate(lines):
    if HEAD.match(ln.strip()):
        print("---- line", i, "page", p, "linepos", k)
        for j in range(i, min(len(lines), i + 6)):
            print("   ", repr(lines[j][1])[:120])
        shown += 1
        if shown >= n:
            break
print("shown", shown, "of total lines", len(lines))
