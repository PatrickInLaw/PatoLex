# BUILD RUNBOOK — historical corpus OCR + ingest

**Status:** Operational entry point for the one-time 1850-forward historical corpus build. Written cc002, 2026-06-02, to close the "no deterministic orchestration doc" gap (COLD_START_DOC_AUDIT_2026-06-02 §TOP GAPS #1). This is the single resume point for the multi-day build.

**Scope:** the **historical OCR + ingest** pipeline (image-only Chief Clerk session laws). The modern era is a different channel — see `docs/30_SYSTEM_DESIGN/DATA_SOURCES.md` (leginfo PUBINFO XML).

> Authoritative companions: `pipeline/README.md` (canonical-vs-lossy ingest), `docs/30_SYSTEM_DESIGN/DATA_SOURCES_HISTORICAL.md` §1d (three-tier model), `docs/80_PROJECT_HISTORY/MODERN_STATUTE_FORMAT_2026-06-02.md` (modern parser spec).

---

## 0. The corpus and which method per tier (DO NOT OCR the wrong tier)

The Chief Clerk backbone is **653 PDFs, 1850-2008** (258 body volumes, 413,987 body pages; per-volume counts in `C:\Users\PatrickKolasinski\PatoLex-scratch\corpus_page_counts.csv`). Three tiers, three methods — full detail in `DATA_SOURCES_HISTORICAL.md` §1d:

| Tier | Era | Method | Script |
|------|-----|--------|--------|
| (a) Image-only | **1850 – ~1996** | **OCR** (multi-engine consensus) | the OCR pipeline below (`ocr_only_*.py`) |
| (b) Born-digital Chief Clerk | **~1997 – 2008** | **Direct text extract, NO OCR** | `pipeline/5080/parse_born_digital.py` |
| (c) Modern structured | **1989/1994 – present** | Bulk import + reconstruct backward from chaptered bill XML | leginfo PUBINFO (separate channel, `DATA_SOURCES.md`) |

**The OCR campaign (tier a) is bounded on the modern end at ~1993-94, NOT 2008.** Years after ~1996 are born-digital (b) or covered by structured XML (c). The image-only/born-digital crossover is **~1997, exact volume TBD** — tighten it to the volume before the OCR campaign reaches it. **Do not OCR the born-digital tail.**

**Format eras → parser path:**
- **1850 – ~1910:** single-volume/year; `CHAP. N / An Act / do enact / Approved <date>` (Roman chapters; OCR-fuzzy on long-s 1850s-1870s scans). → the pre-1900 OCR-fuzzy parser.
- **~1915+:** multi-volume/year (`Vol1_Chapters`..`VolN`), **chapters numbered continuously across volumes of a year** → roll volumes up into one chapter stream.
- **Modern (~1997+ born-digital):** `Approved by Governor <date> / Filed with Secretary of State <date>`, Arabic chapters, **no bill markers** → `parse_born_digital.py`. Modern-format parser fixes are **in flight and un-ingested** as of 2026-06-02.

---

## 1. Infrastructure topology

- **5090** (`PK_Alien_5090`, RTX 5090, 32 GB) — the **strong OCR node**: 3-engine consensus. Hosts the **shared queue** (`production_queue_state.json`) that both nodes claim from. Tailscale IP `100.70.54.56`.
- **5080** (`PKS_2025_ALIEN`, RTX 5080, 16 GB) — **also a valid 1-worker consensus OCR node** (docTR offline-load fix is in `pipeline/5080/ocr_only_5080.py`), AND the **ingest box** that hosts local **PostgreSQL 16** (`postgres`/`postgres`@5432, DB `patolex`; `psql` at `C:\Program Files\PostgreSQL\16\bin\psql.exe`).
- Communication over **Tailscale**; SSH recipe in memory `ssh-over-tailscale-recipe`. Secrets at `C:\Users\PatrickKolasinski\Documents\PatoLex-secrets.env`.

**Scheduled Tasks (Windows Task Scheduler):**
- `PatoLex_OCR_5090` → `pipeline/5090/supervisor_5090.ps1` (dynamic worker count via `max_workers.txt`, self-relaunches dead workers).
- `PatoLex_OCR_5080` → the 5080 OCR worker (`pipeline/5080/queue_worker_5080.py` via its supervisor).
- `PatoLex_Ingest_5080` → the **lossy** version-A ingest watcher (`pipeline/5080/ingest_supervisor.ps1` → `ingest_watcher.py`). **KEEP DISABLED** until the parser is fixed + Hans-reviewed (it runs the superseded version-A path; see §4).

> The repo `pipeline/` copies are read-only version-control snapshots; the **live** copies the tasks execute are in each box's `PatoLex-scratch`.

---

## 2. The OCR pipeline (tier-a image-only years)

**Queue model:** a shared atomic-claim queue on the 5090 (`production_queue_state.json`). `pipeline/5090/queue_claim.py` is the lock-serialized claim engine. A worker claims the lowest-year `pending` volume, OCRs it, banks pages. **Stale-claim recovery:** an `in_progress`/`failed` volume whose heartbeat is older than `STALE_SECONDS` (1800 s) is reclaimable on the next claim cycle. `ocr_only_*.py` is **checkpoint-resumable** — banked pages are never re-OCR'd, so a reclaimed or restarted volume continues where it left off.

**Engines:** **3 consensus engines (Tesseract + docTR + Surya)** → token-majority **consensus = the committed text** (`pipeline/consensus.py`, `N_MAX_ENGINES=3`; method tags `token_majority_3` / `token_majority_2` / `single`). qwen2.5vl (+GOT) run as **flagging vectors only, never committed** (they modernize spelling). **PaddleOCR is NOT a consensus voter** (older prose listed 4 classical engines incl. PaddleOCR — the code and the live DB use 3). See `OCR_ACCURACY_VALIDATION.md`.

### Start / stop
- **Start (interactive overnight run):** ensure both scheduled tasks (`PatoLex_OCR_5090`, `PatoLex_OCR_5080`) are enabled and running; the supervisors launch workers. Worker count on the 5090 is set via `max_workers.txt`.
- **Stop the 5080 worker:** `pipeline/5080/stop_5080_worker.ps1`.
- **DAYTIME-THROTTLE TASKS MUST STAY DISABLED for an open-ended run.** `pipeline/5090/scale_to_one_5090.ps1` (the **0800 scale-to-1 backoff**) will throttle the campaign to a single worker mid-run if enabled. Disable it (and its 5080 analog) before an open-ended overnight/multi-day push; re-enable only when you want the daytime throttle back.

### Append more volumes to the campaign
Add the volume entries (lowest-year-first ordering) to the shared `production_queue_state.json` as `pending`. Workers pick them up on the next claim cycle. To **resume past the current frontier** (1875 done; 1877-1910 OCRing as of 2026-06-02), enqueue the next image-only volumes through ~1993; **stop before the born-digital crossover (~1997)** — those go to `parse_born_digital.py`, not OCR.

### Deferred OCR throughput optimizations (analyzed 2026-06-02, NOT implemented — logged per Patrick)
The per-page loop in `ocr_only_5090.py` / `ocr_only_5080.py` runs the 3 engines **strictly in series** (Tesseract → docTR → Surya → consensus). Models load **once per volume** (resident — no per-page reload; the per-page `torch.cuda.empty_cache()` is leak cleanup, not a model unload). Two measured-potential speedups, deferred:
- **CPU/GPU overlap (priority lever — safe on BOTH boxes):** Tesseract is CPU-only while docTR/Surya are GPU. Running Tesseract on a worker thread concurrent with the GPU engines (join before consensus) hides the ~0.9 s Tesseract behind GPU work → per-page ~2.6 s → ~1.7 s, roughly **1.3–1.5×**. Zero extra VRAM, no quality/determinism change; `pytesseract` shells out (releases the GIL) so threading genuinely overlaps.
- **Surya page-batching (5090-only):** Surya is fed one image at a time (`surya_rec([img], ...)`, un-batched); batched on the 5090 it benchmarked ~0.70 s/page. Bigger lever, but raises peak VRAM → unsafe on the 16 GB 5080 (already ~saturated at one worker; the per-page hygiene exists because accumulating tensors OOM'd it).
Implement + Hans + a before/after benchmark before trusting either. The running campaign is unaffected.

---

## 3. The canonical ingest chain (OCR text → DB system of record)

**Order:** OCR (§2) → parse → **`ingest_clean.py --commit`**.

`pipeline/ingest_clean.py` is the **CANONICAL system-of-record** path (version-B multi-engine consensus, UTF-8 faithful). Per-volume it is **atomic**: in one transaction it resolves the `source_document` by **`content_sha256`** (read from `sha256.txt`), runs a **scoped purge of all prior rows for that source_document**, then inserts the consensus acts keyed by **`(source_document_id, in_act_order)`**, and banks `consensus_output.json` ONLY after the commit succeeds.

### Commit a volume (the only sanctioned write)
`ingest_clean.py` is **DRY-RUN by default** and refuses to write unless BOTH guards are set:
```
# environment: PATOLEX_ALLOW_COMMIT=1  and  PATOLEX_PG_DSN=<postgres dsn>
python ingest_clean.py <session_label> --commit
# e.g.  python ingest_clean.py 1858 --commit
```
Without `--commit` it prints exactly what it WOULD write (the dry-run is the review artifact). Run dry-run first, eyeball the would-write summary, then add `--commit` with `PATOLEX_ALLOW_COMMIT=1`.

### Verify after ingest
- Row count by `source_document`; confirm `ocr_provenance` / `consensus_method` columns are populated (= version-B consensus, not single-engine).
- `provision_version` is **0 by design** — materialization is a deferred sweep, not a sign of failure.

---

## 4. The superseded lossy path — do NOT use its DB output as final

`pipeline/5080/ingest_from_ocr.py` is **version-A, single-engine, lossy.** It still runs early in the chain to create `source_document` rows + parse, but its DB rows are **replaced** by `ingest_clean.py`. Never serve/trust its committed text as canonical.

**HAZARD (open):** `ingest_from_ocr.py` has **no `if __name__ == "__main__":` guard** — its driver runs at module top level (~lines 494-507), so **importing it triggers a DB ingest.** Do not import it; add a guard before reusing its functions. This is why `PatoLex_Ingest_5080` stays disabled.

Full rationale: `pipeline/README.md` → "Canonical vs. superseded ingest path."

---

## 5. Current build state (2026-06-02) and resume procedure

**System of record:** version-B multi-engine consensus, **1850-1875, 4262 acts** (verified via `ocr_provenance` / `consensus_method`). `provision_version` = 0 by design.

**In flight:** 1877-1910 OCRing now (tier a). Modern-format parser fixes (tier b, `parse_born_digital.py`) are **in flight and NOT yet ingested.**

**To resume the build:**
1. Confirm local Postgres 16 is up on the 5080; confirm `PatoLex_Ingest_5080` is DISABLED and the 0800 backoff tasks are DISABLED (for an open-ended run).
2. Confirm the OCR scheduled tasks are running and the queue is advancing past 1875 (check `production_queue_state.json` + `production-batch-run.log`).
3. As volumes finish OCR, run `ingest_clean.py <label> --commit` (with both guards) per volume; verify per §3.
4. Stop the OCR campaign at the **~1996/1997 born-digital crossover**; switch those years to `parse_born_digital.py` (tier b), and the modern era to the leginfo XML channel (tier c).
5. Deferred (not part of this runbook's loop): materialize `provision_version` when the serving layer is built; re-verify the `lineage_edge` purge at the 1872 recodification; Phase C VLM-flagging + crowd correction on persisted low-confidence tokens.

---

## Revision History

| Date | Change |
|------|--------|
| 2026-06-02 | cc002: Created. Captured three-tier corpus + per-tier method, OCR queue/two-node/scheduled-task mechanics, the 0800 backoff-disable rule, the canonical `ingest_clean.py --commit` chain (sha256-keyed, scoped-purge, atomic) vs the superseded lossy `ingest_from_ocr.py`, format eras, and current state (1850-1875 version-B / 1877-1910 OCRing / modern parser un-ingested). |
| 2026-06-02 | cc002 (doc rewrite): Corrected §2 engine count to **3 consensus engines (Tesseract+docTR+Surya), PaddleOCR not a voter** (was "4 classical incl. PaddleOCR"), matching `consensus.py` (`N_MAX_ENGINES=3`) and the live DB. |
