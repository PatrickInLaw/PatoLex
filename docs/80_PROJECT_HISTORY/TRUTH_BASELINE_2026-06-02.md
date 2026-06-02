# PatoLex TRUTH BASELINE — 2026-06-02

**Purpose:** The authoritative, evidence-backed current-state-of-truth, verified against **code + live DB + artifacts + the OS scheduler** — NOT by trusting the existing docs (known stale/partly wrong). This is the reference the wholesale documentation rewrite must be reconciled against. Companion: `DOC_DELTA_MAP_2026-06-02.md` (doc-by-doc remediation table).

**Method:** Live local Postgres queries (`localhost:5432/patolex`), direct reads of `pipeline/` code with cited line numbers, `Get-ScheduledTask`, `.claude/settings.json` + hook source, and `corpus_page_counts.csv`. Builds on (does not redo) `COLD_START_DOC_AUDIT_2026-06-02.md`, `MODERN_STATUTE_FORMAT_2026-06-02.md`, `BUILD_RUNBOOK.md`, and the corrected `DATA_SOURCES_HISTORICAL.md`.

**Evidence legend:** [DB] = live query result · [CODE file:line] · [TASK] = Task Scheduler · [FS] = filesystem artifact.

---

## DIMENSION 1 — PROJECT SCOPE / GOAL

**VERIFIED CURRENT SCOPE:** PatoLex is a public-facing point-in-time archive of California statutory law, **built historical-first / risk-first**: full depth from **1850 (blank page) → present**, no public launch until the full corpus is present and validated; agentic-coding-at-scale is a secondary goal. The corpus is built **forward from 1850 (the only baseline)**, with the **1872 codification modeled as a recodification EVENT in the chain, not an enact-from-nothing baseline**.

- CLAUDE.md still *describes* the older "POC = modern 1991-present first, historical = Phase 2" framing in its "What PatoLex Is" section, but its memory-layer and ROADMAP override it. **Net current truth = historical-first.** [ROADMAP.md:11, "Built historical-first, risk-first"; revision 2026-05-31 "Reversed to historical-first"]
- **`ARCHITECTURE.md` is ACTIVELY WRONG on scope.** It leads (line 7) with: *"The POC targets the modern point-in-time archive (1991-1992 session to present)... Full historical depth back to 1849... is a Phase 2 research program, not part of the POC."* [ARCHITECTURE.md:7] This is the SUPERSEDED framing — the exact reversal happened on 2026-05-31. A cold reader hitting ARCHITECTURE first is actively misled on both **scope** (it inverts the build order) and **stack** (see Dimension 3).

**FLAG:** ARCHITECTURE.md is the single most scope-misleading doc in the repo.

---

## DIMENSION 2 — SCHEMA AS BUILT (live DB)

