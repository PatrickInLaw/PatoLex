"""
queue_worker_5080.py -- shared-forward-queue OCR worker for the RTX 5080.
=========================================================================
The 5080 is a GENUINE SECOND OCR producer that shares the SAME forward queue
as the 5090's three workers. It never double-works a volume because every
claim is taken via the 5090's queue_claim.py under the SAME exclusive lock
file the 5090 workers use (claims are serialized across both boxes).

Per claimed volume:
  1. SSH the 5090 -> queue_claim.py claim <worker_id>  (atomic, lowest-year
     pending/reclaimable; forward/chronological -- never a volume the 5090 has
     in_progress/done).
  2. OCR the volume LOCALLY with ocr_only_5080.py (pinned + offline docTR, the
     proven 5080 load fix; per-page GPU hygiene). Reads the PDF from the local
     chief-clerk-archive. Resumable.
  3. While OCR runs, SSH a heartbeat to the 5090 every HEARTBEAT_SECONDS so the
     claim is not reclaimed as stale.
  4. On exit 0: scp the three OCR outputs UP to the 5090's production-<label>/
     tree (sha256.txt, page_classification.json,
     ocr_consensus/page_ocr_results.json), then SSH queue_claim.py done -- which
     writes OCR_COMPLETE.marker on the 5090. The existing ingest_watcher.py loop
     (running on this 5080 box, polling the 5090) then ingests it unchanged.
     On non-zero exit: SSH queue_claim.py fail (reclaimable).
  5. Loop until the queue is drained, then exit.

Graceful stop: the 08:00 backoff task creates STOP_FLAG. We only check it
BETWEEN volumes -- a volume in flight always finishes (no partial/lost work),
its OCR is pushed + marked done, and only THEN do we exit. Banked OCR is never
discarded.

Single GPU worker (the 5080 is GPU-compute-bound; one worker saturates it).

Usage:
    python queue_worker_5080.py [worker_id]   (default worker_id = "5080-1")
"""
import os
import sys
import time
import datetime
import threading
import subprocess
from pathlib import Path

# --- LOCAL (5080) ---
LOCAL_SCRATCH = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch")
ARCHIVE       = LOCAL_SCRATCH / "chief-clerk-archive"
OCR_SCRIPT    = LOCAL_SCRATCH / "ocr_only_5080.py"
OCR_PY        = r"C:\Users\PatrickKolasinski\AppData\Local\Programs\Python\Python312\python.exe"
STOP_FLAG     = LOCAL_SCRATCH / "STOP_5080_WORKER.flag"
LOG_FILE      = Path(
    r"C:\Users\PatrickKolasinski\Documents\GitHub\patolex"
    r"\docs\80_PROJECT_HISTORY\run-logs\worker-5080-run.log"
)

# --- 5090 remote (owns the shared queue) ---
SSH_EXE     = r"C:\Windows\System32\OpenSSH\ssh.exe"
SCP_EXE     = r"C:\Windows\System32\OpenSSH\scp.exe"
SSH_KEY     = r"C:\Users\PatrickKolasinski\.ssh\patolex_5090"
KNOWN_HOSTS = r"C:\Users\PatrickKolasinski\.ssh\known_hosts"
REMOTE_USER = "patolex"
REMOTE_HOST = "100.70.54.56"
REMOTE_SCRATCH_WIN = r"C:\Users\patolex\PatoLex-scratch"
REMOTE_SCRATCH_FWD = "C:/Users/patolex/PatoLex-scratch"
REMOTE_PY   = r"C:\Users\patolex\PatoLex-scratch\ocr-engines\surya-venv\Scripts\python.exe"
REMOTE_CLAIM = REMOTE_SCRATCH_WIN + r"\queue_claim.py"

HEARTBEAT_SECONDS = 60
SSH_TIMEOUT       = 30
SCP_TIMEOUT       = 600


