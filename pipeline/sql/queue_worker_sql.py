"""
queue_worker_sql.py -- SQL-backed OCR pipeline worker (Step 1, Step-2-ready).

Replaces the JSON-over-SSH queue_worker.py / queue_worker_5080.py / queue_claim.py.
Authoritative design: docs/30_SYSTEM_DESIGN/SQL_PIPELINE_DESIGN_2026-06-03.md (REVISION 2).

ONE generic worker, parameterized by --role == pass prefix:
    prep | ocr | tess | doctr | surya | consensus
The claim/lease/heartbeat/fence machinery is identical for every pass (R2.3); only the
claimable predicate (PASS table below) and the subprocess invocation vary.

Concurrency model (per R2.3/R2.4):
  * Atomic claim: UPDATE ... FROM q WITH (UPDLOCK,ROWLOCK)  -- NO READPAST on the outer target
    WHERE id = (SELECT TOP(1) ... WITH (READPAST,UPDLOCK,ROWLOCK) ORDER BY yr,id) ... OUTPUT.
  * Lease: <prefix>_lease_token = NEWID(), <prefix>_lease_expires_at = now + LEASE_MIN (absolute).
  * Heartbeat extends the lease ONLY if the token still matches (the fence). @@ROWCOUNT==0 => self-abort.
  * DB unreachable for > 50% of the lease window => self-abort (clock-skew safe margin).
  * <prefix>_attempts increments on FAILURE ONLY (never on claim); attempts>=MAX_ATTEMPTS => 'held'.
  * autocommit=True on the connection (each claim/transition is one self-contained statement).

Buffer bound (prep only): a standalone COUNT before claiming (NOT in the claim SQL -- an in-claim
correlated COUNT deadlocks under concurrent prep workers). Soft throttle; bounded overshoot accepted.

NOTHING here touches the live JSON campaign. Connection string comes from the environment
(PATOLEX_QUEUE_DSN), never hardcoded; values never logged.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import pyodbc
except ImportError:
    sys.stderr.write("pyodbc not installed (ODBC Driver 18 + pyodbc are a Step-1 prerequisite)\n")
    raise

# --------------------------------------------------------------------------- config
LEASE_MIN          = 45          # lease window, minutes (R2.3: covers worst-case OCR + margin)
HEARTBEAT_SEC      = 60          # heartbeat cadence
MAX_ATTEMPTS       = 5           # attempts >= this -> 'held' dead-letter
PREP_BUFFER_MAX    = 3           # prep idles when prepped-ahead buffer reaches this
IDLE_SLEEP_SEC     = 20          # sleep when no claimable work
SELF_ABORT_FRAC    = 0.50        # abort if DB unreachable for > this fraction of the lease

# Per-pass definition. `gate` is the SQL predicate (on the row's OWN columns) that must hold for
# the pass to be claimable, beyond "<prefix>_state='pending'". No joins -- single-row predicates.
PASS = {
    "prep":      {"gate": "1=1",                                                         "buffered": True},
    "ocr":       {"gate": "prep_state='done'",                                           "buffered": False},
    "tess":      {"gate": "prep_state='done'",                                           "buffered": False},
    "doctr":     {"gate": "prep_state='done'",                                           "buffered": False},
    "surya":     {"gate": "prep_state='done'",                                           "buffered": False},
    "consensus": {"gate": "tess_state='done' AND doctr_state='done' AND surya_state='done'", "buffered": False},
}

RUN_LOG = Path(os.environ.get("PATOLEX_RUN_LOG", "")) if os.environ.get("PATOLEX_RUN_LOG") else None


def log(phase: str, msg: str, status: str = "OK") -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M} PT] {phase} | {msg} | {status}"
    print(line, flush=True)
    if RUN_LOG:
        try:
            with RUN_LOG.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


def connect() -> "pyodbc.Connection":
    dsn = os.environ.get("PATOLEX_QUEUE_DSN")
    if not dsn:
        sys.stderr.write("PATOLEX_QUEUE_DSN not set (MSSQL conn string -- see PatoAudio config)\n")
        sys.exit(2)
    # autocommit=True: each claim/transition is one self-contained statement (R2.3 / Hans MINOR-10).
    return pyodbc.connect(dsn, autocommit=True)


# --------------------------------------------------------------------------- claim
def claim_next(cx, role: str, worker_id: str):
    """Atomically claim the lowest-year claimable row for `role`. Returns (id,label,pdf,yr) or None.

    Rusanu skip-locked idiom: READPAST on the INNER candidate select only; the OUTER target takes
    UPDLOCK,ROWLOCK with NO READPAST (Hans BLOCKER-1). Single self-contained UPDATE ... OUTPUT.
    """
    p = role
    gate = PASS[role]["gate"]
    # NEWID() inline (NOT a DECLARE) -- a multi-statement DECLARE+UPDATE batch does NOT expose the
    # OUTPUT result set to pyodbc .fetchone() (Hans BLOCKER-1). Single self-contained statement.
    sql = f"""
