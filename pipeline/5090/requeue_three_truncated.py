"""
requeue_three_truncated.py -- one-shot, surgical requeue of EXACTLY three
genuinely-truncated volumes (1993-vol2, 1993-vol5, 1994-vol1) so the 5090's
`--role ocr` queue_worker.py workers re-claim them and RESUME OCR from their
existing ocr_consensus/page_ocr_results.json checkpoints.

Reuses queue_claim.py's IDENTICAL locked write path (acquire_lock / read_queue /
write_queue) so the change is serialized against any live worker and the file
stays consistent. Touches ONLY the three target entries. Self-verifies and
ABORTS (no write) if anything deviates: a target missing, a target not currently
'done', a non-target's status changed, or the done-count delta != -3.

An `ocr` worker claims status 'prepped' (queue_worker.claim_next, role=='ocr')
and marks it 'ocring'. It also force-promotes any volume whose OCR_COMPLETE.marker
exists back to 'done' BEFORE claiming -- so we delete the marker for each target
(idempotent; none are expected to exist).
"""
import sys
from pathlib import Path

# Import the canonical locked-IO helpers from the deployed queue_claim.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
import queue_claim as qc

TARGETS = ["1993-vol2", "1993-vol5", "1994-vol1"]
TARGET_STATUS = "prepped"   # the status a --role ocr worker claims

DO_NOT_TOUCH = {"1995-vol5", "1996-vol1", "1996-vol2", "1996-vol3"}


def main():
    # Snapshot BEFORE (no lock needed for a read snapshot used only for verification)
    before = qc.read_queue()
    before_status = {v["label"]: v["status"] for v in before["volumes"]}

    for label in TARGETS:
        if label not in before_status:
            print(f"ABORT: target {label} not in queue")
            sys.exit(3)
        if before_status[label] != "done":
            print(f"ABORT: target {label} status is {before_status[label]!r}, expected 'done'")
            sys.exit(3)

    # Snapshot the do-not-touch + everything-else statuses for a strict diff later.
    before_all = dict(before_status)

    qc.acquire_lock()
    try:
        state = qc.read_queue()
        changed = []
        for v in state["volumes"]:
            if v["label"] in TARGETS:
                # delete marker so the worker can't force-promote it back to done
                mp = qc.marker_path(v["label"])
                if mp.exists():
                    mp.unlink()
                    print(f"deleted marker {mp}")
                v["status"] = TARGET_STATUS
                # clear any stale claim bookkeeping so it's a clean 'prepped'
                for fld in ("worker_id", "claimed_at", "heartbeat_epoch",
                            "heartbeat_at", "done_at", "error",
                            "ocring_at", "in_progress_at", "failed_at"):
                    v.pop(fld, None)
                changed.append(v["label"])

        # ---- strict in-memory verification BEFORE persisting ----
        if sorted(changed) != sorted(TARGETS):
            print(f"ABORT(no write): changed set {sorted(changed)} != targets {sorted(TARGETS)}")
            sys.exit(4)
        after_status = {v["label"]: v["status"] for v in state["volumes"]}
        # every NON-target must be byte-identical in status to before
        for label, st in before_all.items():
            if label in TARGETS:
                continue
            if after_status.get(label) != st:
                print(f"ABORT(no write): non-target {label} changed {st!r}->{after_status.get(label)!r}")
                sys.exit(5)
        # explicit do-not-touch guard
        for label in DO_NOT_TOUCH:
            if after_status.get(label) != before_all.get(label):
                print(f"ABORT(no write): DO-NOT-TOUCH {label} changed")
                sys.exit(6)
        # each target now 'prepped'
        for label in TARGETS:
            if after_status[label] != TARGET_STATUS:
                print(f"ABORT(no write): target {label} not set to {TARGET_STATUS}")
                sys.exit(7)
        # done-count must drop by exactly 3
        b_done = sum(1 for s in before_all.values() if s == "done")
        a_done = sum(1 for s in after_status.values() if s == "done")
        if a_done != b_done - 3:
            print(f"ABORT(no write): done-count delta {a_done - b_done} != -3")
            sys.exit(8)

        qc.write_queue(state)
        print(f"OK: set {sorted(changed)} -> {TARGET_STATUS}; "
              f"done {b_done}->{a_done}; all other entries unchanged")
    finally:
        qc.release_lock()


if __name__ == "__main__":
    main()
