"""
line_split_reunify.py (v2) -- REUNIFICATION pass for words broken into fragments.

v2 adds the classes v1 missed (the residual was full of fragments v1 never touched):
  1. SPACESPLIT  -- spurious mid-line space INSIDE a word, same line ("superin tendent",
                    "com pensation"). v1 was line-oriented and could not see these.
  2. CROSSPAGE   -- word split across a PAGE boundary (head at end of page N, tail at
                    start of page N+1). v1 scanned per page and could never join these.
  3. NOHYPHEN adjacent line-breaks are now EMITTED (Pass A only rejoins HYPHEN cases, so
                    non-hyphen consecutive-line splits fell through both passes).
  4. LOOKAHEAD raised 3 -> 6 (longer margin notes between the two halves).

SAFETY (unchanged invariant): only join when the JOINED string is a known word AND not both
halves are already known -> never fuses two real words (e.g. "in form of" stays apart). The
unknown half must be >=3 chars. Output is the reversible corrections artifact; nothing is
destructively edited.

Output: _vocab/line_split_corrections.tsv
  cols: vol  page  tier  kind  margin_words  head  tail  joined  margin_text
Parallel per-file, CPU, heartbeat. is_known = same union dict as correction_passes.
"""
import os, sys, re, json, glob, time
from collections import Counter
from datetime import datetime, timezone, timedelta
import multiprocessing as mp

os.environ["CUDA_VISIBLE_DEVICES"] = ""
SCRATCH  = r"C:\Users\patolex\PatoLex-scratch"
OUT_DIR  = r"C:\Users\patolex\PatoLex-scratch\_vocab"
LOG_PATH = os.path.join(OUT_DIR, "line-reunify-run.log")
CORR_OUT = os.path.join(OUT_DIR, "line_split_corrections.tsv")
LOOKAHEAD = 6
MAXFRAG = 4   # max consecutive same-line pieces to try fusing (handles 3-4 fragment words)

WORD = re.compile(r"[A-Za-z\xc0-\xff]+")
HEAD_HYPHEN = re.compile(r"([A-Za-z\xc0-\xff]{2,})-[ \t\r]*$")  # \r-safe for CRLF text
_DIGITS = re.compile(r"(\d+)")

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

_WS = None; _HASWF = False; _WF = None; _ZIPF = None
def _init():
    global _WS, _HASWF, _WF, _ZIPF
    from correction_passes import build_dictionary
    ws, _spell, has_wf, wf = build_dictionary()
    _WS = frozenset(ws); _HASWF = has_wf; _WF = wf
    try:
        from wordfreq import zipf_frequency
        _ZIPF = zipf_frequency
    except Exception:
        _ZIPF = None

def _known(tok):
    if tok in _WS:
        return True
    if _HASWF and _WF(tok, "en") > 0:
        return True
    return False

def _strong_known(tok):
    """Stricter than _known -- for the unconstrained same-line space-rejoin, the JOINED word
    must be in the curated static dict OR genuinely common (zipf >= 2.8). This rejects rare
    misspellings/fragments that _known (wf>0) wrongly accepts: ceecee, philadephia, administra."""
    if tok in _WS:
        return True
    if _ZIPF is not None and _ZIPF(tok, "en") >= 2.8:
        return True
    return False

_ALPHA = "abcdefghijklmnopqrstuvwxyz"
def _insert1_known(s):
    """Is s exactly ONE inserted character away from a strongly-known word? Recovers the common
    OCR failure where a character is DROPPED at the split point (philade+phia -> 'philadephia',
    +l -> 'philadelphia'). Returns the UNIQUE recovered word, or None if zero OR AMBIGUOUS
    (>1 distinct strong word) -- a flagged suggestion must be unambiguous (Hans C2-3).
    Lower bound 5 so 5-char joins like 'ageny'->'agency' are not skipped (Hans C2-4)."""
    if len(s) < 5 or len(s) > 18:
        return None
    found = set()
    for pos in range(len(s) + 1):
        for c in _ALPHA:
            cand = s[:pos] + c + s[pos:]
            if _strong_known(cand):
                found.add(cand)
                if len(found) > 1:
                    return None  # ambiguous -> do not guess
    return next(iter(found)) if found else None

