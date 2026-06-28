# PatoLex OCR-Era Page-Continuity Audit (Missing Leaves)

**Date:** 2026-06-23, UPDATED 2026-06-27 (Cohort-B recovery: position-anchoring + 4-digit pagination), UPDATED 2026-06-28 (no_page_images recovery + render-gap root cause). Filename retains the original 2026-06-23 date; this is the same living deliverable.  
**Tool:** `C:\PatoLex-scratch\page_continuity_audit.py` (deterministic; no GPU/VLM/LLM)  
**Scope:** all `production-*` volumes under `C:\PatoLex-scratch` (225 dirs)

## Headline totals

- **Missing printed pages detected (over the AUDITABLE subset): 175**
- **Volumes affected (>=1 gap): 49**
- Volumes audited clean (0 gaps): 161
- Volumes audited (total): 210
- Volumes NOT auditable: 15 (~1,332 pages NOT checked)

> **This 175 is a FLOOR over the 210 auditable volumes, NOT a corpus-wide figure.** The 15 not-auditable volumes are unchecked for missing leaves -- a dropped statute-body leaf inside any of them is invisible to this page-number method. See section (d) for why each is not auditable.

> **2026-06-28 recovery:** the 10 `no_page_images` volumes were investigated and rendered where a source PDF existed. **7 moved to AUDITABLE and all 7 are CLEAN (0 gaps)** -- the six born-digital `production-2000-vol1..6` (10,332 pp) plus `production-measures-1990` (544 pp). The missing-page total is therefore UNCHANGED at 175 (no new leaf drops found). Three remain not-auditable for real reasons (one with its source PDF missing from the archive, two tiny measures fragments). See the **ROOT CAUSE** section below. The 1872 regression check still reports EXACTLY its four known leaves.

## How to read these numbers (gap confidence -- READ BEFORE THE ARCHIVE TRIP)

The 175 missing pages span **82 detected gaps**. They are NOT all equal confidence:

| Gap type (EVEN-skip prior) | # gaps | # pages | Confidence |
|---|---|---|---|
| **2-page even jump ("one dropped leaf")** | 33 | 66 | **HIGH** -- a physical leaf is one sheet = 2 printed pages; a rapid-scan stuck-page drop loses pages in pairs, so a 2-page even jump is the unambiguous missing-leaf signature (all four Patrick-confirmed 1872 leaves are this shape). |
| **Even multi-page jump (4,6,10,12...)** | 8 | 60 | **HIGH** -- an even number of consecutive pages dropped = several whole leaves (a loosened gathering). The even parity is consistent with whole-leaf loss; confirm the exact span on site. |
| **Odd jump (1,3,5...)** | 41 | 49 | **LOWER / AMBIGUOUS** -- an odd number of printed pages is skipped. A physical leaf is two pages, so an odd break is usually NOT a clean dropped leaf: most often an ORIGINAL printing/numbering skip (unnumbered plate/blank, or a press numbering error), or a torn half-leaf -- indistinguishable from page numbers alone. Treat as 'check, do not assume missing.' (Verified by eye on 1931-vol1-chapters printed 2601: the sequence really jumps 2600 -> 2603 with the intervening leaf unreadable -- a real continuity break whose physical cause cannot be proven from numbering alone; and on 1951-vol2 printed 4195, two consecutive unreadable scan pages span a single skipped number.) |

**Actionable archive-trip number: the ~126 HIGH-confidence pages (even-parity drops: 33 one-leaf + 8 multi-leaf), the unambiguous missing-leaf signal; the 41 odd-parity breaks (49 pages) are a separate 'inspect' list, not assumed losses.**

### Two caveats that change which volumes matter

1. **The `-NNchapters` partial scans are the SOLE digitization of their page range -- their gaps may be REAL.** In the 1929-1963 span each `...-vol1-NNchapters` directory (e.g. `1953-vol1-52chapters`) is a separate scan that covers the FRONT portion of the year (e.g. 1953-52chapters = printed ~3-604) while its `...-chapters` sibling covers the CONTINUATION (printed ~608-2560). They are CONTIGUOUS, not overlapping -- so the 'clean' sibling does NOT contain the pages where the partial reports gaps and CANNOT vouch for them. 13 of the 49 affected volumes are these partials; their gaps were spot-verified as genuine sequence breaks (e.g. 1953 printed 138-139). Treat them as real candidate losses on the same confidence scale as any other volume, NOT as dismissable scan artifacts. Partials in the affected list: production-1929-vol1-29chapters, production-1941-vol1-41chapters, production-1943-vol1-42chapters, production-1947-vol1-46chapters, production-1949-vol1-49chapters-prior, production-1951-vol1-50chapters, production-1953-vol1-52chapters, production-1955-vol1-54chapters, production-1957-vol1-56chapters, production-1957-vol2-57chapters, production-1959-vol1-58chapters, production-1961-vol1-60chapters, production-1963-vol1-62chapters.

2. **The 2026-06-27 Cohort-B recovery moved the modern multi-volume vol3/vol4/vol5 volumes (continuous 4-digit pagination) from NOT-AUDITABLE to AUDITABLE.** They had near-perfect readability (read~=1.0) but previously failed `low_support` because the old 3-digit cap truncated their real 4-digit page stream and garbled 4-digit corner reads blocked a stable fit; the raised cap + position-anchoring noise filter fixed both (see the Cohort-B method note below). The residual NOT-AUDITABLE list is now mostly: genuinely missing page images (10 `no_page_images`), tiny fragments (2 `too_few_pages`), the early 1850s scans whose corner numbers are too faint to read reliably (low_support at read~0.8-0.9), and a few residual multi-stream / reset-numbered volumes the monotone fit still cannot represent. Two refusals keep this honest rather than lossy: RESOLUTION volumes are excluded by content (their 'RESOLUTION CHAPTER N' numbers would otherwise be misread as page numbers; resolutions are out of corpus scope), and `partial_numbering` volumes are refused when the fittable numbered body covers too small a fraction of the volume to localize gaps representatively. The model refuses rather than inventing gaps -- a KNOWN LIMITATION, not a data loss.

## (c) Affected volumes -- missing printed-page ranges

Per-gap tag: **H** = even-parity jump (HIGH confidence real leaf drop); **L** = odd-parity jump (LOWER / inspect, likely printing-numbering artifact).

