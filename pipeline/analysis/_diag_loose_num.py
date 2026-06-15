import json, re, sys
from pathlib import Path
root = Path(r'C:\Users\PatrickKolasinski\PatoLex-scratch')
ORACLE={'1850':146,'1851':139,'1852':202,'1853':180,'1854':71,'1855':231,'1856':152,
 '1857':277,'1858':358,'1859':330,'1860':455,'1861':538,'1862':455,'1863-64':476,
 '1865-66':280,'1867-68':545,'1869-70':583,'1871-72':637,'1873-74':679,'1875-76':613}
ANACT = re.compile(r'\bAn?\s+A[CEO][TI]\b', re.I)
ANACT_FUZZY = re.compile(r'\b[Adl][nu]\s+[Asd][a-z]{1,4}\b')
BODYREF = re.compile(r"of\s+an\s+act|entitled|said\s+act|amendatory\s+of\s+an|supplement\w*\s+to\s+an", re.I)

# FORM-A: line starts with a chapter glyph (C + 2-7 letters), optional sep, then
# UP TO 12 chars of numeral-garble, then an em-dash, then 'An Act' after the dash.
# The numeral is NOT constrained (roman OCRs into letter-soup like 'DXXAILL').
FORMA = re.compile(r"^[\s.,;:'\"]{0,3}C[a-z]{1,7}[.,]?\s*[A-Za-z0-9!|\]\[. ]{0,12}[—–]\s*(.*)$", re.I)
# 1850-54 split form
FORMB = re.compile(r"^[\s.,;:'\"]{0,3}(C[a-z]{1,7})[.,]?\s*([IVXLCDMivxlcdmJTYjty0-9!|\]\[l]{1,7})\s*[.,]?\s*$", re.I)
PROSE_C = re.compile(r"^(county|court|city|chapter|contents|certi|civil|const|comm|compan|coast|colo)", re.I)

def detect(label):
    p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
    raw = json.loads(p.read_text(encoding='utf-8'))
    pages = {int(k): v for k, v in raw.items()}
    lines=[]
    for pidx in sorted(pages):
        for ln in pages[pidx].get('consensus_text','').split('\n'):
            lines.append(ln)
    out=[]; last=-9
    for i,t in enumerate(lines):
        s=t.strip()
        hit=False
        ma=FORMA.match(s)
        if ma:
            after=ma.group(1)
            if (ANACT.search(after) or ANACT_FUZZY.match(after)) and not BODYREF.match(s):
                hit=True
        if not hit:
            mb=FORMB.match(s)
            if mb and not PROSE_C.match(mb.group(1)):
                if any(ANACT.search(lines[j]) for j in range(i+1,min(len(lines),i+3))):
                    hit=True
        if hit and i-last>=2:
            out.append(i); last=i
    return out

for label in sys.argv[1:]:
    out=detect(label)
    N=ORACLE.get(label,0)
    print(f"{label}: detected={len(out)}  oracle={N}  {100.0*len(out)/N if N else 0:.0f}%")