**7 tables exist, matching `src/lib/db/schema/` (8 schema modules: enums + 7 tables) and migrations `drizzle/0000`–`0004`.** [FS: drizzle/0000_breezy_randall_flagg.sql … 0004_clever_proteus.sql; src/lib/db/schema/*.ts]

**Live row counts** [DB]:

| Table | Rows | Note |
|-------|------|------|
| `source_document` | **21** | 1850-1875 session volumes |
| `enactment` | **4262** | one per act |
| `provision` | **4262** | |
| `change_event` | **4262** | append-only system of record (1 per act) |
| `designation_history` | **4262** | |
| `provision_version` | **0** | **0 BY DESIGN — confirmed** (materialization is a deferred read-model sweep) |
| `lineage_edge` | **0** | no recodification edges materialized yet (1872 recod not yet processed) |

**Actual columns** (verified against information_schema — schema is richer than older docs imply):
- `source_document`: id, type, citation, jurisdiction, source_channel, scan_quality, ocr_engine, ocr_cer_estimate, trust_level, retrieved_at, clean_channel, **content_sha256**, edition_year, claimed_year, verification_note, file_name, source_uri, corpus, coverage_start_year, coverage_end_year, section_range, page_count, media_format, **ocr_stats(jsonb)**. PK = `id`.
- `change_event`: id, enactment_id, provision_id, action, new_text, operative_date, in_act_order, supersedes_id, superseded_by_id, double_jointed_with_id, chaptered_out, diff_from_prior(jsonb), source_document_id, page_ref, trust_level, **confident(bool)**, **confidence(real)**, **ocr_provenance(jsonb)**. The capture-all-signals columns are wired.
- `enactment`: source_document_id, citation, jurisdiction, session, legislature, chapter_number, chaptered_date, effective_date, operative_date, title, bill_number, kind. **There is NO `enacted_date` column** (older prose references one — it does not exist; dates are chaptered/effective/operative).
- `provision`: id, public_id(uuid), jurisdiction, unit_type, current_designation, status.
- `lineage_edge`: enactment_id, predecessor_provision_id, successor_provision_id, edge_type, text_disposition, continues, note.

**Built vs documented:** the live schema matches the SCHEMA_DESIGN intent (event-sourced, domain-neutral, synthetic provision id + uuid public_id, daterange/tsvector on provision_version). One naming caveat: ROADMAP/SCHEMA_DESIGN reference a first-class **`recodification`** entity — **no such table exists**; recodification is represented via `lineage_edge` (edge_type) instead. Verify which the design intends.

---

## DIMENSION 3 — PIPELINE AS CODED

**Canonical ingest = `pipeline/ingest_clean.py` — CONFIRMED.**
- Has `if __name__ == "__main__":` guard [CODE ingest_clean.py:1183].
- Resolves `source_document` by **content_sha256** read from `sha256.txt` (Hans C3) [CODE :953-1012].
- **Double commit gate:** requires `--commit` arg AND `PATOLEX_ALLOW_COMMIT=1` env; aborts with FAIL otherwise [CODE :1153-1168]. Also needs `PATOLEX_PG_DSN`. Dry-run by default.
- Per-volume atomic: scoped purge-then-insert keyed by `(source_document_id, in_act_order)`.

**Superseded lossy = `pipeline/5080/ingest_from_ocr.py` — CONFIRMED HAZARD.**
- **NO `__main__` guard** — the driver loop runs at module top level [CODE ingest_from_ocr.py:493-507], so **importing the module triggers a DB ingest**. This is why `PatoLex_Ingest_5080` stays disabled.
- Version-A, single-engine parse; its rows are meant to be replaced by `ingest_clean.py`.

**Consensus = `pipeline/consensus.py`.**
- **Engines = Tesseract + docTR + Surya — THREE engines, `N_MAX_ENGINES = 3`** [CODE consensus.py:107-119]. ENGINE_PRIORITY = `["tesseract","doctr","surya"]` (tie-break only, never overrides a vote).
- Method tags `token_majority_3` / `token_majority_2` / `single` [CODE :80,558].
- **DISCREPANCY (see Dimension 6 + delta map): every prose doc says "4 classical engines incl. PaddleOCR." The consensus code uses only 3 — PaddleOCR is NOT a consensus voter.** The live DB confirms the code: 4057 acts `token_majority_3` + 205 `token_majority_2`, zero with a 4th engine [DB].

**OCR / queue scripts (repo snapshots — live copies run from each box's PatoLex-scratch):**
- 5090: `supervisor_5090.ps1`, `queue_worker.py`, `ocr_only_5090.py`, `queue_claim.py`, `scale_to_one_5090.ps1` (the 0800 backoff), `production_queue_state.json`.
- 5080: `queue_worker_5080.py`, `ocr_only_5080.py`, `ingest_supervisor.ps1`, `ingest_watcher.py`, `stop_5080_worker.ps1`, `parse_born_digital.py`.

---

## DIMENSION 4 — BUILD STATE (live DB)

**System of record = version-B multi-engine consensus, 1850-1875, 4262 acts. CONFIRMED via DB.**
- `change_event.ocr_provenance->>'consensus_method'`: **token_majority_3 = 4057, token_majority_2 = 205** (total 4262). Zero single-engine committed rows. [DB]
- `change_event.confident`: **t = 3424, f = 838** (all `trust_level = ocr_uncertain`). [DB]
- 21 source documents, claimed_year **1850 → 1875** (biennial labels 1863-64 … 1875-76); citation-year act counts run 1850(97) … 1875(285). [DB]
- `provision_version = 0`, `lineage_edge = 0` — both expected (materialization + 1872 recod deferred). [DB]

**Data-quality outliers worth noting (not blockers):** `min(chaptered_date)=1831-05-02` and `max=1895-04-25` are clearly parser misreads (a few acts in 1850-1875 volumes got out-of-range dates). The citation-year distribution (the reliable axis) is clean 1850-1875. This is a known OCR/parse fuzz tail, consistent with `confident=f` on 838 events.

**In flight / OCR'd-but-not-ingested:** **CANNOT be verified from the repo.** The repo's `pipeline/5090/production_queue_state.json` is a STALE version-control snapshot (frozen 2026-06-02 ~06:43; lists only through `1875-76`, note says "1850-1861 banked"). The *live* queue lives on the boxes' PatoLex-scratch, not in the repo. BUILD_RUNBOOK §5 claims **1877-1910 OCRing** — plausible and consistent with the design, but **NOT independently verifiable from this repo/DB** (those years are not yet in the DB, and the live queue is off-box). **FLAG as unverified-from-here.**

---

## DIMENSION 5 — CORPUS REALITY

**653-PDF Chief Clerk backbone, 1850-2008 — CONFIRMED.** `corpus_page_counts.csv` = **654 lines (653 PDFs + header)**, first body row `1850_Statutes.pdf,1850,480,TRUE`, last `2008_Vol5.pdf,2008,1716,TRUE`. [FS]

**Three data tiers (per corrected DATA_SOURCES_HISTORICAL §1d) — consistent with artifacts:**
- (a) **Image-only ≤ ~1996** → OCR (multi-engine consensus). The 21 ingested volumes (1850-1875, `media_format` = `pdf`/`ocr_text` in DB) sit here.
- (b) **Born-digital Chief Clerk ~1997-2008** → direct text extract via `parse_born_digital.py` (NO OCR). Verified on 2001 & 2008 volumes.
- (c) **leginfo PUBINFO XML, 1989/1994-present** → reconstruct backward (separate channel, `DATA_SOURCES.md`).
- Image-only/born-digital **crossover ~1997, exact volume TBD**; OCR campaign ceiling ~1993-94 (NOT 2008).

---

## DIMENSION 6 — FORMAT ERAS + PARSER STATE

**Format evolution (single-vol "Acts" → multi-vol "Chapters") — consistent across code + docs:**
- **1850 – ~1910:** single-volume/year; `CHAP. N / An Act / do enact / Approved <date>`; Roman chapters; OCR-fuzzy long-s in 1850s-1870s. Handled by the pre-1900 OCR-fuzzy parser.
- **~1915+:** multi-volume/year (`Vol1_Chapters`..`VolN`), **chapters numbered continuously across a year's volumes** — requires multi-volume roll-up. **OPEN WORK — not implemented.**
- **Modern (~1997+ born-digital):** `Approved by Governor <date> / Filed with Secretary of State <date>`, Arabic chapters, no bill markers.

**Parser state — verified:**
- **1900 date-cliff fix APPLIED:** `_YEAR = r"((?:18|19|20)\d\d)"` and `APPROVED_MODERN_RE` are present in `ingest_from_ocr.py` [CODE :119-133]. (Lives in the version-A parser; `parse_born_digital.py` imports it so the fix lives in one place [CODE parse_born_digital.py:12].)
- **`parse_born_digital.py` is PROTOTYPE only:** validated on 2008_Vol1 (227 chapters, all confident), **does NOT do multi-volume year roll-up**, and **does NOT write to the DB** (offline characterization usage) [CODE parse_born_digital.py:15-21]. So tier (b) is characterized but NOT yet ingested.
- **OPEN WORK:** (1) multi-volume roll-up (~1915+), (2) OCR-fuzz tolerance for 1915-1996 (cannot finalize until real OCR consensus text for those years exists), (3) wire `parse_born_digital.py` output through `ingest_clean.py` for tier (b).

---

## DIMENSION 7 — INFRA + AUTOMATION

**Topology:** 5090 (`100.70.54.56`, 32GB, strong OCR node, hosts shared queue) + 5080 (16GB, OCR + ingest box, hosts local Postgres 16) over **Tailscale**. Secrets at `C:\Users\PatrickKolasinski\Documents\PatoLex-secrets.env`.

**Scheduled tasks (verified on THIS box via Get-ScheduledTask):** [TASK]
- `PatoLex_OCR_5080` → **Running**
- `PatoLex_Ingest_5080` → **Disabled** (correct — runs the lossy version-A path)
- `PatoLex_OCR_5080_Backoff_0800` → **Disabled** (the 0800 daytime throttle — correctly disabled for an open-ended run)
- **5090 tasks (`PatoLex_OCR_5090`, the 5090 0800 backoff) are NOT registered on this box** — they live on the 5090. Their running state is **unverified from here.**

**Hooks — `.claude/hooks/`:** `block-compound-bash.ps1`, `pre-bash-check.ps1` (session-log enforcement + Hans/Codex push reminder), `haiku-delegation-nudge.ps1`.
- **CONFIRMED: hooks fire on the Bash tool ONLY.** `.claude/settings.json` PreToolUse `"matcher": "Bash"` [FS settings.json:5], and `pre-bash-check.ps1` keys off `tool_input.command` matching `git commit`/`git push` [CODE pre-bash-check.ps1:71,19]. **A `git commit`/`git push` issued via the PowerShell tool bypasses session-log enforcement, the Hans reminder, and the compound-command block entirely.** This is a real governance gap, not just a note.

---

## SUMMARY OF SURPRISES (reality ≠ every doc)

1. **PaddleOCR is NOT a consensus engine.** Every prose doc says "4 classical (Surya + docTR + Tesseract + PaddleOCR)"; `consensus.py` hard-codes `N_MAX_ENGINES=3` (Tesseract + docTR + Surya) and the DB has zero 4-engine acts. The consensus is 3-engine.
2. **`enacted_date` does not exist** on `enactment` (older prose implies it); the real date columns are chaptered/effective/operative.
3. **No `recodification` table** — recodification is modeled via `lineage_edge`, contradicting ROADMAP/SCHEMA prose that names a first-class `recodification` entity.
4. **Hooks are Bash-tool-only** — PowerShell-tool commits/pushes bypass all enforcement.
5. **Date outliers (1831, 1895)** exist in the 1850-1875 set — parser fuzz tail, ~838 low-confidence events.

## UNVERIFIABLE FROM HERE (flagged)
- "1877-1910 OCRing in flight" (live queue is off-box; repo copy is stale).
- 5090 task running-state (tasks not on this box).
- The ~1.5% CER / OpusGold accuracy claim (rests on a still-pending human-gold certification — per prior audits).
