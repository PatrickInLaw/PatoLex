import json, re, sys
from pathlib import Path
root = Path(r'C:\Users\PatrickKolasinski\PatoLex-scratch')
label=sys.argv[1]
p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
raw = json.loads(p.read_text(encoding='utf-8'))
pages = {int(k): v for k, v in raw.items()}
# A page is a TOC/index page if many of its lines end with dotted leaders +
# a bill no / page no, or it contains 'TITLE OF ACT' / 'CONTENTS'.
TOC_HEAD = re.compile(r'TITLE\s+OF\s+ACT|CONTENTS|No\.\s+of\s+bill|INDEX', re.I)
LEADER = re.compile(r'\.{4,}|\,{4,}|(?:\.\s){4,}')
for pidx in sorted(pages):
    txt = pages[pidx].get('consensus_text','')
    lines=[l for l in txt.split('\n') if l.strip()]
    if not lines: continue
    head = TOC_HEAD.search(txt)
    n_leader = sum(1 for l in lines if LEADER.search(l))
    frac = n_leader/len(lines)
    if head or frac>0.25:
        print(f"pg{pidx:>4}  leaders={n_leader}/{len(lines)} ({frac:.0%})  head={bool(head)}  TOC?")
