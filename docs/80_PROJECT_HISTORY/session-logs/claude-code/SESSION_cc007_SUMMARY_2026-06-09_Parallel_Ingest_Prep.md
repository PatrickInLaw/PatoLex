# SESSION cc007 — Parallel Ingest Prep

| Field | Value |
|-------|-------|
| Session | cc007 |
| Date | 2026-06-09 |
| Type | Orchestrator (Opus delegating to subagents) |
| Status | **COMMITTED & PUSHED through 2026-06-11.** Started as ingest-prep; evolved into a deep **text-correction-pipeline** phase (chapters, reunifier, dictionary, autocorrect). |
| Goal | (orig) clear the 1876–1993 ingest backlog → (became) characterize & build the OCR text-correction stack and prove the error rate is reducible |

> **READ THIS FIRST — the sections immediately below (What Was Done / Files Changed / Decisions Owed / Next Session) describe the ORIGINAL ingest-prep phase only. The bulk of this session was the correction-pipeline work summarized in "## Session Arc (2026-06-11)" just below, with full detail in Continuations 1–44 and the Lessons section at the end.**

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

## Session Arc (2026-06-11) — Correction-Pipeline Phase (the bulk of this session)

High-level narrative; details in Continuations 1–44 + Lessons. All committed/pushed.

**Chapter numbers — DONE (215/215):** the garbled Roman/Arabic chapter numbers were resolved as a reversible overlay. Deterministic monotonic-sequence reconstruction handled ~991; the 215 hardest REVIEW cases were finished by **rendering the heading page from the archive PDFs and reading the scan** (deterministic re-OCR for modern Arabic; Sonnet-vision + sequence-bracket cross-check for 19th-c Roman; ~35 hand-read). `chapter_corrections_GRAND.tsv`.

