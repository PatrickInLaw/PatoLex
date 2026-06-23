# Human-Review List — Machine-Unreadable Biennial Chapters — 2026-06-22

**Total chapters needing human review: 71** (across the seven biennial OCR-era session-years
1866, 1868, 1870, 1872, 1874, 1876, 1878).

These are the chapters the OCR-recovery campaign could **not** resolve by machine
(Tesseract + Surya + Qwen2.5-VL all miss them — almost always tiny multi-act entries with no
cleanly-printed running head). **They do NOT need a re-scan.** The printed page is present in
our source PDF; a human can read the chapter number and act title straight off the existing
image. (The nine *truly-missing* chapters — page physically absent from every scan — are a
separate list and are tracked in `ARCHIVES_SCAN_REQUEST_2026-06-22.md`; none of them appear here.)

---

## How to use this list

1. Open the source PDF named in the table:
   `C:\PatoLex-scratch\chief-clerk-archive\<biennium>_Statutes.pdf`.
2. Jump to the **candidate PDF page(s)** given for the chapter. These are **1-based PDF page
   numbers** (i.e. the page-sequence number the viewer shows — *not* the printed running-head
   page number). The candidate range is bracketed by the nearest chapters we already have, so
   the missing chapter's heading sits inside (or immediately around) that range.
3. On the page, find the printed `CHAPTER <number>` running head (early-era volumes print it as
   a Roman numeral, e.g. `CHAP. CCCXLIII` = 343; OCR garbles the word "CHAPTER" but the printed
   page is legible to a human).
4. Record three things for each chapter: **(a)** the printed CHAPTER number (confirm it matches
   the expected number in the table), **(b)** the act title (the "An Act to …" line), and
   **(c)** the PDF page where you read it.

**Note on "page range reliability":** the candidate range is derived from the OCR'd
`source_page` of the neighboring present chapters. For most rows this is a tight, reliable
bracket. A handful of rows are flagged **⚠ wide / unreliable** — there the bracketing neighbor
carries a corrupt OCR page number, so the range is implausibly large (or out of order). For
those, ignore the numeric range and instead **page to the printed running-head page that is
numerically just before/after the neighbor chapters**, or scan the volume around the expected
chapter's neighbors. (One known case: 1870 ch.143/CXLIII sits where the page sequence jumps
142→144 — read carefully around that break.)

> No page-image renders (`pages_raw/*.png`) exist on disk for these biennial volumes; work
> directly from the source PDF. The PDF is a pure image scan (no text layer), so a viewer's
> built-in text search will not find the chapter — you must read it visually.

---

## 1866 — `1865-66_Statutes.pdf` — 10 chapters

| Expected Chapter | Candidate PDF page(s) | Note |
|---|---|---|
| 143 | 212–214 | |
| 150 | 172–220 | ⚠ wide / unreliable — read near printed ch.149/151 |
| 198 | 264–279 | |
| 275 | 313–396 | ⚠ wide / unreliable — read near printed ch.274/276 |
| 343 | 468–471 | multi-act cluster (343/344/345 share this band) |
| 344 | 468–471 | multi-act cluster |
| 345 | 468–471 | multi-act cluster |
| 423 | 619–621 | |
| 448 | 657–667 | |
| 613 | 927–949 | ⚠ wide — neighbor pages out of order; read near printed ch.612/614 |

## 1868 — `1867-68_Statutes.pdf` — 1 chapter

| Expected Chapter | Candidate PDF page(s) | Note |
|---|---|---|
| 483 | 719–728 | |

## 1870 — `1869-70_Statutes.pdf` — 9 chapters

| Expected Chapter | Candidate PDF page(s) | Note |
|---|---|---|
| 143 | 209–212 | page sequence jumps 142→144 — read carefully at the break |
| 181 | 327–344 | |
| 384 | 590–594 | |
| 431 | 687–688 | |
| 453 | 718–724 | |
| 483 | 714–765 | ⚠ wide — neighbor pages out of order; read near printed ch.482/485 |
| 484 | 714–765 | ⚠ wide — read near printed ch.482/485 |
| 491 | 780–786 | |
| 525 | 846–850 | |

## 1872 — `1871-72_Statutes.pdf` — 14 chapters

