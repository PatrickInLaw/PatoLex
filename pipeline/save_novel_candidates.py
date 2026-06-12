"""Save the genuine-novel corpus-vocab candidates (high-freq, not within edit-2 of a COMMON
English word) for LLM validation. These are the ambiguous real-legal-term vs fragment/error cases."""
import os
VOCAB = r"C:\Users\patolex\PatoLex-scratch\_vocab"
from spellchecker import SpellChecker
spell = SpellChecker()
try:
    from wordfreq import zipf_frequency as zipf
except Exception:
    zipf = None
def common(t): return zipf is not None and zipf(t, "en") >= 3.0
def near_common(w):
    cands = spell.candidates(w)
    return bool(cands) and any(c != w and common(c) for c in cands)

# corpus freq for context
import re, json, glob
from collections import Counter
WORD = re.compile(r"[A-Za-z\xc0-\xff]+")
freq = Counter()
for fp in sorted(glob.glob(r"C:\Users\patolex\PatoLex-scratch\production-*\ocr_consensus\page_ocr_results.json")):
    try: data = json.load(open(fp, encoding="utf-8", errors="replace"))
    except Exception: continue
    for pk, po in data.items():
        for t in WORD.findall(po.get("consensus_text") or ""):
            if len(t) >= 2: freq[t.lower()] += 1

novel = []
for ln in open(os.path.join(VOCAB, "corpus_confident_vocab.txt"), encoding="utf-8"):
    w = ln.strip().lower()
    if w and w.isalpha() and len(w) >= 3 and not near_common(w):
        novel.append((w, freq.get(w, 0)))
novel.sort(key=lambda x: -x[1])
with open(os.path.join(VOCAB, "corpus_novel_candidates.tsv"), "w", encoding="utf-8") as f:
    f.write("token\tcorpus_freq\n")
    for w, fq in novel:
        f.write(f"{w}\t{fq}\n")
print(f"saved {len(novel):,} novel candidates -> corpus_novel_candidates.tsv")