def _pagekey(k):
    m = _DIGITS.search(str(k))
    return (int(m.group(1)) if m else 0, str(k))

def _lines(txt):
    """list of (line_idx, toks, first_low, last_low, head_hyphen_low)."""
    content = []
    for idx, ln in enumerate(txt.split("\n")):
        toks = WORD.findall(ln)
        if not toks:
            continue
        m = HEAD_HYPHEN.search(ln)
        content.append((idx, toks, toks[0].lower(), toks[-1].lower(),
                        (m.group(1).lower() if m else None)))
    return content

def _scan_file(path):
    counts = Counter()
    out = []   # (vol,page,tier,kind,margin_words,head,tail,joined,margin_text)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception:
        return (counts, out)
    vol = os.path.basename(os.path.dirname(os.path.dirname(path)))
    pages = []   # (pagekey, content) in reading order
    for pk in sorted(data.keys(), key=_pagekey):
        txt = (data[pk].get("consensus_text") or "")
        pages.append((pk, _lines(txt)))

    for pidx, (pk, content) in enumerate(pages):
        # ---- Class 1: line-break splits (hyphen / margin / blank-gap, lookahead) ----
        for ci in range(len(content)):
            idx, toks, first, last, head_h = content[ci]
            if head_h:
                head, hyph = head_h, True
            elif (not _known(last)) and len(last) >= 3:
                head, hyph = last, False
            else:
                continue
            for k in range(1, min(LOOKAHEAD + 1, len(content) - ci)):
                t_idx = content[ci + k][0]
                tail = content[ci + k][2]
                joined = head + tail
                if _known(joined) and not (_known(head) and _known(tail)):
                    separated = (t_idx != idx + 1)
                    tier = "HYPHEN" if hyph else "NOHYPHEN"
                    if separated:
                        mw = sum(len(content[ci + j][1]) for j in range(1, k))
                        kind = "margin" if mw > 0 else "blankgap"
                        mtext = " | ".join(" ".join(content[ci + j][1]) for j in range(1, k))
                        out.append((vol, pk, tier, kind, mw, head, tail, joined, mtext))
                        counts[(tier, kind)] += 1
                    elif tier == "NOHYPHEN":
                        # Pass A only rejoins HYPHEN -> emit NOHYPHEN adjacent ourselves
                        out.append((vol, pk, "NOHYPHEN", "adjacent", 0, head, tail, joined, ""))
                        counts[("NOHYPHEN", "adjacent")] += 1
                    else:
                        counts[("HYPHEN", "adjacent_passA")] += 1  # Pass A handles
                    break

        # ---- Class 2: same-line spurious-space splits, MULTI-FRAGMENT (2..MAXFRAG pieces) ----
        # Greedy: from token i, try the SHORTEST run (len 2..MAXFRAG) whose concatenation is a
        # real word, with not-all-pieces-already-known. Consume the whole run (i += L) so a token
        # is never both a tail and the next head (no overlap; handles 3+ -fragment words like
        # "ad min istration"). If the exact join fails but is one dropped char from a real word
        # ("philade phia" -> philadelphia), emit a FLAG-ONLY FUZZY_REVIEW (never auto-applied).
        for idx, toks, first, last, head_h in content:
            low = [t.lower() for t in toks]
            i = 0
            while i < len(low) - 1:
                emitted = False
                maxL = min(MAXFRAG, len(low) - i)
                # LONGEST-first (Hans C2-1): a 3-fragment word ("dep art ment"->department) must
                # win over the shorter sub-word ("dep"+"art"->depart) that would strand "ment".
                # The _strong_known guard means we only take a longer run if it IS a real word.
                def _valid_run(run):
                    if any(len(c) < 2 for c in run):
                        return False
                    if len("".join(run)) < 5:
                        return False
                    if all(_known(c) for c in run):
                        return False  # all real words -> never fuse
                    if any((not _known(c)) and len(c) < 3 for c in run):
                        return False  # an unknown piece too short -> noise
                    return True
                for L in range(maxL, 1, -1):
                    run = low[i:i + L]
                    if not _valid_run(run):
                        continue
                    joined = "".join(run)
                    if _strong_known(joined):
                        out.append((vol, pk, "SPACESPLIT", f"spacesplit{L}", 0, run[0], "".join(run[1:]), joined, ""))
                        counts[("SPACESPLIT", f"spacesplit{L}")] += 1
                        i += L; emitted = True; break
                if not emitted:
                    # fuzzy (flag-only): longest-first, ALL-fragment runs only (no real word inside)
                    for L in range(maxL, 1, -1):
                        run = low[i:i + L]
                        if not _valid_run(run) or any(_known(c) for c in run):
                            continue
                        fz = _insert1_known("".join(run))
                        if fz:
                            out.append((vol, pk, "FUZZY_REVIEW", f"fuzzy{L}", 0, run[0], "".join(run[1:]), fz, "".join(run)))
                            counts[("FUZZY_REVIEW", f"fuzzy{L}")] += 1
                            i += L; emitted = True; break
                if not emitted:
                    i += 1

    # ---- Class 3: cross-page splits (head end of page N, tail start of page N+1) ----
    for pidx in range(len(pages) - 1):
        pk, content = pages[pidx]
        if not content:
            continue
        idx, toks, first, last, head_h = content[-1]
        if head_h:
            head, hyph = head_h, True
        elif (not _known(last)) and len(last) >= 3:
            head, hyph = last, False
        else:
            continue
        # next non-empty page's first token
        for j in range(pidx + 1, min(pidx + 1 + LOOKAHEAD, len(pages))):
            npk, ncontent = pages[j]
            if ncontent:
                tail = ncontent[0][2]
                joined = head + tail
                if _known(joined) and not (_known(head) and _known(tail)):
                    tier = "HYPHEN" if hyph else "NOHYPHEN"
                    out.append((vol, pk, tier, "crosspage", 0, head, tail, joined, f"->{npk}"))
                    counts[(tier, "crosspage")] += 1
                break
    return (counts, out)

