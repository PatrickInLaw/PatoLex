"""
Build the VALIDATED dictionary additions wired into correction_passes.build_dictionary().
Currently emits corpus-attested real NAMES (gazetteer_keep, validated against census/GeoNames).
The genuine-novel corpus LEGAL vocab is NOT emitted here: heuristic curation (freq + edit-distance
to common English) was proven to keep fragments/legal-word errors (admunistra, aforesnid, actshall),
so that layer needs an LLM validation pass before integration. Runs on the 5090 (has _vocab + dict).
Output: _vocab/dict_additions.txt  (one token per line) -> loaded by build_dictionary if present.
"""
import os
VOCAB = r"C:\Users\patolex\PatoLex-scratch\_vocab"

names = set()
fp = os.path.join(VOCAB, "gazetteer_keep.tsv")
for i, ln in enumerate(open(fp, encoding="utf-8")):
    if i == 0:
        continue
    p = ln.rstrip("\n").split("\t")
    if p and p[0] and p[0].isalpha() and len(p[0]) >= 3:
        names.add(p[0].lower())

with open(os.path.join(VOCAB, "dict_additions.txt"), "w", encoding="utf-8") as f:
    for w in sorted(names):
        f.write(w + "\n")
print(f"dict_additions.txt = {len(names):,} DB-validated corpus-attested names")
