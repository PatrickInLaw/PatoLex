"""
queue_worker.py -- shared forward-queue OCR worker for the RTX 5090.
====================================================================
Each worker process:
  1. Atomically claims the LOWEST-year volume still 'pending' in
     production_queue_state.json (forward / chronological order).
  2. Marks it 'in_progress' with worker_id + claimed_at + heartbeat.
  3. Runs ocr_only_5090.py on that volume (own child process => fresh CUDA
     context per volume, per-page GPU hygiene as in the fixed pipeline).
  4. On exit 0 writes production-<label>/OCR_COMPLETE.marker and marks the
     queue entry 'done'. On non-zero exit marks 'failed' (reclaimable).
  5. Loops to the next pending volume until the queue is drained.

Concurrency / safety:
  - All read-modify-write of the queue JSON is serialized by an exclusive
    lock file (os.O_CREAT|os.O_EXCL) with bounded spin -- safe across the
    3+ concurrent workers AND across SSH-session death.
  - Idempotent: a volume whose OCR_COMPLETE.marker exists is treated as
    'done' and never re-OCR'd. ocr_only_5090.py is itself resumable, so a
    reclaimed in-progress volume continues from its checkpoint -- no banked
    page is ever lost.
  - Stale claim: an 'in_progress' entry whose heartbeat is older than
    STALE_SECONDS is reclaimable (the worker died).
  - 'held' volumes are NEVER claimable -- they are not 'pending' and not
    stale-reclaimable. 'held' is set OUT-OF-BAND by an operator tool to fence
    off volumes; the supervisor's per-worker scale-down does NOT set 'held'
    (scale-down drains a worker via a per-worker stop flag, not by holding work).

Graceful drain:
  - Between volumes (top of the claim loop) the worker checks two stop signals
    and exits 0 WITHOUT claiming a new volume if either is set:
      * STOP_WORKER.flag           -- GLOBAL: drains ALL workers (pause/stop).
      * STOP_WORKER_<id>.flag      -- PER-WORKER: drains just THIS worker (the
        supervisor writes it to scale down; the supervisor owns its lifecycle,
        the worker only reads it).
    Because both checks are between volumes, an in-flight volume is always
    allowed to finish + write its marker first -- never killed.

Heartbeat: while ocr_only runs, this worker bumps the entry's heartbeat
every HEARTBEAT_SECONDS so live work is not mistaken for a dead claim.

Usage:
    python queue_worker.py <worker_id>
"""
import os
import sys
import json
import time
import errno
import datetime
import threading
import subprocess
from pathlib import Path

SCRATCH = Path(r"C:\Users\patolex\PatoLex-scratch")
QUEUE   = SCRATCH / "production_queue_state.json"
LOCK    = SCRATCH / "production_queue_state.lock"
SCRIPT  = SCRATCH / "ocr_only_5090.py"
ARCHIVE = SCRATCH / "chief-clerk-archive"
PY      = r"C:\Users\patolex\PatoLex-scratch\ocr-engines\surya-venv\Scripts\python.exe"
LOG     = SCRATCH / "queue-worker.log"
STOP_FLAG = SCRATCH / "STOP_WORKER.flag"

STALE_SECONDS     = 1800   # 30 min with no heartbeat => reclaimable
HEARTBEAT_SECONDS = 60
LOCK_SPIN_SECONDS = 0.15
LOCK_MAX_WAIT     = 120


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def log(worker_id, msg, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    line = f"[{ts}] [W{worker_id}] {msg} | {status}\n"
    with open(str(LOG), "a", encoding="utf-8") as f:
        f.write(line)
    print(line.strip(), flush=True)


def acquire_lock():
    waited = 0.0
    while True:
        try:
            fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            # stale-lock guard: if lock older than 60s, steal it
            try:
                age = time.time() - os.path.getmtime(str(LOCK))
                if age > 60:
                    os.remove(str(LOCK))
                    continue
            except OSError:
                pass
            time.sleep(LOCK_SPIN_SECONDS)
            waited += LOCK_SPIN_SECONDS
            if waited > LOCK_MAX_WAIT:
                # give up the lock wait; treat as fatal contention
                raise RuntimeError("queue lock wait exceeded")


def release_lock():
    try:
        os.remove(str(LOCK))
    except OSError:
        pass


def read_queue():
    return json.loads(QUEUE.read_text(encoding="utf-8"))


def write_queue(state):
    tmp = QUEUE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(QUEUE))


def marker_path(label):
    return SCRATCH / f"production-{label}" / "OCR_COMPLETE.marker"


def pdf_name_for(v):
    """Resolve the PDF filename for a work-item. Backward-compatible:
    an entry with no explicit 'pdf' falls back to the legacy
    '<label>_Statutes.pdf' convention -- existing entries are unchanged.
    A Code/amendments volume (or any non-Statutes body PDF) sets 'pdf'
    explicitly and keeps its own distinct 'label'."""
    return v.get("pdf") or (v["label"] + "_Statutes.pdf")


