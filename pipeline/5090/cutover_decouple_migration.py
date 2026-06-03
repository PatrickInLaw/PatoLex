"""One-time cutover migration for the decoupled prep/OCR pipeline.

Rewrites the 5090-side 'in_progress' orphans (left by the OLD coupled run) into
the new status vocabulary so the new role-based workers can pick them up, based
on on-disk state:
    OCR_COMPLETE.marker exists      -> 'done'
    page_classification.json exists -> 'prepped'   (5090-ocr resumes from any
                                       partial page_ocr_results.json checkpoint;
                                       the 5080 never claims 'prepped', so no
                                       cross-box checkpoint collision -- Hans B1/B2)
    neither                          -> 'pending'   (full re-prep; idempotent)

CRITICAL: only touches entries whose worker_id is a 5090 worker ('5090-*').
The 5080's LIVE 'in_progress' (worker_id '5080-*') is left ALONE -- resetting it
would let a 5090 role double-process a volume the 5080 is actively OCR'ing.

Run ON the 5090 with all 5090 workers STOPPED. Default is DRY-RUN; pass --commit
to apply. Uses the same exclusive lock as the workers.
"""
import sys, os, json, time, errno, datetime
from pathlib import Path

SCRATCH = Path(r"C:\Users\patolex\PatoLex-scratch")
QUEUE   = SCRATCH / "production_queue_state.json"
LOCK    = SCRATCH / "production_queue_state.lock"
COMMIT  = "--commit" in sys.argv


def marker(label):         return SCRATCH / f"production-{label}" / "OCR_COMPLETE.marker"
def classification(label): return SCRATCH / f"production-{label}" / "page_classification.json"
def has_partial_ocr(label):
    return (SCRATCH / f"production-{label}" / "ocr_consensus" / "page_ocr_results.json").exists()


def acquire_lock():
    waited = 0.0
    while True:
        try:
            fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, str(os.getpid()).encode()); os.close(fd); return
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            time.sleep(0.2); waited += 0.2
            if waited > 60:
                raise RuntimeError("queue lock wait exceeded -- are workers still running?")


def release_lock():
    try: os.remove(str(LOCK))
    except OSError: pass


def main():
    acquire_lock()
    try:
        state = json.loads(QUEUE.read_text(encoding="utf-8"))
        plan = []
        for v in state["volumes"]:
            if v.get("status") != "in_progress":
                continue
            wid = str(v.get("worker_id", ""))
            label = v["label"]
            if not wid.startswith("5090-"):
                plan.append((label, "in_progress", f"SKIP (worker {wid or '?'} -- 5080/other owns it)"))
                continue
            if marker(label).exists():
                new = "done"
            elif classification(label).exists():
                new = "prepped"   # NEVER 'pending' when prep exists (Hans B2): keeps the 5080 off the partial checkpoint
            else:
                new = "pending"
            note = " (+partial OCR checkpoint -> resumes)" if (new == "prepped" and has_partial_ocr(label)) else ""
            plan.append((label, "in_progress", new + note))
            if COMMIT:
                v["status"] = new
                v[new + "_at"] = datetime.datetime.now().isoformat(timespec="seconds")
                v["worker_id"] = ""
                v.pop("claimed_at", None)
                v.pop("heartbeat_epoch", None)
                v.pop("heartbeat_at", None)
        if COMMIT:
            tmp = QUEUE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
            os.replace(str(tmp), str(QUEUE))
        print("=== cutover migration " + ("(COMMITTED)" if COMMIT else "(DRY-RUN -- pass --commit to apply)") + " ===")
        if not plan:
            print("  (no in_progress volumes found)")
        for label, old, new in plan:
            print(f"  {label}: {old} -> {new}")
    finally:
        release_lock()


if __name__ == "__main__":
    main()