| Volume | Missing printed-page ranges (count, conf) | Missing pages |
|---|---|---|
| production-1871-72 | 131-134 (4, H); 515-516 (2, H); 586-587 (2, H); 776-777 (2, H) | 10 |
| production-1915-vol1-chapters | 1548-1549 (2, H); 1870-1871 (2, H) | 4 |
| production-1927-vol1-chapters | 1626-1627 (2, H); 1940-1940 (1, L); 1965-1965 (1, L) | 4 |
| production-1929-vol1-29chapters | 1584-1584 (1, L); 1974-1975 (2, H) | 3 |
| production-1931-vol1-chapters | 2601-2601 (1, L) | 1 |
| production-1933-vol1-chapters | 2724-2725 (2, H) | 2 |
| production-1937-vol1-chapters | 2568-2569 (2, H) | 2 |
| production-1938-vol1-chapters | 118-119 (2, H) | 2 |
| production-1941-vol1-41chapters | 3233-3233 (1, L) | 1 |
| production-1943-vol1-42chapters | 34-34 (1, L) | 1 |
| production-1943-vol1-chapters | 3083-3083 (1, L); 3373-3374 (2, H) | 3 |
| production-1945-vol1-chapters | 2865-2865 (1, L) | 1 |
| production-1947-vol1-46chapters | 201-201 (1, L); 339-339 (1, L) | 2 |
| production-1947-vol1-chapters | 3241-3241 (1, L) | 1 |
| production-1948-vol1-chapters | 153-153 (1, L) | 1 |
| production-1949-vol1-49chapters-prior | 31-31 (1, L) | 1 |
| production-1949-vol1-chapters | 2849-2849 (1, L) | 1 |
| production-1950-vol1-chapters | 421-422 (2, H); 555-556 (2, H) | 4 |
| production-1951-vol1-50chapters | 77-77 (1, L) | 1 |
| production-1951-vol1-chapters | 1831-1831 (1, L) | 1 |
| production-1951-vol2-chapters | 4195-4195 (1, L) | 1 |
| production-1953-vol1-52chapters | 138-139 (2, H); 299-300 (2, H); 400-401 (2, H); 434-436 (3, L); 514-515 (2, H) | 11 |
| production-1953-vol2-chapters | 3693-3693 (1, L) | 1 |
| production-1955-vol1-54chapters | 117-117 (1, L); 233-233 (1, L); 371-371 (1, L) | 3 |
| production-1955-vol2-chapters | 3609-3609 (1, L) | 1 |
| production-1957-vol1-56chapters | 142-143 (2, H); 271-272 (2, H); 463-463 (1, L) | 5 |
| production-1957-vol2-57chapters | 4183-4183 (1, L) | 1 |
| production-1959-vol1-58chapters | 175-175 (1, L); 364-365 (2, H); 460-462 (3, L) | 6 |
| production-1959-vol2-chapters | 5317-5317 (1, L) | 1 |
| production-1961-vol1-60chapters | 138-138 (1, L); 288-288 (1, L); 475-475 (1, L) | 3 |
| production-1961-vol2-chapters | 4593-4593 (1, L) | 1 |
| production-1963-vol1-62chapters | 22-22 (1, L); 142-144 (3, L); 383-383 (1, L); 420-422 (3, L); 554-557 (4, H); 571-571 (1, L) | 13 |
| production-1963-vol2-chapters | 4569-4569 (1, L) | 1 |
| production-1967-vol3-chapters | 4304-4305 (2, H) | 2 |
| production-1970-vol1-chapters | 1648-1648 (1, L) | 1 |
| production-1971-vol2 | 4148-4148 (1, L) | 1 |
| production-1972-vol1-chapters | 896-897 (2, H) | 2 |
| production-1981-vol2 | 1562-1563 (2, H) | 2 |
| production-1982-vol1-chapters | 1256-1257 (2, H); 1264-1265 (2, H); 1282-1283 (2, H); 1298-1299 (2, H) | 8 |
| production-1982-vol2 | 2234-2245 (12, H) | 12 |
| production-1983-vol1-chapters | 945-950 (6, H) | 6 |
| production-1985-vol1-chapters | 804-805 (2, H); 1859-1860 (2, H) | 4 |
| production-1986-vol3 | 4812-4815 (4, H) | 4 |
| production-1987-vol2 | 2030-2031 (2, H) | 2 |
| production-1989-vol1-chapters | 1146-1147 (2, H) | 2 |
| production-1989-vol2 | 2128-2129 (2, H); 2832-2835 (4, H) | 6 |
| production-1990-vol2 | 3295-3312 (18, H) | 18 |
| production-1990-vol4 | 6848-6848 (1, L) | 1 |
| production-1991-vol1 | 1244-1251 (8, H); 1258-1259 (2, H) | 10 |

## (d) Volumes NOT auditable (honest coverage)

These volumes could not be audited for printed-page continuity. Reason codes: `no_page_images_source_pdf_missing` = the volume was OCR'd from page images that no longer exist on disk AND no source PDF remains in the archive to re-render them (NOTE: this exact reason string is a MANUAL annotation on the `production-1883-84-regular` row -- the audit tool itself only emits the generic `no_page_images`; the row was hand-edited during the 2026-06-28 merge to record the verified source-missing provenance, and is otherwise consistent: npages 0, auditable false); `low_support`/`weak_offset`/`too_few_pages` = a fragment or too few legible printed page numbers to fit a reliable numbering sequence; `no_digits`/`no_support` = page-number band not legibly recoverable.

| Volume | Reason | Pages | Page-number readability |
|---|---|---|---|
| production-1852 | low_support | 288 | 0.868 |
| production-1853 | low_support | 318 | 0.903 |
| production-1854 | low_support | 230 | 0.8 |
| production-1855 | low_support | 324 | 0.904 |
| production-1856 | low_support | 239 | 0.887 |
| production-1857 | low_support | 394 | 0.825 |
| production-1858 | low_support | 386 | 0.951 |
| production-1859 | low_support | 427 | 0.899 |
| production-1860 | low_support | 453 | 0.876 |
| production-1883-84 | low_support | 15 | 0.533 |
| production-1883-84-regular | no_page_images_source_pdf_missing | 0 | None |
| production-1927-vol1-26chapters | too_few_pages | 4 | 0.25 |
| production-1929-vol1-28chapters | too_few_pages | 6 | 0.333 |
| production-measures-1915 | too_few_pages | 2 | 1.0 |
| production-measures-1935 | weak_offset | 26 | 0.423 |

**Recovered out of this table on 2026-06-28** (rendered from source PDF, then audited -- all CLEAN): production-2000-vol1 (1752 pp), production-2000-vol2 (1664 pp), production-2000-vol3 (1900 pp), production-2000-vol4 (1718 pp), production-2000-vol5 (1860 pp), production-2000-vol6 (1438 pp), production-measures-1990 (544 pp). See per-volume detail (section b) for their offsets/support and the ROOT CAUSE section for why they lacked renders.

## (b) Per-volume detail (all auditable volumes)

Readability = fraction of pages whose top-strip OCR yielded >=1 digit candidate. Base offset = printed_page - pdf_seq_page for the first numbered body segment (derived empirically). Support = body pages whose printed number was positively read.

