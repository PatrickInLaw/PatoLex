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

## Canonical vs. superseded ingest path (READ BEFORE INGESTING — system of record)

There are **two** parse+ingest scripts. They are NOT interchangeable. Using the
wrong one silently re-introduces lossy single-engine text and corrupts the
system of record. This was the exact "green log over an untouched lie" trap a
Hans audit caught (cc002, Phase 21 / Hans pass 3 C1).

- **`pipeline/ingest_clean.py` — CANONICAL. This is the system of record.**
  Version-B, **multi-engine token-consensus** text (UTF-8 faithful), with a
  **scoped purge-then-insert per `source_document`** inside one transaction. The
  source_document is resolved by **`content_sha256`** (content identity, read
  from `sha256.txt`), the within-run act key is **`(source_document_id,
  in_act_order)`**, and the per-volume write is **atomic**. It is **DRY-RUN by
  default** and refuses to write unless BOTH `--commit` is passed AND
  `PATOLEX_ALLOW_COMMIT=1` is set (and it connects via `PATOLEX_PG_DSN`). It also
  banks the per-token `consensus_output.json` (Phase C substrate) ONLY after a
  successful commit. It has a proper `if __name__ == "__main__":` guard.

- **`pipeline/ingest/ingest_from_ocr.py` — SPLIT ROLE. Read this carefully; the
  old blanket "SUPERSEDED / LOSSY" label was misleading and caused a real
  contradiction (Hans, 2026-07-25).**
  - Its **INGEST half is SUPERSEDED / LOSSY** — version-A, single-engine DB rows,
    replaced by `ingest_clean.py`'s consensus output. Never serve or trust its
    committed text as canonical. That is what the original warning meant.
  - Its **PARSER half (STAGE 5, `parse_volume()`) is LIVE AND CANONICAL.** It is
    the parse-side system of record, driven by `python -m ingest.parse_all`, and
    it is the file to edit for heading/date-extraction work. `ingest_clean.py`
    performs **no** heading or date extraction — it only consumes `iso_date`.
  - **PATH CORRECTION:** this file moved from `pipeline/5080/` to
    `pipeline/ingest/` in the module reorg. The stale path in this README (and in
    `docs/60_OPERATIONS/BUILD_RUNBOOK.md`) outlived the move and left two other
    modules pointing at a file that no longer existed — `test_date_parser_fix.py`
    was **dead at import for a month**, and `5080/parse_born_digital.py` was
    **unloadable**. Both fixed 2026-07-24 (cc019).
  - **HAZARD RESOLVED:** the "no `if __name__ == '__main__':` guard" warning is
    **stale** — a guard exists at `ingest_from_ocr.py:1273` (verified 2026-07-25).
    Importing the module no longer triggers a DB ingest.

**Current system of record (2026-06-02):** version-B multi-engine consensus,
**1850-1875, 4262 acts** (verified via the `ocr_provenance` / `consensus_method`
columns). `provision_version` is 0 by design (materialization is a deferred
sweep). The forward campaign (1877-1910) is OCRing now; modern-format parser
fixes are in flight and **not yet ingested.**

**Consensus engine count — 3, not 4.** `pipeline/consensus.py` uses
`N_MAX_ENGINES=3`: **Tesseract + docTR + Surya** (token majority →
`token_majority_3` / `token_majority_2` / `single`). qwen2.5vl / GOT run as
disagreement-flagging vectors only and are never committed as text.
**PaddleOCR is NOT a consensus voter**, despite older prose that listed "4
classical engines incl. PaddleOCR." The live DB confirms the code (4057
`token_majority_3` + 205 `token_majority_2`, zero 4-engine acts).

## Orchestration goal: determinism + idempotent resume (NOT boot-resilience)

> Earlier drafts of this README described an ONSTART / SYSTEM-principal
> "boot-resilience (post-power-outage auto-resume)" model. **That model was
> dropped (cc002, Phase 20):** the build is a one-time, interactive/logged-in run
> — Patrick explicitly decided open-ended auto-resume-on-reboot hardening is NOT
> needed. Do not re-implement it. The properties we actually rely on are:

1. **Idempotent resume.** Re-running a volume is safe: the shared atomic-claim
   queue (`queue_claim.py`, lock-serialized) reclaims `in_progress`/`failed`
   volumes whose heartbeat is older than `STALE_SECONDS` (1800s), and
   `ocr_only_*.py` is **checkpoint-resumable** so banked pages are never re-done
   or lost. `ingest_clean.py`'s scoped purge-then-insert makes re-ingest
   idempotent at the volume grain.
2. **Determinism.** Engine set and consensus method are pinned; the same volume
   produces the same committed consensus text.
3. **For an open-ended overnight run, the 0800 daytime backoff tasks
   (`scale_to_one_5090.ps1` / the 8AM scale-to-1 throttle) must stay DISABLED**,
   or the campaign throttles itself to one worker mid-run. Re-enable them only
   when you want the daytime throttle back.
4. **`PatoLex_Ingest_5080` (the lossy ingest watcher) stays DISABLED** until the
   parser is fixed and Hans-reviewed — it runs the superseded version-A path
   above and would write lossy rows.

See `docs/60_OPERATIONS/BUILD_RUNBOOK.md` for the full operational command
sequence.