def main():
    rlog("START", "line-split reunification v2 (linebreak + spacesplit + crosspage + nohyphen)")
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
                rlog("SCAN", f"{done}/{len(files)} files | rows_so_far={len(allrows):,} | elapsed={now-t0:.0f}s", "HEARTBEAT")
                last = now

    with open(CORR_OUT, "w", encoding="utf-8") as f:
        f.write("vol\tpage\ttier\tkind\tmargin_words\thead\ttail\tjoined\tmargin_text\n")
        for r in sorted(allrows, key=lambda x: (x[0], _pagekey(x[1]))):
            f.write("\t".join(str(x) for x in r) + "\n")

    kindct = Counter(r[3] for r in allrows)
    rlog("SUMMARY", f"emitted corrections = {len(allrows):,}")
    for kind, c in kindct.most_common():
        rlog("SUMMARY", f"  kind={kind}: {c:,}")
    rlog("SUMMARY", f"HYPHEN adjacent deferred to PassA = {totals[('HYPHEN','adjacent_passA')]:,}")
    joined_ct = Counter(r[7] for r in allrows)
    print("\n[TOP 25 reunited words]")
    for w, c in joined_ct.most_common(25):
        print(f"   {w}: {c}")
    print("\n[SPACESPLIT sample (incl. multi-fragment)]")
    n = 0
    for r in allrows:
        if str(r[3]).startswith("spacesplit"):
            print(f"   [{r[3]}] {r[5]} + {r[6]} -> {r[7]}"); n += 1
        if n >= 20: break
    print("\n[FUZZY_REVIEW sample (flag-only: dropped-char-at-split, NOT auto-applied)]")
    n = 0
    for r in allrows:
        if str(r[3]).startswith("fuzzy"):
            print(f"   [{r[3]}] {r[5]} + {r[6]} = '{r[8]}'  ~=>  {r[7]}"); n += 1
        if n >= 20: break
    print("\n[CROSSPAGE sample]")
    n = 0
    for r in allrows:
        if r[3] == "crosspage":
            print(f"   {r[5]} | {r[6]} -> {r[7]}  (p{r[1]}{r[8]})"); n += 1
        if n >= 20: break
    sys.stdout.flush()
    rlog("DONE", f"corrections -> {CORR_OUT}  wall={time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
