"""
line_split_reunify.py -- REUNIFICATION pass: produce the corrections artifact for
words split across line breaks that the current Pass-A LBH MISSES (blank line or
margin note between the two halves).

For each missed split it emits a correction record (head + tail -> joined) for the
reversible corrections layer, and aggregates which fragment tokens get cleared from
the residual/review tier (e.g. trict, sioner, poration as tails).

Adjacent splits (217k) are already handled by Pass A's LBH -> only counted, not emitted.

Output:
  _vocab/line_split_corrections.tsv   (all missed reunifications, w/ provenance)
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
LOOKAHEAD = 3

WORD = re.compile(r"[A-Za-z\xc0-\xff]+")
HEAD_HYPHEN = re.compile(r"([A-Za-z\xc0-\xff]{2,})-[ \t]*$")

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

_WS = None; _HASWF = False; _WF = None
def _init():
    global _WS, _HASWF, _WF
    from correction_passes import build_dictionary
    ws, _spell, has_wf, wf = build_dictionary()
    _WS = frozenset(ws); _HASWF = has_wf; _WF = wf

def _known(tok):
    if tok in _WS:
        return True
    if _HASWF and _WF(tok, "en") > 0:
        return True
    return False

def _scan_file(path):
    counts = Counter()
    missed = []   # (vol,page,tier,kind,margin_words,head,tail,joined,margin_text)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception:
        return (counts, missed)
    vol = os.path.basename(os.path.dirname(os.path.dirname(path)))
    for pk, po in data.items():
        txt = (po.get("consensus_text") or "")
        if "\n" not in txt:
            continue
        raw = txt.split("\n")
        content = []
        for idx, ln in enumerate(raw):
            toks = WORD.findall(ln)
            if not toks:
                continue
            m = HEAD_HYPHEN.search(ln)
            content.append((idx, toks, toks[0].lower(), toks[-1].lower(),
                            (m.group(1).lower() if m else None)))
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
                        margin_words = sum(len(content[ci + j][1]) for j in range(1, k))
                        kind = "margin" if margin_words > 0 else "blankgap"
                        counts[(tier, "missed")] += 1
                        margin_text = " | ".join(" ".join(content[ci + j][1]) for j in range(1, k))
                        missed.append((vol, pk, tier, kind, margin_words, head, tail, joined, margin_text))
                    else:
                        counts[(tier, "adjacent")] += 1  # Pass A already handles
                    break
    return (counts, missed)

def main():
    rlog("START", "line-split reunification (emit corrections for MISSED splits)")
    files = sorted(glob.glob(os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json")))
    rlog("SCAN", f"{len(files)} consensus files")
    try:
        nw = max(2, min(12, (os.cpu_count() or 4) - 2))
    except Exception:
        nw = 8
    totals = Counter(); all_missed = []
    t0 = time.time(); last = time.time(); done = 0
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw, initializer=_init) as pool:
        for counts, missed in pool.imap_unordered(_scan_file, files, chunksize=1):
            totals.update(counts); all_missed.extend(missed)
            done += 1
            now = time.time()
            if now - last >= 15 or done == len(files):
                rlog("SCAN", f"{done}/{len(files)} files | missed_so_far={len(all_missed):,} | elapsed={now-t0:.0f}s", "HEARTBEAT")
                last = now

    # write corrections artifact
    with open(CORR_OUT, "w", encoding="utf-8") as f:
        f.write("vol\tpage\ttier\tkind\tmargin_words\thead\ttail\tjoined\tmargin_text\n")
        for r in sorted(all_missed, key=lambda x: (x[0], x[1])):
            f.write("\t".join(str(x) for x in r) + "\n")

    # aggregates
    joined_ct = Counter(r[7] for r in all_missed)
    head_ct = Counter(r[5] for r in all_missed)
    tail_ct = Counter(r[6] for r in all_missed)
    margin_n = sum(1 for r in all_missed if r[3] == "margin")
    rlog("SUMMARY", f"missed reunifications emitted={len(all_missed):,}  (margin={margin_n:,}, blankgap={len(all_missed)-margin_n:,})")
    rlog("SUMMARY", f"already-handled-by-PassA adjacent: HYPHEN={totals[('HYPHEN','adjacent')]:,} NOHYPHEN={totals[('NOHYPHEN','adjacent')]:,}")
    rlog("SUMMARY", f"distinct joined words={len(joined_ct):,}  distinct head-frags={len(head_ct):,}  distinct tail-frags={len(tail_ct):,}")
    print("\n[TOP 20 reunited words]")
    for w, c in joined_ct.most_common(20):
        print(f"   {w}: {c}")
    print("\n[TOP 20 tail fragments cleared from residual]")
    for w, c in tail_ct.most_common(20):
        print(f"   -{w}: {c}")
    print("\n[TOP 20 head fragments cleared from residual]")
    for w, c in head_ct.most_common(20):
        print(f"   {w}-: {c}")
    sys.stdout.flush()
    rlog("DONE", f"corrections -> {CORR_OUT}  wall={time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
