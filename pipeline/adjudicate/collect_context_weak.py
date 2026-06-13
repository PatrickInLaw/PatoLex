"""
collect_context_weak.py -- gather the context stage's 'context_weak' rows (the weak-collocation band the
sieve routed to Sonnet) from the per-volume audits, dedup to (token, candidate-set) TYPES with occurrence
counts, and write the Sonnet adjudication worklist. Type-level dedup = judge each (token->candidates) once.

Run from the repo:  python -m adjudicate.collect_context_weak
Reads:  <cascade_dir>/audit/*.context.tsv   (rows: page, kind, before, after ; kind=='context_weak')
Writes: <cascade_dir>/context_weak_worklist.tsv   (token  candidates  occ)
"""
import os, glob
from collections import Counter
import config

AUD = config.path_for("cascade_dir", "audit")
OUT = config.path_for("cascade_dir", "context_weak_worklist.tsv")

def main():
    occ = Counter()
    for fp in glob.glob(os.path.join(AUD, "*.context.tsv")):
        for line in open(fp, encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) >= 4 and p[1] == "context_weak":
                occ[(p[2], p[3])] += 1
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("token\tcandidates\tocc\n")
        for (tok, cands), n in sorted(occ.items(), key=lambda kv: -kv[1]):
            f.write(f"{tok}\t{cands}\t{n}\n")
    print(f"context_weak: {len(occ):,} distinct (token->candidates) TYPES / {sum(occ.values()):,} occ -> {OUT}")

if __name__ == "__main__":
    main()
