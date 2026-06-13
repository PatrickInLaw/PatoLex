"""
extract_noctx_band.py -- extract the 'no_ctx' band for context-enriched (approach B) Sonnet adjudication.

The context sieve APPLIED the strong-collocation winners and routed the WEAK band to Sonnet, but left the
'no_ctx' band flagged: tokens that HAVE a candidate fix (edit-1 known or SymSpell edit-2) but had NO
collocation signal (no known-known bigram with either neighbor). Those are NOT garble -- they're recoverable
typos that simply didn't get a context vote. This emits each such OCCURRENCE with its surrounding-word window
(so Sonnet can judge it in context) plus a stable position id (vol/pk/idx) for applying the fix later.

Scans the POST-context cascade output (out_context). Same guards as stage_context (known/roman/affix/garbage).

Run from the repo:  python -m adjudicate.extract_noctx_band
Writes: <cascade_dir>/noctx_worklist.tsv   (vol  pk  idx  token  context_window  candidates)
"""
import os, re, json, glob, time, pickle, math
import multiprocessing as mp
import config

CASCADE   = config.path_for("cascade_dir")
STAGE_OUT = os.path.join(CASCADE, "out_context")
CORPUS_FREQ = config.path_for("cascade_dir", "corpus_freq.json")
COLLOC    = os.path.join(CASCADE, "collocation_bigrams.pkl")
OUT       = os.path.join(CASCADE, "noctx_worklist.tsv")
WIN       = 7                       # +/- this many words of context around the token
_ROMAN    = re.compile(r"^[ivxlcdm]+$")

_WS=None;_HASWF=False;_WF=None;_ZIPF=None;_SORTED=None;_SORTED_REV=None;_SYM=None;_BIG=None
def _init():
    global _WS,_HASWF,_WF,_ZIPF,_SORTED,_SORTED_REV,_SYM,_BIG
    from ocrcorrect.dictionary import build_dictionary, build_sorted_common
    from ocrcorrect.symspell_e2 import SymSpellE2, load_target_freq
    from wordfreq import zipf_frequency
    ws,_s,has,wf = build_dictionary()
    _WS=frozenset(ws);_HASWF=has;_WF=wf;_ZIPF=zipf_frequency
    _SORTED,_SORTED_REV = build_sorted_common(_WS,_ZIPF)
    _SYM = SymSpellE2(load_target_freq(CORPUS_FREQ)) if os.path.exists(CORPUS_FREQ) else None
    _BIG = pickle.load(open(COLLOC,"rb")) if os.path.exists(COLLOC) else {}

def known(t): return (t in _WS) or (_HASWF and _WF(t,"en")>0)

from ocrcorrect.edits import edits1 as _edits1, affix_of_common as _affix
from ocrcorrect.symspell_e2 import _garbage_shaped

def _cands(t):
    cs = {c for c in _edits1(t) if known(c)}
    if _SYM is not None and len(t) >= 5:
        r = _SYM.lookup(t)
        if r: cs.add(r[0])
    return cs

def _colloc(c, prev, nxt):
    return math.log(_BIG.get((prev,c),0)+1) + math.log(_BIG.get((c,nxt),0)+1)

def _extract(fp):
    vol = os.path.basename(os.path.dirname(os.path.dirname(fp)))
    out = []
    try:
        d = json.load(open(fp, encoding="utf-8", errors="replace"))
    except Exception:
        return out
    for pk, lines in d.items():
        for li, toks in enumerate(lines):
            for i, t in enumerate(toks):
                if len(t) < 4 or known(t) or _ROMAN.match(t) or _affix(t,_SORTED,_SORTED_REV) or _garbage_shaped(t):
                    continue
                cands = _cands(t)
                if not cands:
                    continue
                prev = toks[i-1] if i > 0 else ""
                nxt  = toks[i+1] if i+1 < len(toks) else ""
                if max(_colloc(c, prev, nxt) for c in cands) > 0.0:
                    continue                                  # has a collocation signal -> not no_ctx
                lo, hi = max(0, i-WIN), min(len(toks), i+WIN+1)
                window = " ".join(toks[lo:i] + ["<<"+t+">>"] + toks[i+1:hi])
                out.append((vol, str(pk), f"{li}.{i}", t, window, "|".join(sorted(cands)[:6])))
    return out

def main():
    files = sorted(glob.glob(os.path.join(STAGE_OUT, "*.json")))
    nw = max(2, min(8, (os.cpu_count() or 4) - 2))
    print(f"extracting no_ctx band over {len(files)} post-context volumes, {nw} workers...", flush=True)
    t0 = time.time(); n = 0
    ctx = mp.get_context("spawn")
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("vol\tpk\tidx\ttoken\tcontext\tcandidates\n")
        with ctx.Pool(nw, initializer=_init) as pool:
            for rows in pool.imap_unordered(_extract, files, chunksize=1):
                for r in rows:
                    fh.write("\t".join(r) + "\n"); n += 1
    print(f"no_ctx occurrences: {n:,} -> {OUT}  ({time.time()-t0:.0f}s)")

if __name__ == "__main__":
    main()
