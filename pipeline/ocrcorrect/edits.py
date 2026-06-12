"""
edits.py -- the ONE home for the edit-distance + affix primitives that were copy-pasted across
correction_cascade, symspell_e2, context_resolve, and recoverable_compose. Pure functions (no module
globals): callers pass the sorted common-word lists where needed. Behavior is verbatim-identical to the
prior per-file copies -- this is a de-duplication, not a logic change (golden-master gated).
"""
import bisect

ALPHA = "abcdefghijklmnopqrstuvwxyz"

def edits1(w):
    """All strings within Damerau edit distance 1 of w (sub/insert/transpose; delete via the empty tail)."""
    sp = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    out = set()
    for a, b in sp:
        if b: out.add(a + b[1:])                       # delete
        if len(b) > 1: out.add(a + b[1] + b[0] + b[2:]) # transpose
        for c in ALPHA:
            if b: out.add(a + c + b[1:])                # substitute
            out.add(a + c + b)                          # insert
    out.discard(w)
    return out

def deletes(word, max_dist):
    """All strings reachable from `word` by up to max_dist single-char deletions (incl. word itself).
    The SymSpell query/index primitive."""
    out = {word}
    cur = {word}
    for _ in range(max_dist):
        nxt = set()
        for w in cur:
            if len(w) <= 1:
                continue
            for i in range(len(w)):
                nxt.add(w[:i] + w[i + 1:])
        out |= nxt
        cur = nxt
    return out

def dl_within(a, b, maxd):
    """Optimal-string-alignment (restricted Damerau-Levenshtein) distance, early-exit if > maxd."""
    la, lb = len(a), len(b)
    if abs(la - lb) > maxd:
        return maxd + 1
    prev2 = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        rowmin = cur[0]
        ca = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ca == b[j - 1] else 1
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if (prev2 is not None and i > 1 and j > 1
                    and ca == b[j - 2] and a[i - 2] == b[j - 1]):
                v = min(v, prev2[j - 2] + 1)
            cur[j] = v
            if v < rowmin:
                rowmin = v
        if rowmin > maxd:
            return maxd + 1
        prev2, prev = prev, cur
    return prev[lb]

def is_prefix_frag(s, sorted_common):
    """True if some common word STARTS with s (and is >= 2 chars longer) -> s is a head fragment."""
    i = bisect.bisect_left(sorted_common, s)
    return i < len(sorted_common) and sorted_common[i].startswith(s) and len(sorted_common[i]) >= len(s) + 2

def is_suffix_frag(s, sorted_common_rev):
    """True if some common word ENDS with s (and is >= 2 chars longer) -> s is a tail fragment.
    `sorted_common_rev` = sorted list of the common words reversed."""
    r = s[::-1]
    j = bisect.bisect_left(sorted_common_rev, r)
    return j < len(sorted_common_rev) and sorted_common_rev[j].startswith(r) and len(sorted_common_rev[j]) >= len(s) + 2

def affix_of_common(s, sorted_common, sorted_common_rev):
    """s is a prefix OR suffix fragment of some common word."""
    return is_prefix_frag(s, sorted_common) or is_suffix_frag(s, sorted_common_rev)