**Text quality — characterized, then attacked:** post-Pass-ABC garble flag-rate is **0.56% (737k token-occ of ~132M)** — and that's a PRE-overlay UPPER BOUND, not an error rate. Decomposed the residual honestly:
- **Reunifier (line_split_reunify.py v3):** rebuilt to catch what it missed — same-line space-splits, cross-page splits, NOHYPHEN-adjacent, larger lookahead, **multi-fragment (longest-first, post-Hans)**, + a flag-only FUZZY tier for dropped-char-at-split misspellings. 11,156 → 15,434 rejoins.
- **Singleton tail (385k) decomposed RIGHT:** **~17% structural garbage, ~63% autocorrectable (edit-1/2 + real over-merges), ~19% harder typos.** ("60% garbage" was my wrong claim, refuted by measurement.)
- **Singleton autocorrect (Patrick's idea):** corpus-weighted edit-1 fixes ~23% of the tail cleanly; edit-2 lifts it further. The freq≥2 passes had skipped singletons.
- **Dictionary integration (Patrick's #4):** `build_dictionary` now loads **5,926 validated additions** (5,425 census/GeoNames-attested names + **501 LLM-validated legal terms**). Heuristic curation failed 3× (frequency≠validity; it kept fragments/errors); an LLM pass cleanly split REAL/NAME from FRAGMENT/ERROR.
- **Sonnet text-adjudication overlay** expanded to 1,704 freq≥10 fixes (58,700 occ).

**The agreed correction-pass ARCHITECTURE (Patrick):** dict-integration FIRST → reunify (fragments) → split (over-merges, NEW pass TBD) → spell edit-1/2/3 (singletons) → systematic-error sweep. All reversible overlays; **re-measure the residual only AFTER they apply** for the first real error rate.

**Two Hans reviews** (parser tombstones early; dict+reunifier late — caught a CRITICAL shortest-first stranding bug, fixed to longest-first).

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

**Correction-pipeline track (current, as of 2026-06-11):**
1. Build the **over-merge SPLIT pass** (inverse of the reunifier; only split tokens not themselves known). Doesn't exist yet.
2. Build the **singleton autocorrect pass** for real: corpus + general-English weighted edit-1/2 (and test edit-3, flag/LLM-only), guarded against frequent-corpus-error targets, emitting a reversible overlay.
3. **Apply all reversible overlays** (chapter + Sonnet text + line-reunify + autocorrect + dict) to the corpus, then **RE-MEASURE the residual** — that is the first real error rate (everything so far is a pre-overlay upper bound).
4. Extend dict-integration with the LLM-validated legal vocab to the FULL freq tiers (this pass only validated the freq≥15 genuine-novel set).
5. Systematic-error sweep completeness check (high-freq consistently-broken words like `secrion`→section).

**Ingest track (original, still pending):**
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

### Continuation 23 (2026-06-11) — PARSE STAGE materialized on the 5090 (milestone)

- **Ran the parse stage over the whole OCR corpus on the 5090** (authoritative corpus, 64GB RAM -- NOT the 2.5GB-free 5080). `pipeline/run_parse_5090.py` mirrors run_parse_all.py but monkeypatches ingest_from_ocr's 3 write-paths (SCRATCH_ROOT, DATE_REVIEW_WORKLIST, LOG_FILE) to 5090 locations. Smoke-tested on 1862 first (115/7, paths OK).
- **DONE in 57s: 197 volumes, 0 failures -> 69,100 confident + 7,591 flagged = 76,691 acts.** Every `production-*/parsed_acts_fixed.json` now exists on the 5090 (the fine-grained, ordered act sequence: chapter_raw, chapter_int, in_act_order, iso_date, text, confident).
- **Parse is DB-safe** (writes JSON only) and is the FIRST step of the mass-ingest -- so this is real ingest progress, not a one-off. It unblocks: (1) chapter reconstruction on the real act sequence, (2) anchoring the text corrections to acts, (3) the mass-ingest pipeline.
- **NEXT:** point chapter_reconstruct.py at `parsed_acts_fixed.json` (real act sequence, 3-tier confidence) -> emit `chapter_corrections.tsv`. Then the apply/ingest steps.

### Continuation 24 (2026-06-11) — chapter_corrections.tsv built (3-tier, safety-corrected)

- Added `in_act_order` to `ingest_from_ocr.py` act_rec (was missing despite being the Hans-F7 act key) + re-parsed the 5090 corpus (197 vols, 0 fail) so the parsed acts carry reading-order.
- **`pipeline/chapter_corrections.py`** reads `parsed_acts_fixed.json` (confident+flagged merged, sorted by in_act_order) and emits the reversible overlay `_vocab/chapter_corrections.tsv` (vol, in_act_order, chapter_raw, ocr_chapter, corrected_chapter, tier, reason). chapter_raw preserved.
- **CAUGHT MY OWN OVER-CONFIDENCE:** first version had an INFERRED tier that forward-filled prev_anchor+offset and OVERRODE the OCR value even on disagreement (e.g. XXTI: OCR=22 via T->I substitution, fill said 17 -> would have changed a likely-correct citation to a wrong one). The parsed sequence has GAPS (acts missed/merged), so positional offset != chapter numeric offset -> forward-fill is a coin-flip. First (wrong) numbers were "859 fixed / 97% recovered".
- **SAFE corrected tiers:** AUTO (bracket-verified consecutive span -> override OCR, a verified fix), CONFIRMED (fill AGREES with OCR -> trust, no change), REVIEW (fill disagrees / restart / no-anchor -> human; never silently override on a coin-flip).
- **HONEST RESULT:** 76,691 acts, 75,485 clean (98.4%), **1,206 garbled (1.57%)**; **AUTO 470 (of which 293 actual verified fixes)**, CONFIRMED 134, **REVIEW 602 (50% -- only 0.78% of all acts)**. AUTO samples verified correct (CLXXIITI ocr 174 -> 173; XI1->12). REVIEW = genuinely ambiguous (restart_or_decrease, collision, fill_disagrees).
- **Limiting factor = parse completeness** (sequence gaps), not the reconstruction idea -> better act-detection would shrink REVIEW. NEXT options: improve act detection; or resolve REVIEW via image/context (vision) or by trusting the OCR-substitution value where plausible.

### Continuation 25 (2026-06-11) — chapter review: OCR_PLAUSIBLE (358) + vision pass (honest limits)

- **OCR_PLAUSIBLE tier resolved 358 of the 602 deterministically** (OCR value fits monotonically between clean neighbours -> accept; the disagreement was a parse gap). Review pile 602 -> 244 (0.32% of acts).
- **Vision pass on the 244** (`run_chapter_vision.py`, qwen2.5vl, reads the source-page scan). HONEST OUTCOME -- vision is NOT a silver bullet here:
  - **155 of 244 are in volumes WITHOUT page images on the 5090** (pre-1900 scans not present; only ~730 pre-1900 images on the box) -> can't vision them; need the source images sourced first.
  - **qwen2.5vl:32b errors (HTTP 500); only :latest (7B) works**, and it read only **20 of 89** image-available cases (~22%) -- the print is too degraded; a 7B vision model is no better than the 3-engine consensus that already struggled.
  - **The modern-volume REVIEW cases are NOT Roman garbles -- they're Arabic chapters with a stray OCR digit** (e.g. chapter 1138 read as "11382"); a parser/heading issue, and the sequence-fill is likely right (modern sequences are gap-free, so forward-fill is safe THERE).
- **Net: 358/602 auto-resolved safely. The 244 remainder = a small, mixed human-review queue:** (a) old Roman garbles needing image-sourcing + human, (b) old garbles too degraded for the 7B vision model, (c) modern digit-errors recoverable by a per-volume (gap-free) forward-fill. Vision gave ~20 assistive readings (a few useful: 10d->105, XTIV->44).
- Artifacts: `chapter_vision_results.tsv`. NOTE: only 1850-1875 + scattered later volumes have pages_prep_gray on the 5090 -- a real gap for any future image/vision work.

### Continuation 26 (2026-06-11) — MODERN_DIGITFIX (safe) + vision diagnosis

- **MODERN_DIGITFIX tier** (Patrick: "do the modern subset if safe"): a REVIEW case where the OCR numeral is all-digits, too long (>4 = impossible chapter), AND a single-digit removal equals the sequence fill -> two independent signals agree -> safe. Cleared **29**. Tally now: AUTO 470 (322 fixes), CONFIRMED 134, OCR_PLAUSIBLE 358, MODERN_DIGITFIX 29, **REVIEW 215** (0.28% of acts). **991/1,206 garbled resolved (82%).**
- **Vision diagnosis (Patrick: "it's just 600 images, run the strong model"):** I gave up too early before. Real findings:
  - **qwen2.5vl:32b is BROKEN** -- corrupt CLIP/vision blob (`Failed to load CLIP model from ...blobs\sha256-043a...`), not OOM (31GB VRAM free). Fix = re-pull (~20GB).
  - llava:34b useless (refuses); **granite3.2-vision reads document text well** (read act numbers/titles) -- a viable reader.
  - **Page-targeting matters:** my smoke hit a TOC page (granite read "117An Act...118An Act"), not an act body. Must feed the act's real body page.
  - **Images scattered:** 1862's 660 imgs are on THIS box (5080) not the 5090; 1869-70 / 1873-74 on neither. Not a clean set -- needs gathering + some are genuinely missing.
- **Vision IS feasible for the 215 but is real plumbing** (re-pull 32b OR use granite, gather images across both boxes, target body pages). Scoped, pending decision.

### Continuation 27 (2026-06-11) — Claude reads the REVIEW scans directly (Patrick: "YOU can look at the 215!")

- **Key realization (Patrick):** I (Claude) HAVE vision -- I can `Read` the page scans myself, no local vision model needed. The broken qwen blob is irrelevant.
- **Staged the 215 REVIEW scans** (`review_worklist.py` -> `review_worklist.tsv` + `_vocab/review_imgs/`). **63 of 215 have images on the 5090** (pulled locally); 152 don't (some on the 5080, some missing).
- **Read 7 so far, 7/7 correct** (`chapter_vision_resolved.tsv`) -- and crucially several were cases where OCR AND sequence-fill AND digit-fix would ALL be wrong, so only reading the scan gets them: 1861 o91 `CLV`=155 (ocr 101, fill 152), 1861 o218 `CCCCXLIII`=443, 1905 o40 `XLIV`=44 ("restart" was spurious), 1941 o681 `1132` (digit error, fill off by 1), + fill-confirmations (1905 o202=241, o458=571, 1935 o90=105). Next-act numbers confirm each.
- **CONTINUING:** read the remaining ~56 available scans in batches; gather the 152 missing images (1862's 660 are on the 5080; re-source the truly-absent). Output: `chapter_vision_resolved.tsv` (authoritative readings -> overlay).

### Continuation 28 (2026-06-11) — Sonnet vision agents read the scans (validated, scalable)

- **Patrick: "Can sonnet read these?"** YES. Test: 1 Sonnet agent read 3 scans, got the readings right (CLV/CCCCXLIII/XLIV) but mis-CONVERTED one Roman->Arabic (CCCCXLIII->"4343"). Fix: **Sonnet returns the PRINTED numeral; Claude converts Roman->int deterministically** (zero arithmetic risk).
- **Fanned the 63 image-available cases to 3 parallel Sonnet vision agents** (~21 each, ~4 min, ~105k tokens / ~$1). Read 61/63 (2 UNKNOWN). Each writes `sub_chvis_part{N}.tsv` (vol, order, printed-numeral).
- **`aggregate_chvis.py`** converts + VALIDATES against my 7 hand-reads: **7/7 agree** -> Sonnet readings trustworthy. Output `chapter_vision_final.tsv` (61 resolved authoritative chapter numbers).
- Several resolved cases were ones where OCR+fill+digitfix ALL fail (1861 o91=155, o218=443; 1905 o40=44) -> only reading the scan gets them.
- **REVIEW 215 status: 61 resolved by vision.** Remaining 154 = 2 Sonnet-UNKNOWN (Claude to read) + 152 lacking 5090 images (gather from 5080: 1862's 660 imgs are there; re-source the truly-absent, then same Sonnet fan-out). NEXT: apply chapter_vision_final.tsv to the overlay as tier=VISION; finish the 154.

### Continuation 29 (2026-06-11) — Second Sonnet batch aggregated; REVIEW 129/215 resolved

- **Second Sonnet batch** (69 this-box / 5080 images, `sub_chvis2_part{1,2,3}.tsv`): read 68/69. Extended `aggregate_chvis.py` to ingest both batches; re-validated against my 7 hand-reads → still **7/7 agree**.
- **Combined: 129 of 215 REVIEW resolved** (61 batch1 + 68 batch2) → `chapter_vision_final.tsv` (now 129 rows).
- **3 Sonnet-UNKNOWN** (1971-vol1 o1034, 1982-vol3 o72, 1999-vol4 o159): I read the staged images myself — all three are **body-text pages, not chapter-heading pages** (parse `source_page` points off the heading). Confirmed unresolvable from the staged image; they join the image-sourcing bucket, NOT a reasoning failure.
- **86 still open = image-sourcing-bound** (83 no usable image + 3 wrong-page). All need the actual chapter-heading scan re-acquired; model capability is not the limit.
- Finding recorded durably in `docs/30_SYSTEM_DESIGN/CORRECTION_AND_DISPLAY_LAYER.md` ("Layer-2 in practice"). NEXT (deferred to the single mass-ingest): apply `chapter_vision_final.tsv` as overlay tier=VISION; re-source the 86 heading pages.

### Continuation 30 (2026-06-11) — "How is it possible we don't have the scans?" → we DO (corrected)

- Root-caused the 86 "open" REVIEW cases. My earlier "missing / re-acquire" wording was WRONG. Truth: the per-volume OCR bundle (`production-*`) is **text-only** — `ocr_consensus/`, `parsed_acts_fixed.json`, `page_classification.json`, `sha256.txt`; the `pages_prep_gray` rasters are a **working intermediate purged after OCR** to reclaim disk. Early 1850–1875 volumes already cleaned → no cached page image.
- **The source scans are intact** in `…\PatoLex-scratch\chief-clerk-archive\{vol}_Statutes.pdf` (verified: 1873-74=1086pp, 1869-70=1027pp, 1867-68=828pp). Any heading page is **re-renderable on demand with PyMuPDF**. So the 86 are a cheap local render + re-run of the Sonnet pass, NOT data loss or a model limit.
- Corrected the durable doc (`CORRECTION_AND_DISPLAY_LAYER.md`, "Finding (root cause…)") and added memory `ocr-bundles-image-free-source-in-archive`. Diagnostics: `PatoLex-scratch\diag_missing.py` / `diag_5080.py` / `find_sources.py`.

### Continuation 31 (2026-06-11) — Chapter REVIEW finished: 214/215 (render-from-PDF + deterministic-first + vision/bracket)

- Rendered all 86 open heading pages from `chief-clerk-archive\{vol}_Statutes.pdf` (calibrated `source_page-1`=PDF idx, 1:1 on 1862 660pp). `pipeline`-side scripts live in `PatoLex-scratch` (finish_chapters.py, aggregate_render.py, merge_final.py, combine_all.py).
- **Deterministic re-OCR first (Patrick's call):** fresh Tesseract + bracket-fit. Reliable for MODERN Arabic (1971=1235, 1982=830 confirmed) but NOT 19th-c Roman (caught a false 1869-70 o82=111 where page=113). Gated deterministic to Arabic only.
- **Vision (4 Sonnet agents, 84 pages) + bracket validation:** 48 fit→accepted; **35 flagged by bracket as misfits — bracket was RIGHT** (Sonnet stroke-drops on long Roman, e.g. CCXLI→CXLI). Hand-read all 35 against the page; bracket usually pinned the value. Method win: vision+sequence cross-check catches misreads neither catches alone.
- **214/215 resolved** → `chapter_corrections_GRAND.tsv` (129 prior + 85: 48 vision-fit/35 hand-read/2 arabic). Hand-reads in `chapter_handread_flagged.tsv`.
- **1 blocked: 1883-84-regular o42** — archive `1883-84_Statutes.pdf`/`_1E` are **15-page stubs**, not the full regular-session volume the OCR used. Real source-data gap; flagged to re-acquire.
- Durable finding in `CORRECTION_AND_DISPLAY_LAYER.md` ("Chapter REVIEW closeout").

### Continuation 32 (2026-06-11) — "How is a file missing?" → it wasn't; resolver bug. 215/215.

- Patrick challenged the "1 blocked / source missing" claim as scope-narrowing. He was right. The `1883-84_Statutes.pdf` (15pp) I'd grabbed is the wrong file — `production-1883-84-regular` was OCR'd from **`1883-84_Code.pdf` (448pp)**, matching the bundle's page_classification max of 448. My `resolve_pdf()` chose by filename keyword (preferred `*_Statutes.pdf`) and silently took a 15pp stub.
- Rendered o42 from the correct file → **CHAPTER LIV (54)** (Napa Asylum amendment, title matches). **Chapter REVIEW = 215/215.**
- Ran `verify_mapping.py` integrity sweep over all 16 open volumes: 1883-84 was the ONLY mismapping; every other chosen PDF's page_count comfortably exceeds its bundle max source_page.
- Fixes recorded durably: corrected `CORRECTION_AND_DISPLAY_LAYER.md` (was "missing source," now "resolver bug, file present"); new lesson `LESSON_2026-06-11_verify_source_dont_scope_to_handy.md`; memory `verify-dont-scope-to-handy`. **Rule: map source PDF by page-count match vs the bundle, never by filename; never declare "missing" from one folder — sweep both machines.**
- **Both-machines sweep CLOSED (`hunt_1883.py` on 5080 + 5090):** the correct `1883-84_Code.pdf` (25,308 KB) and the 15pp `1883-84_Statutes.pdf` (580 KB) exist on **both** boxes, byte-identical sizes — confirming nothing was missing anywhere; the bug was purely the filename-based picker. (5090 page counts showed `?` only because its base Python312 lacks `fitz`; matching sizes confirm identity.) This is the cross-machine verification the new rule demands, actually carried out rather than assumed.

### Continuation 33 (2026-06-11) — Sonnet adjudication expanded + residual characterized

- **Expanded Sonnet text-adjudication** past the timid 541 floor → `text_corrections_overlay.tsv`: AUTO_SAFE 538 / SONNET_FIX 909 / SONNET_NAME 257 / KEEP 587 / GARBAGE_FLAG 361. **1,704 fix types / 58,700 occ** (vs 16,506 floor). Spot-check confirmed recoveries gemma had wrongly GARBAGE'd (pubhe→public, superin→superintendent, shaj→shall). Added a FRAGMENT_HOLD guard (output-not-a-word, e.g. gation→igation) — needs wordfreq box to finalize.
- **Characterized full residual** (`residual_triage.tsv`, 467,978 types: 385,131 singletons): NAMELIKE **243,441 (52%)**, TYPO 146,770, NOISE 38,513, GARBLE 36,644, FRAGMENT 2,610.
- **Q (Patrick): are eeee singletons filtered?** Partially — NOISE+GARBLE (~75K) quarantine most, but ~6,785 structural-garbage tokens still leak into TYPO/NAMELIKE. Filter real but not airtight.
- **Q (Patrick): name dictionary for the rare names?** YES — highest-leverage move. NAMELIKE 243K conflates real surnames (karnette/migden/frusetta) with typos (pubhe). A census-surname + GNIS + given-name gazetteer splits them deterministically, reclassifying a big chunk of "garble" as real vocab (lowers true-error rate). Extends `ca_gazetteer.py` (319 names today).
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("Text-correction overlay — ... residual characterized").

### Continuation 34 (2026-06-11) — Name gazetteer BUILT + MEASURED: corrects my overclaim

- Built `build_gazetteer.py`: **370,183 names** (Census surnames 162k + SSA given 88k + GeoNames US places 120k + ca_gazetteer). GNIS per-state URLs dead (404/503); GeoNames US.zip is the working place source. Saved `name_gazetteer.txt`.
- Matched vs the 467,978 residual types: **only 5,438 types / 17,929 occ (1.2% / 2.4%)** are real names — and even that has coincidental matches (`repressuring`, `agricul`, `meanor`). `gazetteer_keep.tsv` = the KEEP list (top = real legislators ducheny/karnette/escutia/migden/poochigian, places islais/fricot).
- **HONEST CORRECTION:** I oversold the gazetteer as "highest-leverage" and claimed the 243K NAMELIKE bucket was mostly real names. **Wrong** — names explain only ~1–2% of the residual; NAMELIKE is overwhelmingly pronounceable OCR garble. A name dictionary does NOT materially lower the true-error rate. The residual really is mostly OCR damage/typos/fragments.
- Value retained: apply the gazetteer KEEP list (cross-checked, esp. high-freq) so corrections never overwrite a real name — a precision guard, not a residual-slasher.
- Durable: corrected the `CORRECTION_AND_DISPLAY_LAYER.md` note (was "highest-leverage move").

### Continuation 35 (2026-06-11) — residual is PRE-overlay; `agricul`/`ramento` already solved

- Patrick: why are line-split fragments (`agricul`|tural, sac|`ramento`) in the residual? They're ALREADY in `line_split_corrections.tsv` (11,156 rejoin fixes incl. NOHYPHEN + margin cases). They appear in `residual_triage.tsv` because the garble metric was computed BEFORE the line-reunify (+ Sonnet text + chapter) overlays were applied.
- Quantified (`xref_linesplit.py`): **1,104 residual types / 14,792 occ (~2%) are already-solved line-split fragments** (erty/superin/pensation/priation/retary/legisla…).
- **Key implication: the 0.44–0.56% residual OVERSTATES the true rate** — it reflects none of the 3 computed overlays. A faithful number needs re-measuring after overlays apply (at ingest).
- **Gap exposed:** reunify still misses margin-interleaved/cross-page fragments; recoverable by neighbour-concat + dict-check (Patrick's method). Extend before re-measuring.
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("The residual is measured PRE-overlay").

### Continuation 36 (2026-06-11) — REAL post-overlay number (0.50%) + reunify gap owned

- **Post-overlay residual (`post_overlay.py`): 0.5014%** (663,833 occ), down only from 0.5568%. Overlays removed 73,282 occ (sonnet 58,700 + linesplit 4,138 + names 10,444). Remaining: 0.0741% TRUE garbage (98k) + 0.4273% UNRESOLVED (565k = rare-real-words + unadjudicated freq2-9/singletons + uncaught fragments). NOT a final error rate; the 0.43% mass is unprocessed.
- **Reunify gap owned (Patrick: I told you to handle line wraps + margin notes — why fail?):** `line_split_reunify.py` DOES implement LOOKAHEAD=3 + margin handling (11,156 emitted, 1,507 margin) — so not ignored — but it's INCOMPLETE: misses (1) cross-page splits (scans per-page), (2) same-line spurious-space splits (`superin tendent` — line-oriented pass can't see mid-line space), (3) gaps >3 lines. **Real failure: declared done without verifying completeness vs the residual.** Fix: add cross-page + same-line space-rejoin + larger lookahead, re-run, RE-MEASURE.
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("The REAL number" + "Reunify gap").

### Continuation 37 (2026-06-11) — Reunifier FIXED (v2) + re-measured; singleton tail is the bottleneck

- Rebuilt `line_split_reunify.py` v2 (Patrick: "fix the unifier"): same-line space-splits + cross-page + NOHYPHEN-adjacent + LOOKAHEAD 3→6. Corrections 11,156→15,516. First run had same-line false joins (philadephia/administra/offerred) → added `_strong_known` (static dict OR zipf≥2.8); cross-page + line-break samples clean. v1 backed up as line_split_corrections_v1.tsv on 5090.
- **Re-measured (`post_overlay.py`): 0.5014% → 0.5005% — barely moved.** Why: (1) high-freq fragments overlap the Sonnet overlay (already fixed), reunifier unique add ≈ +1,348 occ; (2) residual is dominated by the ~385k SINGLETON tail, which neither reunifier (recurring) nor Sonnet (freq≥10) touches.
- **Honest conclusion:** fixing the reunifier was right for correctness but is NOT the lever on the rate. The 0.43% lives in 385k one-off tokens (rare-real-words + one-off garbles/fragments). That tail is the real work.
- NEXT: decompose the singleton tail (real-word vs garble vs fragment) to find the true error rate; Hans review on the reunifier (pipeline change).
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("Reunifier FIXED (v2)").

### Continuation 38 (2026-06-11) — Reunifier v3: multi-fragment + fuzzy + Hans

- Patrick (2 catches): v2 ignored 3+-fragment splits, and discarded misspelled-real-words (philade+phia='philadephia', dropped l). v3: **MAXFRAG=4 greedy multi-fragment** (consume whole run, no overlap) + **FUZZY_REVIEW flag-only tier** (`_insert1_known`: 1 inserted char from a strong word) → 131 found (subdivision/slaughter/apportionment/embezzlement/unconstitutional...), NOT auto-applied.
- **Hans round-1**: CRITICAL-3 (same-line overlapping emissions) REAL → fixed by greedy consume-run. CRITICAL-1 (missing break) was Hans MISREAD (break at line 139, verified). MAJOR-2 (pagekey)/MAJOR-4 (CRLF) hypothetical — verified data: pure-digit keys, LF-only. Hardened anyway (CRLF regex, numeric TSV sort, cross-page lookahead→LOOKAHEAD). Round-2 Hans on new loop still owed.
- Corrections 11,156→15,647. Re-measured: still **0.5003%** (singleton tail bound, not fragments).
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("Reunifier v3").

### Continuation 39 (2026-06-11) — corpus vocab: frequency ≠ validity (Patrick's "ridiculous" catch)

- Verified: `build_dictionary` = English (pyspellchecker+nltk+wordfreq) + small LEGAL_SUPPLEMENT, NO corpus vocab. Patrick right in principle (real corpus words wrongly flagged into residual).
- BUT tested it (`build_corpus_confident.py`): naive high-freq corpus vocab is CONTAMINATED — top "new" tokens are systematic OCR errors/fragments (`wuereas`/`secrion`/`publie`/`sball`/`trict`/`compen`/`sioner`), because OCR errors are SYSTEMATIC → frequency ≠ validity. Adding raw corpus vocab would legitimize thousands of recurring errors.
- Real corpus words DO hide there (`deukmbejian`=Deukmejian, `encumbrancers`, `distributees`, `roadmasters`, `indorser`) — value exists, but only after VALIDATION.
- Measured: only 1,707/467,978 residual reclaimed (several themselves errors). So residual is mostly GENUINE errors, not wrongly-flagged real words.
- Correct path: validate (LLM/Sonnet) the high-freq corpus vocab to split real-words from systematic-errors; systematic errors (secrion→section) are themselves high-value bulk fixes.
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("Corpus vocabulary: frequency ≠ validity").

### Continuation 40 (2026-06-11) — Singleton autocorrect (Patrick's idea) = the real tail lever

- Freq≥2 passes skipped the 385k singletons (autocorrecting freq-1 risks corrupting rare real words). Tested corpus-weighted edit-1 autocorrect on 8,000 sample (`singleton_autocorrect_test.py`): **23.1% confident fix (~89k of 385k)**, 13.8% ambiguous (~53k), 63.1% no-candidate/deep-garbage (~243k).
- Confident sample mostly excellent (cisplayed→displayed, califorcia→california, fuperintendent→superintendent, impiisonment→imprisonment). These are one-off typos never processed before.
- Caveat: corpus-freq weighting sometimes targets a FREQUENT CORPUS ERROR (clther→cither, ofticia→officia) ~10-15%; mitigate by also requiring general-English-common target + flagged reversible layer + LLM on borderline.
- **Corrects my "tail intractable" claim:** ~25-35% recoverable typos, ~60% deep unrecoverable garbage (re-OCR floor), small real-word remainder. Most promising rate-reducer found.
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("Singleton autocorrect").

### Continuation 41 (2026-06-11) — "60% garbage" REFUTED (it's ~17%) + pass architecture

- Patrick challenged "60% deep garbage" (built on weak proxy: no-edit-1 = garbage). Measured (`singleton_decompose.py`, 6k, context): **GARBAGE structural = 17.4%** (solid), EDIT1 = 15.7%, OVER_MERGE 38.5% (INFLATED — permissive known() false-splits typos), STANDALONE 28.3% (mislabeled — mostly edit-2 typos + fragments), FRAG ≈0% (artifact — needs corpus-word dict). **Tail is ~17% garbage, ~83% recoverable.** My 60% was wrong.
- Patrick's 5 points = correct pass architecture: (1) dict integration FIRST (validated corpus vocab + gazetteer_keep, NOT raw 370k; currently only 319-name ca_gazetteer wired in — the rest are standalone, never integrated — HONEST gap), (2) reunify frags, (3) NEW split pass for over-merges, (4) spell edit-1/2/3 (singletons skipped by freq≥2 passes), (5) systematic-error sweep (largely done, unverified).
- edit-2 in decompose was infeasible (enumerated ~500k cands/token) → killed stuck 5090 python (PID 44860), re-ran without it.
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("Singleton tail decomposed" + "Correct correction-pass architecture").

### Continuation 42 (2026-06-11) — Dict integration LIVE + tail decomposed RIGHT (Patrick: integrate, fix edit-2, done right)

- **Dict integration DONE (names):** `build_dictionary` now loads `_vocab/dict_additions.txt` (5,438 DB-validated corpus-attested names) → 328,139→333,563. Reunifier + all passes benefit. Legal/corpus vocab NOT added — both heuristic curations failed (novel-filter kept `admunistra`/`aforesnid`; name-filter dropped real legislators & kept `aaad`). 3rd proof heuristics can't curate vocab → legal vocab needs LLM validation.
- **Singleton decompose FIXED** (Patrick's 2 bugs: OVER_MERGE-before-EDIT1 order + permissive `known`=wf>0 false-splitting typos; plus edit-2 was removed). v2: integrated dict, reliability order, `strong_known` strict split, efficient edit-2 (pyspellchecker). Result: **GARBAGE 17.1%, EDIT1 36.3%, EDIT2 25.2%, OVER_MERGE 1.9% (was 38.5%), STANDALONE 19.4%.** → ~17% garbage, ~63% autocorrectable, ~19% harder typos. `applicatien`/`swearirg` now correctly EDIT1.
- **"60% garbage" fully refuted; tail is overwhelmingly recoverable.** Error rate is very reducible via reunify→split→spell-1/2/3.
- Scripts: `build_dict_additions.py`, `singleton_decompose.py` (5090 + scratch); `correction_passes.py` build_dictionary patched.
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("Dict integration LIVE + singleton tail decomposed RIGHT").

### Continuation 43 (2026-06-11) — Hans review of dict-integration + reunifier; CRITICAL fix

- Ran Hans on the two pipeline changes (build_dictionary additions + reunifier multi-fragment/fuzzy).
- **CRITICAL C2-1 (real, verified):** shortest-first MAXFRAG greedy emitted the shorter sub-word and stranded the rest (`dep art ment`→emits `depart`, strands `ment` instead of `department`). FIXED → **longest-first** (only takes a longer run if it IS a real word). Verified: `spacesplit3` now appears (3-fragment recovered).
- **C2-3 (major):** `_insert1_known` returned arbitrary first match → now returns None if AMBIGUOUS (>1 strong word). fuzzy 131→121. **C2-4:** lower bound 6→5 (catches `ageny`→agency). **C1-1:** removed dead `globals()` guard. **C1-4:** dict_additions committed for auditability + dropped 3-char name tokens (len≥4 → 5,425).
- Hans's CRITICAL on build_dictionary (C1-4) downgraded on verify: names only affect `is_known`, not `is_common` (de-merge unchanged); coincidental-name risk is the known small contamination; mitigated by len≥4 + committing the file. Hans also caught my doc overclaim conflating the 319 ca_gazetteer with the 5,425 dict_additions — corrected.
- Dict integration visibly helps reunifier: name-fragments now rejoin (`covaru+bias`→covarubias, `hy+desville`→hydesville). Corrections 15,647→15,434 (len≥4 + longest-first).
- Durable: design doc updated. NEXT: LLM validation of corpus legal-vocab candidates (running).

### Continuation 44 (2026-06-11) — LLM validation unlocked the legal-vocab dict layer (both owed items DONE)

- 4 Sonnet agents validated the 1,266 genuine-novel candidates: REAL 446 + NAME 119 = **565 real vocab** (estrays/subpenas/depositaries/appraisements/acetylmethadol/accountholder); FRAGMENT 412 + ERROR 289 = 701 correctly excluded (expendi/cerning/frecholders/hcense). LLM cleanly did what heuristics couldn't (3x).
- Merged validated terms → **dict_additions.txt = 5,926 (5,425 names + 501 legal vocab)**, live in build_dictionary. `validated_legal_vocab.txt`, `sub_nv_b1..4.tsv`, `aggregate_nv.py`.
- Both owed items now done: Hans review (Cont. 43, CRITICAL longest-first fix) + LLM validation (this).
- Pattern locked in: corpus-vocab curation = real ground truth (name DBs) OR LLM validation, NEVER a frequency/distance heuristic.
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("LLM validation unlocked the legal-vocab dict layer").

### Continuation 45 (2026-06-11) — SEQUENCE insight + correction cascade harness

- **Patrick: "the sequence we run the tools in is very important."** Correct and load-bearing. Running each pass in ISOLATION on raw text is why each over-fired (word-splitter mangled `tollowing` because the typo was still present). Passes must run as an ORDERED CASCADE, each on the previous pass's output: dict → reunify (fragments) → autocorrect (typos) → split (over-merges) → sonnet → re-measure. Order also IS the conflict-resolution policy. Recorded in `CORRECTION_AND_DISPLAY_LAYER.md` ("SEQUENCE IS THE ARCHITECTURE").
- Built `word_splitter.py` (over-merges) — heuristic only ~50% precise even guarded (edit-2 typos slip, real merges mis-segment `actshall`→"acts hall", place names split) → CANDIDATE generator for LLM validation, NOT auto-apply. Over-merges are ~2% of residual.
- Built `autocorrect_pass.py` (edit-1/2, zipf-ranked to avoid correcting one OCR error into another). Killed the isolated-on-raw run (pointless once cascade understood).
- Built **`correction_cascade.py`** — runs the cascade per-volume in order, measures flagged-rate raw vs after, with run-log heartbeats, per-volume corrected/audit/counts persistence + DONE markers (resumable). Autocorrect is EDIT-1-only in the cascade (edit-2 brute force is intractable corpus-wide → deferred, needs SymSpell). Running now.
- NEXT: cascade numbers (raw vs post-cascade flagged rate) + then a validation SAMPLE (LLM-judged) for the true defensible error rate.

### Continuation 46 (2026-06-11) — Cascade RAN: 1.10% → 0.42% flagged (62.5%); autocorrect-precision caveat

- Full cascade over 133.7M tokens (`cascade_report.json`): **raw 1.1042% flagged → 0.4153% after = 62.5% relative reduction.** Raw 1.10% ≈ old baseline 1.14% (comparable); **0.42% beats old Pass-ABC 0.56%.** Stages: reunify_break 225,418 / autocorrect_e1 647,402 / sonnet 41,113 / split 4,805.
- **CAVEAT (verified by spot-check, not assumed):** autocorrect-e1 ~80% precise (juagment→judgment ✓) but ~15-20% WRONG — over-merge grabbed before split (stateboard→skateboard), orphaned fragments mis-fixed (ferred→feared=referred, urer→user=treasurer), Roman numeral corrupted (cxiii→xiii). A wrong autocorrect = VISIBLE error → INVISIBLE error (worse for legal). So 0.42% flagged ≠ true error rate.
- NEXT: (1) tighten autocorrect (protect roman numerals, affix-of-word fragments, raise margin; consider split-before-autocorrect); (2) validation SAMPLE judged vs ground-truth image for the defensible number (measures residual-visible + autocorrect-invisible errors). Audit trail `_cascade/audit/{vol}.tsv` makes every change reviewable.
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("Cascade RESULT + autocorrect-precision caveat").

### Continuation 47 (2026-06-12) — Cascade TIGHTENED (reorder + guards), re-running

- Reordered cascade: **reunify → SPLIT → autocorrect → sonnet** (split BEFORE autocorrect, so over-merges aren't mis-fixed by edit-1). Autocorrect guards added: skip Roman numerals (`is_roman`), skip affix-of-a-real-word tokens (orphaned fragments `ferred`/`urer`/`examina` → leave flagged not mis-fixed). Tightened thresholds: zipf 3.0→3.3, margin 0.4→0.5.
- Cleared `_cascade/done/*.marker` (logic changed → full re-run). Re-running.
- NEXT: compare tightened before/after + re-validate autocorrect precision; then the ground-truth validation sample for the defensible number.

### Continuation 48 (2026-06-12) — Cascade: per-stage measurement + STOP-before-sonnet (Patrick)

- Patrick: the harness should expose PER-STAGE flagged rates so we can tune each stage/order and compare runs apples-to-apples "heading into sonnet", then run sonnet once tuned. I'd only measured raw + final. Fixed: `_measure_now()` after each stage → report `stage_progression` (raw → after_reunify → after_split → after_autocorrect). `APPLY_SONNET=False` halts before the overlay.
- Re-running (sonnet off) for the per-stage breakdown of the tightened cascade.

### Continuation 49 (2026-06-12) — Cascade restructured: per-stage OUTPUTS + timing + resume

- Patrick: capture per-stage OUTPUTS (not just counts); and run-log needs per-stage TIMING + a heartbeat. Restructured `correction_cascade.py`: each stage reads the prior stage's PERSISTED output (`out_reunify`/`out_split`/`out_autocorrect/{vol}.json`), writes its own output + per-stage audit (`{vol}.{stage}.tsv`) + per-stage flagged measurement + done marker. `CASCADE_FROM={stage}` re-runs from any stage reading the prior cached output (tune one stage without re-running earlier ones).
- Added per-stage **cpu-seconds** timing (timed each transform, aggregated) → report `stage_cpu_seconds` + final log + heartbeat. Heartbeat every 15s shows raw%→pre-sonnet% + per-stage cpu time + wall.
- Cleared stale `_cascade`, syntax-checked, running fresh from reunify (sonnet held out).

### Continuation 50 (2026-06-12) — Tightened cascade per-stage result + heartbeat fixes

- Per-stage progression (tightened, sonnet held out, 133.7M tokens): raw **1.1042%** → reunify **0.9319%** (226,285 fixes) → split **0.9282%** (4,805) → autocorrect **0.4977%** (574,543 e1). **Pre-sonnet 0.4977%, 55% reduction, 7min.** cpu: reunify 352s / split 1,624s / autocorrect 2,278s.
- Split = low-value (4.8k) + expensive (guards run edit-1/token) → tuning target. Autocorrect = big reducer + cpu hog.
- **Autocorrect precision tightened ~80%→~90-95%** (verified spot-check): affix+roman guards killed fragment mis-fixes (ferred/urer/examina) + cxiii. Residual: short-merge mis-grab (whoare→whore, split MINPIECE=4 misses it) + ambiguous garbles.
- Heartbeat fixed (Patrick): was illusory (volume-completion-gated) → now a daemon thread fires every 15s on a true wall clock with per-stage counts+rates + cpu timing.
- Per-volume counts ALREADY persisted (`counts/{vol}.json`); adding a consolidated per-volume summary TSV next.
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("Tightened cascade — per-stage progression + precision").

### Continuation 51 (2026-06-12) — Per-volume summary (counts + timing)

- Per-volume counts + timing were ALREADY persisted (`counts/{vol}.json`). Added `cascade_summary.py` → consolidated `per_volume_summary.tsv` (per-volume raw/reunify/split/presonnet rates, reduction, per-stage correction counts, per-stage cpu seconds). Auto-generated at end of every cascade run.
- **Quality is era-stratified:** worst = 1862 (8.19%→4.35%), 1863 (7.33%→3.60%), 1869-70 (7.45%→3.56%); best = modern 1996-1998 (~0.05%). `1873-74-code` is an outlier (5.06%→4.22%, only 16.8% reduction — code-volume text resists autocorrect). The corpus 0.50% avg is dragged up by the 19th-c tail.
- Slowest volumes = large modern (1991-vol1 136s); split+autocorrect dominate cpu (edit-1 per token).
- Both answered Patrick's "per-volume counts?" + "per-volume timing?": yes, captured + now surfaced.

### Continuation 52 (2026-06-12) — Procedural garbage filter (Patrick)

- `garbage_filter.py`: classify post-cascade flagged tokens, high-precision structural-only. Of 664,247 flagged: **guaranteed garbage 77,297 (11.6% ≈ 0.058% corpus)** [repeat3 66,964 / cons5 8,600 / toolong 1,712], **roman numerals 4,906 (0.7%, valid not errors)**, **recoverable 582,044 (87.6% ≈ 0.436%)**. 4s.
- Verify-the-output: first cut mis-flagged Roman numerals (cccc runs) + single-� words (cl�rk=clerk) as garbage → fixed (exclude roman charset, drop single-mojibake; residual novowel nicks ~21, negligible).
- Use: subtract roman from error count; garbage = re-OCR floor; ~0.436% recoverable = real target. Fold garbage/roman/recoverable split into cascade measurement next.
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("Procedural garbage filter").

### Continuation 53 (2026-06-12) — Garbage filter refined (4+ not 3+) + integrated into cascade

- Patrick: 3+ repeat too aggressive (fiancee→fianeee recoverable); long→splitter first; garbage collector must be IN the cascade. Implemented: **4+ repeat** for garbage + 3-repeat recoverability check; `_decompose_long` in split stage for run-ons; `classify_residual` is now an in-cascade stage reported in cascade_report.json.
- **Answers 0.058 vs ~0.040:** the 3+→4+ change moved ~17k recoverable 3-repeats out → garbage **77,297 (0.058%) → 60,404 (0.0453%)**. The 3+ rule was the inflation (exactly as flagged). Long-decomp: split 4,805→5,590.
- Final pre-sonnet residual: **0.0453% garbage floor + 0.4482% recoverable + 4,906 valid Romans** (of 0.4971% flagged). Run wall 6.6min (split+autocorrect are the cpu-heavy stages; from-split doesn't save much). Timer heartbeat confirmed firing.
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("Garbage filter refined + INTEGRATED into the cascade").

### Continuation 54 (2026-06-12) — Gazetteer onto 5090 + reunify A4 positional within-window matcher (Patrick)

- **"wtf about the gazetteer":** audited which artifacts live on which box. `dict_additions.txt` + `validated_legal_vocab.txt` were already on the 5090 in `_vocab/` (built there); only `name_gazetteer.txt` (3,356,144 B, built on the 5080) was missing → that's why NAMELIKE came back 0. scp'd it over; removed the dead path-override line in `recoverable_compose.py`; re-ran → NAMELIKE now 259 types / 2,557 occ (0.4%). Note: gazetteer membership is a triage HINT, not exoneration — it also catches OCR errors that collide with the name list (`sheritt`, `wilham`), per the dictionary-membership lesson.
- **Patrick caught a real miss:** the reunify stage was NOT the design we agreed. The `LOOKAHEAD=6` I'd wired was a 6-**line/page** boundary window (last-tok-of-line + first-tok-of-later-line) + same-line adjacency — NOT the agreed **within-~6-words positional** partner search. FRAGMENT bucket (8.7%) was the evidence.
- **Built A4** in `stage_reunify`: reading-order token flatten; unknown affix-anchor scans `FRAG_WINDOW=6` tokens in the right direction (suffix→back, prefix→forward); guards: anchor non-word, join `strong_known`, **test join before the known-partner check** (the tail half is usually a real word: `incorpo|rated`), real word between halves stops the search, nearest-first. Micro-tested 4 cases (fwd-gap, back-gap, real-word block, out-of-window) before the full run.
- **Result (full re-run from reunify, 205 vols, 449s wall): `reunify_window` = 6,681 joins, sampled 30/30 correct.** after-reunify 0.9319→**0.9268%**, **pre-Sonnet 0.4971→0.4921%**, recoverable 0.4482→**0.4431%**, reduction 55.1→**55.5%**. Honest scope: ~13% of the FRAGMENT bucket; rest need partner >6 away / OCR-corrupted partner / genuinely orphaned.
- **Launch lesson:** OpenSSH-on-Windows reaps the process tree when the SSH command returns — `Start-Process` detach died (0 python, empty stdout). `Win32_Process.Create` spawns a truly detached process that survives. Use that (or a Scheduled Task) for long 5090 jobs.
- Durable: `CORRECTION_AND_DISPLAY_LAYER.md` ("Reunify A4 — positional within-window fragment matcher").

### Continuation 55 (2026-06-12) — Edit-2 SymSpell engine + precision finding (route to Sonnet) + mojibake/context tools + refactor plan

- **Built corpus-aware SymSpell edit-2** (`symspell_e2.py` + `build_corpus_freq.py`): custom (not symspellpy) so the correction TARGET vocab + ranking are CORPUS-NATIVE (fixes the bug that general-zipf e1 rejects archaic/legal words like `thereon`). 44k→35k target words after tightening to strict-dict membership.
- **Measured precision honestly (the gate):** es1(dist-1) ~83%, es2(dist-2) ~75-80% — BELOW legal-grade. Failure classes: misspelled targets (fixed via strict membership), run-together words (`sameand`="same and"), genuinely ambiguous (`peution`=section/petition), garbage-source. **DECISION (Patrick): route SymSpell to Sonnet context-adjudication, do NOT auto-apply.** Gated behind `CASCADE_APPLY_SYMSPELL=1` (default OFF) so the cascade stays deterministic.
- **Local-model evidence reconfirmed:** gemma3:27b = 62% adjudication agreement, over-discards real words, 33x substitution-inflation → NOT the adjudicator; at most recall-preserving tail triage.
- **Worklist sizing:** 124,353 distinct token→fix TYPES / 280,063 occ. freq>=10 = 2,897 types (39% of occ, ~217K Sonnet tok); freq>=2 = 25,965 (~1.9M); all = ~9.3M. Long tail: 98k singletons = 35% of occ.
- **Mojibake fix** (`mojibake_fix.py`, Patrick): constrained-position substitution (the `�` marks the error location) → far higher precision than blind edit; auto-applyable when unambiguous. Refactored to injectable `mojibake_candidates(t, known)` + `choose_fix(cands, score)`.
- **Context-resolve prototype** (`context_resolve.py`, Patrick): collocation/bigram disambiguation of ambiguous candidates (legal text is hyper-repetitive). Injectable `ctx_score` + `resolve`. Both #2 and #3 are FREE deterministic ways to shrink the AI worklist before Sonnet.
- **5090 went OFFLINE mid-work (~Tailscale-level, tx>0 rx=0)** — pivoted to local 5080 work (Python 3.12, no pipeline deps). **Local unit tests** (`pipeline/test_local_fixes.py`, 13/13) validate both cores with synthetic dicts — no corpus/box needed.
- **Refactor + open-source plan** (`docs/30_SYSTEM_DESIGN/PIPELINE_REFACTOR_PLAN.md`): inventory (canonical/superseded/analysis/llm); #1 finding = duplication (`build_dictionary` in 5 files, `known/zipf/edits1/affix` copy-pasted in ~8); target `ocrcorrect/` injectable package; **golden-master regression fixture** (`pipeline/tests/golden_master_cascade.json` + `check_golden_master.py`, verified PASS) locks the deterministic numbers so the eventual refactor is provably non-regressing. Sequence: plan+fixture NOW, execute refactor AFTER tuning + box back.
- Memory added: `opensource-ocr-engine-plan`. Token-budget note: Sonnet runs on Patrick's SUBSCRIPTION (weekly limit, resets Sat 2 PM) not API $ — spend heavier adjudication BEFORE reset.
- **Honest scope check (Patrick asked):** I only DOCUMENTED the mess + did boy-scout cleanup on the 2 files I touched — the duplication (build_dictionary x5, primitives x8) and dead files are all still present; nothing deleted, no `ocrcorrect/` package exists. Wrote `docs/30_SYSTEM_DESIGN/PIPELINE_CLEANUP_RUNBOOK.md` — a step-by-step for a FRESH session to execute the cleanup (extract `dictionary.py`/`edits.py`, re-point importers, delete verified-dead files, validate against the golden master on the 5090). 5090 back online 15:27 UTC.

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

### Correction-pipeline lessons (2026-06-11 phase)
- **VERIFY, don't assert.** Nearly every confident claim I made this phase was wrong and caught by Patrick + measurement: "scans are missing", "the file is missing", "60% of the tail is garbage", "the tail is intractable", "names are the highest-leverage move." Each collapsed under a real check. Measure the contents of a bucket; never label it by what one test couldn't do.
- **Frequency ≠ validity for OCR.** Systematic OCR errors recur thousands of times (`secrion`→section, `sball`→shall), so a frequency gate happily admits them as "real words." Corpus frequency cannot validate vocabulary.
- **Heuristics cannot curate vocabulary — proven 3×.** freq+edit-distance filters kept fragments (`admunistra`) and legal-word errors (`aforesnid`); an edit/affix filter dropped real legislators and kept `aaad`. Clean curation needs **real ground truth (name DBs) or an LLM validation pass** — and the LLM pass worked (split 1,266 candidates into 565 real / 701 error+fragment).
- **The error-rate number is measured PRE-overlay.** The 0.56% (and 0.50% "after") reflect text with NONE of the computed overlays applied, and with a then-broken reunifier — so they're upper bounds, not the rate. The real number only exists after overlays apply + re-measure.
- **"No edit-1 candidate" ≠ garbage.** It conflates garbage with fragments, over-merges, and edit-2 typos. The honest singleton split is ~17% garbage / ~63% autocorrectable / ~19% harder typos.
- **Don't scope to one machine.** "Missing file" was a filename-picker bug + not sweeping both boxes; the 448-page source was right there named `_Code.pdf`. A "missing" claim needs a both-machines sweep reconciled against what artifacts prove must exist.
- **OCR bundles are text-only; source PDFs live in `chief-clerk-archive`.** Absent `pages_prep_gray` ≠ data loss — render the page from the archive PDF (`source_page-1`, calibrated 1:1).
- **Classifier ORDER + permissive `known()` corrupt results.** Putting OVER_MERGE before EDIT1 (with `wf>0` splits) mislabeled typos as merges; longest-first + `strong_known` fixed it. Same `wf>0`-too-permissive trap recurred in the reunifier and the de-merge.
- **Correction-pass architecture:** dict-integration FIRST → reunify → split → spell-1/2/3 → systematic sweep; all reversible; re-measure after applying.
