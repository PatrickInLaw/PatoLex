"""
run_worker_5080.py -- Memory-SAFE single-worker OCR driver for the 16 GB / RTX 5080 box.
=========================================================================================
This is the deliberate counterpart to prep_runner.py. prep_runner.py fans out to
--parallel 8 (default 16) concurrent full-volume render processes; on a 16 GB box each
process holds a 300-DPI page buffer plus float64 Sauvola integral images, and 8-16 of
them at once is the ~25 GB load that OOM-crashes this machine.

This driver instead processes volumes STRICTLY ONE AT A TIME:

  * Exactly one ocr_only_5080.py subprocess is alive at any moment. When it exits, the
    OS reclaims 100% of its memory before the next volume starts. Peak RAM is therefore
    bounded by a single worker (~1-2 GB transient), never N workers.
  * A hard RAM guard checks available physical memory BEFORE launching each volume and
    pauses (does not pile on) until enough is free, so it can never flood RAM.
  * ocr_only_5080.py itself already streams page-by-page to/from disk, so the per-volume
    footprint is bounded regardless of volume size.

It NEVER parallelizes. There is no --parallel knob on purpose.

Work source (in priority order):
  --worklist <file>   explicit "pdf_path|label" lines (one per volume); blank lines and
                      lines starting with # ignored. This is the safe, exact mode.
  (default)           scan the chief-clerk-archive for *.pdf, derive a label from the PDF
                      stem, and skip any volume whose OCR output already exists. Use
                      --dry-run first to review the plan before committing.

Usage:
  python run_worker_5080.py --dry-run
  python run_worker_5080.py --worklist work.txt
  python run_worker_5080.py --max-volumes 3 --min-ram-gb 3.5
  python run_worker_5080.py --year-min 1877 --year-max 1900

Flags:
  --dry-run           print the plan (what would run / what is skipped and why) and exit
  --worklist FILE     explicit pdf|label worklist instead of scanning the archive
  --max-volumes N     stop after N volumes this run (default: no limit)
  --min-ram-gb X      do not start a volume unless >= X GB physical RAM is free (default 3.0)
  --year-min Y        only volumes whose leading 4-digit year >= Y (archive-scan mode)
  --year-max Y        only volumes whose leading 4-digit year <= Y (archive-scan mode)
  --python PATH       python.exe to run the OCR worker (default: the surya venv, then this one)
"""

import argparse
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

import config

SCRATCH   = Path(config.path_for("data_root"))
ARCHIVE   = SCRATCH / "chief-clerk-archive"
OCR_SCRIPT = Path(__file__).resolve().parent / "ocr_only_5080.py"
RUN_LOG   = Path(r"C:\Users\PatrickKolasinski\Documents\GitHub\patolex"
                 r"\docs\80_PROJECT_HISTORY\run-logs\worker-5080-run.log")

# Interpreter for the OCR worker subprocess. On this 5080 box the system Python312 has the
# full stack (fitz/PyMuPDF + torch + doctr + surya + cv2 + pytesseract, CUDA enabled) while
# the local surya-venv is MISSING fitz -- so default to the interpreter running this driver
# (run the driver with the system python). Override with --python if needed.
DEFAULT_PYTHON = sys.executable


