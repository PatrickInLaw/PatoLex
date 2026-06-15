import json, sys, re
from pathlib import Path
root = Path(r'C:\Users\PatrickKolasinski\PatoLex-scratch')
label = sys.argv[1]
p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
raw = json.loads(p.read_text(encoding='utf-8'))
pages = {int(k): v for k, v in raw.items()}
lines=[]
for pidx in sorted(pages):
    for ln in pages[pidx].get('consensus_text','').split('\n'):
        lines.append(ln)

# Show every line that contains an 'An Act' style title (strict) AND starts the line
ANACT_STRICT = re.compile(r"\bAn?\s+A[CEO][TI]\b", re.I)
# how do the act headers actually look? print first 40 lines that have An Act near a Cuap/Chap glyph
import itertools
shown=0
for i,t in enumerate(lines):
    s=t.strip()
    if re.match(r"^[\s.,;:'\"\-]{0,4}c[a-z]{2,7}", s, re.I) and ANACT_STRICT.search(s):
        print(repr(s[:120]))
        shown+=1
        if shown>=40: break