def claim_next(worker_id):
    """Atomically claim the lowest-year pending/reclaimable volume.
    Returns (label, pdf_name) or None if nothing claimable.
    'held' volumes are never claimable."""
    acquire_lock()
    try:
        state = read_queue()
        vols = state["volumes"]  # already chronological
        nowt = time.time()
        for v in vols:
            label = v["label"]
            # idempotent completion: marker on disk overrides
            if marker_path(label).exists():
                if v["status"] != "done":
                    v["status"] = "done"
                    v["done_at"] = now_iso()
                continue
            if v["status"] == "done":
                continue
            if v["status"] == "held":
                continue
            claimable = v["status"] == "pending"
            if v["status"] in ("in_progress", "failed"):
                hb = v.get("heartbeat_epoch", 0)
                if nowt - hb > STALE_SECONDS:
                    claimable = True
                    log(worker_id, f"{label}: reclaiming stale {v['status']} "
                                   f"(age {int(nowt-hb)}s)", "WARN")
            if claimable:
                v["status"] = "in_progress"
                v["worker_id"] = worker_id
                v["claimed_at"] = now_iso()
                v["heartbeat_epoch"] = nowt
                v["heartbeat_at"] = now_iso()
                write_queue(state)
                return label, pdf_name_for(v)
        write_queue(state)  # persist any marker-driven 'done' promotions
        return None
    finally:
        release_lock()


def update_status(label, status, extra=None):
    acquire_lock()
    try:
        state = read_queue()
        for v in state["volumes"]:
            if v["label"] == label:
                v["status"] = status
                v[status + "_at"] = now_iso()
                if extra:
                    v.update(extra)
                break
        write_queue(state)
    finally:
        release_lock()


def heartbeat(label):
    acquire_lock()
    try:
        state = read_queue()
        for v in state["volumes"]:
            if v["label"] == label and v["status"] == "in_progress":
                v["heartbeat_epoch"] = time.time()
                v["heartbeat_at"] = now_iso()
                break
        write_queue(state)
    finally:
        release_lock()


def run_volume(worker_id, label, pdf_name):
    pdf = ARCHIVE / pdf_name
    if not pdf.exists():
        log(worker_id, f"{label}: PDF MISSING {pdf}", "FAIL")
        update_status(label, "failed", {"error": "pdf_missing"})
        return
    log(worker_id, f"{label}: START OCR ({pdf.name})", "OK")

    proc = subprocess.Popen([PY, str(SCRIPT), str(pdf), label])

    stop = threading.Event()

    def hb_loop():
        while not stop.is_set():
            if stop.wait(HEARTBEAT_SECONDS):
                break
            try:
                heartbeat(label)
            except Exception:
                pass

    hbt = threading.Thread(target=hb_loop, daemon=True)
    hbt.start()
    rc = proc.wait()
    stop.set()

    if rc == 0:
        marker_path(label).parent.mkdir(parents=True, exist_ok=True)
        marker_path(label).write_text(f"OCR complete {now_iso()} by W{worker_id}\n",
                                      encoding="utf-8")
        update_status(label, "done")
        log(worker_id, f"{label}: OCR DONE (exit 0)", "OK")
    else:
        update_status(label, "failed", {"error": f"exit_{rc}"})
        log(worker_id, f"{label}: OCR FAILED exit {rc} (reclaimable)", "FAIL")


def main():
    worker_id = sys.argv[1] if len(sys.argv) > 1 else str(os.getpid())
    log(worker_id, f"=== queue worker online (pid {os.getpid()}) ===", "OK")
    idle = 0
    while True:
        # Graceful drain: between volumes only. An in-flight volume (inside
        # run_volume) always finishes + checkpoints before we reach here.
        if STOP_FLAG.exists():
            log(worker_id, "STOP_WORKER.flag present -- exiting gracefully between volumes", "OK")
            return
        # Live, SELECTIVE scale-down: a per-worker stop flag (created by the
        # supervisor when max_workers is lowered) drains just THIS worker after
        # its current volume -- unlike the global STOP_WORKER.flag which stops
        # all of them. Checked between volumes only, so an in-flight volume
        # always finishes + checkpoints first (never killed mid-volume).
        # The SUPERVISOR owns this flag's whole lifecycle (create / cancel-on-
        # raise / clear-on-reap); the worker only READS it. We must NOT unlink
        # it here -- a worker-side delete races the supervisor's cancel and can
        # defeat a "raise max_workers to cancel the drain" (Hans BLOCKER-2).
        wstop = SCRATCH / f"STOP_WORKER_{worker_id}.flag"
        if wstop.exists():
            log(worker_id, "per-worker stop flag present -- scaled down, exiting gracefully between volumes", "OK")
            return
        try:
            claimed = claim_next(worker_id)
        except Exception as e:
            log(worker_id, f"claim error: {e}", "WARN")
            time.sleep(5)
            continue
        if claimed is None:
            idle += 1
            if idle >= 3:
                log(worker_id, "queue drained -- no claimable volumes; exiting", "OK")
                return
            time.sleep(10)
            continue
        idle = 0
        label, pdf_name = claimed
        run_volume(worker_id, label, pdf_name)


if __name__ == "__main__":
    main()