| Volume | Source | Pages | Read | Base off | Anchor printed | Support | Gaps | Missing |
|---|---|---|---|---|---|---|---|---|
| production-1850 | pages_prep_gray | 480 | 0.938 | -10 | 5 | 185 | 0 | 0 |
| production-1851 | pages_prep_gray | 545 | 0.884 | -4 | 10 | 154 | 0 | 0 |
| production-1861 | page-renders/1861_Statutes | 730 | 0.941 | -43 | 2 | 601 | 0 | 0 |
| production-1862 | page-renders/1862_Statutes | 660 | 0.889 | -46 | 5 | 381 | 0 | 0 |
| production-1863 | page-renders/1863_Statutes | 863 | 0.939 | -63 | 3 | 572 | 0 | 0 |
| production-1863-64 | page-renders/1863-64_Statutes | 644 | 0.893 | -83 | 5 | 491 | 0 | 0 |
| production-1865-66 | page-renders/1865-66_Statutes | 999 | 0.921 | -87 | 10 | 749 | 0 | 0 |
| production-1867-68 | page-renders/1867-68_Statutes | 828 | 0.921 | -71 | 8 | 663 | 0 | 0 |
| production-1869-70 | page-renders/1869-70_Statutes | 1027 | 0.932 | -63 | 2 | 693 | 0 | 0 |
| production-1871-72 | page-renders/1871-72_Statutes | 1064 | 0.918 | -93 | 3 | 927 | 4 | 10 |
| production-1873-74 | page-renders/1873-74_Statutes | 1086 | 0.91 | -89 | 3 | 920 | 0 | 0 |
| production-1873-74-code | page-renders/1873-74_Code | 511 | 0.918 | -9 | 10 | 389 | 0 | 0 |
| production-1875-76 | page-renders/1875-76_Statutes | 1025 | 0.934 | -63 | 6 | 508 | 0 | 0 |
| production-1875-76-code | page-renders/1875-76_Code | 136 | 0.787 | -11 | 4 | 81 | 0 | 0 |
| production-1877-78 | page-renders/1877-78_Statutes | 1153 | 0.858 | -67 | 10 | 779 | 0 | 0 |
| production-1877-78-code | page-renders/1877-78_Code | 134 | 0.731 | -9 | 10 | 81 | 0 | 0 |
| production-1880 | page-renders/1880_Statutes | 300 | 0.807 | -47 | 10 | 206 | 0 | 0 |
| production-1880-code | page-renders/1880_Code | 364 | 0.819 | -165 | 4 | 113 | 0 | 0 |
| production-1881 | page-renders/1881_Statutes | 151 | 0.464 | -46 | 6 | 30 | 0 | 0 |
| production-1885-86 | page-renders/1885-86_Statutes | 294 | 0.83 | -51 | 7 | 190 | 0 | 0 |
| production-1887 | page-renders/1887_Statutes | 306 | 0.781 | -51 | 10 | 211 | 0 | 0 |
| production-1889 | page-renders/1889_Statutes | 792 | 0.914 | -55 | 4 | 543 | 0 | 0 |
| production-1891 | page-renders/1891_Statutes | 593 | 0.933 | -55 | 2 | 480 | 0 | 0 |
| production-1893 | page-renders/1893_Statutes | 716 | 0.877 | -55 | 10 | 503 | 0 | 0 |
| production-1895 | page-renders/1895_Statutes | 508 | 0.919 | -53 | 5 | 408 | 0 | 0 |
| production-1897 | page-renders/1897_Statutes | 708 | 0.925 | -55 | 5 | 583 | 0 | 0 |
| production-1899 | page-renders/1899_Statutes | 566 | 0.917 | -57 | 1 | 304 | 0 | 0 |
| production-1900-01 | page-renders/1900-01_Statutes | 1030 | 0.95 | -58 | 10 | 893 | 0 | 0 |
| production-1903 | page-renders/1903_Statutes | 812 | 0.938 | -68 | 149 | 536 | 0 | 0 |
| production-1905 | page-renders/1905_Statutes | 1126 | 0.94 | -49 | 10 | 989 | 0 | 0 |
| production-1906-07 | page-renders/1906-07_Statutes | 1415 | 0.961 | -43 | 10 | 1290 | 0 | 0 |
| production-1907-09 | page-renders/1907-09_Statutes | 1403 | 0.917 | -52 | 701 | 570 | 0 | 0 |
| production-1910-11 | page-renders/1910-11_Statutes | 2240 | 0.973 | -53 | 783 | 1246 | 0 | 0 |
| production-1913-statutes | page-renders/1913_Statutes | 1808 | 0.96 | -57 | 2 | 1012 | 0 | 0 |
| production-1915-vol1-chapters | page-renders/1915_Vol1_Chapters | 1922 | 0.986 | -6 | 2 | 1257 | 2 | 4 |
| production-1917-vol1-chapters | page-renders/1917_Vol1_Chapters | 1978 | 0.976 | 1 | 3 | 1756 | 0 | 0 |
| production-1919-vol1-chapters | page-renders/1919_Vol1_Chapters | 1557 | 0.993 | 1 | 6 | 1371 | 0 | 0 |
| production-1921-vol1-chapters | page-renders/1921_Vol1_Chapters | 2270 | 0.995 | 1 | 3 | 2023 | 0 | 0 |
| production-1923-vol1-chapters | page-renders/1923_Vol1_Chapters | 1689 | 0.993 | 1 | 2 | 1515 | 0 | 0 |
| production-1925-vol1-chapters | page-renders/1925_Vol1_Chapters | 1423 | 0.994 | 1 | 8 | 1214 | 0 | 0 |
| production-1927-vol1-chapters | page-renders/1927_Vol1_Chapters | 2399 | 0.999 | 1 | 4 | 2342 | 3 | 4 |
| production-1929-vol1-29chapters | page-renders/1929_Vol1_29Chapters | 2276 | 0.999 | 0 | 4 | 1841 | 2 | 3 |
| production-1931-vol1-chapters | page-renders/1931_Vol1_Chapters | 3163 | 0.999 | 0 | 3 | 2880 | 1 | 1 |
| production-1933-vol1-chapters | page-renders/1933_Vol1_Chapters | 3270 | 0.999 | 0 | 2 | 3116 | 1 | 2 |
| production-1935-vol1-34chapters | page-renders/1935_Vol1_34Chapters | 44 | 0.886 | -1 | 7 | 26 | 0 | 0 |
| production-1935-vol1-chapters | page-renders/1935_Vol1_Chapters | 2679 | 0.998 | 46 | 48 | 2146 | 0 | 0 |
| production-1937-vol1-chapters | page-renders/1937_Vol1_Chapters | 3066 | 0.997 | -2 | 2 | 2862 | 1 | 2 |
| production-1938-vol1-chapters | page-renders/1938_Vol1_Chapters | 181 | 0.945 | -5 | 2 | 153 | 1 | 2 |
| production-1939-vol1-chapters | page-renders/1939_Vol1_Chapters | 3271 | 0.999 | 0 | 2 | 2691 | 0 | 0 |
| production-1941-vol1-41chapters | page-renders/1941_Vol1_41Chapters | 3154 | 0.999 | 400 | 402 | 2984 | 1 | 1 |
| production-1943-vol1-42chapters | page-renders/1943_Vol1_42Chapters | 102 | 0.892 | 2 | 9 | 78 | 1 | 1 |
| production-1943-vol1-chapters | page-renders/1943_Vol1_Chapters | 3290 | 0.996 | 108 | 110 | 3091 | 2 | 3 |
| production-1945-vol1-chapters | page-renders/1945_Vol1_Chapters | 2868 | 0.998 | 308 | 310 | 2664 | 1 | 1 |
| production-1947-vol1-46chapters | page-renders/1947_Vol1_46Chapters | 467 | 0.979 | 3 | 10 | 431 | 2 | 2 |
| production-1947-vol1-chapters | page-renders/1947_Vol1_Chapters | 3302 | 0.999 | 474 | 476 | 3173 | 1 | 1 |
| production-1948-vol1-chapters | page-renders/1948_Vol1_Chapters | 364 | 0.989 | 2 | 10 | 332 | 1 | 1 |
| production-1949-vol1-49chapters-prior | page-renders/1949_Vol1_49Chapters_prior | 251 | 0.98 | 1 | 10 | 216 | 1 | 1 |
| production-1949-vol1-chapters | page-renders/1949_Vol1_Chapters | 3423 | 0.999 | 2 | 10 | 3218 | 1 | 1 |
| production-1950-vol1-chapters | page-renders/1950_Vol1_Chapters | 353 | 0.955 | 254 | 256 | 301 | 2 | 4 |
| production-1951-vol1-50chapters | page-renders/1951_Vol1_50Chapters | 115 | 0.965 | 3 | 10 | 83 | 1 | 1 |
| production-1951-vol1-chapters | page-renders/1951_Vol1_Chapters | 2598 | 0.999 | 120 | 122 | 2395 | 1 | 1 |
| production-1951-vol2-chapters | page-renders/1951_Vol2_Chapters | 2024 | 0.999 | 2720 | 2721 | 1895 | 1 | 1 |
| production-1953-vol1-52chapters | page-renders/1953_Vol1_52Chapters | 592 | 0.97 | 2 | 10 | 507 | 5 | 11 |
| production-1953-vol1-chapters | page-renders/1953_Vol1_Chapters | 1955 | 0.999 | 606 | 608 | 1833 | 0 | 0 |
| production-1953-vol2-chapters | page-renders/1953_Vol2_Chapters | 1732 | 0.998 | 2560 | 2561 | 1602 | 1 | 1 |
| production-1955-vol1-54chapters | page-renders/1955_Vol1_54Chapters | 422 | 0.979 | 2 | 10 | 376 | 3 | 3 |
| production-1955-vol1-55chapters | page-renders/1955_Vol1_55Chapters | 1703 | 0.999 | 428 | 430 | 1639 | 0 | 0 |
| production-1955-vol2-chapters | page-renders/1955_Vol2_Chapters | 2134 | 0.999 | 2132 | 2133 | 2037 | 1 | 1 |
| production-1957-vol1-56chapters | page-renders/1957_Vol1_56Chapters | 535 | 0.981 | 2 | 10 | 478 | 3 | 5 |
| production-1957-vol1-57chapters | page-renders/1957_Vol1_57Chapters | 2191 | 0.999 | 544 | 546 | 2057 | 0 | 0 |
| production-1957-vol2-57chapters | page-renders/1957_Vol2_57Chapters | 2092 | 0.999 | 2736 | 2737 | 1919 | 1 | 1 |
| production-1959-vol1-58chapters | page-renders/1959_Vol1_58Chapters | 582 | 0.971 | 2 | 9 | 488 | 3 | 6 |
| production-1959-vol1-59chapters | page-renders/1959_Vol1_59Chapters | 2431 | 0.999 | 592 | 594 | 2338 | 0 | 0 |
| production-1959-vol2-chapters | page-renders/1959_Vol2_Chapters | 2812 | 0.999 | 3022 | 3023 | 2481 | 1 | 1 |
| production-1961-vol1-60chapters | page-renders/1961_Vol1_60Chapters | 510 | 0.971 | 2 | 4 | 455 | 3 | 3 |
| production-1961-vol1-61chapters | page-renders/1961_Vol1_61Chapters | 2485 | 0.999 | 522 | 526 | 2365 | 0 | 0 |
| production-1961-vol2-chapters | page-renders/1961_Vol2_Chapters | 2070 | 0.999 | 3005 | 3007 | 1829 | 1 | 1 |
| production-1963-vol1-62chapters | page-renders/1963_Vol1_62Chapters | 588 | 0.966 | 2 | 5 | 510 | 6 | 13 |
| production-1963-vol1-63chapters | page-renders/1963_Vol1_63Chapters | 1898 | 0.999 | 604 | 606 | 1815 | 0 | 0 |
| production-1963-vol2-chapters | page-renders/1963_Vol2_Chapters | 2494 | 0.999 | 2502 | 2503 | 2358 | 1 | 1 |
| production-1965-vol1-64chapters | page-renders/1965_Vol1_64Chapters | 864 | 0.971 | 1 | 8 | 740 | 0 | 0 |
| production-1965-vol1-65chapters | page-renders/1965_Vol1_65Chapters | 950 | 0.996 | 865 | 868 | 920 | 0 | 0 |
| production-1965-vol2 | page-renders/1965_Vol2 | 2006 | 0.999 | 1813 | 1815 | 1887 | 0 | 0 |
| production-1965-vol3-chapters | page-renders/1965_Vol3_Chapters | 1621 | 0.998 | 3818 | 3819 | 1498 | 0 | 0 |
| production-1966-vol1-chapters | page-renders/1966_Vol1_Chapters | 72 | 0.917 | 173 | 176 | 58 | 0 | 0 |
| production-1967-vol1-chapters | page-renders/1967_Vol1_Chapters | 1855 | 0.998 | 1 | 4 | 1743 | 0 | 0 |
| production-1967-vol2 | page-renders/1967_Vol2 | 2015 | 0.998 | 1856 | 1857 | 1891 | 0 | 0 |
| production-1967-vol3-chapters | page-renders/1967_Vol3_Chapters | 945 | 0.997 | 3869 | 3872 | 920 | 1 | 2 |
| production-1968-vol1-chapters | page-renders/1968_Vol1_Chapters | 1648 | 0.998 | 81 | 84 | 1560 | 0 | 0 |
| production-1968-vol2-chapters | page-renders/1968_Vol2_Chapters | 1682 | 0.996 | 1727 | 1729 | 739 | 0 | 0 |
| production-1969-vol1-chapters | page-renders/1969_Vol1_Chapters | 2220 | 0.999 | 53 | 56 | 2167 | 0 | 0 |
| production-1969-vol2-chapters | page-renders/1969_Vol2_Chapters | 2412 | 0.975 | 2272 | 2273 | 1505 | 0 | 0 |
| production-1970-vol1-chapters | page-renders/1970_Vol1_Chapters | 2012 | 0.995 | 1 | 4 | 1948 | 1 | 1 |
| production-1970-vol2-chapters | page-renders/1970_Vol2_Chapters | 1902 | 0.995 | 2013 | 2015 | 1616 | 0 | 0 |
| production-1971-vol1-chapters | page-renders/1971_Vol1_Chapters | 2592 | 0.997 | 1 | 5 | 2507 | 0 | 0 |
| production-1971-vol2 | page-renders/1971_Vol2 | 1887 | 0.997 | 2591 | 2593 | 1589 | 1 | 1 |
| production-1971-vol3-chapters | page-renders/1971_Vol3_Chapters | 392 | 0.995 | 4477 | 4479 | 358 | 0 | 0 |
| production-1972-vol1-chapters | page-renders/1972_Vol1_Chapters | 2586 | 0.999 | 1 | 1 | 2390 | 1 | 2 |
| production-1972-vol2-chapters | page-renders/1972_Vol2_Chapters | 948 | 0.993 | 2587 | 2590 | 750 | 0 | 0 |
| production-1973-vol1-chapters | page-renders/1973_Vol1_Chapters | 2288 | 0.999 | -1 | 1 | 2146 | 0 | 0 |
| production-1973-vol2-chapters | page-renders/1973_Vol2_Chapters | 1071 | 0.993 | 2285 | 2288 | 897 | 0 | 0 |
| production-1974-vol1-chapters | page-renders/1974_Vol1_Chapters | 2530 | 0.999 | -1 | 1 | 2377 | 0 | 0 |
| production-1974-vol2-chapters | page-renders/1974_Vol2_Chapters | 1422 | 0.997 | 2527 | 2529 | 1192 | 0 | 0 |
| production-1975-vol1-chapters | page-renders/1975_Vol1_Chapters | 2620 | 0.999 | -1 | 1 | 2451 | 0 | 0 |
| production-1975-vol2-chapters | page-renders/1975_Vol2_Chapters | 1419 | 0.989 | 2617 | 2619 | 1258 | 0 | 0 |
| production-1976-vol1-chapters | page-renders/1976_Vol1_Chapters | 2364 | 0.999 | -1 | 1 | 2204 | 0 | 0 |
| production-1976-vol2 | page-renders/1976_Vol2 | 2222 | 0.999 | 2361 | 2365 | 2115 | 0 | 0 |
| production-1976-vol3 | page-renders/1976_Vol3 | 2240 | 0.998 | 4581 | 4583 | 1986 | 0 | 0 |
| production-1977-vol1-chapters | page-renders/1977_Vol1_Chapters | 2308 | 0.999 | 1 | 4 | 2191 | 0 | 0 |
| production-1977-vol2 | page-renders/1977_Vol2 | 2434 | 0.999 | 2307 | 2310 | 2374 | 0 | 0 |
| production-1977-vol3-chapters | page-renders/1977_Vol3_Chapters | 225 | 0.978 | 4739 | 4742 | 117 | 0 | 0 |
| production-1978-vol1-chapters | page-renders/1978_Vol1_Chapters | 1926 | 0.999 | -1 | 1 | 1691 | 0 | 0 |
| production-1978-vol2 | page-renders/1978_Vol2 | 1536 | 0.999 | 1923 | 1925 | 1409 | 0 | 0 |
| production-1978-vol3 | page-renders/1978_Vol3 | 1448 | 0.995 | 3457 | 3459 | 1248 | 0 | 0 |
| production-1979-vol1-chapters | page-renders/1979_Vol1_Chapters | 1820 | 0.999 | -1 | 1 | 1712 | 0 | 0 |
| production-1979-vol2 | page-renders/1979_Vol2 | 1504 | 0.999 | 1817 | 1819 | 1454 | 0 | 0 |
| production-1979-vol3 | page-renders/1979_Vol3 | 1602 | 0.998 | 3319 | 3321 | 1479 | 0 | 0 |
| production-1980-vol1-chapters | page-renders/1980_Vol1_Chapters | 1500 | 0.999 | 1 | 4 | 1344 | 0 | 0 |
| production-1980-vol2 | page-renders/1980_Vol2 | 1750 | 0.999 | 1499 | 1501 | 1677 | 0 | 0 |
| production-1980-vol3 | page-renders/1980_Vol3 | 1930 | 0.998 | 3247 | 3249 | 1751 | 0 | 0 |
| production-1981-vol1-chapters | page-renders/1981_Vol1_Chapters | 1500 | 0.999 | 1 | 5 | 1343 | 0 | 0 |
| production-1981-vol2 | page-renders/1981_Vol2 | 1750 | 0.999 | 1499 | 1501 | 1680 | 1 | 2 |
| production-1981-vol3 | page-renders/1981_Vol3 | 1686 | 0.998 | 3249 | 3251 | 1558 | 0 | 0 |
| production-1982-vol1-chapters | page-renders/1982_Vol1_Chapters | 1418 | 0.999 | -1 | 1 | 1318 | 4 | 8 |
| production-1982-vol2 | page-renders/1982_Vol2 | 1526 | 0.999 | 1423 | 1425 | 1447 | 1 | 12 |
| production-1982-vol3 | page-renders/1982_Vol3 | 1578 | 0.999 | 2959 | 2961 | 1477 | 0 | 0 |
| production-1982-vol4 | page-renders/1982_Vol4 | 1360 | 0.999 | 4535 | 4537 | 1258 | 0 | 0 |
| production-1982-vol5 | page-renders/1982_Vol5 | 1055 | 0.99 | 5893 | 5896 | 841 | 0 | 0 |
| production-1983-vol1-chapters | page-renders/1983_Vol1_Chapters | 1602 | 0.999 | -1 | 1 | 1552 | 1 | 6 |
| production-1983-vol2 | page-renders/1983_Vol2 | 1798 | 0.999 | 1605 | 1607 | 1701 | 0 | 0 |
| production-1983-vol3 | page-renders/1983_Vol3 | 1750 | 0.999 | 3401 | 3404 | 1683 | 0 | 0 |
| production-1983-vol4-chapters | page-renders/1983_Vol4_Chapters | 722 | 0.983 | 5149 | 5151 | 511 | 0 | 0 |
| production-1984-vol1-chapters | page-renders/1984_Vol1_Chapters | 1986 | 0.999 | 1 | 10 | 1760 | 0 | 0 |
| production-1984-vol2 | page-renders/1984_Vol2 | 2350 | 0.999 | 1985 | 1987 | 2104 | 0 | 0 |
| production-1984-vol3 | page-renders/1984_Vol3 | 2327 | 0.994 | 4333 | 4336 | 1999 | 0 | 0 |
| production-1985-vol1-chapters | page-renders/1985_Vol1_Chapters | 1888 | 0.999 | 1 | 5 | 1785 | 2 | 4 |
| production-1985-vol2 | page-renders/1985_Vol2 | 2192 | 0.999 | 1891 | 1893 | 2079 | 0 | 0 |
| production-1985-vol3 | page-renders/1985_Vol3 | 2142 | 0.997 | 4081 | 4084 | 1923 | 0 | 0 |
| production-1986-vol1-chapters | page-renders/1986_Vol1_Chapters | 1666 | 0.999 | -1 | 1 | 1516 | 0 | 0 |
| production-1986-vol2 | page-renders/1986_Vol2 | 2016 | 0.999 | 1723 | 1744 | 1904 | 0 | 0 |
| production-1986-vol3 | page-renders/1986_Vol3 | 1947 | 0.993 | 3737 | 3739 | 1666 | 1 | 4 |
| production-1987-vol1-chapters | page-renders/1987_Vol1_Chapters | 1838 | 0.999 | 1 | 4 | 1703 | 0 | 0 |
| production-1987-vol2 | page-renders/1987_Vol2 | 2040 | 0.999 | 1837 | 1839 | 1934 | 1 | 2 |
| production-1987-vol3 | page-renders/1987_Vol3 | 2175 | 0.994 | 3877 | 3879 | 1971 | 0 | 0 |
| production-1987-vol4-chapters | page-renders/1987_Vol4_Chapters | 732 | 0.966 | -7 | 4 | 669 | 0 | 0 |
| production-1988-vol1-chapters | page-renders/1988_Vol1_Chapters | 1748 | 0.999 | 1 | 6 | 1668 | 0 | 0 |
| production-1988-vol2 | page-renders/1988_Vol2 | 2286 | 1.0 | 1747 | 1749 | 2181 | 0 | 0 |
| production-1988-vol3 | page-renders/1988_Vol3 | 2207 | 0.998 | 4029 | 4752 | 1298 | 0 | 0 |
| production-1988-vol4-chapters | page-renders/1988_Vol4_Chapters | 711 | 0.986 | -7 | 4 | 680 | 0 | 0 |
| production-1989-vol1-chapters | page-renders/1989_Vol1_Chapters | 2044 | 0.999 | 1 | 4 | 1937 | 1 | 2 |
| production-1989-vol2 | page-renders/1989_Vol2 | 2184 | 1.0 | 2045 | 2047 | 2118 | 2 | 6 |
| production-1989-vol3 | page-renders/1989_Vol3 | 2174 | 1.0 | 4233 | 4235 | 2119 | 0 | 0 |
| production-1990-vol1-chapters | page-renders/1990_Vol1_Chapters | 1350 | 0.999 | 1 | 4 | 933 | 0 | 0 |
| production-1990-vol2 | page-renders/1990_Vol2 | 2176 | 0.999 | 1327 | 1329 | 2042 | 1 | 18 |
| production-1990-vol3 | page-renders/1990_Vol3 | 2208 | 1.0 | 3519 | 3521 | 2124 | 0 | 0 |
| production-1990-vol4 | page-renders/1990_Vol4 | 2075 | 1.0 | 5725 | 5727 | 1954 | 1 | 1 |
| production-1990-vol5-firstextra | page-renders/1990_Vol5_FirstExtra | 141 | 0.943 | 8403 | 8410 | 125 | 0 | 0 |
| production-1990-vol5-reg-session | page-renders/1990_Vol5_Reg_Session | 604 | 0.995 | 7799 | 7801 | 438 | 0 | 0 |
| production-1991-vol1 | page-renders/1991_Vol1 | 1943 | 0.999 | -2 | 1 | 1123 | 2 | 10 |
| production-1991-vol2 | page-renders/1991_Vol2 | 2144 | 0.999 | 1945 | 3016 | 1029 | 0 | 0 |
| production-1991-vol3 | page-renders/1991_Vol3 | 2155 | 0.998 | 4087 | 4090 | 1942 | 0 | 0 |
| production-1992-vol1-statutes | page-renders/1992_Vol1_Statutes | 2128 | 0.998 | 1 | 5 | 2030 | 0 | 0 |
| production-1992-vol2 | page-renders/1992_Vol2 | 2528 | 1.0 | 2125 | 2127 | 2206 | 0 | 0 |
| production-1992-vol3 | page-renders/1992_Vol3 | 2582 | 0.989 | 4651 | 4654 | 2275 | 0 | 0 |
| production-1992-vol4 | page-renders/1992_Vol4 | 1515 | 0.956 | -7 | 4 | 693 | 0 | 0 |
| production-1993-vol1 | page-renders/1993_Vol1 | 2206 | 0.99 | -267 | 4 | 1771 | 0 | 0 |
| production-1993-vol2 | page-renders/1993_Vol2 | 2239 | 1.0 | 1938 | 1939 | 2170 | 0 | 0 |
| production-1993-vol3 | page-renders/1993_Vol3 | 2207 | 1.0 | 4176 | 4177 | 2125 | 0 | 0 |
| production-1993-vol4 | page-renders/1993_Vol4 | 1565 | 0.998 | 6382 | 6383 | 1440 | 0 | 0 |
| production-1993-vol5 | page-renders/1993_Vol5 | 1485 | 0.977 | -4 | 7 | 633 | 0 | 0 |
| production-1994-vol1 | page-renders/1994_Vol1 | 2208 | 0.986 | -461 | 6 | 1680 | 0 | 0 |
| production-1994-vol2 | page-renders/1994_Vol2 | 2240 | 0.999 | 1745 | 1747 | 2206 | 0 | 0 |
| production-1994-vol3 | page-renders/1994_Vol3 | 2208 | 0.999 | 3983 | 3985 | 2181 | 0 | 0 |
| production-1994-vol4 | page-renders/1994_Vol4 | 2144 | 1.0 | 6189 | 6191 | 2118 | 0 | 0 |
| production-1994-vol5 | page-renders/1994_Vol5 | 2153 | 0.97 | -488 | 4 | 626 | 0 | 0 |
| production-1995-vol1 | page-renders/1995_Vol1 | 2201 | 0.995 | -244 | 4 | 1919 | 0 | 0 |
| production-1995-vol2 | page-renders/1995_Vol2 | 2139 | 1.0 | 1956 | 1957 | 2116 | 0 | 0 |
| production-1995-vol3 | page-renders/1995_Vol3 | 2207 | 1.0 | 4194 | 4195 | 2155 | 0 | 0 |
| production-1995-vol4 | page-renders/1995_Vol4 | 1183 | 0.998 | 6400 | 6401 | 1099 | 0 | 0 |
| production-1995-vol5 | page-renders/1995_Vol5 | 2062 | 0.972 | -709 | 7 | 632 | 0 | 0 |
| production-1996-vol1 | page-renders/1996_Vol1 | 1921 | 0.985 | -453 | 4 | 1440 | 0 | 0 |
| production-1996-vol2 | page-renders/1996_Vol2 | 1888 | 0.994 | 1457 | 1459 | 1871 | 0 | 0 |
| production-1996-vol3 | page-renders/1996_Vol3 | 1904 | 0.995 | 3333 | 3335 | 1885 | 0 | 0 |
| production-1996-vol4 | page-renders/1996_Vol4 | 2144 | 0.994 | 5227 | 5230 | 2089 | 0 | 0 |
| production-1996-vol5 | page-renders/1996_Vol5 | 1376 | 0.975 | 7357 | 7359 | 1262 | 0 | 0 |
| production-1996-vol6 | page-renders/1996_Vol6 | 1929 | 0.94 | -813 | 5 | 764 | 0 | 0 |
| production-1997-vol1 | page-renders/1997_Vol1 | 1356 | 0.987 | -267 | 4 | 1075 | 0 | 0 |
| production-1997-vol2 | page-renders/1997_Vol2 | 1382 | 0.999 | 1087 | 1089 | 1378 | 0 | 0 |
| production-1997-vol3 | page-renders/1997_Vol3 | 1176 | 0.999 | 2467 | 2469 | 1169 | 0 | 0 |
| production-1997-vol4 | page-renders/1997_Vol4 | 1740 | 0.999 | 3641 | 3643 | 1735 | 0 | 0 |
| production-1997-vol5 | page-renders/1997_Vol5 | 1705 | 0.994 | 5379 | 5381 | 1558 | 0 | 0 |
| production-1997-vol6 | page-renders/1997_Vol6 | 1904 | 0.972 | -743 | 5 | 1053 | 0 | 0 |
| production-1998-vol1 | page-renders/1998_Vol1 | 1984 | 0.987 | -431 | 5 | 1540 | 0 | 0 |
| production-1998-vol2 | page-renders/1998_Vol2 | 1674 | 0.999 | 1551 | 1553 | 1666 | 0 | 0 |
| production-1998-vol3 | page-renders/1998_Vol3 | 1930 | 0.999 | 3223 | 3225 | 1927 | 0 | 0 |
| production-1998-vol4 | page-renders/1998_Vol4 | 1820 | 0.999 | 5151 | 5153 | 1810 | 0 | 0 |
| production-1998-vol5 | page-renders/1998_Vol5 | 1826 | 0.993 | 6969 | 6971 | 1636 | 0 | 0 |
| production-1998-vol6 | page-renders/1998_Vol6 | 2157 | 0.978 | -850 | 5 | 1035 | 0 | 0 |
| production-1999-vol1 | page-renders/1999_Vol1 | 1922 | 0.99 | -287 | 5 | 1620 | 0 | 0 |
| production-1999-vol2 | page-renders/1999_Vol2 | 2040 | 1.0 | 1633 | 1635 | 2031 | 0 | 0 |
| production-1999-vol3 | page-renders/1999_Vol3 | 1918 | 0.999 | 3671 | 3673 | 1912 | 0 | 0 |
| production-1999-vol4 | page-renders/1999_Vol4 | 1726 | 0.999 | 5587 | 5589 | 1718 | 0 | 0 |
| production-1999-vol5 | page-renders/1999_Vol5 | 2002 | 0.972 | 7311 | 7313 | 653 | 0 | 0 |
| production-2000-vol1 | page-renders/2000_Vol1 | 1752 | 0.986 | -533 | 10 | 1194 | 0 | 0 |
| production-2000-vol2 | page-renders/2000_Vol2 | 1664 | 0.999 | 1217 | 1219 | 1618 | 0 | 0 |
| production-2000-vol3 | page-renders/2000_Vol3 | 1900 | 0.999 | 2879 | 2881 | 1893 | 0 | 0 |
| production-2000-vol4 | page-renders/2000_Vol4 | 1718 | 0.999 | 4777 | 4779 | 1654 | 0 | 0 |
| production-2000-vol5 | page-renders/2000_Vol5 | 1860 | 0.999 | 6493 | 6495 | 1829 | 0 | 0 |
| production-2000-vol6 | page-renders/2000_Vol6 | 1438 | 0.974 | -359 | 4 | 778 | 0 | 0 |
| production-measures-1990 | page-renders/Measures_1990 | 544 | 0.985 | 219 | 221 | 477 | 0 | 0 |

