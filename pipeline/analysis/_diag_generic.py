import json, sys, re
from pathlib import Path
root = Path(r'C:\Users\PatrickKolasinski\PatoLex-scratch')
ORACLE={'1850':146,'1851':139,'1852':202,'1853':180,'1854':71,'1855':231,'1856':152,
 '1857':277,'1858':358,'1859':330,'1860':455,'1861':538,'1862':455,'1863-64':476,
 '1865-66':280,'1867-68':545,'1869-70':583,'1871-72':637,'1873-74':679,'1875-76':613}
ANACT = re.compile(r"\bAn?\s+A[CEO][TI]\b", re.I)
ANACT_FUZZY = re.compile(r"\b[Adl][nu]\s+[Asd][a-z]{1,4}\b")  # An slet / dn det / ln lect
BODYREF = re.compile(r"of\s+an\s+act|entitled|said\s+act|amendatory\s+of\s+an|supplement\w*\s+to\s+an", re.I)

# FORM-A generic: line starts with a short C-word (the chap glyph, 2-8 chars),
# then a numeral-ish token, then an em-dash, then (later on line) An Act.
# The dash is the act-title separator -- prose "County of..." has no such dash+AnAct.
NUM = r"[IVXLCDMivxlcdmJTYjty0-9!|\]\[l. ]{0,9}"
FORMA = re.compile(r"^[\s.,;:'\"]{0,3}C[a-z]{1,7}\.?\s*" + NUM + r"[—–]\s*", re.I)
# 1850-54 split: short C-word then numeral ALONE on the line; An Act on next lines
FORMB = re.compile(r"^[\s.,;:'\"]{0,3}(C[a-z]{1,7})\.?\s*([IVXLCDMivxlcdmJTYjty0-9!|\]\[l]{1,7})\s*[.,]?\s*$", re.I)
# C-words that are PROSE, not chapter glyphs (reject as FORM-B numerals)
PROSE_C = re.compile(r"^(county|court|city|chap?ter\w|contents|certi|civil|const|comm|compan|coast|colo|coun)", re.I)

for label in sys.argv[1:]:
    p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
    raw = json.loads(p.read_text(encoding='utf-8'))
    pages = {int(k): v for k,v in raw.items()}
    lines=[]
    for pidx in sorted(pages):
        for ln in pages[pidx].get('consensus_text','').split('\n'):
            lines.append(ln)
    a=0; last=-9
    for i,t in enumerate(lines):
        s=t.strip()
        hit=False
        if FORMA.match(s):
            # require An Act somewhere on this line AFTER the dash, not a body ref
            if (ANACT.search(s) or ANACT_FUZZY.search(s)) and not BODYREF.match(s):
                hit=True
        else:
            mb=FORMB.match(s)
            if mb and not PROSE_C.match(mb.group(1)):
                if any(ANACT.search(lines[j]) for j in range(i+1,min(len(lines),i+3))):
                    hit=True
        if hit and i-last>=2:
            a+=1; last=i
    N=ORACLE.get(label,0)
    print(f"{label}: detected={a}  oracle={N}  {100.0*a/N if N else 0:.0f}%")
