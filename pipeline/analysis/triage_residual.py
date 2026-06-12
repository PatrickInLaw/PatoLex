"""
triage_residual.py -- procedural triage of the OCR-correction residual.

Classifies every residual "bad" token (from _vocab/residual_bad_words.tsv) into:
  NOISE     -- repeated-char scanner artifact (eeeeee, cceeee)  -> strip
  TYPO      -- within edit-1 of a COMMON word                   -> correctable (suggestion given)
  FRAGMENT  -- a prefix/suffix of a common word (line-break piece, recla-, -sively) -> rejoin candidate
  NAMELIKE  -- pronounceable, not in dict, no garble signals     -> likely name/foreign, KEEP/flag
  GARBLE    -- none of the above (consonant clusters, low plausibility) -> needs image/LLM

No model. Frequency-scored "common" reference = wordfreq top-N + legal + stopwords.
Parallel (12 workers), heartbeat run log. Output: _vocab/residual_triage.tsv + summary.
"""
import os, sys, re, json, time, bisect
from collections import Counter
from datetime import datetime, timezone, timedelta
import multiprocessing as mp
import config

os.environ["CUDA_VISIBLE_DEVICES"] = ""

OUT_DIR  = config.path_for("vocab_dir")
TSV_IN   = os.path.join(OUT_DIR, "residual_bad_words.tsv")
TSV_OUT  = os.path.join(OUT_DIR, "residual_triage.tsv")
LOG_PATH = os.path.join(OUT_DIR, "triage-run.log")
TOP_N    = int(os.environ.get("TRIAGE_TOP_N", "60000"))

LEGAL_SUPPLEMENT = {
    "hereinafter","heretofore","thereof","therein","thereto","whereas","aforesaid",
    "notwithstanding","appropriation","appropriated","legislature","legislative",
    "subdivision","subsection","commissioner","superintendent","conservatee",
    "habilitative","mobilehome","nonmotorized","materialmen","indorser",
}
STOPWORDS = {"of","the","in","to","and","for","by","an","as","at","or","on","a","is","it"}
VOWELS = set("aeiou")

def pt():
    try:
        z = timezone(timedelta(hours=-7))
        return datetime.now(timezone.utc).astimezone(z).strftime("%Y-%m-%d %H:%M PT")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

def rlog(phase, desc, status="OK"):
    line = f"[{pt()}] {phase} | {desc} | {status}\n"
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line); f.flush()
    print(line.rstrip()); sys.stdout.flush()

# ---- worker globals (spawn-safe) ----
_COMMON = None          # set of common words
_COMMON_SORTED = None    # sorted list (for prefix bisect)
_COMMON_REV_SORTED = None  # sorted reversed words (for suffix bisect)
_FULL = None             # full union dict (is_known)
_HAS_WF = False
_WF = None

def _build_refs():
    global _COMMON, _COMMON_SORTED, _COMMON_REV_SORTED, _FULL, _HAS_WF, _WF
    common = set()
    try:
        from wordfreq import top_n_list
        common |= set(top_n_list("en", TOP_N))
    except Exception as e:
        print(f"[WARN] wordfreq top_n_list: {e}", file=sys.stderr)
    common |= LEGAL_SUPPLEMENT | STOPWORDS
    common = {w for w in common if w.isalpha() and len(w) >= 2}
    _COMMON = common
    _COMMON_SORTED = sorted(common)
    _COMMON_REV_SORTED = sorted(w[::-1] for w in common)
    # full union for is_known (broader)
    full = set(common)
    try:
        from spellchecker import SpellChecker
        full |= set(SpellChecker().word_frequency.dictionary.keys())
    except Exception:
        pass
    try:
        from nltk.corpus import words as nw
        full |= set(w.lower() for w in nw.words())
    except Exception:
        pass
    _FULL = full
    try:
        from wordfreq import word_frequency
        _WF = word_frequency; _HAS_WF = True
    except Exception:
        _HAS_WF = False

def _init():
    _build_refs()

def _max_run(s):
    best = run = 1
    for i in range(1, len(s)):
        run = run + 1 if s[i] == s[i-1] else 1
        if run > best: best = run
    return best if s else 0

def _vowel_ratio(s):
    return sum(1 for c in s if c in VOWELS) / len(s) if s else 0.0

def _edit1_common(tok):
    """First common word within edit distance 1 of tok (early-exit), else None."""
    if len(tok) > 18:
        return None
    ab = "abcdefghijklmnopqrstuvwxyz"; n = len(tok); C = _COMMON
    for i in range(n):
        c = tok[:i] + tok[i+1:]
        if len(c) >= 2 and c in C: return c
    for i in range(n):
        for ch in ab:
            if ch == tok[i]: continue
            c = tok[:i] + ch + tok[i+1:]
            if c in C: return c
    for i in range(n+1):
        for ch in ab:
            c = tok[:i] + ch + tok[i:]
            if c in C: return c
    for i in range(n-1):
        c = tok[:i] + tok[i+1] + tok[i] + tok[i+2:]
        if c in C: return c
    return None

