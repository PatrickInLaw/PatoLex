# Session cc019 — Deterministic Page-Continuity (Missing-Leaf) Audit

**Date:** 2026-06-23/24
**Type:** New deterministic tool + corpus run + deliverable + Hans audit

## Goal
Build, validate, run, and self-audit a DETERMINISTIC tool that finds MISSING LEAVES
(physically dropped printed pages) in the OCR-era statute volumes via printed-page-number
continuity. Pure Python, no GPU/VLM/LLM, read-only on corpus, no DB, no git commit.

## What was built
- **Tool:** `C:\PatoLex-scratch\page_continuity_audit.py`
  - Re-OCRs the top ~11% strip of each rendered page image with Tesseract (`--psm 11`,
    digit whitelist) to recover the running-head page number (confirmed: the number is
    NOT in the full-page consensus OCR — it is a dropped corner number).
  - Models `printed = pdf_seq + offset`, offset piecewise-constant & monotone
    NON-DECREASING; fits the best monotone offset step-function by **dynamic programming**
    (score = supported pages − STEP_PENALTY·#steps). Each offset INCREASE = a gap.
  - Crash-safe `--jsonl` + `--resume`; self-writes the run log; multiprocessing.
  - Image source: prefers `page-renders/<Vol>/NNNN.png` (NNNN==page_1indexed), falls back
    to the volume's own `pages_prep_gray/page_NNNN.png` (NNNN==page_1indexed−1) when no
    render dir / partial render.
- **Report generator:** `C:\PatoLex-scratch\_make_report.py` (reproducible doc from JSON).

## Validation (1872)
`production-1871-72`: detects EXACTLY the four Patrick-confirmed missing leaves —
printed pp **131-134, 515-516, 586-587, 776-777 (10 pages)** — with ZERO false positives.
Determinism: Tesseract digit OCR on a fixed crop + integer DP (no randomness).

## False-positive class fixed mid-session
Early front-matter / table-of-contents pages produce coincidental incrementing digit runs
(act page-references) that a naive anchor latched onto, inventing huge early gaps
(1869-70 "31-80", 1853 "22-64", etc.). Fixed via (a) DP base-offset selection that is NOT
anchored to the global mode, and (b) a per-SEGMENT support+density floor that drops short
coincidental runs. After the fix these volumes correctly report NOT AUDITABLE instead of
phantom gaps; 1872 still passes; clean volumes stay clean.

## Corpus run — HARD TOTALS (after Hans fixes)
**133 missing printed pages across 34 volumes; 157 auditable (123 clean); 68 NOT AUDITABLE; 225 dirs.**
Command (crash-safe; killed twice by the env time limit and resumed):
`python page_continuity_audit.py all --workers 16 --jsonl _audit_all.jsonl --resume --json-out _audit_all.json`
Report is generated from the JSONL (complete record across chunks).

Gap-confidence breakdown (65 gaps): 25 two-page even→odd one-leaf drops (50 pp, HIGH);
15 other multi-page (58 pp, med-high); 25 single-page (25 pp, AMBIGUOUS). "133" is a FLOOR
over the 157 auditable volumes; ~82,976 pages in 68 not-auditable volumes are unchecked.

## Hans round 1 — NOT SOUND, 4 blockers; ALL FIXED
1. **Segment-merge mislocalized clustered gaps** (wrong ranges + omitted gaps when drops sit
   <MIN_SEG_SUPPORT apart). FIX: walk the per-page offset path, emit a gap at EVERY offset
   step localized at its true position. Verified: 1991-vol1 → `1244-1251(8); 1258-1259(2)`
   (was wrong `1244-1253(10)`); 1982-vol1 → 4 one-leaf gaps incl. previously-OMITTED 1264-1265.
2. **Resolution-chapter phantom gaps.** FIX: `_resolution_pages()` excludes resolution pages
   by consensus-OCR content before fitting → 8 volumes (~20 pp) now NOT AUDITABLE.
3. **Partial-scan cross-check premise false** (partial & primary are CONTIGUOUS not overlapping).
   FIX: dropped the dismissive claim; partial-scan gaps treated as real candidates (spot-verified).
4. **"159" overstated coverage.** FIX: relabeled as auditable-subset floor; ~82,976 unaudited
   pages disclosed; added coverage gate (`partial_numbering`) refusing sliver fits of
   multi-stream vol2/vol3 (e.g. 1961-vol2, 1967-vol3 now NOT AUDITABLE).
Minor: MAX_LEAP over-jumps surfaced in `big_leaps` stat; corrected cosmetic page-mapping docstring.

## Deliverable
`C:\GitHub\PatoLex\docs\80_PROJECT_HISTORY\PAGE_CONTINUITY_AUDIT_2026-06-23.md` —
headline totals, gap-confidence guidance, two caveats (partial "NNchapters" alternate scans
that show gaps while the year's primary scan is clean; high-readability NOT-AUDITABLE volumes
that are index/reset-numbered, not damaged), affected-volume table, NOT-AUDITABLE honesty
table, per-volume detail, reproducible command + method note.

## Findings (durable — also recorded in the deliverable doc)
- The running-head page number is NOT recoverable from full-page consensus OCR; targeted
  top-strip re-OCR is required.
- A dropped physical leaf manifests as a 2-page even→odd gap; single-page breaks are usually
  printing/numbering skips, not leaf losses — the tool cannot distinguish cause from numbers.
- 1850-1860 + several modern index/topical volumes are NOT AUDITABLE from page numbers
  (genuinely noisy band, or numbering resets the monotone model correctly refuses to fit).

## Hans
verify-auditor (Opus) run after the corpus run — see verdict in session thread; all BLOCKERs
addressed and re-run until SOUND.

## Constraints honored
Deterministic only; read-only on corpus; no DB; NO git commit (caller commits).
