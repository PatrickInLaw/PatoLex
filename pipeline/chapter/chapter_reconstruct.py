"""
chapter_reconstruct.py -- MEASURE-FIRST: recover OCR-garbled chapter numbers from
the SEQUENCE (chapter numbers are monotonic within a session), rather than trusting
the garbled OCR numeral.

Per volume: find chapter headings IN ORDER, get each numeral's OCR value + whether it
is a clean numeral. For each GARBLED heading, if it is bracketed by clean anchors whose
NUMERIC gap exactly matches the POSITIONAL gap (a consecutive run), its value is
UNIQUELY determined -> RECOVERED. Otherwise (run of garbles, restart boundary, no
anchor) -> AMBIGUOUS (leave for review). Reports how many of the garbled headings the
sequence confidently recovers, and how many of those the garbled OCR value had WRONG.

Self-contained: HEADER_RE / parse_chapter_number / clean-check copied verbatim from
ingest_from_ocr.py + ingest_clean.py (so the measurement matches the real parser).
Parallel per-volume, CPU, heartbeat. Output _vocab/chapter_reconstruct_sample.tsv.
"""
import os, sys, re, json, glob, time
from collections import Counter
from datetime import datetime, timezone, timedelta
import multiprocessing as mp
import config

SCRATCH = config.path_for("data_root")
OUT_DIR = config.path_for("vocab_dir")
LOG     = os.path.join(OUT_DIR, "chapter-reconstruct-run.log")
SAMPLE  = os.path.join(OUT_DIR, "chapter_reconstruct_sample.tsv")

# ---- copied verbatim from ingest_from_ocr.py ----
# cc019 (2026-07-24): _HDR_SEP era-variant fix applied here too -- this is a
# verbatim copy of the canonical HEADER_RE, so it carried the identical em-dash
# blindness ("CHAP.—XCI." in the 1876/78 volumes never matched). Keep in sync
# with ingest_from_ocr.py:_HDR_SEP.
_DASH = "—–‒‐‑\\-"
# Keep BYTE-IDENTICAL to ingest_from_ocr.py:_HDR_SEP -- see the measured
# rationale there. Short version: the comma is required (the 1860s-70s printed
# period was routinely OCR'd as a comma -- 116 genuine headings depend on it) but
# only before a ROMAN numeral, which blocks the 9 measured index-line false
# positives ("crabs, 874"), all of which carry Arabic numerals.
_HDR_SEP = r"[\s—–‒‐‑-]*(?:,[\s.]*(?=[IVXLCDMivxlcdm]))?[\s—–‒‐‑-]*"
HEADER_RE = re.compile(
    r"^[^A-Za-z0-9]*"
    r"(?:[Cc][HhUuNnRrAaOoEe][AaRrVvPpOo][PpVvRrTt]?[a-zA-Z]{0,3}\.?\s*"
    r"|[Cc][Hh][Aa][Pp][Tt][Ee][Rr]\s*)"
    r"\.?" + _HDR_SEP +
    r"([IVXLCDMivxlcdm0-9JjTtYyLl!|]{1,8})"
    r"\s*[.,;:]?"
    r"(?:\s*[" + _DASH + r"].*)?$",
    re.I,
)
_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_ROMAN_OCR_SUBST = {"J": "I", "T": "I", "1": "I", "!": "I", "|": "I"}
# A real act heading is followed shortly by an enactment marker -- this is
# parse_volume's core act-validation test, applied here to filter TOC entries,
# running page-heads, and stray "Chapter" mentions out of the heading sequence.
ENACT_MARKER_RE = re.compile(
    r"People\s+of\s+the\s+State\s+of\s+California"
    r"|do\s+enact\s+as\s+follow",
    re.I,
)
ENACT_LOOKAHEAD = 40   # lines after the heading to find the enact marker

def parse_chapter_number(tok):
    raw = tok.strip().strip(".,;:")
    if not raw:
        return 0
    if re.fullmatch(r"\d+(?:st|nd|rd|th|d)", raw, re.I):
        return 0
    raw = raw.replace("l", "I")
    t = raw.upper()
    if t.isdigit():
        try:
            return int(t)
        except ValueError:
            return 0
    sub = "".join(_ROMAN_OCR_SUBST.get(c, c) for c in t)
    sub = re.sub(r"(?<=I)L+$", lambda m: "I" * len(m.group(0)), sub)
    roman = "".join(c for c in sub if c in _ROMAN)
    if not roman:
        return 0
    val = prev = 0
    for c in reversed(roman):
        cur = _ROMAN[c]
        val += cur if cur >= prev else -cur
        prev = cur
    return val

# ---- copied verbatim from ingest_clean.py (the F11 clean-check) ----
_CLEAN_ARABIC = re.compile(r"^\d{1,4}$")
_CLEAN_ROMAN = re.compile(r"^[IVXLCDM]{1,12}$")
_ROMAN_VAL = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
def _roman_to_int(s):
    val = prev = 0
    for c in reversed(s):
        cur = _ROMAN_VAL.get(c, 0)
        val += cur if cur >= prev else -cur
        prev = cur
    return val
