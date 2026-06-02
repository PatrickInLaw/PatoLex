# DOC DELTA MAP — 2026-06-02

**Purpose:** doc-by-doc remediation table for the wholesale documentation rewrite. Each row gives the doc's CURRENT STATE (accurate / stale / **actively-wrong**), the specific discrepancies vs `TRUTH_BASELINE_2026-06-02.md`, and what must change. **Ordered by severity (actively-wrong first).** Verified against code + live DB, not against the docs.

**State definitions:** **ACTIVELY-WRONG** = asserts something a cold reader would act on that is false today. **STALE** = frozen at an earlier state, understates/misstates progress but not dangerously misleading. **ACCURATE** = matches the verified baseline.

---

## TIER 1 — ACTIVELY-WRONG (fix first)

### 1. `docs/30_SYSTEM_DESIGN/ARCHITECTURE.md` — **ACTIVELY-WRONG (highest harm)**
Discrepancies vs baseline:
- **Scope inverted.** Leads (line 7) with "POC targets the modern point-in-time archive (1991-1992 session to present)... historical depth back to 1849 is a Phase 2 research program, not part of the POC." Reality = **historical-first**; 1850-1875 is already built and ingested. [baseline D1]
- **Wrong pipeline stack.** Lines 5, 21: "private **C# data pipeline**", ".NET 8 ... **Dapper** (load), AngleSharp, PdfPig / OCR reserved for Phase 2." Reality = **Python OCR/parse (Tesseract+docTR+Surya, PyMuPDF) + TypeScript/Drizzle ingest**; C#/.NET is explicitly DEFERRED (CLAUDE.md pipeline-stack note). [baseline D3]
- "Primary data source = leginfo bulk 1991-1992 forward" framed as the source of truth — true for the modern tier only; the PRIMARY current build is Chief Clerk session laws.
**Must change:** Rewrite the scope + stack + primary-source paragraphs to historical-first / Python+TS pipeline / Chief Clerk-primary. This doc needs the heaviest rewrite of any.