| Expected Chapter | Candidate PDF page(s) | Note |
|---|---|---|
| 125 | 224–227 | multi-act cluster (125–128) |
| 126 | 224–227 | multi-act cluster |
| 127 | 224–227 | multi-act cluster |
| 128 | 224–227 | multi-act cluster |
| 363 | 604–605 | multi-act cluster (363/364) |
| 364 | 604–605 | multi-act cluster |
| 417 | 672–674 | multi-act cluster (417/418) |
| 418 | 672–674 | multi-act cluster |
| 433 | 714–739 | multi-act cluster (433–436) |
| 434 | 714–739 | multi-act cluster |
| 435 | 714–739 | multi-act cluster |
| 436 | 714–739 | multi-act cluster |
| 439 | 712–740 | ⚠ neighbor pages out of order — read near printed ch.438/440 |
| 538 | 179–863 | ⚠ wide / unreliable — neighbor ch.537 page corrupt; read near printed ch.537/539 |

## 1874 — `1873-74_Statutes.pdf` — 4 chapters

| Expected Chapter | Candidate PDF page(s) | Note |
|---|---|---|
| 261 | 448–449 | |
| 587 | 183–915 | ⚠ wide / unreliable — neighbor ch.586 page corrupt; read near printed ch.586/588 |
| 678 | 1036–1040 | end-of-volume; no following chapter to bracket — read the last chapters |
| 679 | 1036–1040 | end-of-volume; read the last chapters |

## 1876 — `1875-76_Statutes.pdf` — 22 chapters

| Expected Chapter | Candidate PDF page(s) | Note |
|---|---|---|
| 91 | 123–126 | |
| 306 | 123–464 | ⚠ wide / unreliable — neighbor page corrupt; read near printed ch.305/307 |
| 403 | 631–633 | |
| 417 | 42–646 | ⚠ wide / unreliable — read near printed ch.416/419 |
| 418 | 42–646 | ⚠ wide / unreliable — read near printed ch.416/419 |
| 421 | 648–658 | |
| 431 | 668–673 | |
| 438 | 687–689 | |
| 442 | 692–702 | multi-act cluster (442/443) |
| 443 | 692–702 | multi-act cluster |
| 447 | 702–708 | |
| 452 | 126–714 | ⚠ wide / unreliable — read near printed ch.451/453 |
| 459 | 718–734 | |
| 477 | 757–790 | multi-act cluster (477/478) |
| 478 | 757–790 | multi-act cluster |
| 497 | 89–824 | ⚠ wide / unreliable — read near printed ch.496/499 |
| 498 | 89–824 | ⚠ wide / unreliable — read near printed ch.496/499 |
| 503 | 63–826 | ⚠ wide / unreliable — read near printed ch.502/504 |
| 508 | 827–837 | |
| 518 | 103–859 | ⚠ wide / unreliable — read near printed ch.517/519 |
| 522 | 41–861 | ⚠ wide / unreliable — read near printed ch.521/523 |
| 541 | 871–882 | |

## 1878 — `1877-78_Statutes.pdf` — 11 chapters

| Expected Chapter | Candidate PDF page(s) | Note |
|---|---|---|
| 173 | 272–279 | |
| 418 | 682–691 | |
| 428 | 699–702 | |
| 441 | 710–750 | |
| 447 | 753–763 | multi-act cluster (447–449) |
| 448 | 753–763 | multi-act cluster |
| 449 | 753–763 | multi-act cluster |
| 484 | 814–816 | |
| 534 | 900–903 | |
| 642 | 1037–1055 | |
| 662 | 125–1090 | ⚠ wide / unreliable — neighbor page corrupt; read the last chapters of the volume |

---

## Per-year totals

| Year | Source PDF | Chapters to review |
|---|---|---|
| 1866 | `1865-66_Statutes.pdf` | 10 |
| 1868 | `1867-68_Statutes.pdf` | 1 |
| 1870 | `1869-70_Statutes.pdf` | 9 |
| 1872 | `1871-72_Statutes.pdf` | 14 |
| 1874 | `1873-74_Statutes.pdf` | 4 |
| 1876 | `1875-76_Statutes.pdf` | 22 |
| 1878 | `1877-78_Statutes.pdf` | 11 |
| **Total** | | **71** |

---

## Provenance

- Generated from `python pipeline/analysis/_residual_manifest.py <year>` for each year above
  (writes `C:\PatoLex-scratch\_manifest_<year>.json`), run 2026-06-22.
- `source_page` = 1-based source-PDF page index (confirmed in
  `lessons/LESSON_2026-06-22_vlm_header_recovery_pilot.md` finding 3:
  manifest `source_page` == `page_1indexed` == source-PDF page, 1-indexed).
- The wide/unreliable flags follow `lessons/LESSON_2026-06-21_local_header_ocr_recovery.md`
  finding 3 (early-era `source_page` is reliable for present chapters but some recorded pages
  point at mid-act continuation pages with no header; drive off the bracketed ranges, not point
  lookups).
- All recovery output remains additive draft JSON in `C:\PatoLex-scratch` — nothing here is
  written to Postgres or to any existing `parsed_acts_*.json`.
