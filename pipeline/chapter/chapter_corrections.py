"""
chapter_corrections.py -- emit the chapter-number CORRECTIONS overlay from the
parsed-act sequence (real parse_volume output, parsed_acts_fixed.json).

Chapter numbers are monotonic within a session, so a garbled numeral can be
recovered from its position between correctly-read neighbours. Three tiers:

  AUTO      bracket-verified: garbled act sits between two clean anchors whose
            numeric gap == positional gap (a consecutive run) -> value is unique.
  INFERRED  forward/backward-fill from a single nearby anchor (very likely, but
            not double-checked) -> applied but marked inferred.
  REVIEW    runs of garbles that collide, restart boundaries, or no anchor ->
            cannot determine; flagged for a human.

Output: _vocab/chapter_corrections.tsv (the reversible overlay; original chapter_raw
preserved). Self-contained is_clean (copied from ingest_clean). Parallel per-volume.
"""
import os, sys, re, json, glob, time, bisect
from collections import Counter
from datetime import datetime, timezone, timedelta
import multiprocessing as mp
import config

SCRATCH = config.path_for("data_root")
OUT_DIR = config.path_for("vocab_dir")
LOG     = os.path.join(OUT_DIR, "chapter-corrections-run.log")
OUT     = os.path.join(OUT_DIR, "chapter_corrections.tsv")

# ---- is_clean copied verbatim from ingest_clean.py (F11 clean-check) ----
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
def _modern_digitfix(raw, fillv):
    """SAFE modern Arabic digit-error fix: the OCR numeral is all-digits and too long
    (>4 = impossible chapter), AND removing exactly one digit yields the sequence fill.
    Two independent signals (digit-corrected OCR + sequence position) agree -> trustworthy."""
    raw = (raw or "").strip()
    if not raw.isdigit() or len(raw) <= 4:
        return False
    if not (1 <= fillv <= 9999):
        return False
    for k in range(len(raw)):
        d = raw[:k] + raw[k + 1:]
        if d and d.isdigit() and int(d) == fillv:
            return True
    return False

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
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{pt()}] {msg} | {status}\n")
    print(msg, flush=True)

def _process_vol(path):
    counts = Counter()
    rows = []   # (vol, in_act_order, chapter_raw, ocr, corrected, tier, reason)
    vol = os.path.basename(os.path.dirname(path))
    try:
        data = json.load(open(path, encoding="utf-8", errors="replace"))
    except Exception:
        return (counts, rows)
    acts = list(data.get("confident_acts", [])) + list(data.get("flagged_acts", []))
    if not acts:
        return (counts, rows)
    acts.sort(key=lambda a: a.get("in_act_order", 0))
    n = len(acts)
    vals = [int(a.get("chapter_int", 0) or 0) for a in acts]
    raws = [str(a.get("chapter_raw", "")) for a in acts]
    clean = [is_clean(raws[i], vals[i]) and vals[i] > 0 for i in range(n)]
    anchors = [i for i in range(n) if clean[i]]
    counts["acts"] += n
    counts["clean"] += len(anchors)

    for i in range(n):
        if clean[i]:
            continue
        counts["garbled"] += 1
        p = bisect.bisect_left(anchors, i)
        pi = anchors[p-1] if p > 0 else None
        ni = anchors[p] if p < len(anchors) else None
        # TIER LOGIC (safety-first):
        #   AUTO      bracket-verified consecutive span -> the position UNIQUELY fixes
        #             the value; override the OCR value (a verified fix).
        #   CONFIRMED a forward/backward fill that AGREES with the OCR-recovered value
        #             -> the numeral is consistent with the sequence; trust it, no change.
        #   REVIEW    everything else -- a fill that DISAGREES with OCR is genuinely
        #             ambiguous (parse gap vs OCR garble) and must NOT silently override
        #             a possibly-correct citation; also restarts/collisions/no-anchor.
        #   OCR_PLAUSIBLE  fill disagrees, BUT the OCR-recovered numeral sits
        #                  monotonically between the clean neighbours -> the printed
        #                  numeral is readable+plausible; the disagreement was a parse
        #                  gap. Accept the OCR value (no change, just un-flagged).
        ocr = vals[i]
        corrected = None; tier = "REVIEW"; reason = "no_anchor"
        if pi is not None and ni is not None:
            a, b = vals[pi], vals[ni]
            if b > a and (b - a) == (ni - pi):
                corrected, tier, reason = a + (i - pi), "AUTO", f"bracket({a}<{b})"
            elif b <= a:
                tier, reason = "REVIEW", f"restart_or_decrease({a}->{b})"
            else:
                cand = a + (i - pi)
                if cand == ocr and cand < b:
                    corrected, tier, reason = cand, "CONFIRMED", f"fill_agrees({a})"
                elif a < ocr < b:
                    corrected, tier, reason = ocr, "OCR_PLAUSIBLE", f"ocr_fits({a}<{ocr}<{b})"
                else:
                    tier, reason = "REVIEW", f"fill_disagrees(ocr={ocr},fill={cand})"
        elif pi is not None:
            cand = vals[pi] + (i - pi)
            if cand == ocr:
                corrected, tier, reason = cand, "CONFIRMED", f"fill_agrees({vals[pi]})"
            elif ocr > vals[pi]:
                corrected, tier, reason = ocr, "OCR_PLAUSIBLE", f"ocr_after({vals[pi]}<{ocr})"
            else:
                tier, reason = "REVIEW", f"fill_disagrees(ocr={ocr},fill={cand})"
        elif ni is not None:
            cand = vals[ni] - (ni - i)
            if cand > 0 and cand == ocr:
                corrected, tier, reason = cand, "CONFIRMED", f"fill_agrees({vals[ni]})"
            elif 0 < ocr < vals[ni]:
                corrected, tier, reason = ocr, "OCR_PLAUSIBLE", f"ocr_before({ocr}<{vals[ni]})"
            else:
                tier, reason = "REVIEW", f"fill_disagrees(ocr={ocr},fill={cand})"
        # SAFE modern digit-error rescue: a REVIEW where the OCR is digits and a
        # single-digit removal equals the sequence fill -> two signals agree, accept it.
        if tier == "REVIEW" and reason.startswith("fill_disagrees"):
            mfill = re.search(r"fill=(\d+)", reason)
            if mfill and _modern_digitfix(raws[i], int(mfill.group(1))):
                corrected, tier, reason = int(mfill.group(1)), "MODERN_DIGITFIX", f"digit_corr_agrees({mfill.group(1)})"
        counts[tier] += 1
        if tier in ("AUTO", "MODERN_DIGITFIX") and corrected != ocr:
            counts["value_changed"] += 1
        rows.append((vol, acts[i].get("in_act_order", 0), raws[i], vals[i],
                     ("" if corrected is None else corrected), tier, reason))
    return (counts, rows)