### 2. `docs/20_ROADMAP/ROADMAP.md` — **ACTIVELY-WRONG**
Discrepancies vs baseline:
- **"No corpus data ingested yet"** (line 5) and "no mass OCR or ingest until an engine is verified" — **FALSE.** 4262 acts (1850-1875) are ingested as version-B consensus. [baseline D4]
- **Gate D status "DDL implemented... Not yet applied to a live DB"** (line 39) — **FALSE.** Schema is live on local Postgres with 4262 acts across all 7 tables. [baseline D2]
- **Gate C "In progress"** with the 726-section throwaway and "OCR bake-off pending human gold" narrative (line 5/38) — frozen before the production build that has since happened.
- Mentions PaddleOCR as a bake-off candidate (line 5) — fine as historical bake-off narrative, but if any "selected engines" claim implies 4-engine consensus, correct to 3 (Tesseract+docTR+Surya). [baseline surprise #1]
**Must change:** Update Current Status + Gate C/D to reflect "1850-1875 ingested, version-B canonical, schema live, 4262 acts"; advance the gate state.

---

## TIER 2 — STALE (understates reality or carries dead detail)

### 3. `CLAUDE.md` — **STALE (scope intro) / ACCURATE (rules + stacks)**
- "What PatoLex Is" still describes "POC = modern point-in-time archive (1991-present), reconstructed first; pre-1992 = Phase 2." This contradicts the historical-first reality, though the pipeline-stack note (Python+TS canonical, C# deferred) and all the mandatory-process sections are accurate.
**Must change:** Reconcile the "What PatoLex Is" scope paragraph with historical-first (or add a one-line pointer to ROADMAP as the scope source of truth). Leave the process/stack rules as-is. Consider documenting the **Bash-only hook gap** (PowerShell-tool commits bypass enforcement) under Bash/Session-log hygiene. [baseline D7]

### 4. `docs/40_SCHEMA/SCHEMA_DESIGN.md` — **STALE / needs verification against live columns**
Discrepancies vs baseline:
- Names a first-class **`recodification`** entity; the live DB has **no such table** — recodification is via `lineage_edge`. Reconcile (rename in doc, or note the as-built choice). [baseline surprise #3]
- If it references `enacted_date`, correct: `enactment` has chaptered/effective/operative, **no `enacted_date`**. [baseline surprise #2]
- Should state the as-built capture-all-signals columns (`change_event.confident/confidence/ocr_provenance`, `source_document.ocr_stats/content_sha256`) and that **`provision_version`/`lineage_edge` are 0 by design**.
**Must change:** Reconcile entity names with the live schema (migrations 0000-0004); add the as-built column inventory + the "0 by design" note.

### 5. `docs/30_SYSTEM_DESIGN/DATA_SOURCES.md` (modern) — **likely STALE on framing**
- Modern-channel facts (leginfo PUBINFO, 1989-2025, current-only snapshot, reconstruct-backward, POC floor ~1994) are documented and accurate per prior audits. The risk is the surrounding "modern-first" framing if present.
**Must change:** Ensure it presents the modern era as the SECOND build (after historical), not the POC. Verify no "modern-first" language remains.

### 6. `docs/80_PROJECT_HISTORY/CHANGELOG.md` — **STALE (by definition; append-only)**
- Almost certainly lacks the 1850-1875 version-B production-build entry and the doc-remediation entries (BUILD_RUNBOOK, three-tier correction, this baseline).
**Must change:** Append entries for: 1850-1875 version-B ingest (4262 acts), the canonical `ingest_clean.py` chain, the three-tier corpus correction, and the truth-baseline/doc-rewrite effort.

### 7. The cc002→cc003 HANDOFF — **STALE**
- Predates the 1850-1875 build; its "first steps" (apply DDL, seed 1872) are already done.
**Must change:** Refresh to "version-B complete through 1875; resume per BUILD_RUNBOOK §5; next = extend past 1875 + Phase C." (Per COLD_START audit gap #6.)

---

## TIER 3 — ACCURATE (light touch / one addition each)

### 8. `pipeline/README.md` — **ACCURATE**
- Correctly states `ingest_clean.py` canonical (line 42), `ingest_from_ocr.py` superseded/lossy with the **no-`__main__`-guard hazard** (line 58), boot-resilience explicitly dropped (line 70), and **1850-1875 / 4262 acts / provision_version=0 by design** (lines 64-66). Matches the DB exactly.
- **One gap:** it does not flag the **PaddleOCR-not-in-consensus** discrepancy. Add a line: consensus = Tesseract+docTR+Surya (3 engines, `N_MAX_ENGINES=3`); PaddleOCR is not a voter despite older prose. [baseline surprise #1]

### 9. `docs/60_OPERATIONS/BUILD_RUNBOOK.md` — **ACCURATE**
- Three-tier method, queue/two-node mechanics, 0800-backoff-disable rule, the canonical `ingest_clean.py --commit` double-guard chain, and current state (1850-1875 version-B / modern parser un-ingested) all match the baseline.
- **Two notes:** (a) it says "4 classical (Surya+docTR+Tesseract+PaddleOCR)" in §2 — correct to 3 engines to match `consensus.py`. (b) Its "1877-1910 OCRing" claim is **unverifiable from the repo** (live queue is off-box); keep but mark as the live-box state.

### 10. `docs/30_SYSTEM_DESIGN/DATA_SOURCES_HISTORICAL.md` — **ACCURATE (just corrected)**
- The 2026-06-02 §1d three-tier correction is sound and matches artifacts. No change needed beyond the PaddleOCR-engine-count note if it appears (it references "multi-engine consensus" without naming engines, so likely fine).

### 11. ADJACENT-DOMAIN / `LAW_AS_GIT` docs — **ACCURATE / out of near-term scope**
- Conceptual; no code/DB claims to falsify. No rewrite needed; ensure they remain labeled as forward-looking design, not current state.

---

## CROSS-CUTTING FIXES (apply wherever the phrase appears)
1. **"4 engines / PaddleOCR in consensus" → "3 engines (Tesseract+docTR+Surya), PaddleOCR not a voter."** Appears in OCR_ACCURACY_VALIDATION, BUILD_RUNBOOK, COLD_START audit, memory `ocr-verification-architecture`, and likely DATA_SOURCES_HISTORICAL. The DB and `consensus.py:119` are ground truth (3).
2. **"modern POC first / historical Phase 2" → "historical-first."** ARCHITECTURE, CLAUDE.md intro, possibly DATA_SOURCES.
3. **"schema not yet applied to live DB" / "no corpus ingested" → "schema live, 1850-1875 / 4262 acts ingested."** ROADMAP.
4. **`enacted_date` → chaptered/effective/operative.** SCHEMA_DESIGN and any query examples.
5. **`recodification` table → `lineage_edge`** (or document the as-built decision). SCHEMA_DESIGN, ROADMAP Gate D.
