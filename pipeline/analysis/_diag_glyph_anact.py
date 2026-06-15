import json, sys, re
from pathlib import Path
root = Path(r'C:\Users\PatrickKolasinski\PatoLex-scratch')
ORACLE={'1850':146,'1851':139,'1852':202,'1853':180,'1854':71,'1855':231,'1856':152,
 '1857':277,'1858':358,'1859':330,'1860':455,'1861':538,'1862':455,'1863-64':476,
 '1865-66':280,'1867-68':545,'1869-70':583,'1871-72':637,'1873-74':679,'1875-76':613}

# tight chapter glyph anchored at line start (NOT County/Court/City/construct):
# require the glyph to be a chapter-abbrev family token, then a NON-letter (./dash/space+num)
GLYPH = re.compile(r"^[\s.,;:'\"]{0,3}C(?:uarrer|oarrer|hapter|uap|hap|rap|iap|nap|uav|uar|aap|oap|ap|nar|har)r?t?\.?\s*[IVXLCDMivxlcdmJTYjty0-9!|\]\[l. ]{0,9}[—–\-]", re.I)
ANACT = re.compile(r"\bAn?\s+A[CEO][TI]\b", re.I)
BODYREF = re.compile(r"of\s+an\s+act|entitled|said\s+act|amendatory\s+of\s+an", re.I)

# 1850-54 split form: glyph+num on own line, AN ACT next line(s)
GLYPHNUM = re.compile(r"^[\s.,;:'\"]{0,3}C(?:uarrer|oarrer|hapter|uap|hap|rap|iap|nap|uav|uar|aap|oap|ap)r?t?\.?\s*([IVXLCDMivxlcdmJTYjty0-9!|\]\[l]{1,7})\s*[.,]?\s*$", re.I)

for label in sys.argv[1:]:
    p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
    raw = json.loads(p.read_text(encoding='utf-8'))
    pages = {int(k): v for k,v in raw.items()}
    lines=[]
    for pidx in sorted(pages):
        for ln in pages[pidx].get('consensus_text','').split('\n'):
            lines.append(ln)
    # FORM A: glyph-start line containing An Act (not body ref)
    a=0; b=0
    last=-9
    for i,t in enumerate(lines):
        s=t.strip()
        hit=False
        if GLYPH.match(s) and ANACT.search(s) and not BODYREF.match(s):
            hit=True
        elif GLYPHNUM.match(s) and any(ANACT.search(lines[j]) for j in range(i+1,min(len(lines),i+3))):
            hit=True
        if hit and i-last>=2:
            a+=1; last=i
    N=ORACLE.get(label,0)
    print(f"{label}: detected={a}  oracle={N}  {100.0*a/N if N else 0:.0f}%")
