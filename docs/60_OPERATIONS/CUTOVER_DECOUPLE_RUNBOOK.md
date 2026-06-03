# Cutover runbook -- decoupled prep/OCR pipeline (5090)

**Status:** Code complete + Hans-reviewed (3 passes, GO for a SUPERVISED cutover). Deploy with the operator present, NOT unattended. The live campaign keeps producing on the proven coupled 3/1 until this runs, so there's no time pressure.

## What this deploys
Splits the 5090 per-volume pipeline into a **prep pool** (CPU render/preprocess/classify, BelowNormal, fills a bounded buffer of `prepped` volumes) and an **OCR pool** (GPU-only, consumes `prepped`). The 5080 stays on its current coupled pipeline and coexists on the shared queue. New queue statuses: `prepping`, `prepped`, `ocring`, `ocr_failed` (5090-only) alongside the existing `pending`/`in_progress`(5080)/`done`/`failed`/`held`.

Files (repo -> deploy to `C:\Users\patolex\PatoLex-scratch\`):
`ocr_only_5090.py` (--stage), `queue_worker.py` (--role), `supervisor_5090.ps1` (--role ocr + glob), NEW `prep_supervisor.ps1`, NEW `cutover_decouple_migration.py`, and `archive_images.py` (status-set fix, used only when idle).

## Preconditions
- Permission mode allows PowerShell + Bash without per-command prompts (Shift+Tab bypass, or /permissions allow).
- **Back up `production_queue_state.json`** (copy aside) before the migration -- it's the rollback anchor.
- Operator present to eyeball the migration dry-run.

## Steps (in order -- do NOT reorder; drain before migrate)
1. **Verify the live task target.** Confirm the `PatoLex_OCR_5090` scheduled-task action runs `supervisor_5090.ps1`, and that `supervisor_5090.ps1`/`prep_supervisor.ps1` resolve `queue_worker.py` from `C:\Users\patolex\PatoLex-scratch\` -- NOT any `pipeline\5090-scale\` copy. (Highest-risk item: a stale coupled worker that doesn't understand `prepped` kills the decouple.)
2. **Deploy the new scripts** to scratch (scp), sha256-verify each against the repo.
3. **Drain.** Set global `STOP_WORKER.flag` (and/or `max_workers.txt`=0); stop the 5080 worker too. Let in-flight volumes FINISH (they checkpoint). Stop the old OCR supervisor task. **Verify no `python.exe` running `queue_worker`/`ocr_only` remains** (worker_pids dead) before migrating -- the migration must not rewrite a status out from under a live process.
4. **Migration -- dry run first.** `python cutover_decouple_migration.py` (no flag). Eyeball every line: each `5090-*` in_progress -> `done`/`prepped`/`pending`; every SKIP must be a genuine `5080-*` owner. **Watch for a "ghost"**: an in_progress with blank/other worker_id is SKIPPED and would strand -- if any appears, set it to `pending` by hand first. If it aborts "lock wait exceeded", remove a stale `production_queue_state.lock` and retry.
5. **Migration -- commit.** `python cutover_decouple_migration.py --commit`. Re-read the queue; confirm no orphaned `5090-*` in_progress remains.
6. **Prep config + task.** Write `max_prep_workers.txt` (=2). Register `PatoLex_Prep_5090` scheduled task -> `prep_supervisor.ps1` (run-as that works for the per-user python; restart-on-failure).
7. **Start prep.** Run the prep task; watch `prep_supervisor.log` -- buffer fills toward `PREP_BUFFER_MAX=3`. Wait until >=1 volume is `prepped`.
8. **Clear `STOP_WORKER.flag`. Start the OCR supervisor** (`PatoLex_OCR_5090`, now launches `--role ocr`). Confirm OCR workers claim `prepped` and pages advance (not just PID presence).
9. **Restart the 5080 worker** (stays coupled, claims `pending`).
10. **Verify ~15 min:** prep + OCR both producing; GPU stays fed (util doesn't dip into long prep valleys); no label appears in two non-terminal statuses at once; `OCR_COMPLETE.marker` written on done. Then it's running.

## Standing rules
- **Archiver runs only against an idle/drained queue** -- never alongside active prep/OCR (its eligibility read is a snapshot; a `prepped->ocring` flip mid-run could race). 
- Office-hours scale-down currently scales the OCR pool (`max_workers.txt`). If CPU-fan noise during meetings matters, also have the office scripts set `max_prep_workers.txt` low. (Optional follow-up.)

## Rollback
Redeploy the previous `queue_worker.py`/`supervisor_5090.ps1` from git, restore the backed-up `production_queue_state.json`, restart the coupled task. Banked prep/OCR on disk is preserved (idempotent), so coupled workers resume cleanly.
