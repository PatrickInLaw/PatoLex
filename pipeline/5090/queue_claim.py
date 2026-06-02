"""
queue_claim.py -- one-shot atomic queue operations, run ON the 5090 over SSH.
=============================================================================
Lets a REMOTE worker (the 5080) participate in the SAME shared forward queue
as the 5090's in-process queue_worker.py workers, using the IDENTICAL
exclusive lock file (production_queue_state.lock) so all claims -- local 5090
workers AND the remote 5080 worker -- are serialized against each other.

This script is deployed to the 5090 and invoked one operation per SSH call:

  python queue_claim.py claim     <worker_id>          -> prints "CLAIMED <label>" or "NONE"
  python queue_claim.py heartbeat <worker_id> <label>  -> prints "OK"
  python queue_claim.py done      <worker_id> <label>  -> prints "OK"  (writes marker too)
  python queue_claim.py fail      <worker_id> <label>  -> prints "OK"  (reclaimable)

Claim policy = lowest-year pending/reclaimable volume (forward/chronological),
identical to queue_worker.claim_next, including marker-driven 'done' promotion
and STALE_SECONDS reclamation. Idempotent + safe across worker/SSH death.
"""
import os
import sys
import json
import time
import errno
import datetime
from pathlib import Path

SCRATCH = Path(r"C:\Users\patolex\PatoLex-scratch")
QUEUE   = SCRATCH / "production_queue_state.json"
LOCK    = SCRATCH / "production_queue_state.lock"

STALE_SECONDS     = 1800
LOCK_SPIN_SECONDS = 0.15
LOCK_MAX_WAIT     = 120


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


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
    return SCRATCH / ("production-" + label) / "OCR_COMPLETE.marker"


def op_claim(worker_id):
    acquire_lock()
    try:
        state = read_queue()
        nowt = time.time()
        for v in state["volumes"]:
            label = v["label"]
            if marker_path(label).exists():
                if v["status"] != "done":
                    v["status"] = "done"
                    v["done_at"] = now_iso()
                continue
            if v["status"] == "done":
                continue
            claimable = v["status"] == "pending"
            if v["status"] in ("in_progress", "failed"):
                hb = v.get("heartbeat_epoch", 0)
                if nowt - hb > STALE_SECONDS:
                    claimable = True
            if claimable:
                v["status"] = "in_progress"
                v["worker_id"] = worker_id
                v["claimed_at"] = now_iso()
                v["heartbeat_epoch"] = nowt
                v["heartbeat_at"] = now_iso()
                write_queue(state)
                print("CLAIMED " + label)
                return
        write_queue(state)
        print("NONE")
    finally:
        release_lock()


def op_update(worker_id, label, status, write_marker=False):
    acquire_lock()
    try:
        state = read_queue()
        for v in state["volumes"]:
            if v["label"] == label:
                v["status"] = status
                v[status + "_at"] = now_iso()
                if status == "in_progress":
                    v["heartbeat_epoch"] = time.time()
                    v["heartbeat_at"] = now_iso()
                break
        write_queue(state)
    finally:
        release_lock()
    if write_marker:
        mp = marker_path(label)
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text("OCR complete " + now_iso() + " by " + worker_id + "\n",
                      encoding="utf-8")
    print("OK")


def op_heartbeat(worker_id, label):
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
    print("OK")


def main():
    if len(sys.argv) < 3:
        print("usage: queue_claim.py {claim|heartbeat|done|fail} <worker_id> [label]")
        sys.exit(1)
    op = sys.argv[1]
    worker_id = sys.argv[2]
    if op == "claim":
        op_claim(worker_id)
    elif op == "heartbeat":
        op_heartbeat(worker_id, sys.argv[3])
    elif op == "done":
        # mark in_progress->done is not required; set done + write marker
        op_update(worker_id, sys.argv[3], "done", write_marker=True)
    elif op == "fail":
        op_update(worker_id, sys.argv[3], "failed")
    else:
        print("unknown op " + op)
        sys.exit(1)


if __name__ == "__main__":
    main()
