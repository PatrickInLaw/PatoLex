"""
Build the CORPUS-CONFIDENT vocabulary: words that appear in the corpus often enough and
are word-like and were NOT adjudicated as errors. This is the layer build_dictionary() is
missing -- legal terms, proper names, archaic statutory words that are real but absent from
standard English dictionaries. Measure how much of the 'residual' is actually real corpus vocab.
"""
import os, sys, re, json, glob
from collections import Counter

SCRATCH = r"C:\Users\patolex\PatoLex-scratch"
VOCAB   = r"C:\Users\patolex\PatoLex-scratch\_vocab"
WORD = re.compile(r"[A-Za-z\xc0-\xff]+")
VOW = set("aeiouy")
THRESH = 15   # a non-English token appearing >=15x across the corpus is almost certainly real

def word_like(t):
    if len(t) < 3 or not t.isalpha(): return False
    if not (set(t) & VOW): return False
    if re.search(r"(.)\1\1", t): return False
    if re.search(r"[bcdfghjklmnpqrstvwxz]{5,}", t): return False
    return True

# 1) corpus frequency
freq = Counter()
files = sorted(glob.glob(os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json")))
for fp in files:
    try:
        data = json.load(open(fp, encoding="utf-8", errors="replace"))
    except Exception:
        continue
    for pk, po in data.items():
        for t in WORD.findall(po.get("consensus_text") or ""):
            if len(t) >= 2:
                freq[t.lower()] += 1
print(f"distinct corpus tokens = {len(freq):,}")

# 2) adjudicated-error exclusion (Sonnet FIX/GARBAGE verdicts = these tokens ARE errors)
adjudicated_bad = set()
for p in glob.glob(os.path.join(VOCAB, "review_sonnet_part*.json")):
    for tok, v in json.load(open(p, encoding="utf-8")).items():
        if v.get("verdict") in ("FIX", "GARBAGE"):
            adjudicated_bad.add(tok.lower())
print(f"adjudicated-bad (Sonnet FIX/GARBAGE) = {len(adjudicated_bad):,}")

# 3) standard English dict, to see what's NEW
from ocrcorrect.correction_passes import build_dictionary
ws, _spell, has_wf, wf = build_dictionary()
WS = frozenset(ws)
def english(t):
    return (t in WS) or (has_wf and wf(t, "en") > 0)

# 4) confident corpus vocab = freq>=THRESH, word-like, not adjudicated-bad
confident = set()
confident_new = set()  # the ones NOT in standard English (the words we were missing)
for tok, f in freq.items():
    if f >= THRESH and word_like(tok) and tok not in adjudicated_bad:
        confident.add(tok)
        if not english(tok):
            confident_new.add(tok)
print(f"\nconfident corpus vocab (freq>={THRESH}) = {len(confident):,}")
print(f"  of which NEW (not in standard English) = {len(confident_new):,}  <- the missing layer")

with open(os.path.join(VOCAB, "corpus_confident_vocab.txt"), "w", encoding="utf-8") as f:
    for w in sorted(confident_new):
        f.write(w + "\n")

# 5) how much of the RESIDUAL is actually real corpus vocab?
res = []
for i, ln in enumerate(open(os.path.join(VOCAB, "residual_triage.tsv"), encoding="utf-8")):
    if i == 0: continue
    p = ln.rstrip("\n").split("\t")
    if len(p) >= 3:
        try: fq = int(p[1])
        except Exception: fq = 0
        res.append((p[0].lower(), fq, p[2]))
reclaim = [r for r in res if r[0] in confident_new]
from collections import Counter as C
tier_reclaim = C(r[2] for r in reclaim)
print(f"\nRESIDUAL types reclaimed as real corpus vocab = {len(reclaim):,} of {len(res):,}")
print(f"  by tier: {dict(tier_reclaim)}")
print(f"  examples: {[r[0] for r in sorted(reclaim, key=lambda x:-x[1])[:25]]}")
# top NEW confident words by freq
print(f"\ntop NEW confident corpus words: {[w for w,_ in sorted(((w,freq[w]) for w in confident_new), key=lambda x:-x[1])[:30]]}")