def _prefix_of_common(tok):
    """A common word that starts with tok (tok is a head fragment)."""
    i = bisect.bisect_left(_COMMON_SORTED, tok)
    if i < len(_COMMON_SORTED):
        w = _COMMON_SORTED[i]
        if w.startswith(tok) and len(w) > len(tok):
            return w
    return None

def _suffix_of_common(tok):
    """A common word that ends with tok (tok is a tail fragment)."""
    r = tok[::-1]
    i = bisect.bisect_left(_COMMON_REV_SORTED, r)
    if i < len(_COMMON_REV_SORTED):
        w = _COMMON_REV_SORTED[i]
        if w.startswith(r) and len(w) > len(tok):
            return w[::-1]
    return None

def _namelike(tok):
    vr = _vowel_ratio(tok)
    return 0.2 <= vr <= 0.6 and _max_run(tok) <= 2 and len(tok) >= 4

def _classify(tok):
    """Return (category, suggestion)."""
    n = len(tok)
    # NOISE: repeated-char scanner artifact
    if _max_run(tok) >= 4:
        return ("NOISE", "")
    # TYPO: edit-1 of a common word (strongest recovery signal)
    e1 = _edit1_common(tok)
    if e1:
        return ("TYPO", e1)
    # FRAGMENT: a head/tail of a common word, length >= 4
    if n >= 4:
        pf = _prefix_of_common(tok)
        if pf: return ("FRAGMENT", pf)
        sf = _suffix_of_common(tok)
        if sf: return ("FRAGMENT", sf)
    # NAMELIKE vs GARBLE
    if _namelike(tok):
        return ("NAMELIKE", "")
    return ("GARBLE", "")

def _classify_row(row):
    tok, freq, tier = row
    cat, sug = _classify(tok)
    return (tok, freq, tier, cat, sug)

def load_rows():
    rows = []
    with open(TSV_IN, encoding="utf-8") as f:
        next(f, None)
        for ln in f:
            p = ln.rstrip("\n").split("\t")
            if len(p) >= 3:
                rows.append((p[0], int(p[1]) if p[1].isdigit() else 0, p[2]))
    return rows

def main():
    rlog("START", f"residual triage  top_n={TOP_N}")
    rows = load_rows()
    total = len(rows)
    rlog("LOAD", f"{total:,} residual tokens from {os.path.basename(TSV_IN)}")
    try:
        nw = min(12, (os.cpu_count() or 4) - 2)
    except Exception:
        nw = 8
    nw = max(2, nw)

    results = []
    # tier x category tally
    tally = {}
    t0 = time.time(); last = time.time(); done = 0
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw, initializer=_init) as pool:
        for tok, freq, tier, cat, sug in pool.imap_unordered(_classify_row, rows, chunksize=1000):
            results.append((tok, freq, tier, cat, sug))
            tier_key = "singleton" if tier == "singleton" else ("low_2_9" if tier in ("low_freq","low_2_9") else "high_10")
            tally[(tier_key, cat)] = tally.get((tier_key, cat), 0) + 1
            done += 1
            now = time.time()
            if now - last >= 15 or done == total:
                rlog("TRIAGE", f"{done:,}/{total:,} | elapsed={now-t0:.0f}s | rate={done/max(now-t0,0.001):.0f}/s", "HEARTBEAT")
                last = now

    with open(TSV_OUT, "w", encoding="utf-8") as f:
        f.write("token\tfreq\ttier\tcategory\tsuggestion\n")
        for tok, freq, tier, cat, sug in sorted(results, key=lambda r: (-r[1], r[0])):
            f.write(f"{tok}\t{freq}\t{tier}\t{cat}\t{sug}\n")

    # summary
    cats = ["NOISE", "TYPO", "FRAGMENT", "NAMELIKE", "GARBLE"]
    tiers = ["singleton", "low_2_9", "high_10"]
    rlog("SUMMARY", "category x tier counts:")
    header = "tier".ljust(12) + "".join(c.ljust(11) for c in cats) + "TOTAL"
    rlog("SUMMARY", header)
    grand = Counter()
    for ti in tiers:
        rowc = [tally.get((ti, c), 0) for c in cats]
        for c, v in zip(cats, rowc): grand[c] += v
        rlog("SUMMARY", ti.ljust(12) + "".join(str(v).ljust(11) for v in rowc) + str(sum(rowc)))
    rlog("SUMMARY", "ALL".ljust(12) + "".join(str(grand[c]).ljust(11) for c in cats) + str(sum(grand.values())))
    rlog("DONE", f"out={TSV_OUT}  wall={time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
