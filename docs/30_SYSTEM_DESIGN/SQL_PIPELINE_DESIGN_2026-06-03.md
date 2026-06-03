# SQL-backed shared OCR pipeline (inbox / midbox / outbox + SQL queue)

**Status:** DESIGN for review (2026-06-03, revised post-Hans-pass-1). Replaces JSON-over-SSH + box-local prep with a distributed pipeline. Nothing deployed; the JSON-queue campaign keeps running until cutover.

## Why
The queue belongs in a DB. File-lock-over-SSH is fragile. A SQL work-queue gives atomic concurrent claims (`FOR UPDATE SKIP LOCKED`); a shared file store lets idle CPUs on every box preload one pool any GPU drains, so GPUs never wait on prep.

## Topology
**3060 = file server + queue-DB host** (most RAM, central, big disk).
- Shares on the 3060: **inbox** (source PDFs) → CPU prep → **midbox** (prepped pages) → GPU OCR → **outbox** (results + markers).
- **Queue:** `ocr_queue` table in the project **PostgreSQL** (`DATABASE_URL`). One DB for the project. (Fallback: 3060 MSSQL per PatoAudio — same schema.) **Open #1:** confirm the DB accepts connections from all three Tailnet IPs.
- **GPU-concurrency rationale (corrected, per `LESSON_2026-06-02`):** the old caps (5090≤3, 5080=1) were **CPU-prep-contention / compute** limits, NOT VRAM (Surya is ~1–5 GB; 16 GB holds 2). Decoupling prep onto the 3060/idle cores **removes the 5090's prep-contention cap** — so the 5090 GPU-worker count is re-derived empirically from GPU sharing once buffer-fed (likely >3), not copied. The 5080 stays compute-bound (start at 1, test 2). We tune these live after cutover; they are no longer VRAM-driven.

## 1. SMB shares + auth (run ELEVATED on the 3060)
Cross-machine SMB is the trap: the boxes have **different local accounts** (`patolex`, `PatrickKolasinski`) and workers under tasks run as **SYSTEM** (which authenticates as `MACHINE$`). Modern Windows **disables guest logons**, so `-FullAccess Everyone` will be *refused* on first connect. Real auth model:
```powershell
# --- on the 3060, elevated ---
# 1. a dedicated service account the workers authenticate AS:
net user patolexsvc <STRONGPASS> /add
net localgroup Users patolexsvc /add
$root = 'D:\PatoLex-pipeline'
New-Item -ItemType Directory -Force -Path "$root\inbox","$root\midbox","$root\outbox" | Out-Null
# 2. share + NTFS grant to that account (share ACL AND NTFS ACL both matter):
foreach ($s in 'inbox','midbox','outbox') {
  New-SmbShare -Name "patolex_$s" -Path "$root\$s" -FullAccess 'PK_XPS\patolexsvc'
  icacls "$root\$s" /grant 'PK_XPS\patolexsvc:(OI)(CI)F'
}
Set-NetFirewallRule -Name 'FPS-SMB-In-TCP' -Enabled True -RemoteAddress 100.64.0.0/10  # Tailnet only
```
On **each 5-series box**, store the credential so workers (incl. SYSTEM tasks) can mount the UNC:
```powershell
cmdkey /add:<3060-tailscale-ip> /user:PK_XPS\patolexsvc /pass:<STRONGPASS>   # run in the worker's account context
```
**Open #2 (must verify):** SYSTEM-context tasks reaching the share. Cleanest fix may be to **run the workers as the `patolexsvc` user (stored creds) instead of SYSTEM**, since SYSTEM can't use `cmdkey` user creds. Decide the run-as before cutover.

## 2. SQL schema + atomic claim (PostgreSQL)
```sql
CREATE TABLE IF NOT EXISTS ocr_queue (
  id bigserial PRIMARY KEY,
  label text UNIQUE NOT NULL,
  pdf   text NOT NULL,
  yr    int NOT NULL,                 -- NOT NULL: NULL would sort to the back and never run
  state text NOT NULL DEFAULT 'pending', -- pending|prepping|prepped|ocring|done|ocr_failed|held
  attempts int NOT NULL DEFAULT 0,
  claimed_by text, claimed_at timestamptz, heartbeat_at timestamptz,
  done_at timestamptz, error text,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ocr_queue_state_yr ON ocr_queue(state, yr);
-- maintain updated_at on every change:
CREATE OR REPLACE FUNCTION ocr_queue_touch() RETURNS trigger AS $$ BEGIN NEW.updated_at=now(); RETURN NEW; END $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_ocr_queue_touch BEFORE UPDATE ON ocr_queue FOR EACH ROW EXECUTE FUNCTION ocr_queue_touch();
```
**Atomic claim** (prep role) — buffer bound folded INTO the claim so it can't TOCTOU-overshoot:
```sql
UPDATE ocr_queue SET state='prepping', claimed_by=$1, claimed_at=now(), heartbeat_at=now()
WHERE id = (
  SELECT id FROM ocr_queue
  WHERE (state='pending' OR (state='prepping' AND heartbeat_at < now()-interval '20 min'))
    AND (SELECT count(*) FROM ocr_queue WHERE state IN ('prepped','ocring')) < 3   -- buffer bound, evaluated atomically
  ORDER BY yr, id FOR UPDATE SKIP LOCKED LIMIT 1
) RETURNING id, label, pdf;
```
OCR role claim: `WHERE state='prepped' OR (state IN ('ocring','ocr_failed') AND heartbeat_at < now()-interval '20 min')` (no buffer bound). Runs in its **own committed transaction** (autocommit off, explicit commit — a forgotten commit = every worker re-claims the same row).

