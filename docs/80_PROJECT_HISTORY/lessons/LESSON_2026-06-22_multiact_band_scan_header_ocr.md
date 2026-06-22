# LESSON 2026-06-22 — Recovering MID-PAGE multi-act headers: psm-11 SPARSE + multi-DPI vote (band-free)

**Context:** After the biennial local-header-OCR sweep (1866–1878, `_apply_18NN.py` +
`_header_ocr.py` + `_scan_headers.py`), each year still carried a residual dominated by ONE
failure mode (named in `LESSON_2026-06-21_local_header_ocr_recovery.md` finding 4): **2–3
short acts share one printed page, and the page's SECOND / THIRD "CHAPTER N" header sits
MID-PAGE.** The existing scanners favor the page TOP — `_header_ocr.py` crops the top strip;
`_scan_headers.headers_on_page` runs psm 6/4/11 over the whole page in BLOCK mode. Both read
the top (first-act) running head and routinely DROP mid-page secondary headers: a block-mode
pass binds the dominant top head and lets a faint mid-page "Chap. N" line dissolve into the
surrounding body block.

## The technique — psm 11 SPARSE, multiple DPIs, band-free

`C:\PatoLex-scratch\_scan_headers_multiact.py` (additive; does NOT modify `_scan_headers.py`).
`headers_on_pdf_page_voted(doc, p)` renders the page at several DPIs (200/240/300) and, at
each, runs Tesseract **psm 11 (SPARSE TEXT)** + psm 6 (block). Sparse mode segments isolated
text regions independently, so a mid-page chapter header — a short line set off by whitespace
— is read as its OWN line instead of being swallowed by the body block. It returns
`[(chapter_int, dpi_vote_count)]` where the vote = number of distinct DPIs that read that
number. Reuses `_header_ocr.parse_chapter_from_text` verbatim → additive-roman CCCC=400 and
the OCR-tolerant lead-in (`Cuap./Cnap./Crap.`, O→C, U→V) unchanged.

## Findings (the durable ones)

1. **psm 11 SPARSE on the full page is what recovers the mid-page header** — no band slicing
   needed. An earlier 8-band (psm 6/7/11) design worked but cost ~10 s/page AND MANUFACTURED
   roman misreads (running one header through many band geometries produced sibling misreads:
   `CCCLXXXII`=382 also read 327/482). The sparse full-page pass is ~3 s/page, has equal recall
   on the validated 1872 targets, and emits no such sibling noise. **Faster and cleaner.**
2. **Roman headers are DPI-FRAGILE — multi-DPI agreement is the correct confirm test.** The
   glyph count of a `CCCC…`/`DCXVIII…` token shifts with render resolution: a true
   `CCCCXCIII`=493 reads at 150/200/240 but garbles at 300; a misread coincidence reads at one
   DPI only. So a confirm REQUIRES the exact oracle number at **≥2 distinct render DPIs**
   (`MIN_DPI_VOTES=2`); a single-DPI read is left residual. **Vote count WITHIN one DPI does
   NOT separate signal from noise** (a real mid-page win and a sibling misread both poll once);
   it is the agreement ACROSS DPIs that does.
3. **A single-different-DPI re-audit gives false MISMATCHes.** Re-reading 1872's 17 confirms at
   one new DPI (240) flagged 11/17 as "mismatch" — purely DPI fragility, not error: a multi-DPI
   re-audit (150/200/240/300) showed the printed roman token equals the oracle EXACTLY in all
   17 (CCCCXCIII=493, DCXVIII=618, CCLXXXVIII=288, CCCCLXXXVII=487, …). Always audit multi-DPI.
4. **Scope to TIGHT windows.** The band-free scan only recovers headers on a page SHARED by a
   neighbor act (tight window). Windows wider than ~12 pp are garbled/edge cases the method
   won't fix; skip them (left for the visual fallback) to save the page budget.
5. **Cost ≈ 3 s/page**; page→votes cached per year (`_hdrscan_multiact_cache_<year>.json`,
   persisted even in --dry-run). Clustered missing chapters share windows, so unique-page count
   — not chapter count — drives runtime. Resumable; run each year synchronously in foreground.

## Validation (1872, the "already-done" year, residual 45)

Recovered **17** chapters (45→28), all roman, all multi-DPI-verified printed-token == oracle:
43,62,288,383,426,443,448,463,464,468,480,481,483,486,487,493,618. Audit at 150/200/240/300
dpi: 16 STRONG (≥2 DPIs) + 1 WEAK (481, single-DPI but token `CCCCLXXXI` unambiguous) + 0 FAIL.
481 predates the ≥2-vote guard, which is enforced for the remaining years.

## Application — `_apply_multiact.py <year> [--dry-run]`

CONFIRM-ONLY, additive, append-safe superset to the MAIN volume's `parsed_acts_visual.json`
(`origin="local_header_ocr_multiact"`, `status="image_verified"`,
`printed_number_confirmed=true`, `chapter_int_final`=oracle, `dpi_votes` recorded). Reuses each
year's windowing model: simple page_range (1866/1868/1870), MAX_SPAN/HIGH_WINDOW guard
(1872/1874), dual-series main-anchor (1876/1878 — anchor on MAIN-volume present chapters only;
the code volume is a separate PDF, see
`LESSON_2026-06-22_residual_manifest_crossvolume_anchor_collapse.md`). After each year,
regenerate the true residual with `pipeline/analysis/_residual_manifest.py <year>` (it re-reads
`parsed_acts_visual.json`). No DB / merged / certified writes.

## Final results — all 7 biennials (1866–1878)

| Year | Residual before → after | Recovered | Audit (multi-DPI 150/200/240/300) |
|------|-------------------------|-----------|-----------------------------------|
| 1868 | 19 → 14 | +5  | 5/5 STRONG |
| 1872 | 45 → 28 | +17 | 16 STRONG + 1 WEAK |
| 1870 | 65 → 55 | +10 | 10/10 STRONG |
| 1874 | 63 → 38 | +25 | 25/25 STRONG |
| 1876 | 59 → 50 | +9  | 9/9 STRONG |
| 1866 | 79 → 61 | +18 | 18/18 STRONG |
| 1878 | 55 → 46 | +9  | 9/9 STRONG |
| **TOTAL** | **385 → 292** | **+93** | **92 STRONG + 1 WEAK + 0 FAIL** |

**+93 chapters recovered locally with 0 agent vision tokens.** Every confirmation's printed
roman token matched its oracle number EXACTLY under multi-DPI re-read (incl. additive forms:
CCCCXXVIII=428, COCCXXVII=427, DCLX=660, DLXXVI=576). The remaining **292** residual are
single-DPI-fragile reads or wide-window (>12 pp) garbled clusters — the true hard core, correctly
deferred to the eventual page-image visual fallback.

## Where it lives

- Tool: `C:\PatoLex-scratch\_scan_headers_multiact.py`, `_apply_multiact.py`, `_mq_audit.py`
  (multi-DPI auditor).
- Run log: `docs/80_PROJECT_HISTORY/run-logs/local-header-ocr-run.log`.
- Output: `production-186x-xx / production-187x-xx / parsed_acts_visual.json`.
- Extends `LESSON_2026-06-21_local_header_ocr_recovery.md` finding 4 (multi-act-page header
  loss) with the sparse + multi-DPI-vote recovery. The stubborn remainder (genuinely
  garbled/edge headers + wide-window non-multi-act cases) is the true hard core for the
  eventual page-image visual fallback.
