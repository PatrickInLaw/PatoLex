import json, sys, re
from pathlib import Path
root = Path(r'C:\Users\PatrickKolasinski\PatoLex-scratch')
label = sys.argv[1] if len(sys.argv) > 1 else '1861'
p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
raw = json.loads(p.read_text(encoding='utf-8'))
pages = {int(k): v for k, v in raw.items()}
ks = sorted(pages.keys())
# find first page where enacting clause appears (start of body / acts)
ENACT = re.compile(r"do\s+enact\s+as\s+follow|People\s+of\s+the\s+State\s+of\s+California", re.I)
first = None
for pidx in ks:
    if ENACT.search(pages[pidx].get('consensus_text','')):
        first = pidx; break
print('label', label, 'first enacting-clause page idx =', first)
# print a window of pages around there
start = ks.index(first)
for pidx in ks[start:start+4]:
    txt = pages[pidx].get('consensus_text','')
    print('==== page idx', pidx, '====')
    print(txt[:1700])
    print()