## 3. State machine (explicit — closes the strand/crash-loop)
```
pending --prep--> prepping --ok--> prepped --ocr--> ocring --ok(+marker)--> done
prepping --fail--> pending (attempts++)            ocring --fail--> ocr_failed (attempts++)
ocr_failed --(reclaimed by OCR role after backoff)--> ocring
ANY role, attempts >= 5 --> held   (dead-letter; never auto-claimed; surfaced in monitoring)
```
- **prep-fail → `pending`** (re-preppable). **ocr-fail → `ocr_failed`**, reclaimed by the **OCR role** only, after the stale/backoff window — prevents a poison volume from tight-looping. (In the shared model the checkpoint lives on the *shared* outbox, so any OCR worker can safely resume it — the old box-local poach hazard is gone; but we keep the distinct state for backoff + clarity.)
- **`attempts >= 5` → `held`** dead-letter so a bad PDF stops spinning.
- **Idempotency:** the `OCR_COMPLETE` marker in outbox is the on-disk truth; `done` in SQL mirrors it. Seed/claim treat marker-present as `done`.

## 4. Store flow + the partial-file barrier (closes the cross-box race)
`ocr_only_*.py` needs a real **three-root refactor** (today everything derives from one `SCRATCH_ROOT`): take `--inbox --midbox --outbox` roots.
- **inbox:** source PDF (read-only).
- **midbox/`production-<label>`/:** `pages_raw`, `pages_prep_gray`, `page_classification.json` (prep output / OCR input).
- **outbox/`production-<label>`/:** `ocr_consensus/page_ocr_results.json` (checkpoint) + `OCR_COMPLETE.marker`.
**Barrier — `prepped` must mean "all input bytes durably visible":** prep writes pages to `pages_prep_gray.tmp/` then does ONE atomic directory rename to `pages_prep_gray/`, writes a `PREP_COMPLETE` marker (temp+rename) as the **last** write, *then* flips SQL state to `prepped`. The OCR worker requires (a) SQL `prepped`, (b) the `PREP_COMPLETE` marker present, and (c) **each PNG decodes** (`cv2.imread` non-None) before use — a decode failure is treated as "prep not done," not "skip page." **OCR reads `page_classification.json` from midbox to get the body-page list and does NOT re-run classify** (classify runs once, in prep — deterministic, no cross-box divergence).

## 5. Workers
- New `queue_worker_sql.py --role {prep,ocr}` (psycopg **v3**, explicit-commit claim). Replaces `queue_worker.py` + `queue_worker_5080.py` + `queue_claim.py` (SSH/scp path deleted).
- **Fencing against stale-reclaim double-write (S3):** the worker re-reads `claimed_by` on every heartbeat; if it's no longer this worker, it **self-aborts before writing any result**. Checkpoint is written to a `claimed_by`-scoped temp, promoted to the canonical outbox path only on success. A heartbeat that can't reach the DB for > the stale window forces self-abort (don't run headless). Stale window 20 min vs 60 s heartbeat.
- **Graceful drain carries over:** keep the `STOP_WORKER.flag` + per-worker stop flags + the drain-budget ("first-to-finish stops") logic, so office-hours scale-down still works.
- **Secret on all 3 boxes:** `DATABASE_URL` (+ the share creds) deployed to each box (dotenv, gitignored) — today it lives only on the 5080.

## 6. Migration + cutover (ordered to avoid double-processing)
1. **You (elevated, 3060):** run §1 (shares + `patolexsvc` + firewall). Confirm DB reachable from all 3 (Open #1).
2. **Me:** `CREATE TABLE ocr_queue`. Centralize/point inbox at PDFs.
3. **Drain the JSON-queue workers to 0 FIRST** (graceful — in-flight volumes finish; no orphans).
4. **THEN snapshot + seed** (`seed_ocr_queue.py`): port the 106 volumes (done→`done`; anything still in-flight at snapshot is carried as `prepped`/`pending` by disk state, never claimed by both systems) **+ append the 1976–1999 chapters (100 vols / ~180k pages)** — this is where "extend to 2000" lands.
5. **Then deploy SQL workers**, start prep pool (fills midbox) then OCR pool; verify rows flow pending→…→done and files flow inbox→midbox→outbox.
6. Retire the JSON queue + SSH/scp.

## 7. Outbox → ingest handoff
The TS/Drizzle ingest currently polls a local `production-<label>` tree. After cutover, outputs live on the **outbox UNC**; ingest polls the SQL `done` state (single source of truth) and reads results from the outbox path. Specify the run-as + the path before cutover (don't improvise it).

## 8. Observability
A `state_history(label, from_state, to_state, at, by)` insert on each transition (or a trigger), plus standard queries: counts by state, `held` dead-letters, oldest `prepping`/`ocring` (stuck detection), throughput from `done_at`. Replaces the greppable-JSON visibility we're giving up.

## Open decisions for you
1. **Queue DB reachable from all 3 boxes?** (Postgres vs 3060-MSSQL fallback.) — biggest item.
2. **Worker run-as for SMB:** run workers as `patolexsvc` (stored creds, simplest for share auth) vs SYSTEM (can't use cmdkey creds). 
3. **Inbox:** centralize PDFs onto the 3060 (clean, one-time ~GB copy) vs point inbox at the existing per-box archive.
4. GPU worker counts are now tuned live post-cutover (not VRAM-bound) — start 5090=3 / 5080=1, raise the 5090 since prep no longer contends.
