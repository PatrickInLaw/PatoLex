"""
symspell_e2.py -- corpus-aware SymSpell edit-distance-2 corrector for the cascade autocorrect stage.

Why custom (not symspellpy): the real lever on the HARD residual bucket isn't only edit-2 reach --
it's that a general-English zipf threshold REJECTS legitimate archaic/legal words that are common in
THIS corpus (thereon, thirtieth, hereinafter). So the correction TARGET vocabulary and the ranking
frequency are CORPUS-NATIVE: targets = known words attested >= MIN_TARGET_COUNT times in our own
post-split corpus; ranking = corpus count. That both (a) reaches edit-2 typos (cightecn->eighteen)
and (b) admits archaic edit-1 words the strict general-zipf e1 pass declined.

SymSpell: precompute deletes of every TARGET word up to max_dist -> index[delete_str] = [words].
At query time, generate deletes of the term up to max_dist; any target sharing a delete is a
candidate; verify by true Damerau-Levenshtein <= max_dist. This is O(deletes) not O(alphabet^2*len).

PRECISION GUARDS (legal corpus = a wrong fix turns a visible error invisible; bias to DECLINE):
  - candidate must be attested >= MIN_APPLY_COUNT in corpus (solidly real, not a rare dict word)
  - |len(term) - len(cand)| <= max_dist (no wild length jumps)
  - UNAMBIGUOUS: among candidates at the best edit distance, the top corpus-freq must beat the
    runner-up by >= AMBIG_RATIO (cight -> eight/right/night/light... is ambiguous -> declined)
  - prefer smaller edit distance, then higher corpus freq
"""
import os, json, glob, re
from collections import Counter

MIN_TARGET_COUNT = 5     # a word must appear this many times in-corpus to be a correction TARGET at all
MIN_APPLY_1      = 12    # dist-1: candidate must be attested >= this in-corpus to be APPLIED
MIN_APPLY_2      = 30    # dist-2 is riskier -> require stronger corpus attestation
AMBIG_1          = 5.0   # dist-1: top candidate corpus-freq must be >= this x runner-up (same edit dist)
AMBIG_2          = 8.0   # dist-2: stricter ambiguity bar
MAX_DIST         = 2
_REPEAT4 = re.compile(r"(.)\1\1\1"); _CONS5 = re.compile(r"[bcdfghjklmnpqrstvwxz]{5,}")
_VOWELS  = set("aeiouy")
def _garbage_shaped(t):
    return bool(_REPEAT4.search(t)) or bool(_CONS5.search(t)) or (len(t) >= 5 and not (set(t) & _VOWELS))

from ocrcorrect.edits import deletes as _deletes, dl_within as _dl_within   # the ONE home for these (was duplicated)

class SymSpellE2:
    def __init__(self, freq, max_dist=MAX_DIST):
        self.freq = freq                 # {word: corpus_count} for TARGET words only
        self.max_dist = max_dist
        self.index = {}                  # delete_str -> list[word]
        for w in freq:
            for d in _deletes(w, max_dist):
                self.index.setdefault(d, []).append(w)

    def lookup(self, term):
        """Return (word, 's1'|'s2') or None. dist-2 carries a stricter apply + ambiguity bar."""
        md = self.max_dist
        cands = set()
        for d in _deletes(term, md):
            lst = self.index.get(d)
            if lst:
                cands.update(lst)
        if not cands:
            return None
        scored = []
        for w in cands:
            if abs(len(w) - len(term)) > md:
                continue
            dist = _dl_within(term, w, md)
            if 1 <= dist <= md:
                scored.append((dist, self.freq.get(w, 0), w))
        if not scored:
            return None
        scored.sort(key=lambda x: (x[0], -x[1]))     # best edit distance, then highest corpus freq
        bestd, bestf, bestw = scored[0]
        min_apply = MIN_APPLY_1 if bestd == 1 else MIN_APPLY_2
        ambig = AMBIG_1 if bestd == 1 else AMBIG_2
        if bestf < min_apply:
            return None
        same = sorted((f for d, f, w in scored if d == bestd), reverse=True)
        if len(same) > 1 and same[0] < same[1] * ambig:
            return None                               # ambiguous at the best distance -> decline
        return (bestw, "s1" if bestd == 1 else "s2")

# ---- corpus-native frequency model (TARGET vocab) ----
def build_corpus_freq(stage_out_dir, strong_fn, out_path):
    """Count STRONG-dictionary tokens across a persisted cascade stage (out_split) -> {word: count}.
    `strong_fn` must be STRICT dictionary membership (NOT wordfreq>0) so OCR-error/misspelled words
    (aquisition, goverment, appropri) never become correction TARGETS. Garbage shapes excluded."""
    freq = Counter()
    for fp in sorted(glob.glob(os.path.join(stage_out_dir, "*.json"))):
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        for pk, lines in d.items():
            for toks in lines:
                for t in toks:
                    if len(t) >= 4 and t.isalpha() and not _garbage_shaped(t) and strong_fn(t):
                        freq[t] += 1
    tgt = {w: c for w, c in freq.items() if c >= MIN_TARGET_COUNT}
    json.dump(tgt, open(out_path, "w", encoding="utf-8"))
    return tgt

def load_target_freq(path):
    return json.load(open(path, encoding="utf-8"))
