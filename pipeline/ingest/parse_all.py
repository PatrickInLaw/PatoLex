"""
parse_all.py -- PARALLEL parse driver (replaces the sequential run_parse_5090.py / run_parse_all.py and
their path monkeypatching). Parsing is per-volume-independent and CPU-bound, so this fans out over a
ProcessPoolExecutor. Config-driven paths (pipeline/config.py -> the 3060 cutover knob), heartbeat run log,
and it aggregates the per-volume parsed_acts into config.PARSE_OUTPUT_DIR for GIT-VERSIONED diffing.

Run from the pipeline/ root:
    python -m ingest.parse_all                 # all in-scope OCR'd volumes (1850-1999)
    python -m ingest.parse_all 1862 1863        # specific labels
Set PATOLEX_DATA_ROOT to point at a relocated source (e.g. the 3060 share) -- nothing else changes.
"""
import os, sys, re, time, glob, shutil
from concurrent.futures import ProcessPoolExecutor, as_completed

import config
from ingest import ingest_from_ocr as iom   # parse_volume + its (now config-driven) paths

# Non-corpus / code / smoke labels excluded from the 1850-1999 OCR parse (from the prior driver).
SKIP_LABELS = {
    "1873-74-code", "1875-76-code", "1877-78-code", "1880-code",
    "1965-vol1-64chapters", "1971-vol3-chapters",
    "1987-vol4-chapters", "1988-vol4-chapters",
    "smoke-1996-vol2", "smoke-real-1997-vol1", "smoke-real-1998-vol1",
}

def _rlog(msg, status="OK"):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] PARSE-ALL | {msg} | {status}\n"
    os.makedirs(os.path.dirname(config.PARSE_LOG), exist_ok=True)
    with open(config.PARSE_LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.rstrip(), flush=True)

def collect_labels():
    out = []
    for d in sorted(glob.glob(os.path.join(config.DATA_ROOT, "production-*"))):
        if not os.path.isdir(d):
            continue
        label = os.path.basename(d)[len("production-"):]
        if label in SKIP_LABELS:
            continue
        m = re.match(r"^(\d{4})", label)
        if not m:
            continue
        if not (1850 <= int(m.group(1)) <= 1999):
            continue
        if not os.path.exists(os.path.join(d, "ocr_consensus", "page_ocr_results.json")):
            continue
        out.append(label)
    return out

def _parse_one(label):
    """Worker: parse one volume. parse_volume writes its parsed_acts_fixed.json + returns counts."""
    try:
        r = iom.parse_volume(label)
        if r is None:
            return (label, "FAIL:None", 0, 0)
        return (label, "OK", len(r["confident"]), len(r["flagged"]))
    except Exception as e:
        return (label, "EXC:" + str(e)[:140], 0, 0)

def main():
    config.ensure_dirs()
    labels = sys.argv[1:] or collect_labels()
    nw = max(2, min(16, (os.cpu_count() or 4) - 2))
    _rlog(f"START parallel parse: {len(labels)} volumes, {nw} workers, DATA_ROOT={config.DATA_ROOT}")
    t0 = time.time(); last = t0; done = 0; ok = []; fail = []; tot_c = tot_f = 0
    ctx = __import__("multiprocessing").get_context("spawn")
    with ProcessPoolExecutor(max_workers=nw, mp_context=ctx) as ex:
        futs = {ex.submit(_parse_one, lb): lb for lb in labels}
        for fut in as_completed(futs):
            label, status, c, f = fut.result()
            done += 1
            if status == "OK":
                ok.append(label); tot_c += c; tot_f += f
            else:
                fail.append((label, status)); _rlog(f"{label}: {status}", "FAIL")
            now = time.time()
            if now - last >= 15 or done == len(labels):
                _rlog(f"{done}/{len(labels)} | ok={len(ok)} fail={len(fail)} | confident={tot_c:,} flagged={tot_f:,} | {now-t0:.0f}s", "HEARTBEAT")
                last = now
    # aggregate the per-volume outputs into PARSE_OUTPUT_DIR for git-versioned diffing
    copied = 0
    for label in ok:
        src = os.path.join(config.production_dir(label), "parsed_acts_fixed.json")
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(config.PARSE_OUTPUT_DIR, f"parsed_acts_{label}.json")); copied += 1
    _rlog(f"DONE ok={len(ok)} fail={len(fail)} | confident={tot_c:,} flagged={tot_f:,} | "
          f"aggregated {copied} -> {config.PARSE_OUTPUT_DIR} | wall={time.time()-t0:.0f}s")
    if fail:
        _rlog(f"FAILED: {[l for l, _ in fail][:30]}", "WARN")

if __name__ == "__main__":
    main()