SET NOCOUNT ON;
UPDATE q
   SET {p}_state='working',
       {p}_lease_token=NEWID(),
       {p}_lease_expires_at = DATEADD(minute, {LEASE_MIN}, sysutcdatetime()),
       {p}_claimed_by=?,
       {p}_heartbeat_at=sysutcdatetime(),
       updated_at=sysutcdatetime()
  OUTPUT inserted.id, inserted.label, inserted.pdf, inserted.yr, inserted.{p}_lease_token, deleted.{p}_state
  FROM dbo.ocr_queue AS q WITH (UPDLOCK, ROWLOCK)
 WHERE q.id = (
    SELECT TOP (1) q2.id
      FROM dbo.ocr_queue AS q2 WITH (READPAST, UPDLOCK, ROWLOCK)
     WHERE ( q2.{p}_state='pending'
          OR (q2.{p}_state IN ('working','failed') AND q2.{p}_lease_expires_at < sysutcdatetime()) )
       AND ( {gate} )
     ORDER BY q2.yr, q2.id
 );
"""
    row = cx.execute(sql, worker_id).fetchone()
    if not row:
        return None
    return {"id": row[0], "label": row[1], "pdf": row[2], "yr": row[3],
            "lease": row[4], "from": row[5]}


def prep_buffer_full(cx) -> bool:
    """Standalone count (NOT in the claim SQL -- avoids the cross-row deadlock, Hans BLOCKER-2).
    Counts volumes already prepped-ahead of OCR; soft throttle, bounded overshoot accepted."""
    n = cx.execute(
        "SELECT COUNT(*) FROM dbo.ocr_queue "
        "WHERE ocr_state='working' OR (prep_state='done' AND ocr_state='pending')"
    ).fetchone()[0]
    return n >= PREP_BUFFER_MAX


# --------------------------------------------------------------------------- lease / fence
class Lease:
    """Heartbeat + fence for one claimed row. self.lost becomes True if the worker is fenced
    (token mismatch) or the DB is unreachable past the safety margin -> caller must self-abort."""

    def __init__(self, cx_factory, role: str, row_id: int, token, worker_id: str):
        self._cx_factory = cx_factory
        self._p = role
        self._id = row_id
        self._token = token
        self.lost = False
        self._stop = threading.Event()
        self._last_ok = time.monotonic()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=15)
        # if the thread did not confirm a clean exit, we cannot trust its flag -> treat as lost
        # (Hans BLOCKER-2: join timeout must not let the main thread mark_done on an unconfirmed lease).
        if self._thread.is_alive():
            self.lost = True

    def _loop(self):
        p = self._p
        sql = (f"UPDATE dbo.ocr_queue "
               f"SET {p}_heartbeat_at=sysutcdatetime(), "
               f"    {p}_lease_expires_at=DATEADD(minute, {LEASE_MIN}, sysutcdatetime()), "
               f"    updated_at=sysutcdatetime() "
               f"WHERE id=? AND {p}_lease_token=?")
        # own short-lived connection so heartbeat never contends with the worker's main cursor
        hb_cx = None
        while not self._stop.wait(HEARTBEAT_SEC):
            try:
                if hb_cx is None:
                    hb_cx = self._cx_factory()
                cur = hb_cx.execute(sql, self._id, self._token)
                if cur.rowcount == 0:
                    # fenced: our row was reclaimed by someone else.
                    log("FENCE", f"{p} row {self._id} lease lost (token mismatch) -> abort", "WARN")
                    self.lost = True
                    return
                self._last_ok = time.monotonic()
            except pyodbc.Error as e:
                # DB unreachable: decide on the LOCAL clock with a conservative margin (Hans SERIOUS-8).
                if hb_cx is not None:
                    try:
                        hb_cx.close()
                    except Exception:
                        pass
                hb_cx = None  # force reconnect next tick
                if time.monotonic() - self._last_ok > LEASE_MIN * 60 * SELF_ABORT_FRAC:
                    log("FENCE", f"{p} row {self._id} DB unreachable past safety margin -> abort: {str(e)[:80]}", "WARN")
                    self.lost = True
                    return


# --------------------------------------------------------------------------- transitions
def mark_done(cx, role: str, row_id: int, token) -> bool:
    """Terminal success, fenced by token (Hans result-commit fence). Returns False if fenced."""
    p = role
    # `done_at` (volume-complete) is set by whichever pass is terminal: 'ocr' for a Step-1 row,
    # 'consensus' for a Step-2 row. Assumes a row is purely Step-1 OR Step-2, never a hybrid
    # (the seed guarantees this) -- a hybrid row would set done_at prematurely (Hans MINOR-10).
    extra = ", done_at=sysutcdatetime()" if role in ("ocr", "consensus") else ""
    cur = cx.execute(
        f"UPDATE dbo.ocr_queue "
        f"SET {p}_state='done', {p}_done_at=sysutcdatetime(){extra}, updated_at=sysutcdatetime() "
        f"WHERE id=? AND {p}_lease_token=?",
        row_id, token,
    )
    return cur.rowcount == 1


def mark_failed(cx, role: str, row_id: int, token, err: str) -> None:
    """Failure transition: attempts++ HERE (never on claim); attempts>=MAX -> 'held' (atomic)."""
    p = role
    cx.execute(
        f"UPDATE dbo.ocr_queue "
        f"SET {p}_state = CASE WHEN {p}_attempts + 1 >= {MAX_ATTEMPTS} THEN 'held' ELSE 'failed' END, "
        f"    {p}_attempts = {p}_attempts + 1, "
        f"    {p}_error = ?, updated_at = sysutcdatetime() "
        f"WHERE id=? AND {p}_lease_token=?",
        (err or "")[:3900], row_id, token,
    )


def record_history(cx, label: str, role: str, from_state: str, to_state: str,
                   worker_id: str, note: str = "") -> None:
    try:
        cx.execute(
            "INSERT INTO dbo.state_history(label, pass, from_state, to_state, by_worker, note) "
            "VALUES (?,?,?,?,?,?)",
            label, role, from_state, to_state, worker_id, (note or "")[:390],
        )
    except pyodbc.Error as e:
        # observability only -- never fail the work over a history insert, but don't go silent (Hans MINOR-12)
        log("HISTORY", f"state_history insert failed for {label}/{role}->{to_state}: {str(e)[:80]}", "WARN")


# --------------------------------------------------------------------------- run one volume
def stage_args(role: str):
    """Map a pass to ocr_only_5090.py CLI flags. prep/ocr use --stage; engines use --engine."""
    if role == "prep":
        return ["--stage", "prep"]
    if role == "ocr":
        return ["--stage", "ocr"]
    # Step-2 passes are DEFERRED (R2.6): ocr_only_5090.py has no --engine/--stage consensus yet.
    # Fail loud rather than crash the subprocess and silently burn attempts -> held (Hans SERIOUS-4).
    if role in ("tess", "doctr", "surya", "consensus"):
        raise NotImplementedError(
            f"Step-2 role '{role}' not yet implemented in ocr_only_5090.py -- build the engine "
            f"refactor before enabling Step-2 rows."
        )
    raise ValueError(role)


def run_volume(role: str, row: dict, roots: dict) -> tuple[int, str]:
    """Invoke the OCR script for this pass. Returns (rc, tail_of_stderr)."""
    script = roots["script"]
    cmd = [sys.executable, str(script),
           "--inbox", roots["inbox"], "--midbox", roots["midbox"], "--outbox", roots["outbox"],
           "--label", row["label"], "--pdf", row["pdf"], *stage_args(role)]
    log("RUN", f"{role} {row['label']} START", "OK")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return proc.returncode, (proc.stderr or "")[-400:]
    return 0, ""


# --------------------------------------------------------------------------- main loop
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("worker_id")
    ap.add_argument("--role", required=True, choices=list(PASS.keys()))
    ap.add_argument("--inbox", required=True)
    ap.add_argument("--midbox", required=True)
    ap.add_argument("--outbox", required=True)
    ap.add_argument("--script", required=True, help="path to ocr_only_5090.py (3-root build)")
    ap.add_argument("--once", action="store_true", help="claim+run a single volume then exit (test mode)")
    args = ap.parse_args()

    role = args.role
    if role in ("tess", "doctr", "surya", "consensus"):
        sys.stderr.write(f"role '{role}' is a Step-2 pass -- not yet implemented (R2.6). Refusing to start.\n")
        sys.exit(2)
    roots = {"inbox": args.inbox, "midbox": args.midbox, "outbox": args.outbox, "script": args.script}
    stop_flag = Path(args.midbox).parent / f"STOP_WORKER_{args.worker_id}.flag"

    cx = connect()
    log("WORKER", f"{args.worker_id} online role={role}", "OK")

    while True:
        if stop_flag.exists():
            log("WORKER", f"{args.worker_id} stop flag seen -> graceful exit", "OK")
            return

        if PASS[role]["buffered"] and prep_buffer_full(cx):
            time.sleep(IDLE_SLEEP_SEC)
            continue

        row = claim_next(cx, role, args.worker_id)
        if not row:
            if args.once:
                log("WORKER", f"{args.worker_id} no claimable {role} work", "OK")
                return
            time.sleep(IDLE_SLEEP_SEC)
            continue

        record_history(cx, row["label"], role, row["from"], "working", args.worker_id)
        lease = Lease(connect, role, row["id"], row["lease"], args.worker_id)
        lease.start()
        try:
            rc, tail = run_volume(role, row, roots)
        except Exception as e:  # noqa: BLE001 -- any crash => failure transition
            rc, tail = 99, str(e)[:400]
        finally:
            lease.stop()

        if lease.lost:
            # fenced / DB-lost mid-run: do NOT write a terminal state (another worker owns it now).
            log("RUN", f"{role} {row['label']} ABORTED (lease lost) -- not marking", "WARN")
        elif rc == 0:
            if mark_done(cx, role, row["id"], row["lease"]):
                record_history(cx, row["label"], role, "working", "done", args.worker_id)
                log("RUN", f"{role} {row['label']} DONE", "OK")
            else:
                log("RUN", f"{role} {row['label']} completed but lease lost at commit -- skipped", "WARN")
        else:
            mark_failed(cx, role, row["id"], row["lease"], tail)
            record_history(cx, row["label"], role, "working", "failed", args.worker_id, tail[:200])
            log("RUN", f"{role} {row['label']} FAILED rc={rc}: {tail[:120]}", "FAIL")

        if args.once:
            return


if __name__ == "__main__":
    main()