def main():
    rlog("START chapter_corrections (3-tier, from parsed_acts_fixed.json)")
    files = sorted(glob.glob(os.path.join(SCRATCH, "production-*", "parsed_acts_fixed.json")))
    rlog(f"{len(files)} parsed volumes")
    try:
        nw = max(2, min(12, (os.cpu_count() or 4) - 2))
    except Exception:
        nw = 8
    totals = Counter(); allrows = []
    t0 = time.time(); last = time.time(); done = 0
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw) as pool:
        for counts, rows in pool.imap_unordered(_process_vol, files, chunksize=1):
            totals.update(counts); allrows.extend(rows)
            done += 1
            now = time.time()
            if now - last >= 15 or done == len(files):
                rlog(f"{done}/{len(files)} vols | acts={totals['acts']:,} garbled={totals['garbled']:,} | elapsed={now-t0:.0f}s", "HEARTBEAT")
                last = now

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("vol\tin_act_order\tchapter_raw\tocr_chapter\tcorrected_chapter\ttier\treason\n")
        for r in sorted(allrows, key=lambda x: (x[0], x[1])):
            f.write("\t".join(str(x) for x in r) + "\n")

    g = totals["garbled"]
    rlog("==== RESULT ====")
    rlog(f"acts total = {totals['acts']:,}  clean = {totals['clean']:,}  garbled = {g:,}")
    if g:
        rlog(f"  AUTO (bracket-verified -> fix/confirm) = {totals['AUTO']:,} ({100.0*totals['AUTO']/g:.1f}%)")
        rlog(f"     of which the chapter number was actually CHANGED (fixed) = {totals['value_changed']:,}")
        rlog(f"  CONFIRMED (fill agrees with OCR, no change) = {totals['CONFIRMED']:,} ({100.0*totals['CONFIRMED']/g:.1f}%)")
        rlog(f"  OCR_PLAUSIBLE (OCR value fits between clean neighbours -> accept) = {totals['OCR_PLAUSIBLE']:,} ({100.0*totals['OCR_PLAUSIBLE']/g:.1f}%)")
        rlog(f"  MODERN_DIGITFIX (digit-corrected OCR agrees with fill -> safe fix) = {totals['MODERN_DIGITFIX']:,} ({100.0*totals['MODERN_DIGITFIX']/g:.1f}%)")
        rlog(f"  REVIEW (irreducible: OCR implausible / restart / no-anchor) = {totals['REVIEW']:,} ({100.0*totals['REVIEW']/g:.1f}%)")
    rlog(f"DONE corrections -> {OUT}  wall={time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