> The seven rows above were recovered on 2026-06-28 (see ROOT CAUSE). The six `2000` volumes form one continuously-paginated 6-volume set (printed pages run vol1 ~10-1200, vol2 ~1219-2700, vol3 ~2881-4500, vol4 ~4779-6300, vol5 ~6495-8200, vol6 continuing) -- the cumulative base offsets confirm the cross-volume continuous pagination, exactly as for the 1990s multi-volume years.

## ROOT CAUSE -- why these 10 volumes had no rendered page images (Job B)

The 10 `no_page_images` volumes are NOT one failure; they are **three distinct cohorts** with three distinct causes. Investigation was deterministic (directory/PDF inspection, OCR-consensus `img_path` provenance, source-PDF page-count matching).

**Cohort 1 -- `production-2000-vol1..6` (6 volumes): a real, isolated ingest GAP -- the OCR pipeline never ran on the year 2000.**
These dirs contain ONLY `page_classification.json` (+ empty `pages_raw/`, empty `pages_prep_gray/`, empty `ocr_consensus/`). There is NO `ocr_consensus/page_ocr_results.json`, NO `OCR_COMPLETE.marker`, and NO `parsed_acts_*.json`. The page-classification step ran (it records e.g. vol1 `total_pages: 1752`, `born_digital: true`), but the OCR/parse stages never executed and the prep-gray page images were never produced -- hence no renders to audit. **This points to a coverage hole WIDER than the audit:** in the file corpus the year-2000 statutes were classified but never OCR'd and never parsed from these dirs (whether the enactments nonetheless reached the DB via another path was not checked -- this audit is no-DB; see the WIDER FINDING caveat below). The good news is the source is intact and clean: all six `2000_VolN.pdf` files are present in `chief-clerk-archive`, are **born-digital with a real text layer**, and their page counts match `page_classification.json` exactly (1752/1664/1900/1718/1860/1438). They render cleanly and audit CLEAN. **FLAGGED SEPARATELY below as a wider corpus gap.**

