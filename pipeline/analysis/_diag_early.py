"""Diagnose WHY the production parser misses early acts.
Count: (a) production header_starts_act fires; (b) enacting-clause occurrences
(a strong proxy for true act count); (c) how the chapter marker is laid out."""
import json, sys, re
from pathlib import Path
import importlib.util
sys.path.insert(0, r"C:\Users\PatrickKolasinski\Documents\GitHub\PatoLex\pipeline")

ING = Path(r"C:\Users\PatrickKolasinski\Documents\GitHub\PatoLex\pipeline\ingest\ingest_from_ocr.py")
spec = importlib.util.spec_from_file_location("ing", str(ING))
ing = importlib.util.module_from_spec(spec); spec.loader.exec_module(ing)

root = Path(r'C:\Users\PatrickKolasinski\PatoLex-scratch')

# Enacting clause: tolerant. "do enact as follows" with OCR noise.
ENACT = re.compile(r"do\s+enact\s+as\s+follow", re.I)
# the early header form: line that begins with a Chap-marker AND contains An Act on same line
CHAPLINE = re.compile(r"^[^A-Za-z0-9]{0,4}(?:c[hu][a-z]{1,4}|cuarrer|chapter)\b", re.I)

for label in sys.argv[1:]:
    p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
    raw = json.loads(p.read_text(encoding='utf-8'))
    pages = {int(k): v for k, v in raw.items()}
    lines = []
    for pidx in sorted(pages):
        for ln in pages[pidx].get('consensus_text','').split('\n'):
            lines.append((pidx, ln))
    plain = [(p_, t) for (p_, t) in lines]
    n_hdr = 0
    for i in range(len(plain)):
        ok, tok = ing.header_starts_act(plain, i)
        if ok: n_hdr += 1
    n_enact = sum(1 for (_,t) in lines if ENACT.search(t))
    # enacting clauses often span 2 lines ("...represented in Senate and\nAssembly, do enact"); count distinct
    n_chapline = sum(1 for (_,t) in lines if CHAPLINE.match(t.strip()))
    print(f"{label}: header_starts_act_fires={n_hdr}  enact_clause_lines={n_enact}  chap_marker_lines={n_chapline}")
