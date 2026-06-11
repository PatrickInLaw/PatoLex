"""
line_split_finder.py -- MEASURE-FIRST analyzer for words split across line breaks,
including the case where a margin/gutter note (or a blank line) sits between the two
halves (Patrick's marginalia insight).

consensus_text preserves one newline per physical scan-line, so:
  right edge = last token of a line (esp. a hyphen-terminated head, "estab-")
  left  edge = first token of a later line (a suffix tail, "lish")
A pair is a real split iff head+tail is a known word (and not both already words).

For each pair we record:
  - tier: HYPHEN (line ends with "<letters>-") vs NOHYPHEN (non-word line-end)
  - separated: was the tail line NOT the immediately-next raw line? (i.e. a blank line
    or margin line in between -> CURRENT Pass-A LBH MISSES these)
  - margin_words: words on content lines strictly between the two halves (the note)

Output: line_splits_sample.tsv (examples) + summary counts. Parallel per-file, CPU,
heartbeat run log. is_known uses the SAME union dict as correction_passes (incl gazetteer).
"""
import os, sys, re, json, glob, time
from collections import Counter
from datetime import datetime, timezone, timedelta
import multiprocessing as mp

os.environ["CUDA_VISIBLE_DEVICES"] = ""
SCRATCH  = r"C:\Users\patolex\PatoLex-scratch"
OUT_DIR  = r"C:\Users\patolex\PatoLex-scratch\_vocab"
LOG_PATH = os.path.join(OUT_DIR, "line-split-run.log")
SAMPLE_OUT = os.path.join(OUT_DIR, "line_splits_sample.tsv")
LOOKAHEAD = 3   # content lines to look ahead for the continuation

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
    """Return (counts dict, sample list[ (tier,separated,margin_words,head,tail,joined,margin_text) ])."""
    counts = Counter()
    sample = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception:
        return (counts, sample)
    vol = os.path.basename(os.path.dirname(os.path.dirname(path)))
    for pk, po in data.items():
        txt = (po.get("consensus_text") or "")
        if "\n" not in txt:
            continue
        raw = txt.split("\n")
        # content lines: (raw_idx, tokens, first, last, head_hyphen)
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
                t_idx, t_toks, tail, t_last, _ = content[ci + k]
                joined = head + tail
                if _known(joined) and not (_known(head) and _known(tail)):
                    separated = (t_idx != idx + 1)   # blank/margin line between -> current LBH misses
                    margin_words = sum(len(content[ci + j][1]) for j in range(1, k))
                    tier = "HYPHEN" if hyph else "NOHYPHEN"
                    counts[(tier, "sep" if separated else "adj")] += 1
                    if separated and margin_words > 0:
                        counts[(tier, "sep_margin")] += 1   # true interleaving: CONTENT between halves
                    counts[("ALL", "joined_occ")] += 1
                    if len(sample) < 60:
                        margin_text = " | ".join(" ".join(content[ci + j][1]) for j in range(1, k))
                        sample.append((tier, "sep" if separated else "adj", margin_words,
                                       head, tail, joined, margin_text, vol, pk))
                    break
    return (counts, sample)

def main():
    rlog("START", "line-split finder (measure-first)")
    _init_main_note = None
    files = sorted(glob.glob(os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json")))
    rlog("SCAN", f"{len(files)} consensus files; lookahead={LOOKAHEAD} content lines")
    try:
        nw = max(2, min(12, (os.cpu_count() or 4) - 2))
    except Exception:
        nw = 8

    totals = Counter()
    samples = []
    t0 = time.time(); last = time.time(); done = 0
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw, initializer=_init) as pool:
        for counts, sample in pool.imap_unordered(_scan_file, files, chunksize=1):
            totals.update(counts)
            if len(samples) < 60:
                samples.extend(sample[:60 - len(samples)])
            done += 1
            now = time.time()
            if now - last >= 15 or done == len(files):
                rlog("SCAN", f"{done}/{len(files)} files | pairs={totals[('ALL','joined_occ')]:,} | elapsed={now-t0:.0f}s", "HEARTBEAT")
                last = now

    with open(SAMPLE_OUT, "w", encoding="utf-8") as f:
        f.write("tier\tadj_or_sep\tmargin_words\thead\ttail\tjoined\tmargin_text\tvol\tpage\n")
        for row in samples:
            f.write("\t".join(str(x) for x in row) + "\n")

    h_adj = totals[("HYPHEN","adj")]; h_sep = totals[("HYPHEN","sep")]
    n_adj = totals[("NOHYPHEN","adj")]; n_sep = totals[("NOHYPHEN","sep")]
    tot = h_adj + h_sep + n_adj + n_sep
    rlog("SUMMARY", f"TOTAL line-split pairs={tot:,}")
    h_sepm = totals[("HYPHEN","sep_margin")]; n_sepm = totals[("NOHYPHEN","sep_margin")]
    rlog("SUMMARY", f"HYPHEN:   adjacent={h_adj:,} (current LBH catches)  separated={h_sep:,} (MISSED; of which {h_sepm:,} have MARGIN CONTENT between, {h_sep-h_sepm:,} are just blank-line gaps)")
    rlog("SUMMARY", f"NOHYPHEN: adjacent={n_adj:,}  separated={n_sep:,} (of which {n_sepm:,} margin-content)  (looser; non-word line-end joins)")
    rlog("DONE", f"sample -> {SAMPLE_OUT}  wall={time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