**Cohort 2 -- `production-measures-1915 / -1935 / -1990` (3 volumes): NOT a gap -- wrong document type for this audit (the proposition/initiative parser track).**
These dirs contain ONLY `parsed_measures.json` -- the separate proposition/initiative parser track (per the corpus-scope memory: voter-initiative "MEASURES SUBMITTED TO VOTE OF ELECTORS", proposition-keyed, NOT statute chapters). They never had a page-render pipeline because they are not statute-chapter volumes; the measures parser works directly off the measures PDFs without producing prep-gray/render images. The source measures PDFs DO exist and were rendered for completeness: `1915_Vol1_Measures.pdf` is **only 2 pages** (`too_few_pages`), `1935_Vol1_Measures.pdf` is **26 pages** of sparse proposition pagination (`weak_offset`, read 0.42), and `1990_Vol1_Measures.pdf` is **544 pages** (audited CLEAN). Continuity-auditing tiny proposition booklets for "missing leaves" via statute running-head page numbers is not meaningful -- the two small ones legitimately refuse, and the large one is clean.

**Cohort 3 -- `production-1883-84-regular` (1 volume): page images deleted AND source PDF missing from the archive -- genuinely unrecoverable here.**
This volume WAS fully processed: 440 consensus pages, `OCR_COMPLETE.marker`, and a full `parsed_acts_certified.json`. Its OCR `img_path` provenance points at a now-deleted `production-1883-84-regular\pages_prep_gray\page_NNNN.png` set. But its source PDF is **NOT in the archive**: the only 1883-84 statutes PDFs present (`1883-84_Statutes.pdf`, `1883-84_Statutes_1E.pdf`) are **15-page image-only fragments** -- far too short to be the 440-page regular-session volume (verified: "TWENTY-FIFTH SESSION", a real ~440-page 1883 statutes book). A corpus-wide scan for any 400-500 page PDF found no 1883-84 statutes candidate. So this volume cannot be re-rendered from the on-disk corpus. It is parsed/certified (its enactments are not lost), but it cannot be page-continuity-audited until the source scan is re-acquired. (The sibling `production-1883-84`, 13/15 consensus pages, is the same fragment-PDF story and was already `low_support`.)