def log(msg, status="OK"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M PT")
    line = f"[{ts}] WORKER-5080 | {msg} | {status}"
    print(line, flush=True)
    try:
        RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(RUN_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def label_from_stem(stem: str) -> str:
    """Best-effort label for a PDF whose name has no explicit queue entry."""
    return stem.strip().replace(" ", "_")


def year_of(name: str) -> int:
    m = re.match(r"(\d{4})", Path(name).stem)
    return int(m.group(1)) if m else 9999


def ocr_done(label: str) -> bool:
    res = SCRATCH / f"production-{label}" / "ocr_consensus" / "page_ocr_results.json"
    return res.exists() and res.stat().st_size > 200


def year_already_covered(year: int) -> bool:
    """Loose guard: a completed production-<year>* output dir already exists.

    Historical labels are irregular (e.g. production-1877-78-code), so a stem-derived
    label will not always match. This catches the common case and is only used to WARN
    in the plan, not to hard-skip, so the operator can decide."""
    if year == 9999:
        return False
    for d in SCRATCH.glob(f"production-{year}*"):
        res = d / "ocr_consensus" / "page_ocr_results.json"
        if res.exists() and res.stat().st_size > 200:
            return True
    return False


def build_plan_from_archive(args):
    plan = []        # (pdf_path, label)
    skipped = []     # (name, reason)
    for pdf in sorted(ARCHIVE.glob("*.pdf")):
        y = year_of(pdf.name)
        if args.year_min and y < args.year_min:
            continue
        if args.year_max and y > args.year_max:
            continue
        label = label_from_stem(pdf.stem)
        if ocr_done(label):
            skipped.append((pdf.name, f"OCR output already exists for label '{label}'"))
            continue
        note = ""
        if year_already_covered(y):
            note = f"  (NOTE: a completed production-{y}* dir exists -- may be a duplicate under a different label)"
        plan.append((pdf, label, note))
    return plan, skipped


def build_plan_from_worklist(path: Path):
    plan, skipped = [], []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            skipped.append((line, "malformed (expected 'pdf|label')"))
            continue
        pdf_s, label = (p.strip() for p in line.split("|", 1))
        pdf = Path(pdf_s)
        if not pdf.is_absolute():
            pdf = ARCHIVE / pdf
        if not pdf.exists():
            skipped.append((line, f"PDF not found: {pdf}"))
            continue
        if ocr_done(label):
            skipped.append((line, f"OCR output already exists for label '{label}'"))
            continue
        plan.append((pdf, label, ""))
    return plan, skipped


def wait_for_ram(min_gb: float):
    """Block until at least min_gb GB of physical RAM is available."""
    waited = 0
    while True:
        avail = psutil.virtual_memory().available / (1024 ** 3)
        if avail >= min_gb:
            return avail
        if waited % 60 == 0:
            log(f"RAM guard: only {avail:.1f} GB free (< {min_gb} GB) -- waiting", "WARN")
        time.sleep(10)
        waited += 10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--worklist")
    ap.add_argument("--max-volumes", type=int, default=0)
    ap.add_argument("--min-ram-gb", type=float, default=3.0)
    ap.add_argument("--year-min", type=int, default=0)
    ap.add_argument("--year-max", type=int, default=0)
    ap.add_argument("--python", default=DEFAULT_PYTHON)
    args = ap.parse_args()

    if not OCR_SCRIPT.exists():
        log(f"OCR worker not found: {OCR_SCRIPT}", "FAIL")
        sys.exit(1)

    # Refuse to run if another OCR worker is already alive (single-worker invariant).
    others = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cl = " ".join(p.info["cmdline"] or [])
        except Exception:
            continue
        if ("ocr_only_5080.py" in cl or "ocr_only_sql.py" in cl) and p.info["pid"] != 0:
            others.append(p.info["pid"])
    if others:
        log(f"another OCR worker is already running (pids {others}) -- refusing to start a second", "FAIL")
        sys.exit(2)

    if args.worklist:
        plan, skipped = build_plan_from_worklist(Path(args.worklist))
    else:
        plan, skipped = build_plan_from_archive(args)

    log(f"plan: {len(plan)} volume(s) to OCR, {len(skipped)} skipped "
        f"(min_ram={args.min_ram_gb}GB python={Path(args.python).parent.parent.name})", "OK")
    for pdf, label, note in plan:
        print(f"  RUN  {label:32s} <- {pdf.name}{note}")
    if skipped:
        print(f"  ... {len(skipped)} skipped (first 10):")
        for name, reason in skipped[:10]:
            print(f"  SKIP {name}: {reason}")

    if args.dry_run:
        log("dry-run only -- nothing executed", "OK")
        return
    if not plan:
        log("nothing to do", "OK")
        return

    done = 0
    for pdf, label, _ in plan:
        if args.max_volumes and done >= args.max_volumes:
            log(f"reached --max-volumes {args.max_volumes} -- stopping", "OK")
            break
        avail = wait_for_ram(args.min_ram_gb)
        log(f"START {label} ({pdf.name}) | free RAM {avail:.1f} GB", "OK")
        t0 = time.time()
        rc = subprocess.call([args.python, str(OCR_SCRIPT), str(pdf), label])
        dt = time.time() - t0
        status = "OK" if rc == 0 else f"EXIT {rc}"
        log(f"DONE  {label} in {dt/60:.1f} min | rc={rc}", "OK" if rc == 0 else "FAIL")
        done += 1

    log(f"run complete: {done} volume(s) processed this session", "OK")


if __name__ == "__main__":
    main()
