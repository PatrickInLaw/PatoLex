"""
context_resolve.py -- PROTOTYPE / feasibility test for Patrick's idea: can corpus COLLOCATIONS
procedurally disambiguate ambiguous OCR corrections, before spending any AI? Legal drafting is
extremely repetitive, so (prev-word, fix) and (fix, next-word) bigrams should pick the right candidate.

Method:
  1. Build a known-known bigram model from out_autocorrect (e1-applied corpus).
  2. Find edit-1-AMBIGUOUS flagged tokens (>=2 strong known candidates -- exactly the cases strict-e1
     declined for ambiguity), with their KNOWN neighbors, as a sample.
  3. Score each candidate by log(count(prev,cand)+1)+log(count(cand,next)+1); a "clear context winner"
     = top beats runner-up by a margin AND has real attestation.
Reports the resolution rate + a hand-check sample. Does NOT modify any text (measurement only).
"""
import os, re, json, glob, math, time
from collections import Counter
import multiprocessing as mp

SCRATCH = r"C:\Users\patolex\PatoLex-scratch"
CASCADE = os.path.join(SCRATCH, "_cascade")
STAGE_OUT = os.path.join(CASCADE, "out_autocorrect")
LOG = os.path.join(CASCADE, "context-run.log")
ALPHA = "abcdefghijklmnopqrstuvwxyz"
SAMPLE_CAP = 20000        # cap ambiguous occurrences sampled for the feasibility measure
MARGIN = 1.0             # log-score margin for a "clear winner" (~2.7x collocation dominance)

_WS = None; _HASWF = False; _WF = None; _ZIPF = None
def _init():
    global _WS, _HASWF, _WF, _ZIPF
    from correction_passes import build_dictionary
    ws, _s, has, wf = build_dictionary()
    _WS = frozenset(ws); _HASWF = has; _WF = wf
    from wordfreq import zipf_frequency; _ZIPF = zipf_frequency
def known(t): return (t in _WS) or (_HASWF and _WF(t, "en") > 0)
def zipf(t): return _ZIPF(t, "en")

def _bigrams(fp):
    c = Counter()
    try: d = json.load(open(fp, encoding="utf-8"))
    except Exception: return c
    for pk, lines in d.items():
        for toks in lines:
            prev = None
            for t in toks:
                if prev is not None and known(t) and known(prev):
                    c[(prev, t)] += 1
                prev = t
    return c

from edits import edits1 as _edits1   # the ONE home for edit-1 generation (was duplicated)

def _ambig_cands(t):
    cs = sorted({c for c in _edits1(t) if known(c) and zipf(c) >= 3.0}, key=lambda c: -zipf(c))
    return cs[:6] if len(cs) >= 2 else None

# ---- pure, injectable core (unit-testable without the real bigram model) ----
def ctx_score(cand, prev, nxt, big):
    """Collocation score of a candidate in context: log(count(prev,cand)+1)+log(count(cand,next)+1)."""
    return math.log(big.get((prev, cand), 0) + 1) + math.log(big.get((cand, nxt), 0) + 1)

def resolve(cands, prev, nxt, big, margin=MARGIN):
    """Return (pick, status): status is 'resolved' (clear context winner), 'no_ctx' (no attestation),
    or 'tie' (attested but not a clear winner). pick is the chosen word only when 'resolved'."""
    ranked = sorted(cands, key=lambda c: ctx_score(c, prev, nxt, big), reverse=True)
    s0 = ctx_score(ranked[0], prev, nxt, big)
    s1 = ctx_score(ranked[1], prev, nxt, big) if len(ranked) > 1 else 0.0
    if s0 == 0.0: return (None, "no_ctx")
    if s0 - s1 >= margin: return (ranked[0], "resolved")
    return (None, "tie")

def _find_ambig(fp):
    out = []
    try: d = json.load(open(fp, encoding="utf-8"))
    except Exception: return out
    for pk, lines in d.items():
        for toks in lines:
            for i, t in enumerate(toks):
                if len(t) < 4 or known(t): continue
                prev = toks[i - 1] if i > 0 else None
                nxt = toks[i + 1] if i + 1 < len(toks) else None
                kp = prev if (prev and known(prev)) else ""
                kn = nxt if (nxt and known(nxt)) else ""
                if not kp and not kn: continue
                cs = _ambig_cands(t)
                if cs: out.append((kp, t, kn, cs))
    return out

def main():
    files = sorted(glob.glob(os.path.join(STAGE_OUT, "*.json")))
    nw = max(2, min(12, (os.cpu_count() or 4) - 2))
    ctx = mp.get_context("spawn")
    t0 = time.time()
    big = Counter()
    with ctx.Pool(nw, initializer=_init) as pool:
        for c in pool.imap_unordered(_bigrams, files, chunksize=1):
            big.update(c)
    open(LOG, "a", encoding="utf-8").write(f"[{time.strftime('%H:%M:%S')}] bigrams {len(big):,}  ({time.time()-t0:.0f}s)\n")
    print(f"known-known bigrams: {len(big):,}  ({time.time()-t0:.0f}s)", flush=True)

    amb = []
    with ctx.Pool(nw, initializer=_init) as pool:
        for lst in pool.imap_unordered(_find_ambig, files, chunksize=1):
            amb.extend(lst)
            if len(amb) >= SAMPLE_CAP: break
    print(f"ambiguous occurrences sampled: {len(amb):,}", flush=True)

    resolved = 0; total = 0; no_ctx = 0; samples = []
    for prev, t, nxt, cs in amb:
        total += 1
        pick, status = resolve(cs, prev, nxt, big)
        if status == "no_ctx":
            no_ctx += 1
        elif status == "resolved":
            resolved += 1
            if len(samples) < 50: samples.append((prev, t, nxt, pick, cs))
    print(f"\nRESOLVED by context (clear winner): {resolved:,} / {total:,} = {100.0*resolved/max(1,total):.1f}%")
    print(f"no context attestation at all:       {no_ctx:,} ({100.0*no_ctx/max(1,total):.1f}%)")
    print("\nSAMPLE resolutions  [prev (TOKEN) next -> pick]   candidates:")
    for prev, t, nxt, pick, cs in samples:
        print(f"  {prev} ({t}) {nxt}  -> {pick}    {cs[:5]}")

if __name__ == "__main__":
    main()