### WIDER FINDING (flag): year-2000 statute production dirs classified but NEVER OCR'd/parsed (DB ingest status NOT checked -- no-DB audit)

Cohort 1 is the only one of the three that implies a coverage hole beyond the audit. **In the FILE corpus, the six year-2000 statute production dirs (10,332 pages of born-digital text) were page-classified but the OCR and parse stages never ran** -- they have no `ocr_consensus/page_ocr_results.json`, no `OCR_COMPLETE.marker`, and no `parsed_acts_*.json`, unlike every audited neighbor (each of which carries those artifacts). The page-classification step is the ONLY stage that left output.

Caveat (DB not queried -- this audit is no-DB by constraint): CLAUDE.md records a "born-digital 2000-2008" ingest of 8,290 enactments, so it is possible year-2000 enactments reached the database via a DIFFERENT production path than these six `production-2000-vol*` dirs. What is certain from the file corpus is that **these specific production bundles were never OCR'd or parsed** -- so whatever did (or did not) get ingested for 2000 did not come from them, and there is no parsed-acts artifact on disk to reconcile against. This warrants a follow-up DB check: confirm year-2000 chaptered statutes are actually present as enactments. If they are not, this is a real corpus gap; if they are, these six dirs are stale/abandoned scaffolding that should be reconciled or removed. Either way it is worth a dedicated ticket. (The page renders now exist as a by-product of this recovery; 2000 is born-digital, so OCR/parse can proceed cheaply against the PDF text layer if needed.)

