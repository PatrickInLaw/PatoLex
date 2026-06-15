"""Characterize the EXACT header forms per early session so the detector can be
tight. For each session, count how real act headers are laid out:
  FORM-A (joined): a chap glyph + numeral + em-dash + 'An Act' on ONE line
  FORM-B (split) : chap glyph + numeral on its own short line, 'An Act' next line
"""
import json, sys, re
from pathlib import Path
root = Path(r'C:\Users\PatrickKolasinski\PatoLex-scratch')

# tight chapter glyph: C + (h|u|n|i)+(a|o)+(p|r|v) family, i.e. Chap/Cuap/Crap/Ciap/
# Cnap/Cuar/Cuav/Coap... + optional 'r'/'t'/'p'/'rer' + optional '.'. 3-8 chars.
GLYPH = r"C(?:uarrer|oarrer|hapter|uap|hap|rap|iap|nap|uav|uar|aap|oap|hapr|uapr|ap)r?t?\.?"
NUM = r"[IVXLCDMivxlcdmJTYjty0-9!|\]\[l]{1,8}"
JOINED = re.compile(r"^[\s.,;:'\"]{0,3}(" + GLYPH + r")[\s.]{0,3}(" + NUM + r")\s*[—–\-]\s*[A-Za-z]", re.I)
GLYPHNUM = re.compile(r"^[\s.,;:'\"]{0,3}(" + GLYPH + r")[\s.]{0,3}(" + NUM + r")\s*[.,]?\s*$", re.I)
ANACT = re.compile(r"\bAn?\s+A[CEO][TI]\b", re.I)

for label in sys.argv[1:]:
    p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
    raw = json.loads(p.read_text(encoding='utf-8'))
    pages = {int(k): v for k,v in raw.items()}
    lines=[]
    for pidx in sorted(pages):
        for ln in pages[pidx].get('consensus_text','').split('\n'):
            lines.append(ln)
    formA = sum(1 for t in lines if JOINED.match(t.strip()))
    # split: glyph+num alone, An Act within next 2 lines
    formB = 0
    for i,t in enumerate(lines):
        if GLYPHNUM.match(t.strip()):
            if any(ANACT.search(lines[j]) for j in range(i+1, min(len(lines), i+3))):
                formB += 1
    print(f"{label}: FORM-A(joined glyph-dash-AnAct)={formA}  FORM-B(glyph/num then AnAct)={formB}")