def log(phase, description, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    entry = "[" + ts + "] " + phase + " | " + description + " | " + status + "\n"
    try:
        with open(str(LOG_FILE), "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass
    print(entry.strip(), flush=True)


def _ssh_base():
    return [
        SSH_EXE, "-i", SSH_KEY,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        "-o", "UserKnownHostsFile=" + KNOWN_HOSTS,
        "-o", "StrictHostKeyChecking=yes",
        REMOTE_USER + "@" + REMOTE_HOST,
    ]


def ssh_claim_op(*op_args, timeout=SSH_TIMEOUT):
    """Run queue_claim.py <op_args...> on the 5090. Returns (rc, stdout, stderr)."""
    remote_cmd = '"' + REMOTE_PY + '" "' + REMOTE_CLAIM + '" ' + " ".join(op_args)
    args = _ssh_base() + [remote_cmd]
    try:
        r = subprocess.run(args, capture_output=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", "ssh timeout"
    except Exception as e:
        return 1, "", str(e)


def scp_push(local_path, remote_rel, timeout=SCP_TIMEOUT):
    """Push a single local file to the 5090 production tree. True on success.
    Ensures the remote parent dir exists first."""
    remote_dir = os.path.dirname(remote_rel)
    if remote_dir:
        win_dir = (REMOTE_SCRATCH_WIN + "\\" + remote_dir.replace("/", "\\"))
        mk = _ssh_base() + ['if not exist "' + win_dir + '" mkdir "' + win_dir + '"']
        try:
            subprocess.run(mk, capture_output=True, encoding="utf-8",
                           errors="replace", timeout=SSH_TIMEOUT)
        except Exception:
            pass
    remote_spec = (REMOTE_USER + "@" + REMOTE_HOST + ":"
                   + REMOTE_SCRATCH_FWD + "/" + remote_rel)
    args = [
        SCP_EXE, "-i", SSH_KEY,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        "-o", "UserKnownHostsFile=" + KNOWN_HOSTS,
        "-o", "StrictHostKeyChecking=yes",
        str(local_path), remote_spec,
    ]
    try:
        r = subprocess.run(args, capture_output=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        if r.returncode != 0:
            log("SCP", "push FAIL " + remote_rel + ": " + (r.stderr or "")[:160], "WARN")
            return False
        return True
    except subprocess.TimeoutExpired:
        log("SCP", "push TIMEOUT " + remote_rel, "WARN")
        return False
    except Exception as e:
        log("SCP", "push ERROR " + remote_rel + ": " + str(e)[:120], "WARN")
        return False


def claim_next(worker_id):
    """Claim via the 5090's queue_claim.py. Returns (label, pdf_name) or None.
    The 5090 now prints 'CLAIMED <label> <pdf>'. Backward-compatible: if the
    5090 still prints the legacy 'CLAIMED <label>' (no pdf token), we fall back
    to the '<label>_Statutes.pdf' convention so an un-upgraded 5090 still works."""
    rc, out, err = ssh_claim_op("claim", worker_id)
    if rc != 0:
        log("CLAIM", "claim rc=" + str(rc) + " " + err[:140], "WARN")
        return None
    if out.startswith("CLAIMED "):
        rest = out.split(" ", 1)[1].strip()
        parts = rest.split(None, 1)
        label = parts[0]
        pdf_name = parts[1].strip() if len(parts) > 1 else (label + "_Statutes.pdf")
        return label, pdf_name
    return None


def heartbeat(worker_id, label):
    ssh_claim_op("heartbeat", worker_id, label)


def mark_done(worker_id, label):
    rc, out, err = ssh_claim_op("done", worker_id, label)
    return rc == 0 and "OK" in out


def mark_fail(worker_id, label):
    ssh_claim_op("fail", worker_id, label)


def push_outputs(label):
    """scp the three OCR outputs UP to the 5090. True iff all required land."""
    local_dir = LOCAL_SCRATCH / ("production-" + label)
    sha   = local_dir / "sha256.txt"
    cls   = local_dir / "page_classification.json"
    ocr   = local_dir / "ocr_consensus" / "page_ocr_results.json"
    if not (sha.exists() and ocr.exists()):
        log("PUSH", label + ": local OCR outputs missing (sha/ocr)", "FAIL")
        return False
    ok = True
    ok &= scp_push(sha, "production-" + label + "/sha256.txt")
    if cls.exists():
        scp_push(cls, "production-" + label + "/page_classification.json")
    ok &= scp_push(ocr, "production-" + label + "/ocr_consensus/page_ocr_results.json")
    if ok:
        log("PUSH", label + ": OCR outputs pushed to 5090", "OK")
    return ok


def run_volume(worker_id, label, pdf_name):
    pdf = ARCHIVE / pdf_name
    if not pdf.exists():
        log("RUN", label + ": local PDF MISSING " + str(pdf), "FAIL")
        mark_fail(worker_id, label)
        return
    log("RUN", label + ": START local OCR (" + pdf.name + ") on 5080", "OK")

    env = dict(os.environ)
    proc = subprocess.Popen([OCR_PY, str(OCR_SCRIPT), str(pdf), label], env=env)

    stop = threading.Event()

    def hb_loop():
        while not stop.is_set():
            if stop.wait(HEARTBEAT_SECONDS):
                break
            try:
                heartbeat(worker_id, label)
            except Exception:
                pass

    hbt = threading.Thread(target=hb_loop, daemon=True)
    hbt.start()
    rc = proc.wait()
    stop.set()

    if rc == 0:
        if push_outputs(label) and mark_done(worker_id, label):
            log("RUN", label + ": OCR DONE + pushed + marked done on 5090", "OK")
        else:
            # OCR is banked locally; do NOT mark done. Leave reclaimable so a
            # retry (this worker or a 5090 worker) can re-push. Banked OCR safe.
            mark_fail(worker_id, label)
            log("RUN", label + ": OCR ok but push/mark failed -> left reclaimable", "WARN")
    else:
        mark_fail(worker_id, label)
        log("RUN", label + ": OCR FAILED exit " + str(rc) + " (reclaimable)", "FAIL")


def main():
    worker_id = sys.argv[1] if len(sys.argv) > 1 else "5080-1"
    log("WORKER", "=== 5080 queue worker online (pid " + str(os.getpid())
        + ", worker_id=" + worker_id + ") sharing 5090 queue " + REMOTE_HOST + " ===", "OK")
    # Clear any stale stop flag from a previous day so we actually start.
    try:
        if STOP_FLAG.exists():
            STOP_FLAG.unlink()
            log("WORKER", "cleared stale STOP flag at startup", "OK")
    except Exception:
        pass

    idle = 0
    while True:
        # Graceful stop is only honored BETWEEN volumes.
        if STOP_FLAG.exists():
            log("WORKER", "STOP flag present between volumes -- graceful exit", "OK")
            return
        # Per-worker scale-down (symmetric with the 5090 worker): drain just THIS
        # worker if its per-worker stop flag is set. Read-only -- the creator
        # owns the flag's lifecycle; do NOT unlink it here (Hans BLOCKER-2).
        if (STOP_FLAG.parent / ("STOP_WORKER_" + worker_id + ".flag")).exists():
            log("WORKER", "per-worker stop flag present -- scaled down, graceful exit between volumes", "OK")
            return
        claimed = claim_next(worker_id)
        if claimed is None:
            idle += 1
            if idle >= 3:
                log("WORKER", "queue drained / no claimable volume -- exiting", "OK")
                return
            time.sleep(15)
            continue
        idle = 0
        label, pdf_name = claimed
        run_volume(worker_id, label, pdf_name)


if __name__ == "__main__":
    main()
