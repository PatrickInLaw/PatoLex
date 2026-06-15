"""count_tokens.py -- denominator for the garble rate. Sums TOTAL OCR tokens per sieve category
(no dictionary load -> fast). Pairs with full_sieve.py garble counts to give garble % of ingested body text."""
import os, glob, json, re
from collections import Counter
import config
from analysis.full_sieve import (load_label_to_pdfbase, read_two_col, load_vlm, classify,
                                  CASCADE, OUTCTX, SHAPES, RECONCILED, KEPT, REMOVED)

def main():
    l2p = load_label_to_pdfbase(); vlm = load_vlm()
    files = sorted(glob.glob(os.path.join(RECONCILED, "*.reconciled.tsv")))
    tok = Counter()
    for rf in files:
        label = os.path.basename(rf)[:-len(".reconciled.tsv")]
        oc = os.path.join(OUTCTX, "production-" + label + ".json")
        if not os.path.exists(oc):
            continue
        pdfbase = l2p.get(label, label)
        sf = os.path.join(SHAPES, pdfbase + ".shapes.tsv")
        shape = read_two_col(sf) if os.path.exists(sf) else {}
        recon = read_two_col(rf)
        try:
            text = json.load(open(oc, encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for pk, lines in text.items():
            try:
                pidx = int(pk)
            except ValueError:
                continue
            cat = classify(shape.get(pidx, "BODY"), recon.get(pidx, "BODY"), vlm.get((label, pidx)))
            tok[cat] += sum(len(ln) for ln in lines)
    total = sum(tok.values())
    kept = sum(tok[c] for c in KEPT); rem = sum(tok[c] for c in REMOVED)
    print(f"TOTAL OCR tokens: {total:,}")
    print(f"  KEPT (ingested body) tokens:   {kept:,}")
    print(f"  REMOVED (non-body) tokens:     {rem:,}")
    for c in sorted(tok):
        print(f"    {c:<18} {tok[c]:,}")

if __name__ == "__main__":
    main()
