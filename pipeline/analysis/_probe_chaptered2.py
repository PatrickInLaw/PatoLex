"""READ-ONLY: find redirect-stub and resolution CHAPTER headers in chaptered OCR.
Usage: python _probe_chaptered2.py <label>"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config

ROOT = Path(config.path_for("data_root"))
label = sys.argv[1]
ocr = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
raw = json.loads(ocr.read_text(encoding="utf-8"))
pages = {int(k): v for k, v in raw.items()}
lines = []
for pidx in sorted(pages):
    for k, ln in enumerate(pages[pidx].get("consensus_text", "").split("\n")):
        lines.append((pidx, ln, k))

HEAD = re.compile(r"^\s*CHAP(?:TER|T\.?|\.)?\s*([0-9IVXLCDM]{1,6})", re.I)
NOTE = re.compile(r"N[o0]r?z?\.?\s*[.\-—]+\s*For\s+text|For\s+text\s+see\s+Stats", re.I)
RESO = re.compile(r"Concurrent\s+Resolution|Constitutional\s+Amendment|Resolution\s+No", re.I)

stubs = resos = 0
print("=== REDIRECT-STUB samples ===")
for i, (p, ln, k) in enumerate(lines):
    if HEAD.match(ln.strip()):
        win = " ".join(lines[j][1] for j in range(i, min(len(lines), i + 8)))
        if NOTE.search(win):
            if stubs < 6:
                print("-- stub line", i, "page", p)
                for j in range(i, min(len(lines), i + 7)):
                    print("   ", repr(lines[j][1])[:110])
            stubs += 1
print("=== RESOLUTION samples ===")
for i, (p, ln, k) in enumerate(lines):
    if HEAD.match(ln.strip()):
        win = " ".join(lines[j][1] for j in range(i, min(len(lines), i + 6)))
        if RESO.search(win):
            if resos < 5:
                print("-- reso line", i, "page", p)
                for j in range(i, min(len(lines), i + 6)):
                    print("   ", repr(lines[j][1])[:110])
            resos += 1
print("TOTAL stubs(by note)=", stubs, " resolutions=", resos)