## (e) Reproducible command + method note

```
C:/PatoLex-scratch/ocr-engines/qwenvl-venv/Scripts/python.exe \
  C:/PatoLex-scratch/page_continuity_audit.py all --workers 16 \
  --json-out C:/PatoLex-scratch/_audit_all.json
```

Per-volume: `python page_continuity_audit.py <year|all|production-NAME>`.

**Recovery renders (2026-06-28).** The seven recovered volumes were rendered with PyMuPDF (`fitz`) at a fixed `fitz.Matrix(1.6, 1.6)` zoom, RGB, no alpha, saved as `page-renders/<dir>/NNNN.png` (0-based, `NNNN == pdf_seq`). The 1.6 zoom is the constant matching the pre-existing renders (derived empirically: existing `page-renders/1871-72_Statutes/0000.png` is 605x1002 px over a 378x626 pt PDF page = 1.6005; `1991_Vol1` and `1899_Statutes` likewise = 1.60). Render-dir names (`2000_Vol1`..`2000_Vol6`, `Measures_1990`) were chosen so the audit's `render_dir_for()` separator-stripped match resolves them from the `production-2000-vol*` / `production-measures-*` dir names. Source PDFs are `chief-clerk-archive/2000_VolN.pdf` and `chief-clerk-archive/<YEAR>_Vol1_Measures.pdf`. Render script: `C:\PatoLex-scratch\_recover\render_missing.py` (read-only on PDFs; writes only PNGs).

