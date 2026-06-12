"""
prep_runner.py -- Roll CPU preprocessing ahead of GPU workers.

Reads all pending volumes from the queue in chronological order,
skips any already prepped (production-LABEL/pages/ exists with PNGs),
and runs --stage prep N at a time until the full pending queue is done.

Usage: python prep_runner.py [--parallel N] [--ramp-delay S]
  --parallel N   max concurrent prep workers (default 16)
  --ramp-delay S seconds between successive worker starts (default 30)
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRATCH   = Path(r"C:\Users\patolex\PatoLex-scratch")
QUEUE     = SCRATCH / "production_queue_state.json"
ARCHIVE   = SCRATCH / "chief-clerk-archive"
OCR_SCRIPT = SCRATCH / "ocr_only_5090.py"
PYTHON    = SCRATCH / "ocr-engines" / "surya-venv" / "Scripts" / "python.exe"
LOG_DIR   = SCRATCH

PARALLEL    = 16
RAMP_DELAY  = 30  # seconds between successive worker starts
if "--parallel" in sys.argv:
    i = sys.argv.index("--parallel")
    if i + 1 < len(sys.argv):
        PARALLEL = int(sys.argv[i + 1])
if "--ramp-delay" in sys.argv:
    i = sys.argv.index("--ramp-delay")
    if i + 1 < len(sys.argv):
        RAMP_DELAY = int(sys.argv[i + 1])

def already_prepped(label):
    # Done: pages directory has meaningful PNGs
    pages_dir = SCRATCH / f"production-{label}" / "pages"
    if pages_dir.exists() and len(list(pages_dir.glob("*.png"))) > 10:
        return True
    # In-flight: individual schtask already launched a prep job for this label
    if (LOG_DIR / f"prep-{label}.log").exists():
        return True
    return False

def get_pending():
    state = json.loads(QUEUE.read_text(encoding="utf-8-sig"))
    vols = [v for v in state["volumes"] if v["status"] == "pending"]
    vols.sort(key=lambda v: (v["year"], v["label"]))
    return vols

def pdf_for(vol):
    if "pdf" in vol:
        return ARCHIVE / vol["pdf"]
    # fallback: derive from label
    stem = vol["label"].replace("-", "_").title().replace("Vol_", "Vol")
    return ARCHIVE / f"{stem}.pdf"

def main():
    pending = get_pending()
    to_prep = [(v["label"], pdf_for(v)) for v in pending
               if not already_prepped(v["label"])]

    print(f"prep_runner: {len(to_prep)} volumes to prep (parallel={PARALLEL})")
    for label, pdf in to_prep:
        print(f"  queued: {label} ({pdf.name})")

    running = []
    idx = 0

    while idx < len(to_prep) or running:
        # Reap finished
        still = []
        for label, proc in running:
            if proc.poll() is None:
                still.append((label, proc))
            else:
                code = proc.returncode
                status = "OK" if code == 0 else f"EXIT {code}"
                log_line = f"[{time.strftime('%H:%M:%S')}] prep {label}: {status}"
                print(log_line, flush=True)
                (LOG_DIR / "prep_runner.log").open("a").write(log_line + "\n")
        running = still

        # Fill slots
        while len(running) < PARALLEL and idx < len(to_prep):
            label, pdf = to_prep[idx]
            idx += 1
            if not pdf.exists():
                print(f"  SKIP {label}: PDF not found at {pdf}", flush=True)
                continue
            log_file = LOG_DIR / f"prep-runner-{label}.log"
            proc = subprocess.Popen(
                [str(PYTHON), str(OCR_SCRIPT), str(pdf), label, "--stage", "prep"],
                stdout=open(log_file, "w"),
                stderr=subprocess.STDOUT,
            )
            print(f"[{time.strftime('%H:%M:%S')}] START prep {label} (pid {proc.pid})", flush=True)
            running.append((label, proc))
            if len(running) < PARALLEL and idx < len(to_prep):
                time.sleep(RAMP_DELAY)

        if running:
            time.sleep(15)

    print("prep_runner: all done", flush=True)

if __name__ == "__main__":
    main()
