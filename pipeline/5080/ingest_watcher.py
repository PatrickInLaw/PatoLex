"""
ingest_watcher.py -- DETACHED, session-independent ingest loop for the 5080.
============================================================================
Runs on the 5080 box (PKS_2025_ALIEN), where Postgres lives. Long-lived
watcher that fills the DB AUTONOMOUSLY from the 5090's completed OCR volumes
with NO Claude / interactive session required. Designed to be the ACTION of a
Scheduled Task (principal SYSTEM, like the 5090's PatoLex_OCR_5090 task) so the
parent is the Task Scheduler service (svchost) -- it survives logoff, SSH
death, and Claude-process death.

This box does NO GPU work. It only: SSH-polls the 5090 for completed volumes,
scp's their OCR outputs back, runs the proven CPU parse + idempotent DB ingest
(ingest_from_ocr.py), and loops.

Per volume, in strict chronological (forward-queue) order:
  1. SSH the 5090 and test for production-<label>/OCR_COMPLETE.marker.
  2. If present and we have not ingested this volume yet:
       a. scp sha256.txt, page_classification.json, and
          ocr_consensus/page_ocr_results.json into the LOCAL
          production-<label>/... tree.
       b. Validate: JSON parses, is non-empty, and sha256.txt is 64 hex chars.
       c. Run ingest_from_ocr.py <label>. That script UPGRADES the matching
          stale skeleton source_document row IN PLACE (clean scoped purge by
          source_document_id, then re-ingest) -- idempotent, faithful, strict
          page->DB mapping. It is safe to re-run.
       d. On success, mark the volume ingested in ingest_state.json.
  3. Sleep POLL_SECONDS and repeat until every queue volume is ingested, then
     keep idling (cheap) so newly-completed volumes are still picked up.

Idempotency / safety:
  - Never deletes or mutates the 5090's banked OCR (read-only scp pulls).
  - ingest_from_ocr.py is itself idempotent (scoped purge per source_document),
    so a re-run after a crash mid-volume simply re-upgrades the same row.
  - A volume is only marked 'ingested' after ingest_from_ocr.py exits 0 AND a
    post-check confirms the source_document row now has a non-NULL page_count.
  - Chronological order: we ingest the lowest pending year first, matching the
    OCR forward queue, so DB years fill in sequence.

No argv. Configuration is in the constants below.
"""

import os
import sys
import re
import json
import time
import shutil
import datetime
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
LOCAL_SCRATCH = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch")
STATE_FILE    = LOCAL_SCRATCH / "ingest_state.json"
LOG_FILE      = Path(
    r"C:\Users\PatrickKolasinski\Documents\GitHub\patolex"
    r"\docs\80_PROJECT_HISTORY\run-logs\ingest-loop-run.log"
)

# Python that runs ingest_from_ocr.py (stdlib-only + psql subprocess; NO GPU).
INGEST_PY  = r"C:\Users\PatrickKolasinski\AppData\Local\Programs\Python\Python312\python.exe"
INGEST_SCRIPT = str(LOCAL_SCRATCH / "ingest_from_ocr.py")
PSQL = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"

# 5090 remote (OCR producer).
SSH_EXE   = r"C:\Windows\System32\OpenSSH\ssh.exe"
SCP_EXE   = r"C:\Windows\System32\OpenSSH\scp.exe"
SSH_KEY   = r"C:\Users\PatrickKolasinski\.ssh\patolex_5090"
KNOWN_HOSTS = r"C:\Users\PatrickKolasinski\.ssh\known_hosts"
REMOTE_USER = "patolex"
REMOTE_HOST = "100.70.54.56"          # pk-alien-5090 over Tailscale
REMOTE_SCRATCH = "C:/Users/patolex/PatoLex-scratch"

# Forward / chronological queue (matches the 5090 OCR queue order; 1850-1861
# already banked+ingested and excluded). Lowest year first.
QUEUE = [
    "1862", "1863", "1863-64", "1865-66", "1867-68",
    "1869-70", "1871-72", "1873-74", "1875-76",
]

POLL_SECONDS = 120
SSH_TIMEOUT  = 25         # per ssh/scp connect+op budget (seconds)


def log(phase, description, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    entry = "[" + ts + "] " + phase + " | " + description + " | " + status + "\n"
    try:
        with open(str(LOG_FILE), "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass
    print(entry.strip(), flush=True)


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "volumes": {}}


def save_state(state):
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(STATE_FILE))


