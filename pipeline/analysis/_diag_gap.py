import json, re, sys
from pathlib import Path
root = Path(r'C:\Users\PatrickKolasinski\PatoLex-scratch')
label = sys.argv[1] if len(sys.argv) > 1 else '1860'
p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
raw = json.loads(p.read_text(encoding='utf-8'))
pages = {int(k): v for k, v in raw.items()}
ANACT = re.compile(r'\bAn?\s+A[CEO][TI]\b', re.I)
DASH = '—–'
n_struct = 0
n_formA = 0
NUM = r'[IVXLCDMivxlcdmJTYjty0-9!|\]\[l. ]{0,9}'
FORMA = re.compile(r"^[\s.,;:'\"]{0,3}C[a-z]{1,7}\.?\s*" + NUM + r'[—–]\s*', re.I)
miss = []
for pidx in sorted(pages):
    for ln in pages[pidx].get('consensus_text', '').split('\n'):
        s = ln.strip()
        m = ANACT.search(s)
        if not m:
            continue
        if not re.match(r"^[\s.,;:'\"]{0,3}C[a-z]{1,7}", s):
            continue
        if any(d in s[:m.start()] for d in DASH):
            n_struct += 1
            if FORMA.match(s):
                n_formA += 1
            else:
                miss.append(s[:85])
print('struct(C-word+dash+AnAct)=', n_struct, ' FORMA matched=', n_formA)
for x in miss[:25]:
    print('  MISS:', repr(x))
