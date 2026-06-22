# Lesson: Surya (deep-learning OCR, GPU) recovers early-era chapter headers Tesseract could not read

**Date:** 2026-06-22
**Area:** OCR / chapter-header recovery for the historical 1850-forward corpus
**Status:** VERIFIED on the 1866-1878 biennial residuals + 1911

## Context / problem

The local chapter-header recovery tools (`_header_ocr.py`, `_scan_headers.py`,
`_scan_headers_multiact.py`) only ever used **Tesseract** as the OCR engine. After
all Tesseract passes (top-strip crop, full-page psm 6/4/11 block, multi-act
psm 6+11 sparse union across 200/240/300 dpi), a residual of chapters remained
"missing" in the biennial volumes — their printed running-head was a small,
degraded early-era **Roman numeral** (additive `CCCC=400`) that Tesseract simply
could not resolve. These residuals were the untapped lever.

## Finding — Surya is materially better on degraded Roman headers

Swapping the OCR engine for **Surya** (deep-learning OCR: `DetectionPredictor` +
`RecognitionPredictor`, already wired in `_header_ocr._ocr_surya`) run on the
**RTX 5090 (CUDA)** newly reads a large fraction of the Tesseract-missed headers.

**Measured first-batch lift (1868, sample of 14 Tesseract-missed, no writes,
dpis 400/500, >=2-DPI agreement): Surya read 11/14 = 79% correctly.**

Per-year production results (CONFIRM-ONLY, >=2 distinct-DPI agreement):

| Year | Tesseract residual | Surya newly read | New residual |
|------|--------------------|------------------|--------------|
| 1868 | 14 | 11 (79%) | 3 |
| 1872 | 28 | 7 (25%) | 21 |
| 1874 | 38 | 24 (63%) | 14 |
| 1911 (Arabic) | 5 | 2 (40%) | 3 |

(1876/1878/1870/1866 results recorded in the run log
`docs/80_PROJECT_HISTORY/run-logs/surya-header-ocr-run.log`.)

## Why it works / method that proved sound

- **Full-page Surya, not a top-strip crop.** Surya does its own text-line
  detection, so a mid-page secondary-act header on a multi-act page is read as
  its own line — no band-slicing needed.
- **Reuse the proven parser.** `_header_ocr.parse_chapter_from_text` (additive
  `CCCC=400`, OCR-tolerant lead-ins `Cuap./Cnap.`, `O->C`, `U->V`) is engine-
  agnostic; only the text source changed.
- **Cross-DPI agreement is still required.** Roman headers are DPI-fragile, so
  confirm only when Surya reads the EXACT oracle number at **>=2 distinct render
  DPIs (400 + 500)** within the bounded `page_range` window. This is the same
  guard the multi-act Tesseract tool used and it carries over to Surya.
- **Light preprocessing** (grayscale + `autocontrast cutoff=1`) only; Surya is
  robust, hard binarization not needed.

## Where Surya alone is NOT enough (the remainder)

Surya does NOT close the gap on:
- **Tight multi-act clusters** (e.g. 1872 ch 125-128, 433-439; 1874 ch 465-466,
  678-679): several short acts share one page and the secondary headers are
  faint/absent — even Surya's line detection misses them.
- **Very short / degraded page-ranges** where the printed header is genuinely
  illegible or the chapter began without a fresh running-head.
- A handful of **1911 Arabic** chapters (90, 252, 356) on atypical pages.

These remaining residuals would need a stronger local VLM (Qwen2.5-VL or
GOT-OCR2.0) that reasons over the whole page layout, OR clerk-index cross-check,
NOT another OCR-engine swap.

## Reusable artifact

`C:\PatoLex-scratch\_surya_header_recover.py` — year-driven, CONFIRM-ONLY,
append-safe to `<vol>/parsed_acts_visual.json` (origin `surya_header_ocr`,
status `image_verified`, `dpi_votes` recorded). Re-saves every 15 confirms so a
mid-run stop preserves everything. Reads the residual list from
`_manifest_<year>.json` (produced by `pipeline/analysis/_residual_manifest.py`).
Throughput ~12s/chapter on the 5090. No DB writes, no merged/certified writes.

## Operational note

Set `TQDM_DISABLE=1` (and `DISABLE_TQDM=1`) before importing surya — its
per-page detect/recognize progress bars otherwise flood stdout (~37 KB for a
14-chapter sample).