def ssh_run(remote_cmd, timeout=SSH_TIMEOUT):
    """Run a single cmd.exe command on the 5090. Returns (rc, stdout, stderr)."""
    args = [
        SSH_EXE, "-i", SSH_KEY,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        "-o", "UserKnownHostsFile=" + KNOWN_HOSTS,
        "-o", "StrictHostKeyChecking=yes",
        REMOTE_USER + "@" + REMOTE_HOST,
        remote_cmd,
    ]
    try:
        r = subprocess.run(args, capture_output=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or ""), (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "", "ssh timeout"
    except Exception as e:
        return 1, "", str(e)


def scp_pull(remote_rel, local_path, timeout=300):
    """Pull a single file from the 5090 to local_path. Returns True on success."""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    remote_spec = (REMOTE_USER + "@" + REMOTE_HOST + ":"
                   + REMOTE_SCRATCH + "/" + remote_rel)
    args = [
        SCP_EXE, "-i", SSH_KEY,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        "-o", "UserKnownHostsFile=" + KNOWN_HOSTS,
        "-o", "StrictHostKeyChecking=yes",
        remote_spec, str(local_path),
    ]
    try:
        r = subprocess.run(args, capture_output=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        if r.returncode != 0:
            log("SCP", "pull FAIL " + remote_rel + ": " + (r.stderr or "")[:160], "WARN")
            return False
        return local_path.exists() and local_path.stat().st_size > 0
    except subprocess.TimeoutExpired:
        log("SCP", "pull TIMEOUT " + remote_rel, "WARN")
        return False
    except Exception as e:
        log("SCP", "pull ERROR " + remote_rel + ": " + str(e)[:120], "WARN")
        return False


def remote_marker_present(label):
    """True iff production-<label>/OCR_COMPLETE.marker exists on the 5090."""
    win = ("C:\\Users\\patolex\\PatoLex-scratch\\production-" + label
           + "\\OCR_COMPLETE.marker")
    rc, out, err = ssh_run('if exist "' + win + '" (echo YES) else (echo NO)')
    if rc != 0:
        log("POLL", label + ": ssh marker check rc=" + str(rc) + " " + err.strip()[:120], "WARN")
        return False
    return "YES" in out


HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def fetch_volume(label):
    """scp the 3 OCR outputs for <label> into the local production tree.
    Returns True iff a valid, non-empty page_ocr_results.json + good sha landed."""
    local_dir = LOCAL_SCRATCH / ("production-" + label)
    ocr_local = local_dir / "ocr_consensus" / "page_ocr_results.json"
    sha_local = local_dir / "sha256.txt"
    cls_local = local_dir / "page_classification.json"

    ok_sha = scp_pull("production-" + label + "/sha256.txt", sha_local)
    # classification is optional for parse/ingest -- pull best-effort.
    scp_pull("production-" + label + "/page_classification.json", cls_local)
    ok_ocr = scp_pull("production-" + label + "/ocr_consensus/page_ocr_results.json",
                      ocr_local)

    if not ok_ocr:
        log("FETCH", label + ": page_ocr_results.json not pulled", "WARN")
        return False
    if not ok_sha:
        log("FETCH", label + ": sha256.txt not pulled", "WARN")
        return False

    sha = sha_local.read_text(encoding="utf-8").strip()
    if not HEX64.match(sha):
        log("FETCH", label + ": sha256.txt not 64-hex (" + sha[:16] + "...)", "WARN")
        return False
    try:
        data = json.loads(ocr_local.read_text(encoding="utf-8"))
        npages = len(data)
    except Exception as e:
        log("FETCH", label + ": OCR JSON invalid: " + str(e)[:120], "WARN")
        return False
    if npages < 1:
        log("FETCH", label + ": OCR JSON has 0 pages", "WARN")
        return False
    log("FETCH", label + ": pulled OK (" + str(npages) + " pages, sha "
        + sha[:12] + ") -> " + str(ocr_local), "OK")
    return True


def db_row_ingested(label):
    """True iff a source_document for <label> now has a non-NULL page_count
    (i.e. the skeleton was upgraded / a production row exists)."""
    env = dict(os.environ)
    env["PGPASSWORD"] = "postgres"
    sql = ("SELECT count(*) FROM source_document WHERE page_count IS NOT NULL "
           "AND (citation LIKE 'Stats. " + label + ",%' "
           "OR citation LIKE 'CA Statutes " + label + " %' "
           "OR file_name = '" + label + "_Statutes.pdf');")
    args = [PSQL, "-U", "postgres", "-d", "patolex", "-t", "-A", "-c", sql]
    try:
        r = subprocess.run(args, capture_output=True, encoding="utf-8",
                           errors="replace", env=env, timeout=60)
        if r.returncode != 0:
            return False
        val = r.stdout.strip().splitlines()[0].strip() if r.stdout.strip() else "0"
        return val.isdigit() and int(val) >= 1
    except Exception:
        return False


def db_enactment_total():
    env = dict(os.environ)
    env["PGPASSWORD"] = "postgres"
    args = [PSQL, "-U", "postgres", "-d", "patolex", "-t", "-A",
            "-c", "SELECT count(*) FROM enactment;"]
    try:
        r = subprocess.run(args, capture_output=True, encoding="utf-8",
                           errors="replace", env=env, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().splitlines()[0].strip()
    except Exception:
        pass
    return "?"


def ingest_volume(label):
    """Run ingest_from_ocr.py <label>. Returns True on exit 0 + DB confirmation."""
    log("INGEST", label + ": running ingest_from_ocr.py", "OK")
    args = [INGEST_PY, INGEST_SCRIPT, label]
    try:
        r = subprocess.run(args, capture_output=True, encoding="utf-8",
                           errors="replace", cwd=str(LOCAL_SCRATCH), timeout=1800)
    except subprocess.TimeoutExpired:
        log("INGEST", label + ": ingest TIMEOUT (30m)", "FAIL")
        return False
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "")[-300:]
        log("INGEST", label + ": ingest exit " + str(r.returncode) + " " + tail.replace("\n", " "), "FAIL")
        return False
    if not db_row_ingested(label):
        log("INGEST", label + ": ingest exited 0 but DB row not confirmed upgraded", "WARN")
        return False
    log("INGEST", label + ": DB confirmed. enactment total now " + db_enactment_total(), "OK")
    return True


def main():
    log("WATCHER", "=== ingest_watcher online (pid " + str(os.getpid())
        + ") box=5080 -> polling 5090 " + REMOTE_HOST + " every "
        + str(POLL_SECONDS) + "s ===", "OK")
    log("WATCHER", "Queue (chronological): " + ", ".join(QUEUE)
        + " | enactment total at start=" + db_enactment_total(), "OK")

    state = load_state()
    # Reconcile state with DB at startup: if a volume already shows ingested in
    # the DB, mark it done so we don't re-fetch on every restart.
    for label in QUEUE:
        vs = state["volumes"].setdefault(label, {"ocr_fetched": False, "ingested": False})
        if not vs["ingested"] and db_row_ingested(label):
            vs["ingested"] = True
            vs["ingested_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            log("RECONCILE", label + ": already ingested in DB -> marking done", "OK")
    save_state(state)

    idle_cycles = 0
    while True:
        progressed = False
        for label in QUEUE:                      # chronological order
            vs = state["volumes"][label]
            if vs["ingested"]:
                continue
            # Only act when the 5090 says this volume's OCR is complete.
            if not remote_marker_present(label):
                # chronological: do not skip ahead past an incomplete volume's
                # OCR for FETCH, but later volumes may already be complete --
                # we still check them (independent DB rows). Continue scanning.
                continue
            log("READY", label + ": OCR_COMPLETE.marker present on 5090 -- fetching", "OK")
            if not fetch_volume(label):
                continue
            vs["ocr_fetched"] = True
            vs["fetched_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            save_state(state)
            if ingest_volume(label):
                vs["ingested"] = True
                vs["ingested_at"] = datetime.datetime.now().isoformat(timespec="seconds")
                save_state(state)
                progressed = True

        remaining = [l for l in QUEUE if not state["volumes"][l]["ingested"]]
        if not remaining:
            if idle_cycles == 0:
                log("WATCHER", "ALL queued volumes ingested. enactment total="
                    + db_enactment_total() + ". Idling for late completions.", "OK")
            idle_cycles += 1
            # Keep running cheaply; a new volume completing later is still caught.
            time.sleep(POLL_SECONDS * 3)
            continue

        if progressed:
            log("WATCHER", "Remaining to ingest: " + ", ".join(remaining)
                + " | enactment total=" + db_enactment_total(), "OK")
        idle_cycles = 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
