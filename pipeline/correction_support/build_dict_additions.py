"""
Build the VALIDATED dictionary additions wired into correction_passes.build_dictionary().
Two validated layers (both have real ground truth, NOT a frequency/edit heuristic -- those were
proven to keep fragments/errors three times this session):
  A) corpus-attested NAMES (gazetteer_keep, matched against US Census + GeoNames).
  B) LLM-validated corpus legal vocab (validated_legal_vocab.txt = the REAL/NAME verdicts from a
     Sonnet pass over the genuine-novel candidates; FRAGMENT/ERROR verdicts excluded).
Runs on the 5090. Output: _vocab/dict_additions.txt -> loaded by build_dictionary if present.
"""
import os
import config
VOCAB = config.path_for("vocab_dir")

adds = set()
# A) names (len>=4: 3-char tokens are a reunifier noise-floor risk -- Hans C1-4)
fp = os.path.join(VOCAB, "gazetteer_keep.tsv")
for i, ln in enumerate(open(fp, encoding="utf-8")):
    if i == 0:
        continue
    p = ln.rstrip("\n").split("\t")
    if p and p[0] and p[0].isalpha() and len(p[0]) >= 4:
        adds.add(p[0].lower())
n_names = len(adds)

# B) LLM-validated legal vocab
vfp = os.path.join(VOCAB, "validated_legal_vocab.txt")
n_vocab = 0
if os.path.exists(vfp):
    for ln in open(vfp, encoding="utf-8"):
        w = ln.strip().lower()
        if w and w.isalpha() and len(w) >= 3:
            if w not in adds:
                n_vocab += 1
            adds.add(w)

with open(os.path.join(VOCAB, "dict_additions.txt"), "w", encoding="utf-8") as f:
    for w in sorted(adds):
        f.write(w + "\n")
print(f"dict_additions.txt = {len(adds):,} ({n_names:,} DB-validated names + {n_vocab:,} LLM-validated legal vocab)")
