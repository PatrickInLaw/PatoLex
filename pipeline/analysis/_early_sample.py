import json, sys
from pathlib import Path
root = Path(r'C:\Users\PatrickKolasinski\PatoLex-scratch')
labels = sys.argv[1:] or ['1861']
for label in labels:
    p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
    raw = json.loads(p.read_text(encoding='utf-8'))
    pages = {int(k): v for k, v in raw.items()}
    ks = sorted(pages.keys())
    print('=====', label, 'n_pages=', len(pages), 'page_range', ks[0], '-', ks[-1])
    for pidx in ks[24:27]:
        txt = pages[pidx].get('consensus_text', '')
        print('--- page idx', pidx, '---')
        print(txt[:1600])
        print()