**Method.** The printed running-head page number is NOT present in the full-page consensus OCR (it is a top-outer-corner number dropped/garbled by full-page consensus -- verified). The tool therefore RE-OCRs a thin top strip (top ~11% of the page height) of each rendered page image with Tesseract in sparse-text mode (`--psm 11`) under a digit whitelist, recovering the corner page number. It models `printed = pdf_seq + offset`, where `offset` is piecewise-constant and MONOTONE NON-DECREASING (each physically dropped leaf bumps the offset UP by the number of leaves lost; nothing can lower it). Each OCR'd page-number candidate votes an offset; the tool fits the best monotone-non-decreasing offset step-function over the numbered body by dynamic programming, scoring (supported pages) minus a per-step penalty. EVERY offset INCREASE in the optimal path -- walked per-page across the fitted body -- is a missing leaf, reported AND LOCALIZED at its own position; two leaf-drops separated by readable numbered pages are reported as two distinct ranges. (Caveat: when two drops are adjacent with only unreadable/filter-removed pages between them, the DP may MERGE them into one reported range -- the TOTAL missing-page COUNT stays correct, but the split between the two drops is not recoverable in that case.) Because a real leaf-drop is corroborated by an entire post-gap segment while a transient OCR misread is a single stray vote, the step penalty plus a per-segment support/density floor make isolated misreads unable to create a phantom gap. Front matter (roman-numeral / unnumbered title pages) and trailing index matter fall outside the fitted body window and are not scored.

**Guards against phantom and mislocated gaps (added after adversarial review).** (a) RESOLUTION pages are excluded by consensus-OCR content before fitting, so their 'RESOLUTION CHAPTER N' numbers cannot be misread as page numbers (resolutions are out of corpus scope). (b) Each offset step is localized at its true page position rather than merged between the surviving high-support segments -- this fixes both wrong ranges and omitted gaps when leaf-drops cluster. (c) A coverage gate refuses any volume whose fittable numbered body covers too small a fraction of the volume (a single numbering stream of a multi-stream vol2/vol3) -- reported as `partial_numbering` rather than emitting unrepresentative gaps from a sliver. (d) Odd-parity breaks are reported but flagged LOWER-confidence: a physical leaf is two pages, so an odd-page break is usually an original printing/numbering skip, not a dropped leaf.

**Cohort-B recovery (position anchoring + 4-digit pagination -- 2026-06-27).** The modern multi-volume years (1957, 1971-1999) use CONTINUOUS 4-digit pagination across the year's volumes (vol3 of 1990 runs printed pp ~3500-5700), so the true offset for a vol3/vol4/vol5 is the cumulative page count of the prior volumes (thousands), not a small front-matter offset. Two changes recovered 46 of these volumes -- which previously failed `low_support`/`partial_numbering` despite read~=1.0: (i) the plausible page-number cap was raised to admit real 4-digit page numbers (the old 3-digit cap silently truncated the real page stream); and (ii) a POSITION-ANCHORING noise filter (Patrick's method) was added BEFORE the fit -- it certifies trusted offsets from runs of >=3 consecutive +1 page-number reads, then discards any candidate read whose implied offset (printed - pdf_position) is not certified by a trusted anchor. This cheaply removes garbled 4-digit corner reads (a single misread digit on '4615' implies a wild offset) that previously prevented a stable monotone fit, while NEVER inventing a number. The filter APPLIES BROADLY -- to ~134 of the 225 volumes wherever enough consecutive-run anchors exist, INCLUDING the legacy 3-digit `vol1-chapters` volumes and the 1872 regression case, not only the 4-digit Cohort-B set. It is SAFE on the previously-auditable corpus NOT because it no-ops there (it does not -- `anchor_filter=true` on 1872, 5 anchor offsets), but because it only ever DELETES positionally-implausible reads (never invents one) and the downstream monotone DP is robust to deletions -- a removed read costs at most a little support and can never manufacture a step. VERIFIED: 1872 still reports EXACTLY its four known leaves (pp 131-134, 515-516, 586-587, 776-777, all even/HIGH), byte-identical to the pre-change result, and ZERO previously-auditable volume lost a gap. Each gap now carries an EVEN/ODD confidence tag from the even-skip prior (stuck pages drop in pairs -> even jumps are HIGH confidence).

**Image sources.** Prefer `page-renders/<Volume>/NNNN.png` (NNNN == page_1indexed); fall back to the volume's own `pages_prep_gray/page_NNNN.png` (NNNN == page_1indexed-1) when no render dir exists or the render dir is partial. The audit is READ-ONLY on the corpus and touches NO database.

**Validation.** On `production-1871-72` (1872 Statutes), the four leaves Patrick confirmed missing by eye -- printed pp **131-134, 515-516, 586-587, 776-777** (10 pages) -- are detected EXACTLY, with zero false positives in the clean stretches.