def is_clean(chapter_raw, chapter_int):
    raw = (chapter_raw or "").strip().strip(".,;:")
    if not raw:
        return False
    if _CLEAN_ARABIC.match(raw):
        return int(raw) == chapter_int
    if _CLEAN_ROMAN.match(raw):
        return _roman_to_int(raw) == chapter_int
    return False

def pt():
    z = timezone(timedelta(hours=-7))
    return datetime.now(timezone.utc).astimezone(z).strftime("%Y-%m-%d %H:%M PT")
def rlog(msg, status="OK"):
    line = f"[{pt()}] {msg} | {status}\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.rstrip()); sys.stdout.flush()

def _page_key(k):
    m = re.search(r"\d+", str(k))
    return int(m.group(0)) if m else 0

def _scan_file(path):
    counts = Counter()
    samples = []
    vol = os.path.basename(os.path.dirname(os.path.dirname(path)))
    try:
        data = json.load(open(path, encoding="utf-8", errors="replace"))
    except Exception:
        return (vol, counts, samples)
    # build the volume's lines in reading order, then find ACT headings (a heading
    # followed by an enactment marker within ENACT_LOOKAHEAD lines -- filters TOC /
    # running-heads / stray "Chapter" mentions, approximating parse_volume).
    all_lines = []
    for pk in sorted(data.keys(), key=_page_key):
        all_lines.extend((data[pk].get("consensus_text") or "").split("\n"))
    headings = []   # (raw, ocr_val, clean)
    for i, ln in enumerate(all_lines):
        m = HEADER_RE.match(ln)
        if not m:
            continue
        window = "\n".join(all_lines[i + 1:i + ENACT_LOOKAHEAD])
        if not ENACT_MARKER_RE.search(window):
            counts["headings_skipped_no_enact"] += 1
            continue
        raw = m.group(1)
        val = parse_chapter_number(raw)
        headings.append((raw, val, is_clean(raw, val)))
    n = len(headings)
    counts["headings"] += n
    cleans = [(i, headings[i][1]) for i in range(n) if headings[i][2] and headings[i][1] > 0]
    counts["clean"] += len(cleans)
    # for each garbled heading, can the sequence uniquely determine it?
    clean_idx = [c[0] for c in cleans]
    clean_val = {c[0]: c[1] for c in cleans}
    import bisect
    for i in range(n):
        raw, oval, clean = headings[i]
        if clean and oval > 0:
            continue
        counts["garbled"] += 1
        # nearest clean anchor before / after
        p = bisect.bisect_left(clean_idx, i)
        prev_i = clean_idx[p-1] if p > 0 else None
        next_i = clean_idx[p] if p < len(clean_idx) else None
        if prev_i is not None and next_i is not None:
            A, B = clean_val[prev_i], clean_val[next_i]
            if B > A and (B - A) == (next_i - prev_i):   # consecutive run -> unique
                inferred = A + (i - prev_i)
                counts["recovered"] += 1
                if inferred != oval:
                    counts["ocr_was_wrong"] += 1
                    if len(samples) < 50:
                        samples.append((vol, raw, oval, inferred, A, B))
            else:
                counts["ambiguous_gapmismatch"] += 1
        elif prev_i is not None or next_i is not None:
            counts["one_sided"] += 1
        else:
            counts["ambiguous_noanchor"] += 1
    return (vol, counts, samples)

def main():
    rlog("START chapter sequence-reconstruction (measure-first)")
    files = sorted(glob.glob(os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json")))
    rlog(f"{len(files)} consensus files")
    try:
        nw = max(2, min(12, (os.cpu_count() or 4) - 2))
    except Exception:
        nw = 8
    totals = Counter(); samples = []
    t0 = time.time(); last = time.time(); done = 0
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw) as pool:
        for vol, counts, samp in pool.imap_unordered(_scan_file, files, chunksize=1):
            totals.update(counts)
            if len(samples) < 50:
                samples.extend(samp[:50 - len(samples)])
            done += 1
            now = time.time()
            if now - last >= 15 or done == len(files):
                rlog(f"{done}/{len(files)} vols | headings={totals['headings']:,} | elapsed={now-t0:.0f}s", "HEARTBEAT")
                last = now

    with open(SAMPLE, "w", encoding="utf-8") as f:
        f.write("vol\traw\tocr_value\treconstructed\tanchor_before\tanchor_after\n")
        for r in samples:
            f.write("\t".join(str(x) for x in r) + "\n")

    g = totals["garbled"]
    rlog("==== RESULT ====")
    rlog(f"chapter headings total = {totals['headings']:,}")
    rlog(f"clean (trusted as-is)  = {totals['clean']:,}")
    rlog(f"garbled                = {g:,}")
    if g:
        rlog(f"  -> RECOVERED by sequence (unique) = {totals['recovered']:,} ({100.0*totals['recovered']/g:.1f}% of garbled)")
        rlog(f"       of which OCR value was WRONG  = {totals['ocr_was_wrong']:,} (reconstruction fixes these)")
        rlog(f"  -> one-sided (inferable, unverified) = {totals['one_sided']:,}")
        rlog(f"  -> ambiguous gap-mismatch (restart/missing) = {totals['ambiguous_gapmismatch']:,}")
        rlog(f"  -> ambiguous no-anchor = {totals['ambiguous_noanchor']:,}")
    rlog(f"DONE sample -> {SAMPLE}  wall={time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
