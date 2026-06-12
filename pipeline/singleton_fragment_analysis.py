"""
Answer: is the 385k singleton tail actually full of FRAGMENTS?
For each freq-1 residual token, find its occurrence in the consensus text, look at the
actual neighbours, and classify with CONTEXT (not a guess):
  FRAG_dict_join  : token+next or prev+token is a real dict word (a true split; reunifier
                    missed it because its join wasn't STRONG-known / other-half conditions)
  FRAG_fuzzy_join : that join is ONE inserted char from a real word (misspelled-real-word split)
  FRAG_affix      : token is a prefix/suffix of a real (>=2 longer) dict word AND its neighbour
                    is a non-word -> looks like a chopped word-piece
  GARBAGE         : structural garbage (eeee / cons-run / no-vowel)
  STANDALONE      : none of the above (rare real word / name / unclear)
"""
import os, sys, re, json, glob, bisect
from collections import Counter

SCRATCH = r"C:\Users\patolex\PatoLex-scratch"
RESID   = r"C:\Users\patolex\PatoLex-scratch\_vocab\residual_triage.tsv"
WORD = re.compile(r"[A-Za-z\xc0-\xff]+")
VOW = set("aeiouy")

from correction_passes import build_dictionary
ws, _spell, has_wf, wf = build_dictionary()
WS = frozenset(ws)
def known(t):
    return (t in WS) or (has_wf and wf(t, "en") > 0)

# sorted structures for prefix / suffix membership
SORTED = sorted(WS)
SORTED_REV = sorted(w[::-1] for w in WS)
def is_prefix_of_word(s):
    i = bisect.bisect_left(SORTED, s)
    return i < len(SORTED) and SORTED[i].startswith(s) and len(SORTED[i]) >= len(s) + 2
def is_suffix_of_word(s):
    r = s[::-1]
    i = bisect.bisect_left(SORTED_REV, r)
    return i < len(SORTED_REV) and SORTED_REV[i].startswith(r) and len(SORTED_REV[i]) >= len(s) + 2

ALPHA = "abcdefghijklmnopqrstuvwxyz"
def insert1_known(s):
    if len(s) < 6 or len(s) > 18: return False
    for pos in range(len(s) + 1):
        for c in ALPHA:
            if (s[:pos] + c + s[pos:]) in WS:
                return True
    return False

def garbage(t):
    if len(t) >= 4 and re.search(r"(.)\1\1", t): return True
    if re.search(r"[bcdfghjklmnpqrstvwxz]{5,}", t): return True
    if len(t) >= 5 and not (set(t) & VOW): return True
    return False

# load singletons
singles = set()
for i, ln in enumerate(open(RESID, encoding="utf-8")):
    if i == 0: continue
    p = ln.rstrip("\n").split("\t")
    if len(p) >= 3 and p[2] == "singleton":
        singles.add(p[0].lower())
print(f"singletons = {len(singles):,}")

cat = Counter(); ex = {}
files = sorted(glob.glob(os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json")))
seen = set()
for fp in files:
    try:
        data = json.load(open(fp, encoding="utf-8", errors="replace"))
    except Exception:
        continue
    for pk, po in data.items():
        toks = WORD.findall(po.get("consensus_text") or "")
        low = [t.lower() for t in toks]
        for j, t in enumerate(low):
            if t not in singles or t in seen:
                continue
            seen.add(t)
            prv = low[j-1] if j > 0 else ""
            nxt = low[j+1] if j+1 < len(low) else ""
            jn_next = t + nxt
            jn_prev = prv + t
            if (nxt and known(jn_next) and not known(nxt)) or (prv and known(jn_prev) and not known(prv)):
                c = "FRAG_dict_join"
            elif (nxt and not known(nxt) and insert1_known(jn_next)) or (prv and not known(prv) and insert1_known(jn_prev)):
                c = "FRAG_fuzzy_join"
            elif (is_suffix_of_word(t) and prv and not known(prv)) or (is_prefix_of_word(t) and nxt and not known(nxt)):
                c = "FRAG_affix"
            elif garbage(t):
                c = "GARBAGE"
            else:
                c = "STANDALONE"
            cat[c] += 1
            ex.setdefault(c, [])
            if len(ex[c]) < 12:
                ex[c].append(f"[{prv} <{t}> {nxt}]")

found = sum(cat.values())
print(f"classified {found:,} singleton occurrences found in text")
for c, n in cat.most_common():
    print(f"  {c:16s} {n:7,}  ({100.0*n/max(1,found):.1f}%)")
fragtot = cat["FRAG_dict_join"] + cat["FRAG_fuzzy_join"] + cat["FRAG_affix"]
print(f"\nFRAGMENT-like singletons = {fragtot:,} ({100.0*fragtot/max(1,found):.1f}%)")
print("\nexamples:")
for c in cat:
    print(f"  {c}: {ex.get(c, [])[:8]}")
