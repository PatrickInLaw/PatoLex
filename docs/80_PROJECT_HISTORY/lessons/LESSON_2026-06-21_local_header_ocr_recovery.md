# LESSON 2026-06-21 — Local targeted header-OCR recovers "missing" chapters without burning agent vision tokens

**Context:** The biennial volumes (1864/1866/1868/1870/...) carry large residuals of
"missing" chapters. Root cause (already documented in `LESSON_2026-06-14` and
`LESSON_2026-06-21_early_era_roman_cccc_additive`): full-page OCR skips/garbles the
page-TOP running head (`CHAP. <N>` / `[Ch. N]`), so the chapter looks absent in text
while its body is fully present. Reading 600+ page images with an agent's vision is the
expensive way to recover these. This session built and validated a **LOCAL** alternative.

## The tool

`C:\PatoLex-scratch\_header_ocr.py` (+ `_scan_headers.py`, `_apply_1866.py`). Given a page
image (or a PDF page rendered on demand with PyMuPDF), it crops the top strip(s), upscales,
runs **Tesseract 5.4** (`--oem 1`, psm 6/7/11), and parses the chapter number from the
running head. Engine + interpreter:
`C:\PatoLex-scratch\ocr-engines\surya-venv\Scripts\python.exe` (has pytesseract/PIL/PyMuPDF/Surya);
Tesseract at `C:\Users\patolex\AppData\Local\Tesseract-OCR\tesseract.exe`.

Parser handles arabic (`CHAPTER 482`, `CHAP. 482`, `[Ch. 482]`) and roman
(`CHAP. XXVI`, `CHAPTER CCCCLXXXII`), including the **additive** roman forms
(CCCC=400, XXXX=40, VIIII=9) alongside subtractive (XL/CD/CM).

## Findings (the durable ones)

1. **OCR corrupts the word "CHAP." far more than the numeral.** Tesseract routinely renders
   `Chap.` as `Cuap.`, `CHap.`, `Cnap.`, `Cuar.` (trailing P→R). A literal `CH...` lead-in
   regex misses almost every early-era header. The lead-in MUST tolerate
   `C/O + 2-3 letters + (p|r)` and REQUIRE a word boundary before it + a separator after it
   (else prose/dates like "March 12" produce false chapter hits).
2. **Roman tokens need O→C, U→V normalization.** The `CCC` triple frequently OCRs as `CCO`
   (letter O). Normalize before `roman_to_int`. Example: `Cuar. CCOXXIX` → chapter 329.
3. **Early-era `source_page` in `parsed_acts_merged.json` is only roughly reliable.** For
   PRESENT chapters it lands in the right coordinate system (PDF-page-indexed), but some
   recorded source_pages point at mid-act CONTINUATION pages with NO header at all (e.g.
   1865-66 ch13 "source_page 113" is body text). Do not trust source_page point-lookups for
   the missing set; drive off the residual-manifest page_RANGES (bracketed by reliable
   PRESENT neighbors) instead.
4. **Pages hold 2-3 short acts; a single psm-6 pass reads the FIRST header and drops lower
   ones.** Union psm 6/4/11 in `headers_on_page()`. This helps but does not fully close the
   gap — some genuine lower-on-page headers still elude OCR at 200-230 dpi. This is the main
   reason local-OCR recall < 100%: the limiting factor is page LOCATION of multi-act headers,
   not number READING.

## Validation (go/no-go)

- **Arabic gate (formal):** year 1935 (`production-1935-vol1-chapters`, already
  image_verified). 30 known chapters, header-OCR on each chapter's source-page image:
  **28/30 = 93.3% EXACT** (2 off-by-1 = chapter starts mid-page, running head shows previous
  chapter). **GO** (≥85%).
- **Roman engine (real images, 1865-66 from PDF):** the roman path reads real headers
  correctly (XXIV=24, XXVI=26, CCCXXIX=329) once findings 1-2 were applied.

## Application — 1866 (production-1865-66)

Run in **CONFIRM-ONLY** mode: a missing chapter is written ONLY when its exact oracle number
appears as a clean header within its candidate page range, so a miss costs coverage, never a
wrong claim. Output is an **append-safe superset** `production-1865-66/parsed_acts_visual.json`
(`status="image_verified"`, `origin="local_header_ocr"`, `printed_number_confirmed=true`,
`chapter_int_final`=oracle, `source_page`=the PDF page where the header was read). Never an
all-not_found init. The residual scoreboard alias `1866 → production-1865-66` was added to
`pipeline/analysis/_residual_manifest.py` (also 1864/1868/1870).

## Viability for the remaining biennials (1868-1878)

Viable as a **token-free first pass** that recovers a meaningful fraction of each biennial's
residual at zero agent-vision cost, leaving a much smaller set for the visual-agent method.
It is NOT a complete substitute: multi-act-page header loss (finding 4) caps recall below
100%, so the visual-agent fallback remains necessary for the stubborn remainder. Cost note:
the dominant runtime is the "not found" chapters (each scans its whole page range × 3 psm);
the run is resumable (skips confirmed chapters; persists a page→chapters scan cache), so it
can be chunked.

## Where it lives

- Tool: `C:\PatoLex-scratch\_header_ocr.py`, `_scan_headers.py`, `_apply_1866.py`,
  `_validate_header_ocr.py`, `_validate_roman_pdf.py`.
- Run log: `docs/80_PROJECT_HISTORY/run-logs/local-header-ocr-run.log`.
- Output: `production-1865-66/parsed_acts_visual.json`.
- Relation: extends `LESSON_2026-06-14` (header loss) and
  `LESSON_2026-06-21_early_era_roman_cccc_additive` (additive roman) with a LOCAL,
  token-free recovery path + the OCR-tolerant lead-in/normalization needed to make it work.
