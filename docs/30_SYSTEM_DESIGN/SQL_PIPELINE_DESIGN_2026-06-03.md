# SQL-backed shared OCR pipeline (inbox / midbox / outbox + SQL queue)

**Status:** DESIGN for review (2026-06-03, revised post-Hans-pass-1; REVISION 2 = MSSQL authoritative). Replaces JSON-over-SSH + box-local prep with a distributed pipeline. Nothing deployed; the JSON-queue campaign keeps running until cutover.

## BUILD SEQUENCE — TWO STEPS (decided 2026-06-03, Patrick)
The redesign ships in **two clearly-separated steps**, NOT one monolith and NOT three+ small phases:

- **STEP 1 — SQL shared pipeline WITH prep/OCR decoupling folded in.** One cohesive lift: the 3060 file server (inbox→midbox→outbox shares) + the dedicated MSSQL queue (lease/fencing) + the prep/OCR role split + the 3-root `ocr_only` refactor + the supervised cutover. The prep-decouple and the SQL pipeline **share the same worker rewrite**, so they are built together rather than as two cutovers.
  - **The box-local prep-decouple build (commit `445bea1`: `prep_supervisor.ps1`, `cutover_decouple_migration.py`, the `--role`/`--stage` split in `queue_worker.py`/`ocr_only_5090.py`) is RETIRED — superseded, NOT deployed.** Its *role/stage-split design* is reused (folded into the SQL workers); its box-local JSON-coordination code is discarded.
  - Rationale (recorded so it isn't re-litigated): the hard, risky surface (cross-box SMB auth, the midbox partial-file race, the MSSQL lease/claim semantics) is all in Step 1 and is reviewed against one diff; the campaign keeps running on the JSON queue until a single quiesced cutover.

- **STEP 2 — engine-decoupling (async per-engine passes).** Orthogonal to Step 1: split the single `consensus` pass into per-engine passes mapped to hardware (5090 = Surya farm; 5080/3060 = Tesseract/docTR). It rides the `stage` extension column the Step-1 schema already carries, so it is **additive — no migration of Step-1 rows, no re-architecture.** Deferred until Step 1 is proven and worker counts are re-measured GPU-fed. Do NOT build any Step-2 code during Step 1.

Cost accepted: `445bea1` is throwaway (the end-state shifted under it). The benefit — one cohesive, independently-verifiable lift with the risk concentrated and the campaign never dark — is worth it. See REVISION 2 for the authoritative Step-1 schema/claim/auth.

## DECISIONS LOCKED (2026-06-03, Patrick)
1. **Queue DB = a dedicated database on the 3060's MSSQL** (NOT the project Postgres). It's installed, configured, networked, and already used from all three computers (per the PatoAudio repo — conn info there). Reachability is therefore settled. The claim uses MSSQL `UPDATE ... WITH (READPAST, UPDLOCK, ROWLOCK) ... OUTPUT` (skip-locked semantics) instead of Postgres `FOR UPDATE SKIP LOCKED`.
2. **Richer queue schema** (Patrick: "the first few issues are best resolved by a richer queue DB"): use a proper LEASE/FENCING model — `lease_token` + `lease_expires_at`, extended on each heartbeat; a worker writes results only if its token is still current; a row is reclaimable only after lease expiry. Plus `attempts` + a `held` dead-letter terminal, and a `state_history` audit table. This is the clean resolution of B1 (failure handling), S2 (buffer race, enforced in-claim) and S3 (stale-reclaim double-write) — replacing the ad-hoc fencing below.
3. STILL SEPARATE (filesystem, not DB — a richer DB does NOT fix these): **B2 midbox partial-file barrier** (tmp-dir + atomic rename + `PREP_COMPLETE` marker + decode-validate) and **S6 SMB auth** (`patolexsvc` account + `cmdkey`). Keep both.
**RESOLVED (Patrick, 2026-06-03 PM):**
- (a) **No new user.** Reuse the EXISTING `patolex` local account (already on the 3060 — the SSH target — and the 5090). Grant the three shares to `patolex` (share + NTFS ACL). The 5090 workers authenticate natively; the 5080 stores the `patolex@3060` credential via `cmdkey`. **Workers run as `patolex` (a real user, not SYSTEM)** so the stored credential is usable — this resolves S6 without creating an account. (Confirm `patolex` exists on the 5080 too, or use cmdkey in the PatrickKolasinski context.)
- (b) **Centralize the source PDFs on the 3060 inbox share** (one-time copy from the 5080 master archive).
- **Engine-decoupling = Phase 2 (design for it now, build later):** the engines (Tesseract=CPU, docTR=light, Surya=heavy) are mismatched to hardware; running them as async per-engine passes (5090 = Surya farm, 5080/3060 = Tesseract/docTR) is worth doing AFTER prep-decoupling ships. So the schema below carries an **`engine`/`pass` dimension + a `consensus` stage** as an extension point — adding Phase 2 is then additive, not a re-architecture.

See "REVISION 2" below for the authoritative MSSQL schema/claim + auth (supersedes the Postgres §1/§2 draft).

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

---

# REVISION 2 — AUTHORITATIVE (MSSQL + reuse `patolex` account)

**This section supersedes §1 (auth) and §2 (Postgres schema/claim) above.** Patrick's PM decisions (2026-06-03): queue lives in a **dedicated DB on the 3060's existing MSSQL**; **no new user** — reuse the existing `patolex` local account; **centralize PDFs on the 3060 inbox**; **engine-decoupling is Phase 2** but the schema carries the extension dimension now. Everything else above (§3 state machine, §4 store flow + barrier, §5 worker fencing, §6 cutover order, §7 ingest handoff, §8 observability) stands unchanged unless restated here.

## R2.1 Auth — reuse the existing `patolex` account (no new user)
The 3060 already has a `patolex` local account (it is the SSH target and the 5090's worker account). We grant the three shares to **that** account and run the workers **as `patolex`** (a real interactive/service identity, never SYSTEM — SYSTEM authenticates as `MACHINE$` and cannot present `cmdkey`-stored user creds). This resolves S6 with zero new accounts.

```powershell
# --- on the 3060, ELEVATED (operator runs once; agent session is non-elevated/UAC-walled) ---
$root = 'D:\PatoLex-pipeline'                      # SSD or HDD per Patrick — either is fine
New-Item -ItemType Directory -Force -Path "$root\inbox","$root\midbox","$root\outbox" | Out-Null
foreach ($s in 'inbox','midbox','outbox') {
  New-SmbShare  -Name "patolex_$s" -Path "$root\$s" -FullAccess '<3060HOST>\patolex'
  icacls        "$root\$s" /grant '<3060HOST>\patolex:(OI)(CI)F'
}
# Tailnet-only exposure (NEVER public) — matches the SSH firewall recipe in memory:
Set-NetFirewallRule -Name 'FPS-SMB-In-TCP' -Enabled True -RemoteAddress 100.64.0.0/10
```
Replace `<3060HOST>` with the 3060's actual machine name (the local-account domain). The **5090** workers already run as `patolex` on the 3060's own box if co-located, but for cross-box mounts each non-3060 box stores the credential **in the account context the worker runs as**:
```powershell
# on the 5080 (and 5090 if it is a separate box from the file server), in the worker's run-as context:
cmdkey /add:<3060-tailscale-ip> /user:<3060HOST>\patolex /pass:<PATOLEX-PASS>
```
**Run-as resolution (closes old Open #2):** workers run as `patolex`, NOT SYSTEM. If the office-hours / OCR Scheduled Tasks currently run as SYSTEM, they are re-registered to run as `patolex` (stored password, "Run whether user is logged on or not"). Confirm `patolex` exists on the 5080; if not, either create it there with the same name/pass or store the cred in the existing `PatrickKolasinski` context and run the 5080 workers as `PatrickKolasinski`. **This re-registration needs operator elevation (UAC)** — bundle it into the elevated 3060/5080 setup scripts.

## R2.2 Schema — MSSQL DDL (lease/fencing + dead-letter + state_history + engine/pass extension)
Dedicated DB on the 3060 MSSQL (e.g. `PatoLexQueue`). `NEWID()` lease tokens are the fencing primitive; `lease_expires_at` (absolute, server-clock) drives reclaim so we never compare a worker's clock to the row's.

```sql
-- run once against the dedicated DB (e.g. CREATE DATABASE PatoLexQueue; then USE it)
CREATE TABLE dbo.ocr_queue (
  id              bigint IDENTITY(1,1) PRIMARY KEY,
  label           nvarchar(200) NOT NULL UNIQUE,
  pdf             nvarchar(500) NOT NULL,
  yr              int           NOT NULL,                 -- NOT NULL: NULL sorts last and would never run
  state           nvarchar(50)  NOT NULL DEFAULT 'pending',
                  -- pending|prepping|prepped|ocring|done|ocr_failed|held
  -- Phase-2 engine/pass extension dimension (unused in Phase 1; defaults make it inert):
  stage           nvarchar(50)  NOT NULL DEFAULT 'consensus', -- consensus | tesseract | doctr | surya
  attempts        int           NOT NULL DEFAULT 0,
  lease_token     uniqueidentifier NULL,                 -- fencing token; rotated on each claim
  lease_expires_at datetime2    NULL,                     -- absolute server-clock expiry
  claimed_by      nvarchar(100) NULL,
  claimed_at      datetime2     NULL,
  heartbeat_at    datetime2     NULL,
  done_at         datetime2     NULL,
  error           nvarchar(max) NULL,
  updated_at      datetime2     NOT NULL DEFAULT sysutcdatetime()
);
CREATE INDEX ix_ocr_queue_state_yr ON dbo.ocr_queue(state, yr, id);

CREATE TABLE dbo.state_history (
  id         bigint IDENTITY(1,1) PRIMARY KEY,
  label      nvarchar(200) NOT NULL,
  from_state varchar(20)   NULL,
  to_state   varchar(20)   NOT NULL,
  at         datetime2     NOT NULL DEFAULT sysutcdatetime(),
  by_worker  nvarchar(100) NULL,
  note       nvarchar(400) NULL
);
CREATE INDEX ix_state_history_label ON dbo.state_history(label, at);
```
**Phase-1 invariant:** every row carries `stage='consensus'` (the single end-to-end 2-of-3 pass we run today). The `stage` column is the *only* thing Phase 2 adds rows/values to (per-engine passes + a consensus-merge row), so Phase 2 is additive — no migration of Phase-1 rows. Keep `state` orthogonal to `stage`: `state` is the lifecycle, `stage` is which engine/pass.

## R2.3 Atomic claim — MSSQL lease pattern (replaces `FOR UPDATE SKIP LOCKED`)
MSSQL's skip-locked equivalent is the canonical Rusanu idiom: **`READPAST, UPDLOCK, ROWLOCK` on the INNER candidate-select only**, and **`UPDLOCK, ROWLOCK` (NO `READPAST`) on the OUTER target**. (Hans pass-2 BLOCKER-1: `READPAST` on the outer `FROM` both opens a double-claim window and causes silent no-op false-negatives when the row is already UPDLOCK'd — it must NOT be there.) Each claim rotates `lease_token` and sets an **absolute** `lease_expires_at`.

**Prep-role claim:**
```sql
DECLARE @worker nvarchar(100) = ?, @lease uniqueidentifier = NEWID();
UPDATE q
   SET state='prepping',
       lease_token=@lease, lease_expires_at = DATEADD(minute, 45, sysutcdatetime()),
       claimed_by=@worker, claimed_at=sysutcdatetime(), heartbeat_at=sysutcdatetime()
  OUTPUT inserted.id, inserted.label, inserted.pdf, inserted.lease_token
  FROM dbo.ocr_queue AS q WITH (UPDLOCK, ROWLOCK)              -- outer target: NO READPAST
 WHERE q.id = (
    SELECT TOP (1) q2.id
      FROM dbo.ocr_queue AS q2 WITH (READPAST, UPDLOCK, ROWLOCK)   -- inner candidate: READPAST skips claimed rows
     WHERE q2.stage='consensus'
       AND ( q2.state='pending'
          OR (q2.state='prepping' AND q2.lease_expires_at < sysutcdatetime()) )  -- expired-lease reclaim
     ORDER BY q2.yr, q2.id
 );
```
**OCR-role claim** (reclaims expired `ocring` and backed-off `ocr_failed`):
```sql
DECLARE @worker nvarchar(100) = ?, @lease uniqueidentifier = NEWID();
UPDATE q
   SET state='ocring',
       lease_token=@lease, lease_expires_at = DATEADD(minute, 45, sysutcdatetime()),
       claimed_by=@worker, claimed_at=sysutcdatetime(), heartbeat_at=sysutcdatetime()
  OUTPUT inserted.id, inserted.label, inserted.pdf, inserted.lease_token
  FROM dbo.ocr_queue AS q WITH (UPDLOCK, ROWLOCK)              -- outer target: NO READPAST
 WHERE q.id = (
    SELECT TOP (1) q2.id
      FROM dbo.ocr_queue AS q2 WITH (READPAST, UPDLOCK, ROWLOCK)
     WHERE q2.stage='consensus'
       AND ( q2.state='prepped'
          OR (q2.state IN ('ocring','ocr_failed') AND q2.lease_expires_at < sysutcdatetime()) )
     ORDER BY q2.yr, q2.id
 );
```
**Buffer bound is enforced in the WORKER LOOP, NOT in the claim SQL** (Hans pass-2 BLOCKER-2): an in-claim correlated `(SELECT COUNT(*) ... state IN ('prepped','ocring'))` against the same table the outer UPDATE holds UPDLOCK on **deadlocks** under concurrent prep workers (A locks row X reads row Y; B locks row Y reads row X → err 1205) AND can overshoot under READ COMMITTED anyway. So before issuing the prep claim, the prep worker runs a **standalone** `SELECT COUNT(*) FROM dbo.ocr_queue WHERE state IN ('prepped','ocring')`; if `>= PREP_BUFFER_MAX` (3) it idles and does not claim. This is exactly what `queue_worker.py` does today in the caller. Bounded overshoot by ≤(#concurrent prep workers − 1) is accepted and documented; the buffer is a soft throttle, not a hard invariant.

Both run with **autocommit ON** — set `pyodbc.connect(..., autocommit=True)` on the CONNECTION before first use (Hans pass-2 MINOR-10: pyodbc defaults to autocommit=False; a forgotten commit leaves the row `prepping` with no committer, invisible until lease expiry). If `OUTPUT` returns no row, the role idles (prep WAITs; OCR exits/WAITs per supervisor policy).

**`attempts` increments on FAILURE ONLY, not on claim** (Hans pass-2 BLOCKER-3): incrementing on every (re)claim dead-letters a legitimately *slow* volume — a 25-min OCR exceeds a short lease, gets reclaimed, and 5 reclaims → `held` = a corpus gap from slowness, not failure. So (a) the lease is **45 min** (covers worst-case multi-hundred-page 300-DPI OCR with margin), and (b) `attempts = attempts + 1` is set by the **failure transition** (non-zero exit → `pending`/`ocr_failed`), never by the claim. The dead-letter guard (`attempts >= 5 → held`) therefore counts real failures only.

## R2.4 Fencing + heartbeat + dead-letter (MSSQL)
- **Heartbeat extends the lease ONLY if the token still matches** (the fence — a stale worker whose row was reclaimed cannot extend, so it learns it lost the row):
```sql
UPDATE dbo.ocr_queue
   SET heartbeat_at = sysutcdatetime(),
       lease_expires_at = DATEADD(minute, 20, sysutcdatetime())
 WHERE id = ? AND lease_token = ?;        -- @@ROWCOUNT = 0  =>  this worker was fenced; self-abort before any write
```
The worker checks `@@ROWCOUNT`/affected-rows after each heartbeat; **0 ⇒ self-abort before writing any result to outbox** (resolves S3 stale-reclaim double-write).
- **DB-unreachable self-abort + clock skew (Hans pass-2 SERIOUS-8):** when the DB is unreachable the worker cannot ask whether its lease still holds, so it must decide on its LOCAL clock — which is NOT immune to cross-box skew the way the server-clock `lease_expires_at` is. Two mitigations, both required: (1) **NTP sync across all three boxes is a documented Step-1 prerequisite** (w32time against a common source); (2) the worker self-aborts at **50% of the lease window** of unreachable-DB time (≈22 min of a 45-min lease), not at 100% — a conservative margin that tolerates several minutes of skew before the server-side lease can expire and be reclaimed. Never run headless past that.
- **Dead-letter (Hans pass-2 MINOR-11):** `attempts` is incremented only by the failure transitions (R2.3), and the SAME failure-transition statement routes `attempts >= 5 → held` atomically (`UPDATE ... SET state = CASE WHEN attempts+1 >= 5 THEN 'held' ELSE 'ocr_failed' END, attempts = attempts+1 WHERE id=? AND lease_token=?`). This avoids a separate pre-claim guard that could be skipped on exception. `held` is never auto-claimed (both claim predicates match only `pending`/`prepped` or expired-lease `prepping`/`ocring`/`ocr_failed`). Surface `held` in monitoring.
- **Result-commit fence:** the worker writes its checkpoint to a `claimed_by`-scoped temp path, and the final `state='done'` (+ `done_at`) UPDATE is **also** guarded by `AND lease_token = ?` — so even a TOCTOU between the last heartbeat and the done-write cannot let a fenced worker mark done.

## R2.5 What carries over unchanged
- **§4 file-side barrier (B2):** still mandatory and DB-independent — prep writes to `pages_prep_gray.tmp/`, atomic dir-rename, `PREP_COMPLETE` marker last, *then* flips SQL to `prepped`; OCR requires SQL `prepped` **AND** marker present **AND** each PNG `cv2.imread`-decodes. The richer DB does not fix partial-file visibility on SMB.
- **§3 state machine, §6 cutover order (drain JSON → snapshot+seed → deploy → start prep → start OCR → retire JSON), §7 ingest-from-outbox, §8 state_history observability:** unchanged.
- **Connection:** workers use a 3060-MSSQL connection string (pyodbc + ODBC Driver 18, `Encrypt`/`TrustServerCertificate` per the existing PatoAudio config) deployed to each box's gitignored dotenv — NOT `DATABASE_URL` (that's the project Postgres). Conn details come from the cloned PatoAudio/kolalawdb repo; values never enter the repo or logs.

## R2.7 Cutover-of-in-flight, ingest handoff, and the `ocr_only` refactor (Hans pass-2 SERIOUS 6/7/9)
- **In-flight-at-cutover checkpoints DO NOT resume cross-box (SERIOUS-7).** A volume `ocring` at snapshot has its `page_ocr_results.json` checkpoint on the *local* 5090/5080 scratch, NOT on the outbox UNC. After cutover an OCR worker on a different box cannot see it, so the volume **re-OCRs from scratch** — correct output, wasted time. Two acceptable handlings, decide at build: (a) the seed script copies in-flight checkpoints from the local scratch to `outbox/production-<label>/ocr_consensus/` before seeding (true resume), or (b) accept full re-OCR of the ~0–5 in-flight volumes and **document it** (do not silently imply resume). Default: (b) — the count is tiny and (a) adds cross-box copy risk at the most fragile moment.
- **Ingest handoff is a Step-1 deliverable, not a TODO (SERIOUS-9).** Concretely: ingest runs **on the 3060** (co-located with both the queue DB and the outbox share → no UNC hop, no cross-box auth for the read path), **as `patolex`**. It gets TWO connection strings in its gitignored dotenv: the **MSSQL queue** conn (poll `state='done'`) and the existing project **`DATABASE_URL`** Postgres conn (write statutes). It reads results from the local `outbox\production-<label>\` path. `ingest_clean.py` is repointed from its current local-poll to: poll queue `done` → read outbox path → ingest → (optional) mark an `ingested_at`. This must work before Step 1 is "done" or completed OCR produces no DB rows.
- **The 3-root `ocr_only` refactor is the HIGHEST-RISK code change (SERIOUS-6)** — it rewrites every path in the proven production OCR script (today all derive from one `SCRATCH_ROOT`) to take `--inbox/--midbox/--outbox`. A silent path mistake writes results to the wrong place with no error. Required: test `--stage prep` then `--stage ocr` against a known volume on **local** paths first (shares not yet involved), verify outputs land correctly AND the legacy single-root `<pdf> <label>` invocation still works, THEN test against UNC roots. Build this behind the existing `--stage` split, not as a rewrite.
- **cv2 decode-fail on SMB → retry, then fail (SERIOUS-15):** a `cv2.imread`→None on the midbox can be a transient SMB hiccup, not a partial write. The OCR worker retries the single page N times with backoff before treating the volume as not-prepped; a persistent None → `ocr_failed` (reclaimable), never a silent page-skip.
- **ODBC prereq (NIT-14):** ODBC Driver 18 + pyodbc must be installed in the Python env on **all three** boxes (today only the 3060 has the MSSQL client per PatoAudio) — a documented Step-1 setup step.

## R2.8 RESOLVED — NO new account needed (verified on the 5080, 2026-06-03)
**Checked directly on the 5080.** Facts:
- **No `patolex` local account exists on the 5080.** `Get-LocalUser` shows only built-ins + Codex sandbox accounts. The interactive account is **`azuread\patrickkolasinski`** (an Azure-AD account — absent from `Get-LocalUser`).
- The `PatoLex_OCR_5080` task runs as **`PatrickKolasinski` with `LogonType=Interactive`**.

**DECISION (Patrick: do NOT create new local accounts): keep the 5080 worker running as the EXISTING `PatrickKolasinski` account — create nothing.** Cross-box SMB auth only requires the account to exist on the **server** (the 3060), which it does (`patolex`). The 5080 *client* simply stores that remote credential:
```powershell
cmdkey /add:<3060-tailscale-ip> /user:<3060HOST>\patolex /pass:<PATOLEX-PASS>   # in the PatrickKolasinski profile
```
SMB connections to `\\<3060>\patolex_*` then authenticate AS the 3060's `patolex`. This works precisely because the 5080 task runs as a **real user** (not SYSTEM — SYSTEM was the only context that couldn't use `cmdkey` user creds). **MSSQL:** use the existing PatoAudio connection — **confirm it is SQL authentication** (SQL login + password in the conn string, not a Windows login); if so, no Windows account is involved on the DB side either. (If PatoAudio turns out to use Windows auth, revisit — but SQL auth is the expected case.) Net: **zero new accounts on any box.**

**SEPARATE, OPTIONAL reliability item (NOT required, NOT account-related):** the 5080 task's `LogonType=Interactive` is **why the 5080 OCR dies on logoff/session-reset** (the 07:41 straggler in `LESSON_2026-06-03_ops...` §4). It is a pre-existing fragility, independent of the SQL rework, and the pipeline works without touching it. A clean fix wants a non-interactive ("run whether logged on or not") logon, which is fiddly for an Azure-AD account (must store its password) — so it is left as an explicit OPEN OPTIONAL for Patrick, not a Step-1 requirement. Do not create an account to solve it unless Patrick decides the reliability is worth it.

## R2.6 Phase 2 (engine-decoupling) — extension point only, do NOT build yet
When prep-decoupling is proven, Phase 2 splits the single `consensus` stage into per-engine passes that run on the hardware that fits them (5090 = Surya farm; 5080/3060 = Tesseract/docTR). The schema already supports it: insert per-engine rows (`stage IN ('tesseract','doctr','surya')`) keyed to the same `label`, plus a `consensus` row that becomes claimable once its N engine rows are `done`. The claim predicates gain `AND stage = @role_stage`; no Phase-1 row changes. Captured here so we design Phase 1 to not block it — nothing in Phase 1 is built against it.
