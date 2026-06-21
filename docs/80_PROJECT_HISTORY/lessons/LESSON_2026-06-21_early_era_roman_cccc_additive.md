# LESSON 2026-06-21 — Early-era (1860s) chapter headers print Roman numerals in the CCCC-additive form, not the subtractive CD/CM form

**Context:** Visual recovery of the 40 residual "missing" chapters for year 1863
(`production-1863` + `production-1863-64`). A prior automated pass had marked 21 of them
`legislative_gap` and 17 `not_found_needs_reocr` — almost all of which were WRONG. On
re-run, **all 40 were `image_verified`; 0 were true legislative gaps; 0 needed re-OCR.**

## The finding (the durable one)

The 1863 printed volume renders chapter numbers in the **additive Roman form**, where
**400 = `CCCC`** (not the subtractive `CD`) and likewise **900 = `DCCCC`** would be used,
not `CM`. So chapter 443 prints as **`CCCCXLIII`**, chapter 478 as **`CCCCLXXVIII`**,
chapter 416 as **`CCCCXVI`**. A Roman→Arabic parser that assumes the modern subtractive
form (CD=400, CM=900) silently fails to recognize every 400-series header — it cannot match
`CCCC...` against an expected `CD...`, so the whole 4xx band looks "missing." This was the
single biggest cause of the prior pass's false `legislative_gap` verdicts (e.g. ch300 `CCC`
and ch443 `CCCCXLIII` were both real, both visible on the page, both wrongly called gaps).

**Fix:** the recognizer must accept BOTH additive (`CCCC`, `DCCCC`) and subtractive
(`CD`, `CM`) Roman forms when converting headers in the pre-modern volumes. A round-trip
`to_roman` used for matching must generate the additive variant too, or matching by
converting the OCR token to Arabic (tolerant of either form) rather than string-comparing
against a canonical Roman.

## Secondary failure modes seen in the same pass

- **Surya inserts a spurious extra `C`** in long Roman headers (e.g. `CCCCC...`), shifting
  the converted value. Cross-check against doctr/tess and the page image; do not trust a
  single engine's Roman string.
- **Header truncation at page tops** (the dominant mode, already documented in
  `LESSON_2026-06-14`): the `CHAP. <ROMAN>` line is cut off and the OCR for that page begins
  mid-title, so the chapter looks absent in text while its body is fully present. Recover by
  reading the page render — the Roman header is legible there. ch62 (`LXII`), ch291
  (`CCXCI`), ch480 (`CCCCLXXX`), ch484, ch496 all hit this.

## Operational notes for the early-era visual recovery workflow

- **Page images are NOT under `production-<vol>/pages_raw/`** for the OCR-only volumes
  (1862–1903 etc. ship `ocr_consensus` only). The renders live at
  **`C:\PatoLex-scratch\page-renders\<Year>_Statutes\{page_1indexed-1:04d}.png`**
  (zero-indexed filename). OCR JSON key = `source_page` = `page_1indexed`; the matching
  render is `(source_page - 1):04d.png`. The `img_path` baked into the OCR JSON still points
  at the stale `C:\Users\patolex\...\pages_prep_gray\` path — ignore it, use the canonical
  `page-renders` location resolved via `PATOLEX_LOCATION_ROOT`.
- Every recovered chapter was pinned between two OCR-confirmed neighbors, so no off-by-one
  ambiguity. A header that "looks missing" in the 1860s is far more often a CCCC-form Roman
  the parser couldn't read, or a page-top truncation — **not** a legislative gap. Confirm
  absence on the actual scanned page before ever writing `legislative_gap`.

## Where it lives

- Output: `production-1863/parsed_acts_visual.json` (38 acts) and
  `production-1863-64/parsed_acts_visual.json` (9 acts; ch300 + ch443 corrected from
  `legislative_gap` → `image_verified`, 7 prior entries preserved). Per-chapter run log:
  `docs/80_PROJECT_HISTORY/run-logs/visual-1863-run.log`.
- Relation to prior lessons: extends `LESSON_2026-06-14` (page-top header loss) and
  `LESSON_2026-06-20_ocr_header_garble_dedup` (Arabic-digit header garble) into the
  **Roman-numeral early era** — same "data is present until proven absent on the page"
  standard, new specific failure (additive Roman form).
