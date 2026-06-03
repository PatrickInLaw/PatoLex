# SQL-backed shared OCR pipeline (inbox / midbox / outbox + SQL queue)

**Status:** DESIGN for review (2026-06-03, revised post-Hans-pass-1; REVISION 2 = MSSQL authoritative). Replaces JSON-over-SSH + box-local prep with a distributed pipeline. Nothing deployed; the JSON-queue campaign keeps running until cutover.

## BUILD SEQUENCE — TWO STEPS (decided 2026-06-03, Patrick)
The redesign ships in **two clearly-separated steps**, NOT one monolith and NOT three+ small phases:

- **STEP 1 — SQL shared pipeline WITH prep/OCR decoupling folded in.** One cohesive lift: the 3060 file server (inbox→midbox→outbox shares) + the dedicated MSSQL queue (lease/fencing) + the prep/OCR role split + the 3-root `ocr_only` refactor + the supervised cutover. The prep-decouple and the SQL pipeline **share the same worker rewrite**, so they are built together rather than as two cutovers.
  - **The box-local prep-decouple build (commit `445bea1`: `prep_supervisor.ps1`, `cutover_decouple_migration.py`, the `--role`/`--stage` split in `queue_worker.py`/`ocr_only_5090.py`) is RETIRED — superseded, NOT deployed.** Its *role/stage-split design* is reused (folded into the SQL workers); its box-local JSON-coordination code is discarded.
  - Rationale (recorded so it isn't re-litigated): the hard, risky surface (cross-box SMB auth, the midbox partial-file race, the MSSQL lease/claim semantics) is all in Step 1 and is reviewed against one diff; the campaign keeps running on the JSON queue until a single quiesced cutover.

- **STEP 2 — engine-decoupling (async per-engine passes).** Orthogonal to Step 1: split the single inline `ocr` pass into per-engine passes mapped to hardware (5090 = Surya farm; 5080/3060 = Tesseract/docTR). The **per-pass column-groups (`tess_/doctr_/surya_/consensus_`) are built into the Step-1 schema on day one** (R2.2), inert (`na`) until enabled per-row at seed — so Step 2 is **additive: no schema change, no migration, no re-architecture.** Only the per-engine + consensus-merge *worker code* (and the empirical engine→box mapping) is deferred, until Step 1 is proven and throughput is re-measured GPU-fed. Do NOT build any Step-2 worker code during Step 1.

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

**This section supersedes §1 (auth), §2 (Postgres schema/claim), AND the §3 single-`state` machine above** — the per-pass columns (R2.2) replace the single lifecycle column. Patrick's PM decisions (2026-06-03): queue lives in a **dedicated DB on the 3060's existing MSSQL**; **no new user** — reuse the existing `patolex` local account; **centralize PDFs on the 3060 inbox**; **single wide row per volume, a column-group per pass, NO child/dependency table (KISS)**; the Step-2 engine passes are built into the schema now (inert) so engine-decoupling is additive. Everything else above (§4 store flow + barrier, §5 worker fencing, §6 cutover order, §7 ingest handoff, §8 observability) stands unless restated here.

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

## R2.2 Schema — MSSQL DDL: ONE ROW PER VOLUME, ONE COLUMN-GROUP PER PASS (KISS, no child rows)
Dedicated DB on the 3060 MSSQL (e.g. `PatoLexQueue`). **Decision (Patrick, 2026-06-03): single wide row per volume, a column-group per pass — NO child/dependency table.** "Is this volume's consensus ready?" is then a single-row predicate (`WHERE surya_state='done' AND ...`), never a cross-row join. The table is built **complete and final on day one** (cheaper than `ALTER`-ing a live queue later); the Step-2 passes sit inert (`state='na'`) until turned on per-row at seed time — zero schema change to enable Step 2.

**Per-pass convention.** Every pass `P` carries the *identical* 8-column group, so the lease/claim/heartbeat code is written ONCE and parameterized by the prefix `P_`:
`P_state` (`pending`|`working`|`done`|`failed`|`held`|`na`), `P_attempts`, `P_lease_token`, `P_lease_expires_at`, `P_claimed_by`, `P_heartbeat_at`, `P_done_at`, `P_error`. Per-pass output paths are derived (`outbox\<label>\<pass>\`), not stored — KISS.

```sql
-- run once against the dedicated DB (CREATE DATABASE PatoLexQueue; USE it)
CREATE TABLE dbo.ocr_queue (
  id    bigint IDENTITY(1,1) PRIMARY KEY,
  label nvarchar(200) NOT NULL UNIQUE,
  pdf   nvarchar(500) NOT NULL,
  yr    int           NOT NULL,            -- NOT NULL: NULL sorts last, never runs

  -- ===== PASS: prep (CPU render+preprocess+classify) — used in BOTH steps =====
  prep_state  nvarchar(20) NOT NULL DEFAULT 'pending',
  prep_attempts int NOT NULL DEFAULT 0,
  prep_lease_token uniqueidentifier NULL, prep_lease_expires_at datetime2 NULL,
  prep_claimed_by nvarchar(100) NULL, prep_heartbeat_at datetime2 NULL,
  prep_done_at datetime2 NULL, prep_error nvarchar(max) NULL,

  -- ===== PASS: ocr (STEP-1 coarse: all 3 engines + consensus inline, today's behavior) =====
  ocr_state  nvarchar(20) NOT NULL DEFAULT 'pending',
  ocr_attempts int NOT NULL DEFAULT 0,
  ocr_lease_token uniqueidentifier NULL, ocr_lease_expires_at datetime2 NULL,
  ocr_claimed_by nvarchar(100) NULL, ocr_heartbeat_at datetime2 NULL,
  ocr_done_at datetime2 NULL, ocr_error nvarchar(max) NULL,

  -- ===== STEP-2 PASSES — built now, inert ('na') until enabled per-row at seed =====
  -- tesseract (CPU, 5080/3060)
  tess_state nvarchar(20) NOT NULL DEFAULT 'na',
  tess_attempts int NOT NULL DEFAULT 0,
  tess_lease_token uniqueidentifier NULL, tess_lease_expires_at datetime2 NULL,
  tess_claimed_by nvarchar(100) NULL, tess_heartbeat_at datetime2 NULL,
  tess_done_at datetime2 NULL, tess_error nvarchar(max) NULL,
  -- docTR (light GPU, 5080/3060)
  doctr_state nvarchar(20) NOT NULL DEFAULT 'na',
  doctr_attempts int NOT NULL DEFAULT 0,
  doctr_lease_token uniqueidentifier NULL, doctr_lease_expires_at datetime2 NULL,
  doctr_claimed_by nvarchar(100) NULL, doctr_heartbeat_at datetime2 NULL,
  doctr_done_at datetime2 NULL, doctr_error nvarchar(max) NULL,
  -- Surya (heavy GPU, 5090)
  surya_state nvarchar(20) NOT NULL DEFAULT 'na',
  surya_attempts int NOT NULL DEFAULT 0,
  surya_lease_token uniqueidentifier NULL, surya_lease_expires_at datetime2 NULL,
  surya_claimed_by nvarchar(100) NULL, surya_heartbeat_at datetime2 NULL,
  surya_done_at datetime2 NULL, surya_error nvarchar(max) NULL,
  -- consensus merge (reads the 3 engine outputs, produces 2-of-3 canonical text)
  consensus_state nvarchar(20) NOT NULL DEFAULT 'na',
  consensus_attempts int NOT NULL DEFAULT 0,
  consensus_lease_token uniqueidentifier NULL, consensus_lease_expires_at datetime2 NULL,
  consensus_claimed_by nvarchar(100) NULL, consensus_heartbeat_at datetime2 NULL,
  consensus_done_at datetime2 NULL, consensus_error nvarchar(max) NULL,

  -- experimental-VLM sandbox: throw N candidate disagreement-vector models at a page
  -- WITHOUT touching the canonical row/consensus; promote a proven one to its own column-group later.
  vlm_sandbox  nvarchar(max) NULL,         -- JSON: {model: {state,result_path,...}}

  done_at    datetime2 NULL,               -- volume fully complete (mirrors OCR_COMPLETE marker)
  updated_at datetime2 NOT NULL DEFAULT sysutcdatetime()
);
-- one filtered index per claimable pass keeps each role's claim scan tiny:
CREATE INDEX ix_prep      ON dbo.ocr_queue(yr,id) WHERE prep_state='pending';
CREATE INDEX ix_ocr       ON dbo.ocr_queue(yr,id) WHERE ocr_state='pending';
CREATE INDEX ix_tess      ON dbo.ocr_queue(yr,id) WHERE tess_state='pending';
CREATE INDEX ix_doctr     ON dbo.ocr_queue(yr,id) WHERE doctr_state='pending';
CREATE INDEX ix_surya     ON dbo.ocr_queue(yr,id) WHERE surya_state='pending';
CREATE INDEX ix_consensus ON dbo.ocr_queue(yr,id) WHERE consensus_state='pending';

CREATE TABLE dbo.state_history (
  id        bigint IDENTITY(1,1) PRIMARY KEY,
  label     nvarchar(200) NOT NULL,
  pass      nvarchar(20)  NOT NULL,        -- prep|ocr|tess|doctr|surya|consensus
  from_state nvarchar(20) NULL, to_state nvarchar(20) NOT NULL,
  at        datetime2 NOT NULL DEFAULT sysutcdatetime(),
  by_worker nvarchar(100) NULL, note nvarchar(400) NULL
);
CREATE INDEX ix_state_history_label ON dbo.state_history(label, at);
```
**Step-1 vs Step-2 per row (config flip at seed, not a schema change):**
- **Step-1 row:** `prep_state='pending'`, `ocr_state='pending'`, all Step-2 passes `='na'`. The `ocr` pass runs all 3 engines + consensus inline (today's `ocr_only` behavior).
- **Step-2 row:** `prep_state='pending'`, `ocr_state='na'`, `tess/doctr/surya='pending'`, `consensus='pending'` (gated by the claim predicate). Same table, same lease code, just which columns are live.

A pass in state `na` is **never claimable** (every claim predicate matches only `state='pending'` or an expired-lease `working`/`failed`), so inert passes cost nothing. Adding a *vetted* new engine = one `ALTER TABLE ADD` of its 8-column group + a config entry; experimental VLMs go in `vlm_sandbox` JSON first and get promoted only when proven.

## R2.3 Atomic claim — MSSQL lease pattern (replaces `FOR UPDATE SKIP LOCKED`)
MSSQL's skip-locked equivalent is the canonical Rusanu idiom: **`READPAST, UPDLOCK, ROWLOCK` on the INNER candidate-select only**, and **`UPDLOCK, ROWLOCK` (NO `READPAST`) on the OUTER target**. (Hans pass-2 BLOCKER-1: `READPAST` on the outer `FROM` both opens a double-claim window and causes silent no-op false-negatives when the row is already UPDLOCK'd — it must NOT be there.) Each claim rotates `lease_token` and sets an **absolute** `lease_expires_at`.

**One generic claim, parameterized by the pass prefix `P_`** — written once, reused for every pass. The only thing that varies per pass is the predicate (`P` = the prefix, `@dur` = lease minutes). Shown for `prep`; `ocr`, `tess`, `doctr`, `surya` are identical with their own prefix:
```sql
DECLARE @worker nvarchar(100) = ?, @lease uniqueidentifier = NEWID();
UPDATE q
   SET prep_state='working',
       prep_lease_token=@lease, prep_lease_expires_at = DATEADD(minute, 45, sysutcdatetime()),
       prep_claimed_by=@worker, prep_heartbeat_at=sysutcdatetime()
  OUTPUT inserted.id, inserted.label, inserted.pdf, inserted.prep_lease_token
  FROM dbo.ocr_queue AS q WITH (UPDLOCK, ROWLOCK)              -- outer target: NO READPAST
 WHERE q.id = (
    SELECT TOP (1) q2.id
      FROM dbo.ocr_queue AS q2 WITH (READPAST, UPDLOCK, ROWLOCK)   -- inner candidate: READPAST skips claimed rows
     WHERE ( q2.prep_state='pending'
          OR (q2.prep_state IN ('working','failed') AND q2.prep_lease_expires_at < sysutcdatetime()) )
     ORDER BY q2.yr, q2.id
 );
```
**Each pass gates on its predecessor — all single-row predicates, NO joins** (the KISS payoff):
- **prep:** `prep_state='pending'` (or expired-lease reclaim). *(Buffer-bound — below.)*
- **ocr (Step 1):** `ocr_state='pending' AND prep_state='done'`.
- **tess / doctr / surya (Step 2):** e.g. `tess_state='pending' AND prep_state='done'`.
- **consensus (Step 2):** `consensus_state='pending' AND tess_state='done' AND doctr_state='done' AND surya_state='done'` — readiness is a glance at the volume's own row, never a cross-row count.

**Prep buffer bound is enforced in the WORKER LOOP, NOT in the claim SQL** (Hans pass-2 BLOCKER-2): an in-claim correlated `COUNT(*)` against the same table the outer UPDATE holds UPDLOCK on **deadlocks** under concurrent prep workers (A locks row X reads row Y; B locks row Y reads row X → err 1205) and overshoots under READ COMMITTED anyway. So before the prep claim, the worker runs a **standalone** `SELECT COUNT(*) FROM dbo.ocr_queue WHERE ocr_state='working' OR (prep_state='done' AND ocr_state='pending')`; if `>= PREP_BUFFER_MAX` (3) it idles. Bounded overshoot by ≤(#prep workers − 1) accepted; the buffer is a soft throttle.

All claims run with **autocommit ON** — `pyodbc.connect(..., autocommit=True)` on the CONNECTION before first use (Hans pass-2 MINOR-10: pyodbc defaults to autocommit=False; a forgotten commit leaves a row `working` with no committer, invisible until lease expiry). If `OUTPUT` returns no row, the role idles (prep WAITs on buffer; OCR/engines exit or WAIT per supervisor policy).

**`P_attempts` increments on FAILURE ONLY, not on claim** (Hans pass-2 BLOCKER-3): incrementing on every (re)claim dead-letters a legitimately *slow* volume — a 25-min OCR exceeds a short lease, gets reclaimed, 5 reclaims → `held` = a corpus gap from slowness, not failure. So (a) the lease is **45 min** (covers worst-case multi-hundred-page 300-DPI OCR with margin), and (b) `P_attempts = P_attempts + 1` is set only by the **failure transition** (non-zero exit), never by the claim. The dead-letter guard (`P_attempts >= 5 → P_state='held'`) therefore counts real failures only.

## R2.4 Fencing + heartbeat + dead-letter (MSSQL)
- **Heartbeat extends the lease ONLY if the token still matches** (the fence — a stale worker whose row was reclaimed cannot extend, so it learns it lost the row):
```sql
-- P = the active pass prefix (prep/ocr/tess/doctr/surya/consensus):
UPDATE dbo.ocr_queue
   SET prep_heartbeat_at = sysutcdatetime(),
       prep_lease_expires_at = DATEADD(minute, 45, sysutcdatetime())
 WHERE id = ? AND prep_lease_token = ?;   -- @@ROWCOUNT = 0  =>  this worker was fenced; self-abort before any write
```
The worker checks `@@ROWCOUNT`/affected-rows after each heartbeat; **0 ⇒ self-abort before writing any result to outbox** (resolves S3 stale-reclaim double-write). (Heartbeat lease extension uses the SAME 45-min window as the claim — keep them equal.)
- **DB-unreachable self-abort + clock skew (Hans pass-2 SERIOUS-8):** when the DB is unreachable the worker cannot ask whether its lease still holds, so it must decide on its LOCAL clock — which is NOT immune to cross-box skew the way the server-clock `lease_expires_at` is. Two mitigations, both required: (1) **NTP sync across all three boxes is a documented Step-1 prerequisite** (w32time against a common source); (2) the worker self-aborts at **50% of the lease window** of unreachable-DB time (≈22 min of a 45-min lease), not at 100% — a conservative margin that tolerates several minutes of skew before the server-side lease can expire and be reclaimed. Never run headless past that.
- **Dead-letter (Hans pass-2 MINOR-11):** `P_attempts` is incremented only by the failure transition, and the SAME statement routes `>= 5 → held` atomically (`UPDATE ... SET prep_state = CASE WHEN prep_attempts+1 >= 5 THEN 'held' ELSE 'failed' END, prep_attempts = prep_attempts+1 WHERE id=? AND prep_lease_token=?`). This avoids a separate pre-claim guard that could be skipped on exception. `held` is never auto-claimed (claim predicates match only `pending` or an expired-lease `working`/`failed`). Surface `held` in monitoring.
- **Result-commit fence:** the worker writes its output to a `P_claimed_by`-scoped temp path, and the final `P_state='done'` (+ `P_done_at`) UPDATE is **also** guarded by `AND P_lease_token = ?` — so even a TOCTOU between the last heartbeat and the done-write cannot let a fenced worker mark done.

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

## R2.6 Step 2 (engine-decoupling) — schema built now, WORKER CODE deferred
The **schema is built complete in Step 1** (R2.2) — the `tess_/doctr_/surya_/consensus_` column-groups exist on day one, inert (`na`). Enabling Step 2 is a **per-row config flip at seed** (set those to `pending`, set `ocr_state='na'`), NOT a schema change. The claim/lease/heartbeat code is already generic over the pass prefix (R2.3), so a per-engine worker is the same worker with a different prefix + the engine-gated predicate.

**What is deferred to Step 2 is only the new CODE, and only because its value is unmeasurable until Step 1 is live:**
1. A **single-engine OCR mode** in `ocr_only` (`--engine tesseract|doctr|surya`) that runs ONE engine and writes its raw per-engine output to `outbox\<label>\<engine>\`, instead of the all-3-inline `ocr` pass.
2. A **consensus-merge step** that reads the three engine outputs off the outbox and produces the 2-of-3 canonical text — genuinely new code (today consensus is in-memory in one process; from three independently-written artifacts it must align page/token indices), with its own failure modes → its own Hans pass.
3. The **engine→box mapping + worker counts** (5090=Surya, 5080/3060=Tess/docTR) — empirical, tuned live after Step 1, the schema is indifferent to it.

Nothing in Step 1 is built against this; the schema simply doesn't block it. Experimental VLM disagreement-vectors live in `vlm_sandbox` (JSON) until one proves out and earns a promoted column-group.
