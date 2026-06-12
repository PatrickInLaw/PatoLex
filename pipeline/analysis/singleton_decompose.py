"""
HONEST decomposition of the singleton tail (v2 -- fixed). Uses the INTEGRATED dict
(build_dictionary now loads corpus-vocab additions). Order is reliability-ranked, first match:
  GARBAGE      structural (char salad / repeat / cons-run / no-vowel / non-ascii)
  FRAG_join    token+next or prev+token is a real word (context-confirmed fragment)
  EDIT1        edit-distance-1 to a known word (one-off typo)            <- BEFORE over-merge now
  EDIT2        edit-distance-2 to a known word (pyspellchecker candidates) <- efficient
  OVER_MERGE   STRICT split into 2 strong-known words (real run-on)       <- strong_known, not wf>0
  FRAG_affix   prefix/suffix of a known word, unknown neighbour (weak fragment)
  STANDALONE   none of the above (rare real word / name / novel)
"""
import os, re, json, glob, random, bisect
from collections import Counter
import config

SCRATCH = config.path_for("data_root")
VOCAB   = config.path_for("vocab_dir")
WORD = re.compile(r"[A-Za-z\xc0-\xff]+")
ALPHA = "abcdefghijklmnopqrstuvwxyz"
VOW = set("aeiouy")
SAMPLE = 6000

from ocrcorrect.correction_passes import build_dictionary
ws, spell, has_wf, wf = build_dictionary()
WS = frozenset(ws)
try:
    from wordfreq import zipf_frequency as zipf
except Exception:
    zipf = None
def known(t): return (t in WS) or (has_wf and wf(t, "en") > 0)
def strong_known(t):
    if t in WS: return True
    return zipf is not None and zipf(t, "en") >= 2.8

SORTED = sorted(WS); SORTED_REV = sorted(w[::-1] for w in WS)
def prefix_of(s):
    i = bisect.bisect_left(SORTED, s)
    return i < len(SORTED) and SORTED[i].startswith(s) and len(SORTED[i]) >= len(s) + 2
def suffix_of(s):
    r = s[::-1]; i = bisect.bisect_left(SORTED_REV, r)
    return i < len(SORTED_REV) and SORTED_REV[i].startswith(r) and len(SORTED_REV[i]) >= len(s) + 2

def structural_garbage(t):
    if any(ord(c) > 127 for c in t): return True
    if len(t) >= 4 and re.search(r"(.)\1\1", t): return True
    if re.search(r"[bcdfghjklmnpqrstvwxz]{5,}", t): return True
    if len(t) >= 5 and not (set(t) & VOW): return True
    return False

def strict_splittable(t):  # real over-merge: both halves STRONG-known (>=3 each)
    for i in range(3, len(t) - 2):
        if strong_known(t[:i]) and strong_known(t[i:]):
            return True
    return False

def edits1(w):
    sp = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    out = set()
    for a, b in sp:
        if b: out.add(a + b[1:])
        if len(b) > 1: out.add(a + b[1] + b[0] + b[2:])
        for c in ALPHA:
            if b: out.add(a + c + b[1:])
            out.add(a + c + b)
    return out
def edit1_known(s):
    return any(known(c) and c != s for c in edits1(s))
def edit2_correctable(s):  # efficient edit<=2 via pyspellchecker; called only after edit1 failed
    if spell is None or len(s) > 16: return False
    cands = spell.candidates(s)
    return bool(cands) and cands != {s}

# singletons + one context occurrence
singles = set()
for i, ln in enumerate(open(os.path.join(VOCAB, "residual_triage.tsv"), encoding="utf-8")):
    if i == 0: continue
    p = ln.rstrip("\n").split("\t")
    if len(p) >= 3 and p[2] == "singleton":
        singles.add(p[0].lower())
random.seed(7)
samp = set(random.sample(list(singles), min(SAMPLE, len(singles))))
ctx = {}
for fp in sorted(glob.glob(os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json"))):
    if len(ctx) >= len(samp): break
    try: data = json.load(open(fp, encoding="utf-8", errors="replace"))
    except Exception: continue
    for pk, po in data.items():
        low = [t.lower() for t in WORD.findall(po.get("consensus_text") or "")]
        for j, t in enumerate(low):
            if t in samp and t not in ctx:
                ctx[t] = (low[j-1] if j > 0 else "", low[j+1] if j+1 < len(low) else "")

cat = Counter(); ex = {}
for s in samp:
    prv, nxt = ctx.get(s, ("", ""))
    if structural_garbage(s):
        c = "GARBAGE"
    elif (nxt and not known(nxt) and known(s + nxt)) or (prv and not known(prv) and known(prv + s)):
        c = "FRAG_join"
    elif edit1_known(s):
        c = "EDIT1"
    elif edit2_correctable(s):
        c = "EDIT2"
    elif strict_splittable(s):
        c = "OVER_MERGE"
    elif (suffix_of(s) and prv and not known(prv)) or (prefix_of(s) and nxt and not known(nxt)):
        c = "FRAG_affix"
    else:
        c = "STANDALONE"
    cat[c] += 1
    ex.setdefault(c, [])
    if len(ex[c]) < 12: ex[c].append(f"[{prv} <{s}> {nxt}]")

n = sum(cat.values())
print(f"sampled singletons with context = {n:,} (of {len(singles):,})")
order = ["GARBAGE", "FRAG_join", "EDIT1", "EDIT2", "OVER_MERGE", "FRAG_affix", "STANDALONE"]
for c in order:
    v = cat.get(c, 0)
    print(f"  {c:11s} {v:6,}  ({100.0*v/n:.1f}%)")
recov = ["FRAG_join", "EDIT1", "EDIT2", "OVER_MERGE", "FRAG_affix"]
r = sum(cat.get(c, 0) for c in recov)
print(f"\nRECOVERABLE = {r:,} ({100.0*r/n:.1f}%)   GARBAGE = {cat['GARBAGE']:,} ({100.0*cat['GARBAGE']/n:.1f}%)   STANDALONE = {cat['STANDALONE']:,} ({100.0*cat['STANDALONE']/n:.1f}%)")
print("\nexamples:")
for c in order:
    print(f"  {c}: {ex.get(c, [])[:8]}")
