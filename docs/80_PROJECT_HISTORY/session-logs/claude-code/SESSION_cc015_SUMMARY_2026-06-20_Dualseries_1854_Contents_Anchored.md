# SESSION cc015 — 1854 Dual-Series Contents-Anchored Parse Fix (+ corpus relocation)

**Date:** 2026-06-20
**Focus:** Resolve OCR-era residual rows; fix the 1854 parse; bank the corpus relocation.

## What Was Done

- **Residual-row investigation (opened SOURCES, not derived OCR).** Installed PyMuPDF and opened actual source PDFs / page images instead of trusting garbled derived OCR.
  - **1989 vol3:** the *source PDF itself* ends mid-CHAPTER 1428 (2,174 pp ≈ our bundle) — an **acquisition/truncation gap**, not an OCR loss. Oracle 1467 uncontradicted; needs a complete re-acquired vol3, not a re-parse.
  - **1854:** established it is a **DUAL-SERIES** volume (General Laws 1–71 + Special Acts 1–103 = **174**); verified via the page images that the scan is **complete** (the Special Acts bodies are present, pp.129–215) — *not* missing pages.
- **Corpus relocation banked.** The 5080 moved the corpus out of `C:\Users\patolex\PatoLex-scratch` → **`C:\PatoLex-scratch`** (any-account `Modify`, machine-wide `PATOLEX_LOCATION_ROOT`, `config.py` resolves it) and synced all **653 source PDFs incl. every printed `*_Index.pdf` (1850→modern)** to the 5090. (A mid-session "data deleted" alarm was a **false alarm** from a Glob false-negative during the move — corrected on the raw disk.)
- **Fixed the 1854 parse via contents-anchoring.**
  - v1 re-parse **force-fit to 174**: dropped real General ch18 (County Judges), invented a phantom ch23 ("an Act supplementary thereto" fragment), off-by-one ch18–24 — the drop + phantom canceled, hiding the defect behind a clean count.
  - v2 anchors numbering to the **printed Contents** (chapter→title→page) → **General 71/71 + Special 103/103, zero missing, phantom rejected**.
- **Verification.** Orchestrator independently verified the canonical Contents list at 3 sampled regions (exact); **Hans (verify-auditor) audited body-matching → SOUND** (~42 chapters opened + full header census). Cosmetic ch50/ch70 `source_page` micro-fix applied.
- **Durable docs + hygiene.** Wrote `LESSON_2026-06-20_dualseries_contents_anchored_parse.md` + indexed it; updated `STORAGE_AND_BACKUP.md` and `CLAUDE.md` to the `C:\PatoLex-scratch` / `PATOLEX_LOCATION_ROOT` canonical root.

## Decisions Made

- **Dual-series / garbled-roman volumes: derive numbering from the printed Contents/Index, NOT body roman headers.**
- **A parse total that exactly equals a known target is a RED FLAG** (force-fit risk), not reassurance — require per-chapter body witnesses + Hans gate.
- **Oracle 1854 = 174 unchanged** — it was already correct; the defect was the *parse*, not the oracle.
- Output is an **additive** corrected parse (`parsed_acts_dualseries_v2.json`); **no ingest** (not a current task), no overwrite of v1/source.

## Files Changed

- **NEW** `docs/80_PROJECT_HISTORY/lessons/LESSON_2026-06-20_dualseries_contents_anchored_parse.md`
- **NEW** `docs/80_PROJECT_HISTORY/run-logs/dualseries-1854-reparse-run.log`
- **EDIT** `docs/80_PROJECT_HISTORY/lessons/LESSONS_OVERVIEW.md` (index + revision)
- **EDIT** `docs/60_OPERATIONS/STORAGE_AND_BACKUP.md` (canonical path → `C:\PatoLex-scratch`)
- **EDIT** `CLAUDE.md` (corpus data-root note + revision)
- **NEW** this session log
- **SCRATCH (not in repo)** `C:\PatoLex-scratch\production-1854\{parsed_acts_dualseries.json (v1), parsed_acts_dualseries_v2.json (CORRECTED, verified), _canonical.py, _finalize_v2.py}`
- **REMOVED** this session's throwaway probes in `pipeline/analysis/` (`_check1854`, `_pdf_open`, `_pdf_check`, `_residual_pages`, `_early_raster_status`, `_pathcheck`, `_index_open`, `_fix_v2_sourcepage`)

## Systematic OCR-era index-anchoring sweep (cc015, IN PROGRESS)

**Goal (Patrick-chosen):** validate OCR-era denominators against the printed indexes — the definitive "make the OCR-era trustworthy" pass. Early era first; modern subject-index completeness cross-check after (belt-and-suspenders).

