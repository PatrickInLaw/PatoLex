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
PREP_BUFFER_MAX   = 3      # prep workers stop claiming when this many volumes are prepped-but-not-yet-done (bounds disk)


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


def claim_next(worker_id, role):
    """Atomically claim the lowest-year claimable volume for this ROLE.
      role 'prep': claims 'pending' (+ stale 'prepping'); marks 'prepping'.
                   Bounded by PREP_BUFFER_MAX so prep doesn't run too far ahead.
      role 'ocr' : claims 'prepped' (+ stale 'ocring'/'failed'); marks 'ocring'.
    Returns (label, pdf_name) or None. 'held' is never claimable. A worker
    NEVER touches 'in_progress' (that status belongs to the coupled 5080 path)."""
    acquire_lock()
    try:
        state = read_queue()
        vols = state["volumes"]  # already chronological
        nowt = time.time()
        # PREP buffer bound: count volumes already prepped-but-not-done; if at the
        # cap, prep idles (still does marker promotions below, just doesn't claim).
        under_buffer = True
        if role == "prep":
            ahead = sum(1 for v in vols if v.get("status") in ("prepped", "ocring"))
            under_buffer = ahead < PREP_BUFFER_MAX
        for v in vols:
            label = v["label"]
            # idempotent completion: OCR marker on disk overrides
            if marker_path(label).exists():
                if v["status"] != "done":
                    v["status"] = "done"
                    v["done_at"] = now_iso()
                continue
            if v["status"] in ("done", "held"):
                continue
            claimable = False
            if role == "prep":
                new_status = "prepping"
                if v["status"] == "pending":
                    claimable = under_buffer
                elif v["status"] == "prepping":
                    hb = v.get("heartbeat_epoch", 0)
                    if nowt - hb > STALE_SECONDS:
                        # recovering a dead prep replaces in-flight work, it does
                        # NOT grow the buffer -- so it is NOT buffer-gated, else a
                        # stale prepping could strand while the buffer is full.
                        claimable = True
                        log(worker_id, f"{label}: reclaiming stale prepping (age {int(nowt-hb)}s)", "WARN")
            else:  # role == "ocr"
                new_status = "ocring"
                if v["status"] == "prepped":
                    claimable = True
                elif v["status"] in ("ocring", "ocr_failed", "failed"):
                    # 'ocring'/'ocr_failed' are 5090-only; 'failed' is prep-less
                    # 5080-origin (safe to re-prep+ocr here). The 5080 never
                    # claims 'ocring'/'ocr_failed', so no checkpoint collision.
                    hb = v.get("heartbeat_epoch", 0)
                    if nowt - hb > STALE_SECONDS:
                        claimable = True
                        log(worker_id, f"{label}: reclaiming stale {v['status']} (age {int(nowt-hb)}s)", "WARN")
            if claimable:
                v["status"] = new_status
                v["worker_id"] = worker_id
                v["claimed_at"] = now_iso()
                v["heartbeat_epoch"] = nowt
                v["heartbeat_at"] = now_iso()
                write_queue(state)
                return label, pdf_name_for(v)
        # Nothing claimable right now. Distinguish "WAIT" (pipeline still has
        # work relevant to this role -- prep buffer full, or OCR waiting for prep
        # to produce 'prepped') from None (no role-relevant work left at all, so
        # the worker may exit). This prevents launch/idle-exit churn.
        if role == "prep":
            pipeline_work = any(v.get("status") in ("pending", "prepping") for v in vols)
        else:
            pipeline_work = any(v.get("status") in ("pending", "prepping", "prepped", "ocring", "ocr_failed", "failed") for v in vols)
        write_queue(state)  # persist any marker-driven 'done' promotions
        return "WAIT" if pipeline_work else None
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
            if v["label"] == label and v["status"] in ("in_progress", "prepping", "ocring"):
                v["heartbeat_epoch"] = time.time()
                v["heartbeat_at"] = now_iso()
                break
        write_queue(state)
    finally:
        release_lock()


def run_volume(worker_id, label, pdf_name, role):
    pdf = ARCHIVE / pdf_name
    if not pdf.exists():
        log(worker_id, f"{label}: PDF MISSING {pdf}", "FAIL")
        # missing PDF: prep -> pending (re-claimable later), ocr -> failed
        update_status(label, "pending" if role == "prep" else "failed", {"error": "pdf_missing"})
        return
    stage = "prep" if role == "prep" else "ocr"
    log(worker_id, f"{label}: START {stage.upper()} ({pdf.name})", "OK")

    proc = subprocess.Popen([PY, str(SCRIPT), str(pdf), label, "--stage", stage])

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
        if role == "prep":
            update_status(label, "prepped")
            log(worker_id, f"{label}: PREP DONE (exit 0)", "OK")
        else:
            marker_path(label).parent.mkdir(parents=True, exist_ok=True)
            marker_path(label).write_text(f"OCR complete {now_iso()} by W{worker_id}\n",
                                          encoding="utf-8")
            update_status(label, "done")
            log(worker_id, f"{label}: OCR DONE (exit 0)", "OK")
    else:
        # prep failure -> back to 'pending' (re-preppable); OCR failure -> 'failed'
        # (prep artifacts remain on disk; re-claimable by an ocr worker).
        if role == "prep":
            update_status(label, "pending", {"error": f"prep_exit_{rc}"})
            log(worker_id, f"{label}: PREP FAILED exit {rc} -> pending", "FAIL")
        else:
            # 'ocr_failed' (NOT 'failed') so the unchanged 5080 (which reclaims
            # 'failed') can't poach a volume that has a 5090-side partial OCR
            # checkpoint + prep on disk and clobber it via scp (Hans BLOCKER-1).
            update_status(label, "ocr_failed", {"error": f"exit_{rc}"})
            log(worker_id, f"{label}: OCR FAILED exit {rc} -> ocr_failed (5090-only reclaim)", "FAIL")


def main():
    worker_id = sys.argv[1] if len(sys.argv) > 1 else str(os.getpid())
    role = "ocr"
    if "--role" in sys.argv:
        _ri = sys.argv.index("--role")
        if _ri + 1 < len(sys.argv):
            role = sys.argv[_ri + 1].strip().lower()
    if role not in ("prep", "ocr"):
        log(worker_id, f"invalid --role {role!r} (must be prep|ocr)", "FAIL")
        return
    log(worker_id, f"=== queue worker online (pid {os.getpid()}) role={role} ===", "OK")
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
            claimed = claim_next(worker_id, role)
        except Exception as e:
            log(worker_id, f"claim error: {e}", "WARN")
            time.sleep(5)
            continue
        if claimed == "WAIT":
            # pipeline still has role-relevant work, just not claimable now
            # (prep: buffer full; ocr: nothing prepped yet) -- wait, don't exit.
            idle = 0
            time.sleep(15)
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
        run_volume(worker_id, label, pdf_name, role)


if __name__ == "__main__":
    main()
