"""
ocr_batch_5090.py -- sequential OCR-only driver for the RTX 5090.
==================================================================
Runs ocr_only_5090.py on a list of session labels, one volume per child
process (so each volume gets a fresh CUDA context -- no cross-volume memory
carryover). Resumable: ocr_only_5090.py itself skips rendered/preprocessed
pages and resumes OCR from the checkpointed page_ocr_results.json, so a killed
run continues where it left off.

Usage:
    python ocr_batch_5090.py 1863 1865-66 1867-68 ...
"""
import sys, subprocess, datetime
from pathlib import Path

import config

SCRATCH = Path(config.path_for("data_root"))
PY      = r"C:\Users\patolex\PatoLex-scratch\ocr-engines\surya-venv\Scripts\python.exe"
SCRIPT  = SCRATCH / "ocr_only_5090.py"
ARCHIVE = SCRATCH / "chief-clerk-archive"
LOG     = SCRATCH / "ocr-5090-run.log"

def log(msg, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    line = f"[{ts}] [BATCH5090] {msg} | {status}\n"
    with open(str(LOG), "a", encoding="utf-8") as f:
        f.write(line)
    print(line.strip(), flush=True)

vols = [a.strip() for a in sys.argv[1:]]
log(f"=== OCR batch starting: {vols} ===")
for v in vols:
    pdf = ARCHIVE / f"{v}_Statutes.pdf"
    if not pdf.exists():
        log(f"{v}: PDF missing {pdf}", "FAIL")
        continue
    log(f"{v}: starting OCR ({pdf.name})")
    r = subprocess.run([PY, str(SCRIPT), str(pdf), v])
    if r.returncode == 0:
        log(f"{v}: OCR exit 0")
    else:
        log(f"{v}: OCR exit {r.returncode}", "FAIL")
log("=== OCR batch done ===")
