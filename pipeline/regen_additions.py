"""
Regenerate dict_additions.txt = corpus-attested NAMES only (safe to integrate now).
The corpus legal-vocab (genuine-novel candidates) is contaminated with fragments/errors that
heuristics can't separate -> held for an LLM validation pass, NOT added here.
Filter names lightly: drop any that is a prefix/suffix of a common English word (those are the
coincidental fragment-matches like 'meanor'/'agricul'); keep distinctive real names.
"""
import os, re, bisect
VOCAB = r"C:\Users\patolex\PatoLex-scratch\_vocab"
from spellchecker import SpellChecker
spell = SpellChecker()
try:
    from wordfreq import zipf_frequency as zipf
except Exception:
    zipf = None
COMMON = set(w for w in spell.word_frequency.dictionary.keys())
SORTED = sorted(COMMON); SORTED_REV = sorted(w[::-1] for w in COMMON)
def affix_of_common(s):
    i = bisect.bisect_left(SORTED, s)
    if i < len(SORTED) and SORTED[i].startswith(s) and len(SORTED[i]) >= len(s) + 2: return True
    r = s[::-1]; j = bisect.bisect_left(SORTED_REV, r)
    return j < len(SORTED_REV) and SORTED_REV[j].startswith(r) and len(SORTED_REV[j]) >= len(s) + 2
def near_common(w):
    cands = spell.candidates(w)
    return bool(cands) and any(c != w and zipf and zipf(c, "en") >= 3.0 for c in cands)

names = []
for i, ln in enumerate(open(os.path.join(VOCAB, "gazetteer_keep.tsv"), encoding="utf-8")):
    if i == 0: continue
    p = ln.rstrip("\n").split("\t")
    if p and p[0] and p[0].isalpha():
        names.append(p[0].lower())

clean = set()
dropped = []
for w in names:
    if affix_of_common(w) or near_common(w):
        dropped.append(w)
    else:
        clean.add(w)
with open(os.path.join(VOCAB, "dict_additions.txt"), "w", encoding="utf-8") as f:
    for w in sorted(clean):
        f.write(w + "\n")
print(f"names in = {len(names):,}  clean kept = {len(clean):,}  dropped(coincidental/fragment) = {len(dropped):,}")
print(f"dropped sample: {dropped[:25]}")
print(f"kept sample: {sorted(clean)[:25]}")
print(f"-> dict_additions.txt = {len(clean):,} names")
