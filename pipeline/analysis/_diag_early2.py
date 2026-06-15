"""Measure candidate act-start signals across early sessions vs oracle.
Signals tested:
  CHAP   : line begins with a chapter-marker glyph + a numeral-ish token
  APPR   : [Approved ...] bracket line (the most OCR-robust terminator)
  CHAP near APPR : a chap-marker line with an Approved bracket within 5 lines below
"""
import json, sys, re
from pathlib import Path

root = Path(r'C:\Users\PatrickKolasinski\PatoLex-scratch')

# chapter-marker at line start: c/C + ~2-5 letters (huap/uap/oarrer/iap/rap) then
# optional . then a numeral-ish run (roman incl OCR subs, arabic, or J/I/l confusables)
CHAP = re.compile(r"^[^A-Za-z0-9]{0,4}c[a-z]{1,6}\.?\s*[\[\(]?\s*[ivxlcdmIVXLCDMJjTtYy0-9!|]{1,6}\b", re.I)
# approval bracket -- tolerate (), {}, [], and OCR of "Approved"
APPR = re.compile(r"[\[\(\{].{0,3}A[Pp]{1,3}[Rr]?[Oo]?[Vv]\w{0,4}\b", re.I)
APPR2 = re.compile(r"\bA[Pp]{1,3}[Rr]?[Oo]?[Vv]\w{0,4}\s+(?:Jan|Feb|Mar|Apr|May|Mav|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", re.I)

def appr_line(t):
    return bool(APPR.search(t) or APPR2.search(t))

for label in sys.argv[1:]:
    p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
    raw = json.loads(p.read_text(encoding='utf-8'))
    pages = {int(k): v for k, v in raw.items()}
    lines = []
    for pidx in sorted(pages):
        for ln in pages[pidx].get('consensus_text','').split('\n'):
            lines.append(ln)
    n_chap = sum(1 for t in lines if CHAP.match(t.strip()))
    n_appr = sum(1 for t in lines if appr_line(t))
    # chap-marker with an Approved bracket within 6 lines below
    pair = 0
    for i, t in enumerate(lines):
        if CHAP.match(t.strip()):
            if any(appr_line(lines[j]) for j in range(i, min(len(lines), i+6))):
                pair += 1
    print(f"{label}: chap_marker={n_chap}  approved_lines={n_appr}  chap+appr_within6={pair}")
