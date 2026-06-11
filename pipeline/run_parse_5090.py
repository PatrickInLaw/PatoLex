"""
run_parse_5090.py -- drive parse_volume() over the AUTHORITATIVE corpus on the 5090.

Mirrors run_parse_all.py but for the 5090 layout: imports parse_volume from
ingest_from_ocr (placed alongside in C:/Users/patolex/PatoLex-scratch) and
monkeypatches its three write-paths (SCRATCH_ROOT, DATE_REVIEW_WORKLIST, LOG_FILE)
to 5090 locations. Parse-only -- writes parsed_acts_fixed.json per volume, NO DB.
Heartbeat run log. Sequential (parse_volume is not parallel); 64 GB RAM, no guard needed.
"""
import sys, os, re, time, json
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(r"C:\Users\patolex\PatoLex-scratch")
sys.path.insert(0, str(ROOT))
LOG = ROOT / "_vocab" / "parse-all-5090.log"

def rlog(msg, status="OK"):
    z = timezone(timedelta(hours=-7))
    line = f"[{datetime.now(timezone.utc).astimezone(z):%Y-%m-%d %H:%M PT}] PARSE | {msg} | {status}\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.rstrip(), flush=True)

import ingest_from_ocr as iom
# --- redirect the parser's write-paths to the 5090 ---
iom.SCRATCH_ROOT = ROOT
iom.DATE_REVIEW_WORKLIST = ROOT / "_vocab" / "date-review-worklist.jsonl"
iom.LOG_FILE = ROOT / "_vocab" / "parse-stage-5090.log"

SKIP_LABELS = {
    "1873-74-code", "1875-76-code", "1877-78-code", "1880-code",
    "1965-vol1-64chapters", "1971-vol3-chapters",
    "1987-vol4-chapters", "1988-vol4-chapters",
    "smoke-1996-vol2", "smoke-real-1997-vol1", "smoke-real-1998-vol1",
}

def collect_labels():
    labels = []
    for d in sorted(ROOT.glob("production-*")):
        if not d.is_dir():
            continue
        label = d.name[len("production-"):]
        if label in SKIP_LABELS:
            continue
        m = re.match(r'^(\d{4})', label)
        if not m:
            continue
        yr = int(m.group(1))
        if yr < 1850 or yr > 1999:
            continue
        if not (d / "ocr_consensus" / "page_ocr_results.json").exists():
            continue
        labels.append(label)
    return labels

def main():
    rlog(f"START parse-5090  SCRATCH={ROOT}")
    labels = collect_labels()
    rlog(f"{len(labels)} in-scope volumes (1850-1999, has OCR, not skip)")
    ok = []; fail = []; tot_conf = tot_flag = 0
    t0 = time.time(); last = time.time()
    for i, label in enumerate(labels):
        try:
            r = iom.parse_volume(label)
            if r is None:
                fail.append((label, "returned None")); rlog(f"{label}: parse_volume None", "FAIL")
            else:
                c = len(r["confident"]); fl = len(r["flagged"])
                tot_conf += c; tot_flag += fl; ok.append(label)
        except Exception as e:
            fail.append((label, str(e)[:160])); rlog(f"{label}: EXC {str(e)[:160]}", "FAIL")
        now = time.time()
        if now - last >= 15 or i + 1 == len(labels):
            rlog(f"{i+1}/{len(labels)} vols | ok={len(ok)} fail={len(fail)} | "
                 f"confident={tot_conf:,} flagged={tot_flag:,} | elapsed={now-t0:.0f}s", "HEARTBEAT")
            last = now
    rlog(f"DONE ok={len(ok)} fail={len(fail)} | total_confident={tot_conf:,} "
         f"total_flagged={tot_flag:,} | wall={time.time()-t0:.0f}s")
    if fail:
        rlog(f"FAILED: {[l for l,_ in fail][:30]}", "WARN")

if __name__ == "__main__":
    main()
