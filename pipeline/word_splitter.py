"""
word_splitter.py -- SPLIT pass (the inverse of line_split_reunify). Recovers OCR over-merges:
two real words run together with no space ("workchair"->"work chair", "messhall"->"mess hall").

** STATUS: CANDIDATE GENERATOR, NOT auto-apply. ** Even with strict guards (2-piece, both halves
>=4 chars & common, AND the token is neither edit-1-from-a-word [typo] nor a prefix/suffix-of-a-word
[fragment]), structural splitting is only ~50% precise on this corpus: edit-2 typos slip through
(cornmission->commission), real merges mis-segment (actshall->"acts hall" not "act shall"), and
place names split (richvale). Over-merges are only ~2% of the residual -- low value, high risk --
so the output is a CANDIDATE list for an LLM validation pass (confirm over-merge + correct
segmentation), and only the validated rows are applied. Emits a reversible overlay; never
destructive.

SAFETY:
  - Only split a token that is NOT itself a known word (so "newspaper", "income", "whereas" are
    never split).
  - Segment into 2..MAXPIECES pieces, each STRONG-known and >= MINPIECE chars.
  - Prefer the segmentation with the FEWEST pieces, then the highest minimum piece frequency
    (avoids cutting a word into many tiny common words like "a","i","an").
  - Require the combined min piece zipf >= PIECE_MIN_ZIPF so we don't assemble a "split" out of
    rare/junk dictionary entries.
Runs over the 5090 consensus text. Parallel, heartbeat. is_known = build_dictionary (now includes
the validated corpus-vocab additions).

Output: _vocab/word_split_corrections.tsv  (vol, page, token, split, n_pieces, min_zipf)
"""
import os, sys, re, json, glob, time, bisect
from collections import Counter
from datetime import datetime, timezone, timedelta
import multiprocessing as mp

os.environ["CUDA_VISIBLE_DEVICES"] = ""
SCRATCH  = r"C:\Users\patolex\PatoLex-scratch"
OUT_DIR  = r"C:\Users\patolex\PatoLex-scratch\_vocab"
LOG_PATH = os.path.join(OUT_DIR, "word-split-run.log")
CORR_OUT = os.path.join(OUT_DIR, "word_split_corrections.tsv")

WORD = re.compile(r"[A-Za-z\xc0-\xff]+")
# HIGH-PRECISION ONLY: a true over-merge is rare (~2% of residual) and is structurally
# indistinguishable from a coincidentally-segmentable typo/fragment unless we demand BOTH halves
# be substantial real words. So: exactly TWO pieces, each >= MINPIECE chars and genuinely common
# (zipf >= PIECE_MIN_ZIPF), and the merged token itself unknown. This deliberately MISSES
# short-function-word merges ("anact","ofthe") -- those are too risky to auto-detect (every
# fragment ending in "in"/"to" would false-split). Precision over recall for a legal corpus.
MINPIECE = 4
PIECE_MIN_ZIPF = 3.2
MIN_TOKEN = 8          # two >=4 pieces

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

_ALPHA = "abcdefghijklmnopqrstuvwxyz"
_WS = None; _HASWF = False; _WF = None; _ZIPF = None; _SORTED = None; _SORTED_REV = None
def _init():
    global _WS, _HASWF, _WF, _ZIPF, _SORTED, _SORTED_REV
    from correction_passes import build_dictionary
    ws, _spell, has_wf, wf = build_dictionary()
    _WS = frozenset(ws); _HASWF = has_wf; _WF = wf
    # prefix/suffix indexes over COMMON words only (zipf>=3) -> for the fragment guard
    try:
        from wordfreq import zipf_frequency
        _ZIPF = zipf_frequency
    except Exception:
        _ZIPF = None
    common = [w for w in _WS if w.isalpha() and len(w) >= 6 and (_ZIPF is None or _ZIPF(w, "en") >= 3.0)]
    _SORTED = sorted(common); _SORTED_REV = sorted(w[::-1] for w in common)

def _edits1_known(w):
    """is w edit-distance-1 from a known word? (=> w is a TYPO, not an over-merge)"""
    sp = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    for a, b in sp:
        if b and _known(a + b[1:]): return True
        if len(b) > 1 and _known(a + b[1] + b[0] + b[2:]): return True
        for c in _ALPHA:
            if b and _known(a + c + b[1:]): return True
            if _known(a + c + b): return True
    return False

