"""
mojibake_fix.py -- constrained-position correction of tokens containing a mojibake char (non-ASCII /
U+FFFD replacement). The bad char MARKS the error location, so this is a constrained substitution of
ONLY the bad span (prefer minimal edits: deletion or 1 letter; escalate to 2 letters only if needed),
keeping a fix only when the result is a KNOWN word and UNAMBIGUOUS. Far higher precision than blind
edit-1 because we never guess where the damage is -> auto-applyable when unambiguous.

Reads out_autocorrect (e1-applied). Reports fixable / ambiguous / no-fix counts + a sample for the
precision check, and writes the fix worklist to _cascade/mojibake_fixes.tsv.
"""
import os, re, json, glob, time
from collections import Counter

SCRATCH = r"C:\Users\patolex\PatoLex-scratch"
CASCADE = os.path.join(SCRATCH, "_cascade")
STAGE_OUT = os.path.join(CASCADE, "out_autocorrect")
FREQ_PATH = os.path.join(CASCADE, "corpus_freq.json")
OUT_TSV = os.path.join(CASCADE, "mojibake_fixes.tsv")
LOG = os.path.join(CASCADE, "mojibake-run.log")
ALPHA = "abcdefghijklmnopqrstuvwxyz"
AMBIG = 4.0        # top candidate's score must beat the runner-up by this factor to auto-apply
_NONASCII = re.compile(r"[^\x00-\x7f]")
_SPAN = re.compile(r"[^\x00-\x7f]+")

def _log(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}\n"
    open(LOG, "a", encoding="utf-8").write(line); print(line.rstrip(), flush=True)

# ---- pure, injectable core (unit-testable without the real dict/corpus) ----
def mojibake_candidates(t, known):
    """Known-word fixes by substituting ONLY the single contiguous non-ASCII span (1-2 chars).
    Prefers minimal edits: deletion + 1 letter; escalates to 2 letters only if tier 1 is empty.
    Returns a set of known candidates, or None if the token isn't a single-span <=2-char mojibake."""
    spans = [(m.start(), m.end()) for m in _SPAN.finditer(t)]
    if len(spans) != 1: return None               # one contiguous bad span only
    i, j = spans[0]
    if j - i > 2: return None                      # >2 bad chars = too damaged
    pre, post = t[:i], t[j:]
    c1 = set()                                     # tier 1: deletion + single letter (minimal)
    if known(pre + post): c1.add(pre + post)
    for c in ALPHA:
        if known(pre + c + post): c1.add(pre + c + post)
    if c1: return c1
    c2 = set()                                     # tier 2: two letters (UTF-8 pair -> 1 real char etc.)
    for a in ALPHA:
        for b in ALPHA:
            w = pre + a + b + post
            if known(w): c2.add(w)
    return c2 or None

def choose_fix(cands, score, ambig=AMBIG):
    """From known candidates pick a fix only if UNAMBIGUOUS. Returns (fix|None, is_ambiguous)."""
    if not cands: return (None, False)
    ranked = sorted(cands, key=score, reverse=True)
    if len(ranked) == 1 or score(ranked[0]) >= ambig * max(1e-9, score(ranked[1])):
        return (ranked[0], False)
    return (None, True)

def main():
    from ocrcorrect.dictionary import build_dictionary
    ws, _s, has_wf, wf = build_dictionary()
    WS = frozenset(ws)
    from wordfreq import zipf_frequency
    cf = json.load(open(FREQ_PATH, encoding="utf-8")) if os.path.exists(FREQ_PATH) else {}
    def known(t): return (t in WS) or (has_wf and wf(t, "en") > 0)
    # corpus count dominates (a word attested in OUR corpus is the better target); zipf breaks ties
    def score(w): return cf.get(w, 0) * 100.0 + zipf_frequency(w, "en")

    moj = Counter()
    for fp in sorted(glob.glob(os.path.join(STAGE_OUT, "*.json"))):
        try: d = json.load(open(fp, encoding="utf-8"))
        except Exception: continue
        for pk, lines in d.items():
            for toks in lines:
                for t in toks:
                    if _NONASCII.search(t): moj[t] += 1
    _log(f"mojibake tokens: {len(moj):,} distinct types / {sum(moj.values()):,} occ")

    fixable = Counter(); ambiguous = Counter(); nofix = Counter(); fixes = {}
    for t, occ in moj.items():
        cs = mojibake_candidates(t, known)
        if not cs:
            nofix[t] = occ; continue
        fix, is_amb = choose_fix(cs, score)
        if fix is not None:
            fixes[t] = (fix, occ); fixable[t] = occ
        else:
            ambiguous[t] = occ
    _log(f"FIXABLE (unambiguous): {len(fixable):,} types / {sum(fixable.values()):,} occ")
    _log(f"AMBIGUOUS (>=2 close): {len(ambiguous):,} types / {sum(ambiguous.values()):,} occ")
    _log(f"NO-FIX (too damaged):  {len(nofix):,} types / {sum(nofix.values()):,} occ")
    with open(OUT_TSV, "w", encoding="utf-8") as f:
        f.write("token\tfix\tocc\n")
        for t, (fx, occ) in sorted(fixes.items(), key=lambda kv: -kv[1][1]):
            f.write(f"{t}\t{fx}\t{occ}\n")
    print("\nSAMPLE fixes (by occ):")
    for t, (fx, occ) in list(sorted(fixes.items(), key=lambda kv: -kv[1][1]))[:35]:
        print(f"  {t} -> {fx} ({occ})")
    print("\nSAMPLE ambiguous (declined):")
    for t, occ in list(sorted(ambiguous.items(), key=lambda kv: -kv[1]))[:12]:
        print(f"  {t} ({occ})")

if __name__ == "__main__":
    main()
