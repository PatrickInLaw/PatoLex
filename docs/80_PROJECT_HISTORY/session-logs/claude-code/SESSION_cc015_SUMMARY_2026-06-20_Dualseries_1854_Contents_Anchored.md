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

## Open Items at Close

- **NEXT:** point the contents/index-anchoring method at the next target — the other residual rows / the modern-era **NO_INDEX denominator gap** (now solvable on-box: all `*_Index.pdf` are local).
- Hardcoded old-path references remain in many pipeline scripts + historical logs; they resolve via `PATOLEX_LOCATION_ROOT`/`config.py` — **not** mass-rewritten (historical logs are point-in-time records, intentionally left).
- 1854 v2 is **parse-level corrected + verified**; not ingested (ingest not a current task).
- 1989/1941/1964 residuals: 1989 confirmed a source-truncation gap; 1941/1964 PDFs on-box but not yet opened.
