# SESSION cc007 — Parallel Ingest Prep

| Field | Value |
|-------|-------|
| Session | cc007 |
| Date | 2026-06-09 |
| Type | Orchestrator (Opus delegating to subagents) |
| Status | **IN PROGRESS** — all work is LOCAL; nothing committed or pushed |
| Goal | Clear the path to ingesting the 1876–1993 historical OCR backlog by running four prep streams in parallel |

---

## What Was Done

Four independent streams were fanned out to subagents in parallel, then a fifth (Hans remediation) followed from the parser-fix review. All edits are local working-tree changes; no commit/push, no DB writes, no live-queue mutations.

### 1. Ops diagnosis — 5090 + stranded 1998-vol6 (read-only)
- Confirmed the RTX **5090 box is UP and idle** — the "01:28 2026-06-09 crash" was a **monitor false alarm** (SSH-poll blip; known `monitor_5090.ps1` failure mode). `nvidia-smi`: 37 °C, 0% util, 1.4 GB.
- **No OCR workers running on either box** — consistent with the campaign being complete.
- The stranded **1998-vol6** consensus payload (`page_ocr_results.json`, 27,264,340 B) is intact on the 5080 at `C:\Users\PatrickKolasinski\PatoLex-scratch\production-1998-vol6\ocr_consensus\`. Its queue entry on the 5090 (`production_queue_state.json`) is still `in_progress` (worker 5080-1); the remote `ocr_consensus\` dir is empty (payload never landed) and there is no `OCR_COMPLETE.marker`.
- A **non-destructive recovery sequence** was prepared (scp the 27 MB file → verify byte size on 5090 → `queue_claim.py done 5080-1 1998-vol6`). **AWAITING Patrick's approval — not executed.** The ingest watcher is not running, so marking done will not auto-trigger ingest.

### 2. Parser fix — chaptered_date bugs (local edits + Hans review + remediation)
- Fixed both clusters: **Cluster-A** (OCR year-misread inside `[Approved … 18XX]` on 1850s–70s volumes) and **Cluster-B** (born-digital 2000–2008 body-text date poisoning).
- Added a **±3-year clamp** keyed to the volume year and **modern-RE-first** ordering. The 51 affected rows hold correct text/citation and are fixed in place, **not purged**.
- **Hans (verify-auditor) review** found 0 blockers, **4 SERIOUS**, 3 nitpicks. All remediated:
  - S1: tombstoned the unfixed `parse_act_date` in `reparse.py` (`18[3-9]\d` would reproduce Cluster-A) → now `raise RuntimeError` + DO-NOT-USE header.
  - S2: tombstoned the `parse_born_digital.py` prototype's parse path (`raise NotImplementedError`) — confirmed non-production.
  - S3: added tests asserting both tombstones raise.
  - S4: removed the unjustified `volume_year >= 1915` magic threshold — `APPROVED_MODERN_RE` is now tried first unconditionally (safe on 19th-c text because the pattern is highly specific).
  - N1: guarded the `session_label` year extraction with a regex match.
  - N2: wrapped the `ingest_from_ocr.py` main loop in `if __name__ == "__main__":` (import is now side-effect-free; no more spurious run-log writes from tests).
  - N3: cross-referencing TODOs added for the duplicated `LEGISLATURE_MAP`.
- **Tests: 16 passed / 0 failed** (`pipeline/test_date_parser_fix.py`).

### 3. Ingest-blocker fact-gathering (read-only investigation)
Gathered the facts to clear the 4 Hans-flagged ingest blockers:
- **B1 (registration):** canonical step is `pipeline/register_source_document.py` (idempotent, `ON CONFLICT (content_sha256) DO NOTHING`). All 1877–1990 volumes already have `sha256.txt` on disk — ready to register in batch. Recommend registering only the dedup-winner per year (after B3).
- **B2 (LEGISLATURE_MAP):** map in `ingest_clean.py` stops at `1875-76`; past it, `session`/`legislature` columns get the raw label (ugly, non-fatal). Gathered the authoritative CA Legislature session→year→ordinal mapping (22nd–57th ordinal era through 1948; **year-based, no ordinal, from 1949**) from Wikipedia, ready to paste. Several labels need a decision (see Decisions Owed).
- **B3 (dedup variants):** enumerated all 14 variant pairs 1927–1965 — each pair has distinct SHA-256s (genuinely different files). Clear pattern: the lower-body-page variant is a stub/partial scan; the higher-body-page variant is the real volume. **The 1965 pair (847 vs 948 body pages) is too close to auto-resolve.**
- **B4 (logical-key diff):** confirmed `enactment`/`change_event`/`provision` PKs are all bigint `IDENTITY` (every re-ingest re-IDs rows); `provision.public_id` is UUIDv7 but is also regenerated on re-ingest. Logical keys: `(source_document_id, chapter_number)` for enactment; `(source_document_id, in_act_order)` for change_event (already a unique index). Proposed a before/after snapshot diff on `(chapter_number, in_act_order)` to prove re-ingest preserved/improved data.

### 4. Docs — ROADMAP de-stale
- Rewrote `docs/20_ROADMAP/ROADMAP.md` Current Status + Gate E/F rows: OCR campaign COMPLETE; ~35,332 enactments (1850–2024), ~84,118 provisions, ~151,763 change_events in DB; Gate F modern layer (1991–2024, ~22,780 acts) largely built; real gap = **1876–1993 ingest**.
- Flagged other stale docs for later cleanup: `BUILD_RUNBOOK.md` (§2/§5), `ARCHITECTURE.md` (Working Vision), `SCHEMA_DESIGN.md` (as-built figures).

---

## Files Changed (local, uncommitted)

**Modified — pipeline:**
- `pipeline/5080/ingest_from_ocr.py` — year clamp, modern-RE-first (unconditional), regex-guarded year extraction, `__main__` guard, TODO
- `pipeline/5080/parse_born_digital_prod.py` — modern-RE-first + ±3 clamp fallback
- `pipeline/5080/reparse.py` — tombstoned `parse_act_date` + DO-NOT-USE header + `__main__` guard
- `pipeline/5080/parse_born_digital.py` — tombstoned prototype parse path
- `pipeline/ingest_clean.py` — cross-reference TODO on `LEGISLATURE_MAP`

**New:**
- `pipeline/test_date_parser_fix.py` — 16 tests, all green

**Modified — docs:**
- `docs/20_ROADMAP/ROADMAP.md` — Current Status + gate rows + revision-history entry
- `docs/80_PROJECT_HISTORY/session-logs/claude-code/SESSION_cc007_SUMMARY_2026-06-09_Parallel_Ingest_Prep.md` — this log

---

## Decisions Owed to Patrick

| # | Topic | Decision |
|---|-------|----------|
| 1 | 1998-vol6 recovery | Approve the prepared scp + mark-done sequence? |
| 2 | LEGISLATURE_MAP ambiguities | `1907-09` (37th/38th?), `1938-vol1` (52nd or special?), `1900-01` (33rd adjourned or 34th?) |
| 3 | Dedup winners | Confirm "higher body-page count = real volume" rule; inspect the 1965 pair manually; disposition of losing scratch dirs |
| 4 | `public_id` stabilization | Stabilize provision UUIDv7 across re-ingests before the future Git-emission pass? (not a DB blocker now) |
| 5 | Clamp window | Keep ±3, or tighten to ±2 for the 1877–1990 re-ingest? |

---

## Next Session Should Start With
1. Patrick's decisions on the table above (esp. 1998-vol6 recovery + dedup winners + legislature-map ambiguities).
2. Extend `LEGISLATURE_MAP` (1877→1993) once ambiguities resolved.
3. Build the registration batch for dedup-winner volumes (`register_source_document.py`).
4. Build the logical-key diff harness (before/after snapshot on `(chapter_number, in_act_order)`).
5. **Gated on explicit go:** supervised DB backup → purge → re-ingest of 1876–1993 → logical-key validation.

## Continuation (same session, after first commit `bfaea1c`)

Patrick pushed back on the five "decisions owed" — most dissolved or reversed on inspection:

- **#1 (1998-vol6): DONE.** Pushed the 27 MB consensus JSON to the 5090, verified byte size exact (27,264,340), `queue_claim.py done` returned OK. **OCR campaign is now genuinely 100% closed** (no stranded volume). *(Note: a later completeness sweep flags 1998-vol6 as STUB — 2129 pages present but 0 chapters detected — a chapter-header-detection issue to investigate, NOT a missing-output issue.)*
- **#2 (legislature-map ambiguities): RESOLVED by inspecting the OCR'd title pages** (Patrick's instruction to look rather than ask). Verdicts: `1907-09` → **38th Session, 1909** (Ch.1 approved Jan 11 1909); `1938-vol1` → **1938 First Extraordinary Session** (Gov. Merriam proclamation), distinct from the 1937 regular; `1900-01` → **34th Session, 1901**. Key lesson: these span-named folders document the session in the **later** year — a naive map to the earlier year would be wrong for two of three.
- **#3 (dedup): the page-count rule was retired.** Built `pipeline/verify_volume_completeness.py` to verify extraction completeness instead. It immediately overturned assumptions: `1953-vol1-52chapters` is NOT a stub (covers a regular + two extra sessions); the 1965 "pair" are NOT duplicates (`64chapters` ≈ 1964 Concurrent Resolutions; `65chapters` = 1965 Regular Session). It also found **real silent extraction failures**. Hans-reviewed and bug-fixed (see cc008 log for detail), then re-run.
- **#4 (public_id): plan corrected.** Patrick was right — UUID must stay opaque/history-independent. Fix is to **preserve** existing public_ids across re-ingest (match by logical key, carry the UUID forward), NOT derive from content. No code yet.
- **#5 (clamp): changed from muffle to FLAG.** Implausible dates no longer silently dropped — act marked `date_needs_review`, structured record appended to `docs/.../date-review-worklist.jsonl`. Hans found a born-digital concurrency race (parallel workers corrupting the shared JSONL) + a misleading "act is KEPT" claim — both fixed (records now returned to the main process and written once; docstring made honest). Tests 16 → 33, all green.

**Completeness sweep — first pass was WRONG, corrected.** The first corrected sweep reported "748 mid-volume missing pages across 111 volumes" as a re-OCR punch list. Root-cause investigation showed **all 748 were FALSE POSITIVES** — pages the OCR producer (`ocr_only_5090.py`) intentionally skips (ink-density-classified empty/index pages), which the verifier wasn't consulting `page_classification.json` to recognize. The verifier was then fixed to define a real gap as a **body-classified page absent from OCR output** (`body_pidx − ocr_keys`).

**True completeness picture (254 vols):** COMPLETE 60, LEADING_GAP_ONLY 96, GAPS_FOUND 9, SUSPECT 36, STUB 53, UNVERIFIED 0, ERROR 0. The previously-flagged "worst offenders" (2003_Vol5, 2008_Vol5, the 2000s-Vol1 pattern, 1965-vol1-64chapters) ALL have **zero** real body-page gaps. The genuine finding: **~5–7 OCR-TRUNCATED volumes where the worker exited mid-volume** — `1993-vol2` (p.1850/2239), `1995-vol5`, `1996-vol1/2/3`, plus `1993-vol5`/`1994-vol1` (STUB by chapter count). **All fall in 1993–1996, the OCR/Gate-F overlap zone** where official XML is authoritative — so re-OCR there is optional (cross-check oracle only), not corpus-critical. Net real re-OCR need across the whole corpus: near-zero for primary statute text.

**`1998-vol6` is the 1998 Summary Digest** (bill-summary reference material in `Ch. N (AB 142)` format), NOT a statute-text volume — its STUB/0-chapters verdict is a format mismatch, OCR is sound. It (and similar digest/index/resolution volumes) must be **classified OUT of the statute-text ingest worklist**.

**Flagged-act downstream answer (Patrick's question):** ingesting a `date_needs_review` act is SAFE at write time (date columns nullable, `confident=false` already the schema mechanism). The only breakage is latent, in the **not-yet-written Gate G fold** (a null/`(,)` range on a multiply-amended provision would mis-order point-in-time results or trip the `provision_version` GiST exclusion constraint). The defense is a one-line `WHERE confident = true` in that future fold — no migration. Recommendation: parser-fix-first (done) shrinks the flagged tail; ingest-with-flag is a safe, cheap option for the residue when Gate G is built.

**OCR key convention learned:** `page_ocr_results.json` keys are **0-based `pidx`**, not 1-based; `page_1indexed = pidx + 1`. Volumes legitimately start at pidx≥2 (title pages skipped) — that is NOT a gap.

### Genuine decisions still owed to Patrick (post-continuation)
| # | Topic | Decision |
|---|-------|----------|
| A | Flagged-act ingest policy | When a date is an OCR misread: exclude the act from the DB until corrected (current behavior), or ingest-with-`date_needs_review` flag so it's present but marked? Patrick's philosophy points to the latter; needs ingest/schema support. |
| B | Re-OCR scope/go | RESOLVED by root-cause: 748 were false positives; only ~5–7 OCR-truncated volumes are real, all in the 1993–1996 Gate-F-authoritative overlap → re-OCR is optional, not corpus-critical. No GPU campaign needed for primary statute text. |
| C | 1998-vol6 STUB | RESOLVED: it's the 1998 Summary Digest (reference material), not statute text. Classify digest/index/resolution volumes out of the ingest worklist. |

### Continuation 2 — re-OCR launched + LEGISLATURE_MAP extended (after push of `526b19f`)

- **Re-OCR (5090, 2 workers) — LIVE.** Of the 5–7 "truncated" volumes, **only 3 were genuinely truncated**: `1993-vol2` (p.1850/2239), `1993-vol5` (p.850/1467), `1994-vol1` (p.150/2191). The other four (1995-vol5, 1996-vol1/2/3) were already re-OCR'd on **06-08** on the 5090. **Caveat: the completeness sweep ran against the 5080's local scratch, which is OUT OF SYNC with the 5090's newer output** — so the sweep over-reported truncations for the overlap volumes. The 3 real ones are resuming from checkpoint (banked pages untouched) via a locked `queue_claim.py` write (queue backed up first); the 4 complete ones were left alone. Monitor: 5090 `ocr-5090-run.log` + `OCR_COMPLETE.marker` per volume.
- **Finding (durable):** OCR checkpoints live at `production-<label>/ocr_consensus/page_ocr_results.json` (not directly under `production-<label>/`). A one-shot requeue helper was added at `pipeline/5090/requeue_three_truncated.py`.
- **LEGISLATURE_MAP extended 1877→1993** in `pipeline/ingest_clean.py` (21 → 195 entries; lookup is by full folder label, so every `-code`/`-regular`/`-vol1-chapters`/`-volN` variant has an entry). Ordinal era to 57th/1947-48, year-based from 1949-50. **Four ambiguous labels verified by reading their OCR'd title pages** (and two of the agent's initial guesses corrected): `1906-07`→**37th/1907** (was wrongly 36th), `1910-11`→**39th/1911**, `1938-vol1-chapters`→**"Extra Session of the 52nd Legislature"/1938**, `1990-vol5-firstextra`→**"1989-90 First Extraordinary Session"** (approved Nov 1989, post-Loma Prieta). Lesson re-confirmed: span-named folders document the LATER year.
- **Registration batch (DRY-RUN) surfaced a major reframe — the "dedup pairs" are NOT duplicates.** Worklist: **140 KEEP / 8 EXCLUDE** for 1877–1990. Excludes = 2 code/index TOC volumes (`1877-78-code`, `1880-code`), 2 genuinely-empty OCR stubs (`1927-vol1-26chapters`, `1929-vol1-28chapters` — 2-byte `{}` JSON, never OCR'd), 2 concurrent/joint-resolution volumes (`1965-vol1-64chapters` = the **1964** resolutions, `1971-vol3-chapters`), 2 legislative-digest volumes (`1987-vol4-chapters`, `1988-vol4-chapters` — "This bill would…", no enacted text). **The numbered-chapter variants (`-NNchapters`) are almost all DISTINCT SESSIONS, not duplicate scans:** extraordinary sessions (1934 Extra, 1941 1st Extra, 1946 Extra, 1949 Extra, 1951 3rd Extra) and **even-year (1952/54/56/58/60/62) sessions** — California's pre-1966 annual/budget-session structure. So "keep both" is correct for these; only the 2 empty stubs drop.
- **CORRECTNESS BLOCKER found in the just-extended LEGISLATURE_MAP (held uncommitted):** because the extension agent assumed the numbered-chapter variants were the odd-year regular session, ~12 entries map distinct extra/even-year sessions to the WRONG legislature (e.g. `1953-vol1-52chapters` is the **1952** session but is mapped to 1953-54; `1943-vol1-42chapters` is the **1941 1st Extra** but mapped to 55th/1943). Ingesting against this map would tag acts with the wrong session. **`ingest_clean.py` is NOT committed** for this reason. Fix requires: confirming CA's pre-1966 even-year session representation (Patrick's domain) + title-page-verifying each extra session, then a corrected map.
- `register_source_document.py` confirmed to have a real `--dry-run` mode (no DB write). All 140 keep volumes have `sha256.txt`. Registration itself does not depend on LEGISLATURE_MAP, but is **HELD** pending worklist sign-off + the map fix + re-OCR settling.

### Continuation 3 — empty files diagnosed, map rebuilt (Patrick confirmed representation)

- **The 2 "empty" volumes are NOT broken acquisitions — they're complete tiny extra sessions.** `1927-vol1-26chapters` = **1926 Extra Session, 46th Legislature** (single day, Oct 22 1926, Colorado River Compact ratification; 4-page valid PDF). `1929-vol1-28chapters` = **1928 Extra Session, 47th Legislature** (Sep 4–5 1928, bank/franchise tax; 6-page valid PDF, pages already rendered). Both are genuine distinct sessions not covered by their odd-year partners. They need OCR, not re-acquisition.
- **Durable finding — classifier bug on short volumes:** `detect_body_start()` in `pipeline/5080/ocr_only_5080.py` returns a hardcoded fallback of **30** when there are <10 pages of front matter, so a 4–6 page volume gets `body_start_idx=30 > total_pages` → `body:[]` → STAGE 4 OCRs nothing. This is why these two were skipped. Editing `page_classification.json` alone does NOT fix it (the script recomputes/overwrites it each run); the body list must be forced inside the run. Only these two volumes corpus-wide are short enough to trip it. **Fix owed:** clamp/guard `detect_body_start` for short volumes.
- **OCR of the 2 short volumes is BLOCKED on 5080 memory:** commit charge 62.9/63.7 GB (PatoAudio `diarizer_service.py` PID 2288 + `translation_service.py` PID 26208 resident). Surya/docTR cannot allocate → single-engine only. Agent stopped without writing degraded output; PatoAudio services NOT touched (per confirm-before-disruptive). **Decision owed:** free 5080 RAM (pause PatoAudio briefly) vs run on 5090 after the re-OCR finishes vs raise pagefile.
- **LEGISLATURE_MAP rebuilt** with the consistent verified representation (every post-1877 entry = `("<year> Regular/Extra Session", "<ordinal-or-2yr-term>")`; even-year sessions → prior odd-year term). All special/extra sessions title-page-verified (see the verification table in-session). Self-check: all 167 in-scope production folders have an entry. A handful of plain regular-session entries (e.g. unlabeled `-vol1-chapters` for 1957–1965, post-1965 even-year vols) follow the mechanical rule but were not individually title-page-verified — low risk, flagged for later spot-check.

### Continuation 4 — verified DB state + DB-location doc correction

- **DB is LOCAL, not Supabase — corrected the docs.** The active corpus/pipeline database is **`localhost:5432/patolex` on the 5080** (verified by direct query). The docs (CLAUDE.md "PostgreSQL 16 via Supabase", and a stale note in `GATE_F_LEGINFO_MODERN_LAYER.md` literally saying "use the Supabase pooler endpoint") were WRONG and caused an audit agent to query an unreachable Supabase host and nearly conclude the modern era wasn't ingested. Fixed CLAUDE.md (+ revision entry) and 7 docs (ARCHITECTURE, ROADMAP, SETUP, SCHEMA_DESIGN, GATE_F_LEGINFO_MODERN_LAYER, HANDOFF_cc002, LESSONS_OVERVIEW); Supabase reframed as a *planned future* serving deployment, not the current store. Memory added: [[active-db-is-local-postgres]].
- **Verified DB inventory (direct query, 2026-06-09): 35,332 enactments** = 4,262 OCR (1850-1875) + 22,780 Gate F official_xml (1991-2024) + 8,290 born-digital (2000-2008). change_event 151,763; provision 84,118; source_document 69; provision_version 0; lineage_edge 0.
- **Real integrity gap found:** all **22,780 Gate F (modern) enactments have `source_document_id = NULL`** — ingested without registering/linking a source_document. Needs backfill (register Gate F source docs + link). Plus 2 orphan source_documents (Stats. 2006 Vol6, 2007 Vol5 — resolution vols, 0 acts).
- **Confirmed the corpus gap map:** the only large missing segment is **1876–1990 (image-OCR'd, not ingested)** — the historical-ingest work we've prepped (map + registration). 1991–1999 image-OCR overlaps Gate F (already in DB, authoritative), so it's cross-check-only. The 2000s "held" queue status = the born-digital tier, correctly fenced & ingested.
- **Method note:** two subagent audits this session propagated errors by trusting the wrong source — one queried Supabase (wrong DB) and one reused the stale 5080 completeness report (wrongly listing 4 already-fixed volumes as truncated). Verify against the authoritative live source (the local DB; the 5090's live OCR output), not config/snapshots.

### Continuation 5 — OCR 100% COMPLETE; 2000s verified

- **OCR is COMPLETE across the whole corpus.** The image campaign finished **19:58 PT 2026-06-09** (`1994-vol1`, 2191 pages @ 22.5 p/min, was the last). The worker pool then drained and stopped. The 2 tiny extra-session volumes (`1927-vol1-26chapters`=1926, `1929-vol1-28chapters`=1928) were OCR'd **directly on the idle 5090 at 20:16** with the deployed classifier fix (short-volume path fired: "4 pages <= 12 -> body_start=0"). Output verified real: 1927 = Colorado River Compact / 46th Leg; 1929 = bank-franchise tax / 47th Leg. Both `done`, markers written.
- **2000–2008 born-digital VERIFIED all good** (direct DB query): 48 vols, 8,290 acts, per-volume DB counts EXACTLY match extraction. The `2001_Vol5` / `2002_Vol3` "chapter-gap" flags are confirmed **false positives** (OCR heuristic misapplied to born-digital mid-range/resolution numbering). Only zero-act vols = `2006_Vol6`, `2007_Vol5` (resolution volumes, expected). No silent failures.
- **5090 specs (corrected):** **64 GB system RAM + 32 GB VRAM** — cc006 was RIGHT. Earlier this session I wrongly called it a "64 GB-VRAM box" (conflated RAM with VRAM) and then mis-"corrected" cc006; the nvidia-smi reading of ~32 GB is VRAM, exactly matching cc006.
- **Mass-ingest plan recorded** (memory `mass-ingest-backup-compare-plan`): no ingest until ALL OCR+prep ready; then backup DB → single 1850–2026 pass → compare to backup for already-populated segments.

**Remaining before the mass ingest is now DATA PREP, not OCR:**
1. Parse the 1876–1999 OCR output into acts (with the fixed date parser) — produce `parsed_acts` for every volume. (1997–1999 fell back to OCR from garbled born-digital; they need OCR-path parsing.)
2. Run the registration batch (140 keep / 8 exclude) → `source_document` rows.
3. Decide the flagged-date-act policy (drop vs ingest-with-`date_needs_review`).
4. Wire the digest/resolution/index exclusions (the 8 excludes) into the ingest.
5. Fix the modern-layer integrity gap: 22,780 Gate F acts have NULL `source_document_id` — register/link Gate F source docs (the single-pass re-ingest can do this if the Gate F path registers source docs).
6. Decide on SUSPECT-quality volumes (1852/1860–63 ~100% low-confidence) — re-OCR/human-verify or accept.

### Continuation 6 — 1850-1999 OCR parsed to acts; 2000-2026 determination

- **2000–2026 determination (answer to "what happens to them"):** the OCR parser only covers the 1850–1999 image tier. 2000–2008 = born-digital (own parser, done+ingested); 2009–2024 = Gate F XML (in DB); 2025 = Gate F JSONL parsed, NOT ingested (3,874 acts ready); 2026 = partial (18 acts). **Overlaps currently DUPLICATED in the DB:** years 2000, 2005–2008 have BOTH born-digital AND Gate F enactments. Gate F DB gaps: 1989-90, 1993-94, 2001-04 (JSONL on disk, not ingested). Decisions owed before ingest: authoritative-source-per-year rule (proposed: OCR ≤1990; Gate F 1991-1999 & 2009-2025; born-digital 2000-2008; others = oracle), dedup the overlap duplicates, and **fix Gate F NULL source_document_id** (the Gate F ingest intentionally skips source_document registration — needs a code change to register one per pubinfo year).
- **PARSE COMPLETE (1850–1999):** ran the date-fixed `ingest_from_ocr.py:parse_volume` over **195 statute volumes on the 5080** (OCR already local) → `parsed_acts_fixed.json` each. **67,653 confident acts + 7,687 flagged (1,964 date-review-worklist entries).** 0 failures. Backed up the 70 prior `parsed_acts_fixed.json` first (`_parsed_acts_backup_20260609-204603`). 8 non-statute vols skipped (code/resolution/digest). Map-gate handled: `parse_volume` does NOT use LEGISLATURE_MAP (only the main-loop gate does), so the map in `ingest_from_ocr.py` was extended to mirror `ingest_clean.py` + a parse-only driver `run_parse_all.py` added. Detailed sub-log: SESSION_cc009.
- **OPEN before mass ingest:** (a) **verify the ±3 date clamp isn't over-flagging legitimate dates** — flag rate is uneven (1933 ~22%, 1993 ~0.3%); over-flagging would drop real acts from "confident". (b) **~17 vols (1996–1999) have no local OCR** (on the 5090, unsynced) — sync + parse. (c) the 1926/1928 extra-session OCR is on the 5090, not synced — sync + parse. Hans pass owed on the `ingest_from_ocr.py` map extension + `run_parse_all.py`.

### Continuation 7 — "100% low confidence" investigated: broken metric, not bad data

**Finding (durable):** The `low_conf_rate` in `completeness-report.json` is a MISLEADING quality signal. Investigated the 23 volumes at >=50% low-confidence (incl. 1860/1862/1863/1869-70 at ~100%) by reading the actual consensus text. **NONE are garbage/unreadable.** Two distinct causes, both metric artifacts:
- **Group A (modern 1935–1993, e.g. 1984-vol3, 1993-vol1, 1961-vol2):** docTR engine ran EMPTY, so `agreement_ratio` is mechanically 0.0 — but `consensus_text` is clean Tesseract output (pristine modern legislative English, verified by quoted samples). Complete false alarm. **Ready to ingest as-is.**
- **Group B (19th-c 1850–1875 + early-20th 1907–1923):** all 3 engines ran but disagree on old typefaces (long-s, e↔c). The agreement ceiling for 1860s type is ~0.60–0.70, BELOW the 0.75 completeness threshold, so they flag ~100% even though text is legible. Text is **readable but NOISY** (e.g. `cnuct`→enact, `Snid`→Said) — legal substance (sections, dates, subjects, enactment formula) intact.
- **Group C (genuine garbage): NONE found.**

The 0.75 threshold was never calibrated per era/engine-count (3-engine high-conf threshold is 0.65, 2-engine is 0.70; the completeness checker double-counts). **No volume needs re-OCR on text-quality grounds.**

**Decisions owed (quality bar):**
1. **Recalibrate / fix the completeness verifier's low_conf metric** (per-era threshold; treat docTR-empty as not-a-quality-signal) so we have a TRUE quality gate, not a misleading one.
2. **Quality bar for 19th-c (Group B) noisy text:** accept readable-noisy for launch, OR gate 1850–1875 (+1907–1923) through the planned human-verification pass (the captcha-style tool per [[ocr-verification-architecture]]) before finalizing. Modern Group A = proceed. Note: 1850–1875 are ALREADY ingested (4,262 acts) at this noise level.

### Continuation 8 — completeness metric recalibrated + visual ground-truth check

- **Metric fix (DONE):** `verify_volume_completeness.py` now splits the conflated `low_conf_rate` into `single_engine_rate` (docTR-empty pages = coverage note, NOT quality) and `true_low_conf_rate` (genuine multi-engine pages flagged by the pipeline's OWN 0.65/0.70 thresholds, not a hardcoded 0.75). SUSPECT verdicts: **36 → 3** (only 1850, 1852, 1853 remain — genuinely high disagreement 49–91%). Modern docTR-empty false alarms (1984-vol3, 1993-vol1, 1961-vol2) cleared to ~0% true-low-conf. NOT goalpost-moving — the 19th-c volumes still correctly show high genuine disagreement. Hans pass owed. Report at `completeness-report.json` regenerated.
- **Visual ground-truth check (orchestrator read the actual page scans vs extracted text, 7 samples across eras):** OCR is reading the REAL text — no hallucination — across all eras. Modern (1984) near-perfect; 1850 good; 1862/1863 (0.53 agreement) noisy but substance intact (dollar amounts in the 1863 appropriations act came through accurately: $2,225.15, $191.80, $1,118.10; dates, names, enactment formula all recoverable).
- **CONCRETE FINDING (durable):** **19th-century chapter headings (Roman numerals) are badly OCR-mangled** — verified visually: scan `CHAP. CLXXXIII` → OCR `Cnav. CLUX XXAT`; scan `CHAP. CCXX` → OCR `Crap. CONA`. Since the chapter number IS the act's citation key, this breaks citation/chapter-number extraction, AND explains the STUB verdicts on 1860/1862/1863 (verifier finds "0 chapters" because the mangled header doesn't match a `CHAPTER N` pattern). This is the specific integrity issue the pre-human-verification logic/coherence check must target: **citation/structure integrity (chapter numbers, section sequence, cross-references coherent & sequential)** — not just word-level readability.
- Visual sample images preserved at `C:\Users\PatrickKolasinski\PatoLex-scratch\_visual_check\` for inspection.

### Continuation 9 — coherence check (PARTIAL, then stopped on usage burn) + findings

The 3-layer coherence workflow was STOPPED at ~30% (Patrick: it burned the entire 5-hour usage limit). Process errors recorded as memories: auth-gated Workflow tool used for an unattended/asleep run ([[no-interactive-auth-when-away]]); run-log logging not wired into the workflow ([[mass-ingest...]] hygiene); and the big one — launched a 14,054-act LLM sweep (~350+ model calls) without estimating usage cost ([[estimate-usage-before-fanout]]). Do NOT re-launch the full sweep.

**Findings from what completed (Layer 1 full + Layer 2 on 4,410 of 14,054 at-risk acts):**
- **Layer 1 (deterministic, complete, ZERO model cost):** 75,340 acts/195 vols. Chapter-number issues ~10-11% in 19th-c vs 0.5% modern; date issues peak 1930-59 at ~22.5%; section-sequence issues in modern multi-amendment acts.
- **Layer 2 sample (4,410 at-risk acts — the WORST ~19% slice, risk-weighted so rates are an UPPER bound):** noisy-but-coherent 68.5%, clean 29.3%, **garbage 2.3%**, **citation_mangled 7.2%**.
- **CONCLUSION: corpus is far healthier than the low-conf metric implied.** Even in the worst slice only ~2.3% is true garbage (corpus-wide ≪1%). The dominant real defect is **citation/chapter-number mangling (7.2%, 3× the garbage rate)** — the 19th-c Roman-numeral problem, confirmed now by Layer 1 + visual check + LLM sample. **It's a PARSER fix, not re-OCR.** Garbage clusters in 1920s-50s vols (1953/1925/1949/1947/1939…), not the oldest.
- **Actionable:** (1) parser fix for 19th-c Roman-numeral chapter headings + re-derive citations; (2) a BOUNDED human-verification queue (hundreds of acts: the ~2% garbage + ~7% mangled-citation), not whole volumes. No re-OCR.
- Partial results preserved on disk: `_coherence/layer1_report.json`, `_coherence/l2_results/part_*.jsonl` (131 batches).
- **Can we deterministically PREDICT garbage? NO (verified by a free analysis on the 4,410 labels — `_coherence/garbage_predictor_analysis.md`).** Text-quality features (gibberish/junk-char ratio) have ZERO separating power — OCR noise is pervasive in ALL old acts; "garbage" is about lost legal MEANING (semantic), not noise level. Best deterministic rule ~44% recall / awful precision; ~56% of garbage is intact-structure/corrupted-body = not deterministically catchable. **citation_mangled IS partial-predictable** from Layer-1 chapter flags (chapter_sequence_issue OR chapter_missing → 65% recall, 16% precision) — usable free triage for the priority Roman-numeral defect, already computed on all 75,340 acts.
- **Therefore: for CONFIDENCE, use a small STRATIFIED RANDOM sample (~600 acts ≈ 15 model calls) to estimate the true garbage rate ± CI — NOT an exhaustive sweep (which can't be replaced by a free rule and isn't needed for confidence).** For remediation: free citation triage + targeted model/human review of worst volumes (true_low_conf>0.7), not a sweep.

### Continuation 10 (2026-06-10) — garbage detection: local AI works (right prompt) + model matrix

- **Correction owned:** I'd claimed "no prose garbage" while quoting garbled prose (`Btato`, `cnuct`) in the same breath — flat wrong. The prose HAS OCR corruption; gemma3 with a vague 1-5 prompt just failed to flag it (a TOOL failure, not a clean bill).
- **Local AI CAN catch the garbage — with the right prompt.** Switching from a vague 1–5 coherence grade to an **extraction prompt** ("list the garbled tokens, else CLEAN") took gemma3:27b to **100% recall (20/20)** on a curated known-garbage set, extracting the actual bad tokens. The free local 5090 sweep is therefore viable — no human-reviews-thousands, no 35% misses.
- **Deterministic citation check** (`pipeline/check_citation_integrity.py`) built — free, ~65% recall on the API citation_mangled labels, 10,033-act triage queue (concentrated pre-1930). A re-tune for higher recall was attempted but the background agent thrashed (iterative full-corpus rescans, killed at 40 min — lesson logged).
- **Model matrix benchmarked** (`docs/30_SYSTEM_DESIGN/LOCAL_MODEL_OCR_DETECTION_MATRIX.md`): 10 of 13 models (3 slow thinking models still finishing in `model-matrix-run.log`). **6 models hit 100% recall.** Winner = **phi4-mini** (2.5 GB, 100% recall, 0.8 s/act, multi-streamable across both boxes → ~3–4 h free full-corpus sweep; 60% precision but FPs are a deterministic, filterable pattern). Cleaner alternative = **gemma3:27b** (87% precision, ~18 h). **Thinking models add nothing** (same/worse precision, much slower; SaulLM-54B emits no clean output via Ollama). Includes projected multi-stream throughput at Patrick's 0.8 factor.
- **Process lessons → memories:** [[no-interactive-auth-when-away]] (the overnight coherence Workflow froze on an auth popup), [[estimate-usage-before-fanout]] (a 14k-act sweep burned the 5-hour limit at 30%), [[check-resources-before-heavy-jobs]] (5080 OOM crashed a PatoAudio process), [[active-db-is-local-postgres]] (docs wrongly said Supabase), [[mass-ingest-backup-compare-plan]].
- **Open / next:** pick the sweep model+config (recommend phi4-mini + FP-filter) and run the free corpus-wide garbage detection; finalize the higher-recall citation check (re-tune surgically, foreground); the 3 pending thinking-model rows fill into the run-log. The 1850–2026 mass ingest remains gated on completing all OCR+prep + the garbage sweep.

### Continuation 11 (2026-06-10) — vocabulary-diff approach (Patrick's idea) to replace the LLM garbage sweep

- **New plan (Patrick's, much cheaper):** instead of an LLM reading every act (multi-day GPU run — hardware-longevity concern), find OCR garbage by **vocabulary diff**: tokenize the whole corpus, subtract an English dictionary, the non-dictionary remainder = garbage-word candidates; capture frequency as a SIGNAL (don't filter on it — over-inclusive); then an LLM classifies the *deduped* bad-words list (real word / place-name / garbage), humans break ties; then GREP the confirmed-garbage tokens back to exact acts/pages. Deterministic, CPU-only, GPU stays cool. Limit: catches non-word OCR errors (the bulk), not real-word→real-word substitutions (`State`→`Slate`).
- **`pipeline/vocab_diff.py`** built + run on the 5090 (Python; `english_words` dict + `wordfreq` signal). Run 1: 134M word-tokens, **572,703 unique tokens**, 102 s, CPU-only.
- **BUG found (run-log caught it):** the `english_words` `alpha_2` list id is invalid → the dictionary never loaded → only 74 tokens "matched" → the 572k bad-words list is just the whole vocabulary. **Fix pending:** use `english_words` `web2` (~235k) or `nltk.corpus.words` / `pyspellchecker`, then re-run (102 s).
- Run-logging added to `vocab_diff.py` (`--log` arg; START/SCAN/PROGRESS/DIFF/OUTPUT/DONE). Run log: `docs/80_PROJECT_HISTORY/run-logs/vocab-diff-run.log`.
- **Garbage-detection decision context (from the model matrix):** if an LLM pass is still wanted, the design is a 3-tier cascade — gemma3:27b (100% recall net) → aya-expanse:32b (0-FP filter, rank-don't-drop to preserve recall) → sonnet only on the disagreement tier. But the vocab-diff may make a corpus-wide LLM sweep unnecessary (LLM only on the deduped bad-words list).

### Continuation 12 (2026-06-10) — deterministic correction passes v5→v7 (scored + fully parallel)

Built `pipeline/correction_passes.py` to clean the vocab-diff garbage deterministically (CPU-only, GPU stays cool), launched persistently on the 5090 via **WMI `Win32_Process.Create`** (survives SSH disconnect; `Start-Process`/scheduled-task-without-stored-creds did NOT — they died on session close).

- **Three passes over the 134M-token OCR corpus (205 consensus JSON files):** Pass A = dehyphenation + adjacent-pair rejoin; Pass B = de-merge run-together tokens; Pass C = spell-correct freq≥10 head. Baseline non-dictionary rate ≈ **1.14%**.
- **Parallelism (Patrick's push):** Pass B early-exit Gate-1 + 12-worker pool took de-merge from a projected **2.7 h → 1.4 s**. v6/v7 then parallelized the file-scan (baseline+Pass A in one read, workers read their own files = no big text pickle) and Pass C → **full run 1468 s (v5) → 208 s (v7), ~7×.** 24-core box, capped at 12 workers. Honest decomposition recorded: most of the Pass-B speedup was the *algorithmic* early-exit (~600×), not the 12× parallelism — I'd wrongly credited it all to parallelism.
- **QUALITY finding (Patrick caught it):** a binary `is_known()` dictionary check is too blunt — it accepted garbage-fragment de-merges (`retirant→reti+rant`, `kaloogian→kaloo+gian`) and Pass C mis-corrected real legal terms (`conservatee→conservative`, 3,682 occ) and ambiguous OCR (`cight→right`, `cuap→cup`). The 0.5045% v5 residual was **partly fake** — achieved by corrupting ~50k tokens into dict-passing garbage. Durable writeup: `docs/80_PROJECT_HISTORY/lessons/LESSON_dictionary_membership_too_blunt_for_correction.md` + memory [[dictionary-membership-too-blunt]].
- **v7 SCORING fix:** (1) de-merge pieces must be `is_common` (`wordfreq.zipf_frequency ≥ 2.5`, validated: real pieces ≥2.94, garbage fragments have ≥1 piece ≪2.5) → fragment-splits gone; (2) Pass C ranks candidates by **CORPUS frequency** (general English picks `small` over `shall`) and accepts only a confident winner (corpus_freq ≥ 50 AND ≥ 3× runner-up) → fixed `sball→shall`, `cuap→chap`, `jands→lands`; **2,655 ambiguous tokens routed to `_vocab/passC_review.tsv`** instead of being mis-corrected; (3) legal supplement expanded to protect `conservatee`/`habilitative`/etc.
- **Honest v7 result:** residual ROSE 0.5045% → **0.5568%** (real, no longer corrupting text); Pass B "recovered" 71,363 → 27,946 (the ~43k was the wrong splits). Tunables: `DEMERGE_MIN_ZIPF`, `PASSC_MIN_CORPUS_FREQ`, `PASSC_DOMINANCE`.
- **NEXT (in progress):** LLM comparison on the 2,655 review rows + Pass B edges — local gemma3→aya cascade vs a sonnet pass, then compare. Architecture: apply Pass A safely; Pass B/C apply high-confidence subset; LLM adjudicates the review tier. Remaining Pass B edges: `califorma→cali+forma` (2-edit garble), `twenty-cight→…+ight` (OCR eight→cight in hyphenated numbers).
- **Repo note:** stray scratch `correction_passes_v2.py` (root) + `pipeline/correction_passes_v3.py` are superseded by canonical `pipeline/correction_passes.py` — left untracked, candidates for deletion.

### Continuation 13 (2026-06-10) — LLM adjudication of the review tier + doc-truth fixes

- **LLM comparison on the 2,655 Pass C review tokens (the freq≥10 ambiguous tier, 84,901 occ):** local **gemma3:27b** (free, 765s, 3.5 tok/s, via Ollama on 5090) vs **Sonnet** (5 parallel subagents, ~210K tokens). Verdict scheme FIX/KEEP/GARBAGE/NAME. Harnesses: `pipeline/review_adjudicate_local.py`, `pipeline/compare_adjudications.py`; outputs in run-logs (`review_local_gemma3.json`, `review_sonnet_part1..5.json`, `review_comparison.tsv`).
- **Result:** verdict agreement **62.2%**; both-FIX same-correction **52.6%** (541 high-confidence tokens). **Sonnet is the clearly stronger judge** — gemma3 over-calls GARBAGE (545 tokens it discarded that Sonnet recovered: 361 FIX + 184 real KEEP terms) and fabricates some names. Sonnet wins disagreements ~27/30 (`pubhe→public`, `migden→Migden`, `islais→Islais`, `indorser`=KEEP). Sonnet tally: FIX 1,478 / KEEP 414 / GARBAGE 461 / NAME 302. **Do not run gemma3 standalone here.**
- **HONEST text-quality status (after Sonnet):** we have a validated *method* + characterization (true OCR-error floor **<0.56%**) and verdicts for the hard tier — but **nothing is APPLIED** (corpus text unchanged; reversible corrections layer not built), only **541 tokens are high-confidence**, the **414 KEEP terms still need folding into the dict**, the **~652k singleton+low-freq residual got no correction attempt**, and the **#1 unmeasured risk = real-word→real-word substitutions** (`State→Slate`, digit flips) which vocab-diff structurally cannot see. Adjudication was also context-free.
- **Doc-truth fixes (Patrick flagged repeated mis-documentation):**
  - **ROADMAP** — replaced the wrong "1876–1993 ingest gap" framing with a boxed **THE INGEST PLAN**: back up → **CLEAR the DB** → ingest the **FULL 1850–2026 in one fresh pass** → diff vs backup. NOT a sub-range fill; the listed items are PREREQUISITES to that one ingest. Memory [[mass-ingest-backup-compare-plan]] updated with the explicit CLEAR step + "do not mischaracterize" warning.
  - **CLAUDE.md** — corrected OCR engines to **Tesseract 5 + docTR + Surya** (token-aligned majority vote); the "qwen2.5vl ensemble" wording was wrong (VLMs were only a verification design idea).
  - Added **`docs/PROJECT_STATS.md`** (numbers snapshot).
- **Answered standing questions:** (1) DB stops at 2024 because the 2025+current-2026 modern data is *acquired but not yet parsed/ingested* (a prep item, not a coverage hole); (2) the Roman-numeral **chapter-number mangling is NOT fixed** — parser fix still pending, prerequisite #5 to the mass ingest.
- **NEXT decision teed up:** before/instead of the parser fix, the most valuable quality task may be to **measure the real-word→real-word substitution rate** (the one error class this whole pipeline can't see). Then build the reversible corrections layer (Pass A + the 541) + fold KEEP terms into the dict.

### Continuation 14 (2026-06-11) — residual triage, garbage page-clustering, freq>=2 Pass C

- **Procedural residual triage** (`pipeline/triage_residual.py`, 467,978 tokens in 3s, parallel): classified the whole residual into NOISE 38,513 / TYPO 146,770 / FRAGMENT 2,610 / NAMELIKE 243,441 / GARBLE 36,644. Validated Patrick's instinct: of 385,131 singletons only ~37k (10%) are definitive NOISE; ~97k are near-words, ~215k plausibly-real names/foreign. Honest limit: NOISE/FRAGMENT are clean; TYPO suggestions often coincidental; NAMELIKE mixes real names with pronounceable garbles — the name-vs-garble split structurally needs a model. Output `_vocab/residual_triage.tsv`.
- **Garbage page-clustering** (`pipeline/garbage_page_cluster.py`): 361 Sonnet-GARBAGE tokens (corrected from the wrong 461 self-tally), 340 located, 10,807 instances over 6,447 pages — NOT page-clustered but RECURRING artifacts → resolve each string once. `min_pages_to_cover_all=225`. **21 "not found" were Pass-A line-break-hyphen JOINS** (`appropriadollars`) that exist only in post-transform vocab, not raw text — confirmed NOT corruption.
- **Pass A marginalia finding (Patrick):** 19th-c volumes have margin side-notes in smaller font; OCR interleaves them into the body, causing (1) bad hyphen-joins and (2) mid-sentence real-word insertions (INVISIBLE to vocab-diff). The OCR pipeline already crops margins (`find_margin_and_crop`) but it leaks; **no word coordinates were banked**, so this can't be fixed from saved text — needs targeted re-OCR/layout or LLM-context. Cheap guard: Pass A should only collapse an LBH if the result is_known.
- **Pass C extended to freq>=2** (`PASSC_MIN_FREQ` env): residual 0.5568% -> **0.4049%**, corrections 11,943 -> **71,189**, review tier 2,655 -> **23,601**, +201,062 occ recovered, wall 1145s. Quality: bulk good (OCR-variant->word), but a ~10-15% error tail of FRAGMENTS edit-1-matching a complete word (`ablished->abolished` is really *established*; `acility->ability` is *facility*). Corpus-freq dominance helps (account over mccourt) but can't tell fragment from typo. **Verdict: freq>=2 = reversible/advisory + search recall, NOT destructive auto-apply.**
- **GAP owned:** Pass C never persisted the accepted corrections list (token->correction) — it computed them in-memory to derive the residual %, then discarded. Must add a corrections TSV before any apply. Also add a triage gate (don't TYPO-correct FRAGMENT/NAMELIKE tokens).

### Continuation 15 (2026-06-11) — v8 correction_passes (persist + guards + gazetteer) + display-layer design

Prepped the clean re-run (NOT yet run/committed-with-results):
- **Persist corrections** — Pass C now writes `passC_corrections.tsv` (token->correction + freq + provenance). Fixes the gap where accepted corrections were computed in-memory and discarded.
- **Pass A LBH guard** — `LBH_RE` now captures the full second word and only collapses a line-break hyphen if the join `is_known`; otherwise leaves text untouched. Stops manufacturing marginalia merges (`appropria-\ndollars -> appropriadollars`).
- **Pass C fragment gate** — tokens that are a prefix/suffix of a LONGER common word (line-break pieces: `ablished`=established, `acility`=facility) routed to review instead of TYPO-corrected. Kills the ~10-15% fragment error tail.
- **CA gazetteer** (`pipeline/ca_gazetteer.py`) — 58 counties (authoritative) + 159 cities + 61 features + 55 legislators (incl. the mangled ones: Karnette/Migden/Kaloogian/...) = 319 name-tokens, merged into the known-dictionary so real CA names stop being false-flagged and are protected from mis-correction. Import-verified on the 5090.
- **Design doc** `docs/30_SYSTEM_DESIGN/CORRECTION_AND_DISPLAY_LAYER.md` — captures Patrick's layered display-layer architecture (immutable OCR + reversible overlays: deterministic -> model/vision -> community wiki, materialized display for the hot path) and the OPEN pre-ingestion decisions (anchor granularity, layer precedence, original-also-searchable, correction-axis vs point-in-time-axis).
- v8 syntax-checked + on 5090; re-run (freq>=2) pending Patrick's go.

### Continuation 16 (2026-06-11) — v8 run results + verification; coordinate scoping

- **v8 freq>=2 run DONE** (wall 1086s): baseline 1,531,515 (gazetteer trimmed ~3.4k flagged names vs 1,534,893) -> after_A **1,277,800** (LBH guard recovered +253,715, MORE than the unguarded 217,262, AND stopped manufacturing `appropriadollars`) -> after_B 1,256,448 -> after_C **578,153 = 0.4364%**. Corrections accepted **65,177**, review **~28,029**. Residual slightly HIGHER than the pre-gate 0.4049% ON PURPOSE -- the fragment gate declined ~6k risky fixes.
- **VERIFIED `passC_corrections.tsv` written** (the persistence fix): 65,177 rows, each with provenance (`unique(whereas:32050)`, `dominant(shall:2006583>>small:14032)`). First applyable, auditable corrections artifact. Confirms corpus-freq dominance (sball->shall not small).
- **VERIFIED fragment gate fired** on exactly the dangerous cases: `trict->fragment_gate(tract)`, `sioner->fragment_gate(sooner)`, `poration->fragment_gate(portion)`, `priated->fragment_gate(printed)` -- all conservatee-class corruptions AVERTED. Minor: a few genuine typos over-parked (aiter->after) -- safe direction.
- **KEY: the parked fragments ARE the line-split halves** (dis-trict, commis-sioner, cor-poration, appro-priated) -> validates the line-geometry reunification pass (Patrick's margin idea) has high-frequency targets sitting in the review tier.
- **Coordinates NOT on disk** (confirmed: page objects have only text fields, no bbox -- docTR/Surya boxes dropped at extraction, kept only `.value`). BUT preprocessed page images ARE saved (`pages_prep_gray/*.png` + `img_path`), so coordinates+font-height are RE-DERIVABLE via a Tesseract `image_to_data` CPU pass (no GPU/VRAM risk, parallel). Scale: 267,530 images total but marginalia is old-volume-only (~48.6k from 1901-1950 + ~730 pre-1900; the 218k 1951-99 are modern typeset) -> target ~50k pages, est <1h on the 5090 CPU. Benchmark before committing.
- Newlines in consensus_text = physical scan lines (verified) -> line-end/line-start = right/left-edge proxy for the text-only line-split pass.

### Continuation 17 (2026-06-11) — line-split measure-first + plain-English doc

- **`docs/WHERE_WE_ARE_PLAIN_ENGLISH.md`** added (non-technical status snapshot, Patrick asked to "write that down").
- **Coordinate question answered definitively:** XY coords are NOT on disk (page objects have only text fields; docTR/Surya boxes dropped at extraction). BUT page images ARE saved (`pages_prep_gray/*.png` + `img_path`) -> coords re-derivable via Tesseract `image_to_data` CPU (no GPU/VRAM risk, parallel). Scale 267,530 images but marginalia is old-volume-only (~48.6k 1901-50; 218k 1951-99 are modern typeset) -> target ~50k.
- **`pipeline/line_split_finder.py`** (measure-first, 6s parallel scan) — words split across line breaks, incl. margin/blank-line interleaving (newline = scan-line, verified). RESULT: 229,453 split-word pairs total; **217,463 (95%) already caught by Pass A** (hyphen, adjacent); **~11,156 MISSED** by current LBH (blank/margin between) = the new recoverable set; of the missed, only **~1,507 are TRUE margin interleaving** (content between halves), ~9,650 are blank-line gaps.
- **Decision implication:** split-word marginalia is small (~1,500) and **fully recoverable from text** (join-test works regardless of what's between) -> **coordinate re-derivation likely SKIPPABLE.** The only coordinate-only residue = non-split real-word margin insertions, which path 2 (measure real-word substitutions) will size. If path1+path2 strong -> skip coords (Patrick's hope).
- **NEXT:** build the reunification pass (emit the ~11k missed splits as corrections; clears matching review-tier fragments like trict/sioner/poration), then path 2.

### Continuation 18 (2026-06-11) — line-split reunification pass (Path 1 done)

- **`pipeline/line_split_reunify.py`** — emits the corrections artifact for split words the current Pass-A LBH misses. **11,156 reunifications** written to `_vocab/line_split_corrections.tsv` (1,507 margin-interleaved, 9,649 blank-gap; head+tail->joined w/ provenance + margin_text).
- Reunited words are real high-freq statute terms: district(374), compensation(253), transportation(228), appropriation, commencing, acquisition, superintendent, legislature...
- **Validates the fragment-gate handoff:** the tail fragments cleared (`-trict`374, `-priation`131, `-pensation`114, `-priated`93, `-sition`69, `-tion`943) + heads (`appropria-`, `commis-`, `cor-`, `transporta-`) are EXACTLY the review-tier fragments the Pass C gate parked. Gate parks -> reunify clears.
- **Coordinate re-derivation CONFIRMED skippable for split words** (text-only handled all 11k). Only the non-split real-word margin-insertion class remains -> Path 2 (measure real-word substitutions) sizes it.
- **NEXT: Path 2** -- stratified-sample + LLM-judge measurement of the real-word->real-word substitution rate (the vocab-diff blind spot). Sample, don't sweep (estimate-before-fanout). Local gemma3 free first; estimate Sonnet-sample cost before any Sonnet fan-out.

### Continuation 19 (2026-06-11) — Path 2: real-word substitution rate MEASURED; coords SKIPPED

- **Stratified sample** (`substitution_sample.py`): 498 windows / 39,840 words, 166 per era (<=1900 / 1901-1950 / 1951-1999), seed 20260611 -> `substitution_sample.jsonl`.
- **Local gemma3 judge** (`substitution_judge_local.py`, GPU, ~12 min, peaked 69C -- thermal watch never tripped 75/78): raw 730 subs = **1.83%** -- but precision check showed ~55% were NON-words (vocab-diff already catches) + ~25% false positives on correct legal/archaic terms (therefor, moneys). gemma3 too imprecise to trust the number; over-flags.
- **Sonnet verification** (3 parallel agents, ~155k tokens / ~$1, tighter prompt): **22 genuine valid->valid substitutions / 39,840 words = 0.055%**. By era: <=1900 **0.113%**, 1901-1950 0.038%, 1951-1999 0.015%. All 22 genuine (lion->lien, shell->shall, Ban->San, 80th->30th, 1038->1938...). gemma3 was 33x inflated.
- **DECISION (Patrick's hope confirmed): SKIP coordinate re-derivation.** Both text paths strong (Path1 recovered 11k splits; Path2 invisible class ~0.055%, includes non-split margin insertions). Not worth a ~50k-image detection pass for ~0.05-0.1%. Residue (~74k instances corpus-wide) handled by the layered arch (on-demand LLM + community wiki + reversible overlay), NOT coordinates. Not a launch blocker.
- **Text-quality investigation essentially COMPLETE:** both error classes measured -- visible ~1.14% (->~0.4% after correction, mostly recoverable) + invisible ~0.055%. Method built + validated. Remaining corpus work: parser fix (Roman-numeral chapters) + the single 1850-2026 mass ingest.

### Continuation 20 (2026-06-11) — parser fix: investigated -> ALREADY FIXED; added regression tests

Investigated the "parser fix" (Roman-numeral chapter mangling + chaptered_date bug). **FINDING: both are already fixed in the live path** -- the worklist's "fix parser before re-ingest" demand is satisfied:
- **Date bugs (Cluster A OCR-year, Cluster B body-poison):** fixed in `ingest_from_ocr.parse_act_date` via `YEAR_CLAMP_WINDOW=3` + `APPROVED_MODERN_RE`-tried-first. `run_parse_all.py` imports `parse_volume` from `ingest_from_ocr`, so the PARSE stage produces correct dates on re-parse. **33 regression tests pass** (`test_date_parser_fix.py`).
- **Roman-chapter F11:** handled at the CANONICAL ingest `ingest_clean.py` -- `chapter_was_ocr_substituted(chapter_raw, chapter_int)` returns True (=> confident False) for ANY non-clean numeral (lowercase, junk, roman!=int). Chapter number is DISPLAY-ONLY; the physical-act key is `(source_document_id, in_act_order)` which survives a garbled numeral (Hans F7). So garbled chapters are flagged, never authoritatively mis-cited.
- **I started a parse-stage round-trip guard in `ingest_from_ocr.parse_chapter_number` but REVERTED it** -- redundant with the canonical ingest guard, and adding it to the `confident` gate would have tripped the explicit "DECISION PENDING: do not silently alter routing" comment. Kept the clean separation (parse=value, ingest=confidence). `ingest_from_ocr.py` is byte-unchanged.
- **Added `pipeline/test_chapter_parser.py`** (17 tests, all pass): `parse_chapter_number` value extraction (CCCLIV->354, ordinals->0, garbled->no crash) + `chapter_was_ocr_substituted` F11 guard (trusts clean arabic/roman, flags lowercase/junk/mismatch). Locks in the existing guards (previously untested).
- **Remaining (NOT parser code):** the 51 stray DB date rows self-correct on re-ingest (parser now produces right dates); the flagged-act routing (ingest-with-flag vs exclude) is a pending design decision for Patrick.

### Continuation 21 (2026-06-11) — chapter sequence-RECONSTRUCTION (proper fix, measure-first)

Patrick pushed back on "flag is enough": the existing F11 handling DETECTS garbled chapters but does NOT recover the correct number (~the citation). Proper fix = reconstruct from the monotonic sequence (chapters are 1..N per session).

- **`pipeline/chapter_reconstruct.py`** (self-contained: HEADER_RE + parse_chapter_number + clean-check copied verbatim; parallel; 2s over 205 vols). For each garbled heading, recover its value iff bracketed by clean anchors whose numeric gap == positional gap (unique).
- **Result (LOWER BOUND):** 87,197 headings, 84,972 clean (97.4%), **2,225 garbled**; **723 recovered by sequence (32.5%)**, of which **457 had a WRONG OCR value reconstruction fixes**; 1,455 gap-mismatch, 43 one-sided, 4 no-anchor.
- **Recoveries are clearly CORRECT** (sample): `d`(ocr 500)->148, `Ii`(2)->50, `CLY`(150)->104, `TVI`(5)->56, `CXxX`(130)->120. Real mis-citations recovered, not just flagged. Validates Patrick's instinct.
- **CAVEAT — 32.5% is a lower bound:** the analyzer used RAW HEADER_RE matches (87,197) but the corpus has only ~75,340 real acts; the ~12k extra are non-acts (TOC, running-heads) the real parser filters via enact-markers/TOC-exclusion. They pollute the sequence and inflate the gap-mismatch bucket. On the properly-segmented PARSED-ACT sequence, recovery is substantially higher.
- **NEXT (proper impl):** (1) re-measure on parse_volume's ordered/filtered act sequence for the true rate; (2) wire reconstruction into ingest_clean.py's per-volume pass -- anchor on clean numerals, infer garbled from the run, store `chapter_inferred=true` (auditable/reversible), flag only genuinely-ambiguous (runs/restarts).

### Continuation 22 (2026-06-11) — chapter reconstruction: architecture corrected + measured on act-filtered sequence

- **Architecture correction (Patrick):** chapter reconstruction is a CORRECTION, so it belongs in the cleanup/correction pipeline emitting a reversible artifact (`chapter_corrections.tsv`, sibling to passC_corrections / line_split_corrections), NOT baked into ingest. Ingest stays a dumb faithful loader that APPLIES overlays. Parse provides the act-level anchoring the whole correction layer attaches to (resolves the "anchor granularity" open question).
- **Dependency (Patrick):** reconstruction needs the fine-grained, FILTERED ACT sequence = the PARSE stage output (parse_volume), which is a separate upstream stage (DB-safe, writes JSON), distinct from DB-ingest. Confirmed parse output does NOT exist on disk (0 files) -- only OCR consensus + page_classification.
- **For the MEASURE, sidestepped the full parse stage** by adding parse_volume's core act-validation (ENACT_MARKER_RE within 40 lines) to the analyzer -- filters TOC/running-heads without the parse machinery, RAM, or path hacks.
- **RAM safety:** the 5080 had only 2.5/15.7 GB free (PatoAudio+DB) -- did NOT run parse there (past PatoAudio crash). Measured on the 5090 instead (analyzer, 2s).
- **Result (act-filtered):** 79,737 act headings, 78,318 clean (98.2%), **1,419 garbled (1.78% of acts)**; **564 recovered high-confidence (39.7%, bracket-verified), of which 347 had a WRONG OCR value fixed**; 842 gap-mismatch (NOT all unrecoverable -- forward-fill-able at medium confidence), 13 one-sided. 39.7% is a conservative FLOOR (strict consecutive-run criterion). Chapter-numeral mangling (1.78%) is narrower than the broad ~7% "citation" figure.
- **NEXT (the real build):** chapter reconstruction as a correction pass emitting `chapter_corrections.tsv` (3 tiers: bracket-verified=auto, forward-fill=inferred, ambiguous=review), run on the REAL parse output. Requires running the parse stage first -- which is RAM-blocked on the 5080 (2.5GB free) and is also the first step of the mass-ingest. Operational decision pending: run parse on the 5090 (authoritative corpus, path override) or wait for 5080 RAM.

## Lessons / Notes
- `pipeline/sql/live_queue_snapshot.json` is **stale** (dated 2026-06-02) — trust the git log and live `production_queue_state.json`, not that file.
- `low_conf_rate` in completeness-report.json is NOT a reliable quality score — it conflates docTR-empty (text fine) with old-typeface 3-engine disagreement (text noisy but legible) under an uncalibrated 0.75 threshold. Read actual `consensus_text` to judge quality, not the metric.
- The active DB is **local Postgres `localhost:5432/patolex`**, NOT Supabase — query it directly for any corpus/DB question; docs prior to cc007 misstated this.
- The completeness verifier must run against the **authoritative 5090 OCR output**, not the 5080's local scratch — the two drift (the 5080 copy lagged a 06-08 re-OCR pass), causing false truncation reports.
- A crude heuristic ("more pages wins") nearly drove wrong dedup calls; a completeness verifier overturned it AND found real silent extraction failures. Verify completeness, don't infer it.
- A new tool that will drive expensive action (re-OCR) gets a Hans pass BEFORE its numbers are trusted — the first punch list was inflated by a leading-page false positive the audit caught.
- A completeness verifier MUST consult `page_classification.json`: the OCR producer intentionally omits empty/index pages, so "absent page-key" ≠ "missing content". A real gap = a **body-classified** page absent from OCR output. Root-causing this turned a scary 748-page punch list into ~0 real work — and only the corrected check surfaced the genuine 1993–1996 mid-volume OCR truncations. Verify completeness against the producer's own page taxonomy, never against a naive 1..max range.
- Subagents must use the **Write tool**, not bash heredocs, for file creation — the compound-bash/heredoc hook blocks them, and a haiku worker silently left a `"test"` stub and falsely reported success. Orchestrator must verify subagent file outputs.
- Two unfixed copies of a parser nearly slipped through; the Hans pass caught them — adversarial review earns its keep on pipeline code.
