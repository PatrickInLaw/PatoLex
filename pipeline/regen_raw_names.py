import os
VOCAB = r"C:\Users\patolex\PatoLex-scratch\_vocab"
names = set()
for i, ln in enumerate(open(os.path.join(VOCAB, "gazetteer_keep.tsv"), encoding="utf-8")):
    if i == 0: continue
    p = ln.rstrip("\n").split("\t")
    if p and p[0] and p[0].isalpha() and len(p[0]) >= 3:
        names.add(p[0].lower())
with open(os.path.join(VOCAB, "dict_additions.txt"), "w", encoding="utf-8") as f:
    for w in sorted(names):
        f.write(w + "\n")
print(f"dict_additions.txt = {len(names):,} DB-validated corpus-attested names (raw, no heuristic filter)")
