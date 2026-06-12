"""
recoverable_compose.py -- decompose the post-cascade RECOVERABLE residual (flagged, not garbage,
not roman) into what it actually is + what each part NEEDS, so we triage instead of dumping it all
on an LLM. Type-level (distinct token + corpus freq), cheap signals. Reads _cascade/out_autocorrect.

Buckets (first match):
  FRAGMENT    affix-of-a-common-word (orphaned piece) -> reunify / rejoin
  MOJIBAKE    contains a non-ASCII char -> targeted fuzzy / vision
  SHORT       len<=4 -> needs context (cheap LLM in-context)
  NAMELIKE    matches the name gazetteer -> DICT-ADD (a real word, NOT an error)
  HARD        none of the above -> edit-2 / local-model / LLM / vision triage
Also reports the FREQUENCY split (freq>=10 vs 2-9 vs singleton): only the freq>=10 slice is
"Sonnet-overlay territory"; the bulk is the singleton tail.
"""
import os, sys, re, json, glob, bisect
from collections import Counter
import multiprocessing as mp

SCRATCH = r"C:\Users\patolex\PatoLex-scratch"
CASCADE = os.path.join(SCRATCH, "_cascade")
VOCAB = os.path.join(SCRATCH, "_vocab")
STAGE_OUT = os.path.join(CASCADE, "out_autocorrect")
_ROMAN = re.compile(r"^[ivxlcdm]+$")
_REPEAT4 = re.compile(r"(.)\1\1\1"); _REPEAT3 = re.compile(r"(.)\1\1")
_CONS5 = re.compile(r"[bcdfghjklmnpqrstvwxz]{5,}"); _RUN3 = re.compile(r"(.)\1\1+")
_VOWELS = set("aeiouy")

_WS = None; _HASWF = False; _WF = None; _SORTED = None; _SORTED_REV = None; _NAMES = frozenset()
def _init():
    global _WS, _HASWF, _WF, _SORTED, _SORTED_REV, _NAMES
    from correction_passes import build_dictionary
    ws, _s, has_wf, wf = build_dictionary()
    _WS = frozenset(ws); _HASWF = has_wf; _WF = wf
    from wordfreq import zipf_frequency
    common = [w for w in _WS if w.isalpha() and len(w) >= 6 and zipf_frequency(w, "en") >= 3.0]
    _SORTED = sorted(common); _SORTED_REV = sorted(w[::-1] for w in common)
    p = os.path.join(SCRATCH, "name_gazetteer.txt")
    if os.path.exists(p):
        _NAMES = frozenset(l.strip() for l in open(p, encoding="utf-8") if l.strip())
def known(t): return (t in _WS) or (_HASWF and _WF(t, "en") > 0)
def _collapse(t): return _RUN3.sub(r"\1\1", t)
def _is_garbage(t):
    if sum(1 for c in t if ord(c) > 127) >= 2: return True
    if _REPEAT4.search(t): return True
    if _REPEAT3.search(t) and not known(_collapse(t)):
        if _CONS5.search(t) or (len(t) >= 5 and not (set(t) & _VOWELS)): return True
    if _CONS5.search(t): return True
    if len(t) >= 5 and not (set(t) & _VOWELS): return True
    if len(t) >= 25: return True
    return False
def _affix(s):
    i = bisect.bisect_left(_SORTED, s)
    if i < len(_SORTED) and _SORTED[i].startswith(s) and len(_SORTED[i]) >= len(s) + 2: return True
    r = s[::-1]; j = bisect.bisect_left(_SORTED_REV, r)
    return j < len(_SORTED_REV) and _SORTED_REV[j].startswith(r) and len(_SORTED_REV[j]) >= len(s) + 2

def _bucket(t):
    if any(ord(c) > 127 for c in t): return "MOJIBAKE"
    if len(t) <= 4: return "SHORT"
    if _affix(t): return "FRAGMENT"
    if t in _NAMES: return "NAMELIKE"
    return "HARD"

def _count(vol_file):
    freq = Counter()
    try: d = json.load(open(vol_file, encoding="utf-8"))
    except Exception: return freq
    for pk, lines in d.items():
        for toks in lines:
            for t in toks:
                if len(t) >= 2: freq[t] += 1
    return freq

def main():
    files = sorted(glob.glob(os.path.join(STAGE_OUT, "*.json")))
    print(f"{len(files)} volumes -- aggregating corpus freq", flush=True)
    nw = max(2, min(12, (os.cpu_count() or 4) - 2))
    ctx = mp.get_context("spawn")
    freq = Counter()
    with ctx.Pool(nw, initializer=_init) as pool:
        for fr in pool.imap_unordered(_count, files, chunksize=1):
            freq.update(fr)
    # classify the RECOVERABLE types (flagged, not garbage, not roman) -- single process w/ dict
    _init()
    btypes = Counter(); bocc = Counter(); ftier_occ = Counter(); ex = {}
    rec_types = rec_occ = 0
    for t, f in freq.items():
        if len(t) < 2 or known(t): continue
        if _ROMAN.match(t) and len(t) >= 2: continue   # roman
        if _is_garbage(t): continue                    # garbage
        rec_types += 1; rec_occ += f
        b = _bucket(t); btypes[b] += 1; bocc[b] += f
        ftier_occ["freq>=10" if f >= 10 else ("2-9" if f >= 2 else "singleton")] += f
        ex.setdefault(b, [])
        if len(ex[b]) < 12: ex[b].append(f"{t}({f})")
    print(f"\nRECOVERABLE: {rec_types:,} distinct types, {rec_occ:,} occurrences")
    print("\nby need-bucket (types / occ / %occ):")
    for b in ("HARD", "SHORT", "FRAGMENT", "MOJIBAKE", "NAMELIKE"):
        print(f"  {b:10s} {btypes[b]:7,} / {bocc[b]:8,} / {100.0*bocc[b]/max(1,rec_occ):4.1f}%")
    print("\nby frequency tier (occ):")
    for k in ("freq>=10", "2-9", "singleton"):
        print(f"  {k:10s} {ftier_occ[k]:,} ({100.0*ftier_occ[k]/max(1,rec_occ):.1f}%)")
    print("\nexamples:")
    for b in ("HARD", "SHORT", "FRAGMENT", "MOJIBAKE", "NAMELIKE"):
        print(f"  {b}: {ex.get(b, [])}")
    json.dump({"rec_types": rec_types, "rec_occ": rec_occ,
               "by_bucket_occ": dict(bocc), "by_bucket_types": dict(btypes),
               "by_freq_tier_occ": dict(ftier_occ)},
              open(os.path.join(CASCADE, "recoverable_composition.json"), "w", encoding="utf-8"), indent=2)

if __name__ == "__main__":
    main()
