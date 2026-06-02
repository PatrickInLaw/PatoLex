# pipeline/ — version-controlled OCR + ingest pipeline scripts

Read-only snapshots of the load-bearing scripts that run the one-time
1850-forward historical corpus build. The **live** copies the scheduled tasks
execute are in each box's `PatoLex-scratch` directory; these repo copies are for
version control and disaster recovery, and are marked read-only so they are not
mistaken for the running originals.

## Layout

- `5080/` — the ingest box (`PKS_2025_ALIEN`, hosts PostgreSQL 16). No GPU OCR
  for the campaign except its own worker. Polls the 5090 for completed OCR,
  scp's it back, and runs the idempotent CPU parse + DB ingest.
  - `ingest_supervisor.ps1` — long-lived watcher supervisor (task ACTION)
  - `ingest_watcher.py` — DB-fill loop; **reconciles against the DB on startup**
  - `ingest_from_ocr.py` — idempotent per-volume parse + ingest (scoped purge)
  - `reparse.py`, `re_ingest_fixed.py`, `production_pipeline.py` — parse/build
  - `queue_worker_5080.py`, `ocr_only_5080.py`, `queue_claim.py` — the 5080's OCR
    worker + the shared atomic claim engine (run on the 5090)
  - `doctr_warmup_5080.py`, `register_ingest_task_5080.ps1`, `stop_5080_worker.ps1`
  - `*.json` — queue/ingest state schemas (point-in-time snapshots)

- `5090/` — the OCR producer (`PK_Alien_5090`, RTX 5090). Runs N queue workers.
  - `supervisor_5090.ps1` — long-lived worker supervisor (task ACTION); dynamic
    worker count via `max_workers.txt`; self-relaunches dead workers
  - `queue_worker.py` — per-worker OCR loop; claims lowest-year pending volume
  - `queue_claim.py` — atomic, lock-serialized claim engine. **Stale-claim
    recovery built in:** an `in_progress`/`failed` volume whose heartbeat is
    older than `STALE_SECONDS` (1800s) is reclaimable on the next claim cycle.
  - `ocr_only_5090.py` — per-volume OCR; **resumable from checkpoint** so a
    reclaimed volume continues; banked pages are never re-done or lost
  - `scale_to_one_5090.ps1` — 8AM daily scale-to-1 (daytime throttle)
  - register scripts, `launch_workers_5090.ps1`, `ocr_batch_5090.py`

## Boot resilience (post-power-outage auto-resume)

After a power outage + reboot, the campaign resumes with no agent and no manual
trigger because:

1. **PostgreSQL** service (5080) StartType = Automatic → DB back up on boot.
2. **At-startup (ONSTART) triggers** fire the scheduled tasks:
   - 5090 `PatoLex_OCR_5090` (SYSTEM) → `supervisor_5090.ps1` relaunches workers.
   - 5080 `PatoLex_OCR_5080` + `PatoLex_Ingest_5080` (SYSTEM) → relaunch the
     5080 worker + ingest watcher.
3. **Stale-claim reclamation:** each relaunched OCR worker's first action is
   `claim_next`, which reclaims any `in_progress` volume left by the crash
   (stale heartbeat) back to claimable. Resumable OCR continues from checkpoint.
4. **Ingest reconcile:** the watcher checks the DB on startup, marks already-
   ingested volumes done, and resumes the chronological fill (idempotent ingest).

The 8AM scale/backoff tasks keep their **daily** trigger only (no ONSTART) so a
reboot does not throttle the campaign to one worker.

> NOTE: the 5080 task edits (ONSTART trigger, SYSTEM principal, no-battery)
> require an elevated run of `5080/_lockdown_apply_5080.ps1` if not yet applied —
> see the lockdown run-log. The 5090 task is already boot-resilient.