**Key scoping finding (DURABLE):** the printed `*_Index.pdf` files are **page-keyed SUBJECT indexes, NOT chapter tables** (verified 1899 + 1957: entries cite pages e.g. "ABANDONMENT … 2998"; the 1957 index spans 3 sessions and ends in a Table of Proposed Constitutional Amendments). Modern chapters volumes have **no front-matter table of acts** (1957 Vol1: title → "CHAPTER 1"). So **"OCR the _Index → denominator" does NOT work for the modern era** — its denominator is already double-sourced (Chief Clerk stated ranges = the oracle's own source + body self-index = 96.3% confirmed) and needs no index.

**Where index-anchoring adds value = the EARLY era (1850–1899):** pre-1900 statutes volumes carry a front-matter **"CONTENTS" Table of Acts** (No. of Chapter | Title | Date | Page), chapter-ordered → last entry = the count. Verified in 1854 (scan) and 1899_Statutes.pdf (archive PDF, table starts ~p3). This is an INDEPENDENT denominator, strongest exactly where the oracle was least certain (the 1854=71 error; the 1860/1862/1863/1865-66/1883/1887 corrections).

**Plan & status:**
1. **Early era (1850–1899, 33 regular rows): DONE.** Fan-out (6 sonnet batches + orchestrator finish/verify) anchored each denominator to its printed Table of Acts. **Result: 31/33 CONFIRMED exact; 2 FLAGGED (oracle > printed table — likely over-counts): 1860 (S11) oracle 385 vs table 371 (−14); 1863 (S14) oracle 538 vs table 536 (−2).** Both FLAGs orchestrator-verified; **both edited per Patrick's delegation — 1863→536 (clean), 1860→371** (volume complete at 453pp/single-series; ⚠️ unresolved CLERK-CONFLICT: clerk archive lists 1860 as 1-455, doesn't fit our volume — flagged `toa-verified-CLERK-CONFLICT` for Patrick). Net oracle −16 ch (120,205→120,189). Sweep independently RE-CONFIRMED prior corrections 1865-66=650, 1883=96, 1887=188, 1889=290, 1861=538, 1862=455. Full report: `docs/30_SYSTEM_DESIGN/sources/EARLY_ERA_TOA_SWEEP_2026-06-20.md`. (Source: production-185x scans 1850–1860; `chief-clerk-archive/*_Statutes.pdf` 1861–1899; 1883 in `1883-84_Code.pdf`.) 1854 (S5) done separately (174, dual-series).
2. **Modern era (1900–1999): DONE** (parallel subagent). Primary-source belt-and-suspenders: opened scanned volumes → **ZERO denominator contradictions** (body-self-index derivation confirmed sound; 1975 Vol1→Vol2 "Ch.1071→1072" a clean direct confirm). Structural finding (lesson addendum): modern volumes have NO table of acts + carry dual CHAPTER series (statutes + resolution/ConstAmend) + relocated flagship acts → "last printed CHAPTER" is meaningless; body-self-index is the correct denominator source. Modern parse completeness ≈92.4% (parse-recall gaps on the longest volumes, NOT denominator). **Born-digital 2000–2024 NOW MEASURED** (DB access wired by the 5080 over Tailnet; psycopg3 installed; DSN in `.env.local`): **94.5%** (20,271/21,455) — 2000–2008 ~100%, **2009–2024 ~90% (~1,180 chapters short — a Gate-F ingest gap, not a denominator issue)**; 2000 & 2005–2008 have ~2× duplicate rows. Early-era DB rows have attribution noise (1860 shows ch up to 531 vs true 371). See `BORN_DIGITAL_DB_COMPLETENESS_2026-06-20.md`. **1860 oracle conflict RESOLVED:** the official clerk `1860_Statutes.pdf` (453pp) also ends at Ch.371 → 371 confirmed by two primary sources; the clerk catalog "1-455" is a metadata error. Row now `official-pdf-verified`.

## Open Items at Close

- **NEXT:** point the contents/index-anchoring method at the next target — the other residual rows / the modern-era **NO_INDEX denominator gap** (now solvable on-box: all `*_Index.pdf` are local).
- Hardcoded old-path references remain in many pipeline scripts + historical logs; they resolve via `PATOLEX_LOCATION_ROOT`/`config.py` — **not** mass-rewritten (historical logs are point-in-time records, intentionally left).
- 1854 v2 is **parse-level corrected + verified**; not ingested (ingest not a current task).
- 1989/1941/1964 residuals: 1989 confirmed a source-truncation gap; 1941/1964 PDFs on-box but not yet opened.