def _is_affix_of_common(s):
    """is s a prefix OR suffix of a common word >=2 longer? (=> s is a FRAGMENT, not a merge)"""
    i = bisect.bisect_left(_SORTED, s)
    if i < len(_SORTED) and _SORTED[i].startswith(s) and len(_SORTED[i]) >= len(s) + 2:
        return True
    r = s[::-1]; j = bisect.bisect_left(_SORTED_REV, r)
    return j < len(_SORTED_REV) and _SORTED_REV[j].startswith(r) and len(_SORTED_REV[j]) >= len(s) + 2

def _known(tok):
    if tok in _WS:
        return True
    if _HASWF and _WF(tok, "en") > 0:
        return True
    return False
def _zipf(tok):
    return _ZIPF(tok, "en") if _ZIPF is not None else (4.5 if tok in _WS else 0.0)
def _piece_valid(p):
    return len(p) >= MINPIECE and _zipf(p) >= PIECE_MIN_ZIPF

def _segment(tok):
    """Single best 2-piece split where BOTH halves are substantial common words.
    Among valid splits, pick the one with the highest minimum-piece zipf. Returns (pieces, min_zipf)."""
    n = len(tok)
    best = None  # (min_zipf, [a, b])
    for i in range(MINPIECE, n - MINPIECE + 1):
        a, b = tok[:i], tok[i:]
        if _piece_valid(a) and _piece_valid(b):
            mz = min(_zipf(a), _zipf(b))
            if best is None or mz > best[0]:
                best = (mz, [a, b])
    if best is None:
        return None
    return best[1], best[0]

def _scan_file(path):
    counts = Counter(); rows = []
    try:
        data = json.load(open(path, encoding="utf-8", errors="replace"))
    except Exception:
        return (counts, rows)
    vol = os.path.basename(os.path.dirname(os.path.dirname(path)))
    seen_tok = {}  # token -> (split, mz)  cache within file
    for pk, po in data.items():
        for t in WORD.findall(po.get("consensus_text") or ""):
            low = t.lower()
            if len(low) < MIN_TOKEN or _known(low):
                continue  # too short to be 2 words, or itself a real word -> never split
            if low in seen_tok:
                res = seen_tok[low]
            else:
                res = None
                # GUARDS: an over-merge must NOT be better explained as a typo or a fragment.
                if not _edits1_known(low) and not _is_affix_of_common(low):
                    seg = _segment(low)
                    if seg:
                        pieces, mz = seg
                        res = (" ".join(pieces), mz, len(pieces))
                seen_tok[low] = res
            if res:
                counts["split"] += 1
                rows.append((vol, pk, low, res[0], res[2], f"{res[1]:.2f}"))
    return (counts, rows)

def main():
    rlog("START", f"word-splitter (2-piece, both>={MINPIECE}ch zipf>={PIECE_MIN_ZIPF}, MIN_TOKEN={MIN_TOKEN})")
    files = sorted(glob.glob(os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json")))
    rlog("SCAN", f"{len(files)} consensus files")
    try:
        nw = max(2, min(12, (os.cpu_count() or 4) - 2))
    except Exception:
        nw = 8
    totals = Counter(); allrows = []
    t0 = time.time(); last = time.time(); done = 0
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw, initializer=_init) as pool:
        for counts, rows in pool.imap_unordered(_scan_file, files, chunksize=1):
            totals.update(counts); allrows.extend(rows)
            done += 1
            now = time.time()
            if now - last >= 15 or done == len(files):
                rlog("SCAN", f"{done}/{len(files)} files | splits={len(allrows):,} | elapsed={now-t0:.0f}s", "HEARTBEAT")
                last = now
    with open(CORR_OUT, "w", encoding="utf-8") as f:
        f.write("vol\tpage\ttoken\tsplit\tn_pieces\tmin_zipf\n")
        for r in sorted(allrows, key=lambda x: (x[0], x[1])):
            f.write("\t".join(str(x) for x in r) + "\n")
    uniq = Counter(r[2] for r in allrows)
    npieces = Counter(r[4] for r in allrows)
    rlog("SUMMARY", f"split corrections = {len(allrows):,}  (distinct tokens = {len(uniq):,})")
    rlog("SUMMARY", f"by n_pieces: {dict(npieces)}")
    print("\n[TOP 30 over-merges by occurrence]")
    for tok, c in uniq.most_common(30):
        ex = next(r[3] for r in allrows if r[2] == tok)
        print(f"   {c:4d}  {tok} -> {ex}")
    sys.stdout.flush()
    rlog("DONE", f"-> {CORR_OUT}  wall={time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
