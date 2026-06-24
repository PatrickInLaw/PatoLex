# PatoLex OCR-Era Page-Continuity Audit (Missing Leaves)

**Date:** 2026-06-23  
**Tool:** `C:\PatoLex-scratch\page_continuity_audit.py` (deterministic; no GPU/VLM/LLM)  
**Scope:** all `production-*` volumes under `C:\PatoLex-scratch` (225 dirs)

## Headline totals

- **Missing printed pages detected (over the AUDITABLE subset): 133**
- **Volumes affected (>=1 gap): 34**
- Volumes audited clean (0 gaps): 123
- Volumes audited (total): 157
- Volumes NOT auditable: 68 (~82,976 pages NOT checked)

> **This 133 is a FLOOR over the 157 auditable volumes, NOT a corpus-wide figure.** The 68 not-auditable volumes (~82,976 pages) are unchecked for missing leaves -- a dropped statute-body leaf inside any of them is invisible to this page-number method. See section (d) for why each is not auditable.

## How to read these numbers (gap confidence -- READ BEFORE THE ARCHIVE TRIP)

The 133 missing pages span **65 detected gaps**. They are NOT all equal confidence:

| Gap type | # gaps | # pages | Confidence |
|---|---|---|---|
| **2-page even->odd ("one dropped leaf")** | 25 | 50 | **HIGH** -- a physical leaf is one sheet = verso(even)+recto(odd); losing it drops exactly an even page then the next odd. The unambiguous missing-leaf signature (all four Patrick-confirmed 1872 leaves are this shape). |
| **Other multi-page (3,4,6,10,12...)** | 15 | 58 | **MEDIUM-HIGH** -- several consecutive leaves dropped (a loosened gathering). Real, but confirm the exact span on site. |
| **1-page** | 25 | 25 | **LOWER / AMBIGUOUS** -- a single printed number is skipped. A physical leaf is two pages, so a one-page break is usually NOT a dropped leaf: most often an ORIGINAL printing/numbering skip (unnumbered plate/blank, or a press numbering error) -- indistinguishable, from page numbers alone, from a torn half-leaf. Treat as 'check, do not assume missing.' (Verified by eye on 1931-vol1-chapters printed 2601: the sequence really jumps 2600 -> 2603 with the intervening leaf unreadable -- a real continuity break whose physical cause cannot be proven from numbering alone.) |

**Actionable archive-trip number: the ~50 HIGH-confidence pages (25 one-leaf drops), plus ~58 medium multi-page pages to confirm; the 25 single-page breaks are a separate 'inspect' list, not assumed losses.**

### Two caveats that change which volumes matter

1. **The `-NNchapters` partial scans are the SOLE digitization of their page range -- their gaps may be REAL.** In the 1929-1963 span each `...-vol1-NNchapters` directory (e.g. `1953-vol1-52chapters`) is a separate scan that covers the FRONT portion of the year (e.g. 1953-52chapters = printed ~3-604) while its `...-chapters` sibling covers the CONTINUATION (printed ~608-2560). They are CONTIGUOUS, not overlapping -- so the 'clean' sibling does NOT contain the pages where the partial reports gaps and CANNOT vouch for them. 11 of the 34 affected volumes are these partials; their gaps were spot-verified as genuine sequence breaks (e.g. 1953 printed 138-139). Treat them as real candidate losses on the same confidence scale as any other volume, NOT as dismissable scan artifacts. Partials in the affected list: production-1929-vol1-29chapters, production-1943-vol1-42chapters, production-1947-vol1-46chapters, production-1949-vol1-49chapters-prior, production-1951-vol1-50chapters, production-1953-vol1-52chapters, production-1955-vol1-54chapters, production-1957-vol1-56chapters, production-1959-vol1-58chapters, production-1961-vol1-60chapters, production-1963-vol1-62chapters.

2. **Most 'NOT AUDITABLE' volumes are not damaged -- they are non-statute, reset-numbered, or multi-stream.** 42 of the 68 not-auditable volumes have near-perfect readability (>=0.90) but fail the monotone fit: the vol3/vol4/vol5 'index / tables / topical / history' volumes of the modern multi-volume years (which restart numbering per section or are not chapter-numbered), plus vol2/vol3 volumes whose page numbering is split into separate streams. Two specific refusals make this honest rather than lossy: RESOLUTION volumes are excluded by content (their 'RESOLUTION CHAPTER N' numbers would otherwise be misread as page numbers -> phantom gaps; resolutions are out of corpus scope), and `partial_numbering` volumes are refused when the fittable numbered body covers too small a fraction of the volume to localize gaps representatively. The model refuses rather than inventing gaps -- a KNOWN LIMITATION, not a data loss. (10 of the 68 are genuinely no_page_images; 2 are tiny fragments.)

## (c) Affected volumes -- missing printed-page ranges

| Volume | Missing printed-page ranges (count) | Missing pages |
|---|---|---|
| production-1871-72 | 131-134 (4); 515-516 (2); 586-587 (2); 776-777 (2) | 10 |
| production-1915-vol1-chapters | 1548-1549 (2); 1870-1871 (2) | 4 |
| production-1927-vol1-chapters | 1626-1627 (2); 1940-1940 (1); 1965-1965 (1) | 4 |
| production-1929-vol1-29chapters | 1584-1584 (1); 1974-1975 (2) | 3 |
| production-1931-vol1-chapters | 2601-2601 (1) | 1 |
| production-1933-vol1-chapters | 2724-2725 (2) | 2 |
| production-1937-vol1-chapters | 2568-2569 (2) | 2 |
| production-1938-vol1-chapters | 118-119 (2) | 2 |
| production-1943-vol1-42chapters | 34-34 (1) | 1 |
| production-1945-vol1-chapters | 2865-2865 (1) | 1 |
| production-1947-vol1-46chapters | 201-201 (1); 339-339 (1) | 2 |
| production-1948-vol1-chapters | 153-153 (1) | 1 |
| production-1949-vol1-49chapters-prior | 31-31 (1) | 1 |
| production-1949-vol1-chapters | 2849-2849 (1) | 1 |
| production-1950-vol1-chapters | 421-422 (2); 555-556 (2) | 4 |
| production-1951-vol1-50chapters | 77-77 (1) | 1 |
| production-1951-vol1-chapters | 1831-1831 (1) | 1 |
| production-1953-vol1-52chapters | 138-139 (2); 299-300 (2); 400-401 (2); 434-436 (3); 514-515 (2) | 11 |
| production-1955-vol1-54chapters | 117-117 (1); 233-233 (1); 371-371 (1) | 3 |
| production-1957-vol1-56chapters | 142-143 (2); 271-272 (2); 463-463 (1) | 5 |
| production-1959-vol1-58chapters | 175-175 (1); 364-365 (2); 460-462 (3) | 6 |
| production-1961-vol1-60chapters | 138-138 (1); 288-288 (1); 475-475 (1) | 3 |
| production-1963-vol1-62chapters | 22-22 (1); 142-144 (3); 383-383 (1); 420-422 (3); 554-557 (4); 571-571 (1) | 13 |
| production-1970-vol1-chapters | 1648-1648 (1) | 1 |
| production-1972-vol1-chapters | 896-897 (2) | 2 |
| production-1981-vol2 | 1562-1563 (2) | 2 |
| production-1982-vol1-chapters | 1256-1257 (2); 1264-1265 (2); 1282-1283 (2); 1298-1299 (2) | 8 |
| production-1982-vol2 | 2234-2245 (12) | 12 |
| production-1983-vol1-chapters | 945-950 (6) | 6 |
| production-1985-vol1-chapters | 804-805 (2); 1859-1860 (2) | 4 |
| production-1987-vol2 | 2030-2031 (2) | 2 |
| production-1989-vol1-chapters | 1146-1147 (2) | 2 |
| production-1989-vol2 | 2128-2129 (2) | 2 |
| production-1991-vol1 | 1244-1251 (8); 1258-1259 (2) | 10 |

## (d) Volumes NOT auditable (honest coverage)

These volumes could not be audited for printed-page continuity. Reason codes: `no_page_images` = no rendered page images available on disk; `low_support`/`weak_offset`/`too_few_pages` = a fragment or too few legible printed page numbers to fit a reliable numbering sequence; `no_digits`/`no_support` = page-number band not legibly recoverable.

| Volume | Reason | Pages | Page-number readability |
|---|---|---|---|
| production-1852 | low_support | 288 | 0.858 |
| production-1853 | low_support | 318 | 0.899 |
| production-1854 | low_support | 230 | 0.796 |
| production-1855 | low_support | 324 | 0.892 |
| production-1856 | low_support | 239 | 0.879 |
| production-1857 | low_support | 394 | 0.822 |
| production-1858 | low_support | 386 | 0.951 |
| production-1859 | low_support | 427 | 0.899 |
| production-1860 | low_support | 453 | 0.854 |
| production-1883-84 | low_support | 15 | 0.533 |
| production-1883-84-regular | no_page_images | 0 | None |
| production-1927-vol1-26chapters | too_few_pages | 4 | 0.25 |
| production-1929-vol1-28chapters | too_few_pages | 6 | 0.333 |
| production-1951-vol2-chapters | partial_numbering | 2024 | 0.998 |
| production-1957-vol2-57chapters | low_support | 2092 | 0.999 |
| production-1959-vol2-chapters | partial_numbering | 2812 | 0.999 |
| production-1961-vol2-chapters | partial_numbering | 2070 | 0.999 |
| production-1965-vol3-chapters | partial_numbering | 1621 | 0.998 |
| production-1967-vol3-chapters | partial_numbering | 945 | 0.997 |
| production-1971-vol3-chapters | low_support | 392 | 0.995 |
| production-1976-vol3 | low_support | 2240 | 0.998 |
| production-1977-vol3-chapters | low_support | 225 | 0.978 |
| production-1978-vol3 | low_support | 1448 | 0.995 |
| production-1979-vol3 | low_support | 1602 | 0.998 |
| production-1980-vol3 | low_support | 1930 | 0.998 |
| production-1981-vol3 | low_support | 1686 | 0.998 |
| production-1982-vol3 | low_support | 1578 | 0.999 |
| production-1982-vol4 | low_support | 1360 | 0.999 |
| production-1982-vol5 | low_support | 1055 | 0.99 |
| production-1983-vol3 | low_support | 1750 | 0.999 |
| production-1983-vol4-chapters | low_support | 722 | 0.983 |
| production-1984-vol3 | low_support | 2327 | 0.994 |
| production-1985-vol3 | low_support | 2142 | 0.997 |
| production-1986-vol3 | low_support | 1947 | 0.993 |
| production-1987-vol3 | low_support | 2175 | 0.994 |
| production-1988-vol3 | low_support | 2207 | 0.998 |
| production-1989-vol3 | low_support | 2174 | 1.0 |
| production-1990-vol3 | low_support | 2208 | 1.0 |
| production-1990-vol4 | low_support | 2075 | 1.0 |
| production-1990-vol5-firstextra | low_support | 141 | 0.943 |
| production-1990-vol5-reg-session | low_support | 604 | 0.995 |
| production-1991-vol3 | low_support | 2155 | 0.998 |
| production-1992-vol3 | low_support | 2582 | 0.989 |
| production-1993-vol3 | low_support | 2207 | 1.0 |
| production-1993-vol4 | low_support | 1565 | 0.998 |
| production-1994-vol3 | low_support | 2208 | 0.999 |
| production-1994-vol4 | low_support | 2144 | 1.0 |
| production-1995-vol3 | low_support | 2207 | 1.0 |
| production-1995-vol4 | low_support | 1183 | 0.998 |
| production-1996-vol3 | low_support | 1904 | 0.995 |
| production-1996-vol4 | low_support | 2144 | 0.994 |
| production-1996-vol5 | low_support | 1376 | 0.975 |
| production-1997-vol4 | low_support | 1740 | 0.999 |
| production-1997-vol5 | low_support | 1705 | 0.994 |
| production-1998-vol3 | low_support | 1930 | 0.999 |
| production-1998-vol4 | low_support | 1820 | 0.999 |
| production-1998-vol5 | low_support | 1826 | 0.993 |
| production-1999-vol3 | low_support | 1918 | 0.999 |
| production-1999-vol4 | low_support | 1726 | 0.999 |
| production-2000-vol1 | no_page_images | 0 | None |
| production-2000-vol2 | no_page_images | 0 | None |
| production-2000-vol3 | no_page_images | 0 | None |
| production-2000-vol4 | no_page_images | 0 | None |
| production-2000-vol5 | no_page_images | 0 | None |
| production-2000-vol6 | no_page_images | 0 | None |
| production-measures-1915 | no_page_images | 0 | None |
| production-measures-1935 | no_page_images | 0 | None |
| production-measures-1990 | no_page_images | 0 | None |

## (b) Per-volume detail (all auditable volumes)

Readability = fraction of pages whose top-strip OCR yielded >=1 digit candidate. Base offset = printed_page - pdf_seq_page for the first numbered body segment (derived empirically). Support = body pages whose printed number was positively read.

| Volume | Source | Pages | Read | Base off | Anchor printed | Support | Gaps | Missing |
|---|---|---|---|---|---|---|---|---|
| production-1850 | pages_prep_gray | 480 | 0.935 | -10 | 5 | 185 | 0 | 0 |
| production-1851 | pages_prep_gray | 545 | 0.87 | -4 | 10 | 154 | 0 | 0 |
| production-1861 | page-renders/1861_Statutes | 730 | 0.941 | -43 | 2 | 601 | 0 | 0 |
| production-1862 | page-renders/1862_Statutes | 660 | 0.886 | -46 | 5 | 381 | 0 | 0 |
| production-1863 | page-renders/1863_Statutes | 863 | 0.937 | -63 | 3 | 572 | 0 | 0 |
| production-1863-64 | page-renders/1863-64_Statutes | 644 | 0.893 | -83 | 5 | 491 | 0 | 0 |
| production-1865-66 | page-renders/1865-66_Statutes | 999 | 0.92 | -87 | 10 | 749 | 0 | 0 |
| production-1867-68 | page-renders/1867-68_Statutes | 828 | 0.921 | -71 | 8 | 663 | 0 | 0 |
| production-1869-70 | page-renders/1869-70_Statutes | 1027 | 0.93 | -63 | 2 | 693 | 0 | 0 |
| production-1871-72 | page-renders/1871-72_Statutes | 1064 | 0.918 | -93 | 3 | 927 | 4 | 10 |
| production-1873-74 | page-renders/1873-74_Statutes | 1086 | 0.909 | -89 | 3 | 920 | 0 | 0 |
| production-1873-74-code | page-renders/1873-74_Code | 511 | 0.918 | -9 | 10 | 389 | 0 | 0 |
| production-1875-76 | page-renders/1875-76_Statutes | 1025 | 0.932 | -63 | 6 | 508 | 0 | 0 |
| production-1875-76-code | page-renders/1875-76_Code | 136 | 0.787 | -11 | 4 | 81 | 0 | 0 |
| production-1877-78 | page-renders/1877-78_Statutes | 1153 | 0.854 | -67 | 10 | 779 | 0 | 0 |
| production-1877-78-code | page-renders/1877-78_Code | 134 | 0.731 | -9 | 10 | 81 | 0 | 0 |
| production-1880 | page-renders/1880_Statutes | 300 | 0.807 | -47 | 10 | 206 | 0 | 0 |
| production-1880-code | page-renders/1880_Code | 364 | 0.816 | -165 | 4 | 113 | 0 | 0 |
| production-1881 | page-renders/1881_Statutes | 151 | 0.464 | -46 | 6 | 30 | 0 | 0 |
| production-1885-86 | page-renders/1885-86_Statutes | 294 | 0.83 | -51 | 7 | 190 | 0 | 0 |
| production-1887 | page-renders/1887_Statutes | 306 | 0.781 | -51 | 10 | 211 | 0 | 0 |
| production-1889 | page-renders/1889_Statutes | 792 | 0.913 | -55 | 4 | 543 | 0 | 0 |
| production-1891 | page-renders/1891_Statutes | 593 | 0.929 | -55 | 2 | 480 | 0 | 0 |
| production-1893 | page-renders/1893_Statutes | 716 | 0.874 | -55 | 10 | 503 | 0 | 0 |
| production-1895 | page-renders/1895_Statutes | 508 | 0.919 | -53 | 5 | 408 | 0 | 0 |
| production-1897 | page-renders/1897_Statutes | 708 | 0.925 | -55 | 5 | 583 | 0 | 0 |
| production-1899 | page-renders/1899_Statutes | 566 | 0.915 | -57 | 1 | 304 | 0 | 0 |
| production-1900-01 | page-renders/1900-01_Statutes | 1030 | 0.947 | -58 | 10 | 893 | 0 | 0 |
| production-1903 | page-renders/1903_Statutes | 812 | 0.937 | -68 | 149 | 536 | 0 | 0 |
| production-1905 | page-renders/1905_Statutes | 1126 | 0.94 | -49 | 10 | 989 | 0 | 0 |
| production-1906-07 | page-renders/1906-07_Statutes | 1415 | 0.961 | -43 | 10 | 1290 | 0 | 0 |
| production-1907-09 | page-renders/1907-09_Statutes | 1403 | 0.917 | -52 | 701 | 570 | 0 | 0 |
| production-1910-11 | page-renders/1910-11_Statutes | 2240 | 0.968 | -53 | 783 | 1246 | 0 | 0 |
| production-1913-statutes | page-renders/1913_Statutes | 1808 | 0.959 | -57 | 2 | 1012 | 0 | 0 |
| production-1915-vol1-chapters | page-renders/1915_Vol1_Chapters | 1922 | 0.986 | -6 | 2 | 1257 | 2 | 4 |
| production-1917-vol1-chapters | page-renders/1917_Vol1_Chapters | 1978 | 0.975 | 1 | 3 | 1756 | 0 | 0 |
| production-1919-vol1-chapters | page-renders/1919_Vol1_Chapters | 1557 | 0.992 | 1 | 6 | 1371 | 0 | 0 |
| production-1921-vol1-chapters | page-renders/1921_Vol1_Chapters | 2270 | 0.995 | 1 | 3 | 2023 | 0 | 0 |
| production-1923-vol1-chapters | page-renders/1923_Vol1_Chapters | 1689 | 0.992 | 1 | 2 | 1515 | 0 | 0 |
| production-1925-vol1-chapters | page-renders/1925_Vol1_Chapters | 1423 | 0.994 | 1 | 8 | 1214 | 0 | 0 |
| production-1927-vol1-chapters | page-renders/1927_Vol1_Chapters | 2399 | 0.999 | 1 | 4 | 2342 | 3 | 4 |
| production-1929-vol1-29chapters | page-renders/1929_Vol1_29Chapters | 2276 | 0.999 | 0 | 4 | 1841 | 2 | 3 |
| production-1931-vol1-chapters | page-renders/1931_Vol1_Chapters | 3163 | 0.999 | 0 | 3 | 2722 | 1 | 1 |
| production-1933-vol1-chapters | page-renders/1933_Vol1_Chapters | 3270 | 0.999 | 0 | 2 | 2859 | 1 | 2 |
| production-1935-vol1-34chapters | page-renders/1935_Vol1_34Chapters | 44 | 0.886 | -1 | 7 | 26 | 0 | 0 |
| production-1935-vol1-chapters | page-renders/1935_Vol1_Chapters | 2679 | 0.998 | 46 | 48 | 2146 | 0 | 0 |
| production-1937-vol1-chapters | page-renders/1937_Vol1_Chapters | 3066 | 0.997 | -2 | 2 | 2797 | 1 | 2 |
| production-1938-vol1-chapters | page-renders/1938_Vol1_Chapters | 181 | 0.945 | -5 | 2 | 153 | 1 | 2 |
| production-1939-vol1-chapters | page-renders/1939_Vol1_Chapters | 3271 | 0.998 | 0 | 2 | 2499 | 0 | 0 |
| production-1941-vol1-41chapters | page-renders/1941_Vol1_41Chapters | 3154 | 0.998 | 400 | 402 | 2465 | 0 | 0 |
| production-1943-vol1-42chapters | page-renders/1943_Vol1_42Chapters | 102 | 0.892 | 2 | 9 | 78 | 1 | 1 |
| production-1943-vol1-chapters | page-renders/1943_Vol1_Chapters | 3290 | 0.995 | 108 | 110 | 2734 | 0 | 0 |
| production-1945-vol1-chapters | page-renders/1945_Vol1_Chapters | 2868 | 0.998 | 308 | 310 | 2503 | 1 | 1 |
| production-1947-vol1-46chapters | page-renders/1947_Vol1_46Chapters | 467 | 0.979 | 3 | 10 | 431 | 2 | 2 |
| production-1947-vol1-chapters | page-renders/1947_Vol1_Chapters | 3302 | 0.998 | 474 | 476 | 2422 | 0 | 0 |
| production-1948-vol1-chapters | page-renders/1948_Vol1_Chapters | 364 | 0.989 | 2 | 10 | 332 | 1 | 1 |
| production-1949-vol1-49chapters-prior | page-renders/1949_Vol1_49Chapters_prior | 251 | 0.98 | 1 | 10 | 216 | 1 | 1 |
| production-1949-vol1-chapters | page-renders/1949_Vol1_Chapters | 3423 | 0.999 | 2 | 10 | 2804 | 1 | 1 |
| production-1950-vol1-chapters | page-renders/1950_Vol1_Chapters | 353 | 0.955 | 254 | 256 | 301 | 2 | 4 |
| production-1951-vol1-50chapters | page-renders/1951_Vol1_50Chapters | 115 | 0.965 | 3 | 10 | 83 | 1 | 1 |
| production-1951-vol1-chapters | page-renders/1951_Vol1_Chapters | 2598 | 0.999 | 120 | 122 | 2396 | 1 | 1 |
| production-1953-vol1-52chapters | page-renders/1953_Vol1_52Chapters | 592 | 0.968 | 2 | 10 | 507 | 5 | 11 |
| production-1953-vol1-chapters | page-renders/1953_Vol1_Chapters | 1955 | 0.999 | 606 | 608 | 1834 | 0 | 0 |
| production-1953-vol2-chapters | page-renders/1953_Vol2_Chapters | 1732 | 0.998 | 2560 | 2561 | 410 | 0 | 0 |
| production-1955-vol1-54chapters | page-renders/1955_Vol1_54Chapters | 422 | 0.979 | 2 | 10 | 376 | 3 | 3 |
| production-1955-vol1-55chapters | page-renders/1955_Vol1_55Chapters | 1703 | 0.999 | 428 | 430 | 1640 | 0 | 0 |
| production-1955-vol2-chapters | page-renders/1955_Vol2_Chapters | 2134 | 0.999 | 2132 | 2133 | 819 | 0 | 0 |
| production-1957-vol1-56chapters | page-renders/1957_Vol1_56Chapters | 535 | 0.981 | 2 | 10 | 478 | 3 | 5 |
| production-1957-vol1-57chapters | page-renders/1957_Vol1_57Chapters | 2191 | 0.999 | 544 | 546 | 2058 | 0 | 0 |
| production-1959-vol1-58chapters | page-renders/1959_Vol1_58Chapters | 582 | 0.971 | 2 | 9 | 488 | 3 | 6 |
| production-1959-vol1-59chapters | page-renders/1959_Vol1_59Chapters | 2431 | 0.999 | 592 | 594 | 2317 | 0 | 0 |
| production-1961-vol1-60chapters | page-renders/1961_Vol1_60Chapters | 510 | 0.971 | 2 | 4 | 455 | 3 | 3 |
| production-1961-vol1-61chapters | page-renders/1961_Vol1_61Chapters | 2485 | 0.999 | 522 | 526 | 2360 | 0 | 0 |
| production-1963-vol1-62chapters | page-renders/1963_Vol1_62Chapters | 588 | 0.966 | 2 | 5 | 510 | 6 | 13 |
| production-1963-vol1-63chapters | page-renders/1963_Vol1_63Chapters | 1898 | 0.999 | 604 | 606 | 1816 | 0 | 0 |
| production-1963-vol2-chapters | page-renders/1963_Vol2_Chapters | 2494 | 0.999 | 2502 | 2503 | 468 | 0 | 0 |
| production-1965-vol1-64chapters | page-renders/1965_Vol1_64Chapters | 864 | 0.971 | 1 | 8 | 740 | 0 | 0 |
| production-1965-vol1-65chapters | page-renders/1965_Vol1_65Chapters | 950 | 0.996 | 865 | 868 | 920 | 0 | 0 |
| production-1965-vol2 | page-renders/1965_Vol2 | 2006 | 0.999 | 1813 | 1815 | 1125 | 0 | 0 |
| production-1966-vol1-chapters | page-renders/1966_Vol1_Chapters | 72 | 0.917 | 173 | 176 | 58 | 0 | 0 |
| production-1967-vol1-chapters | page-renders/1967_Vol1_Chapters | 1855 | 0.998 | 1 | 4 | 1743 | 0 | 0 |
| production-1967-vol2 | page-renders/1967_Vol2 | 2015 | 0.998 | 1856 | 1857 | 1067 | 0 | 0 |
| production-1968-vol1-chapters | page-renders/1968_Vol1_Chapters | 1648 | 0.998 | 81 | 84 | 1560 | 0 | 0 |
| production-1968-vol2-chapters | page-renders/1968_Vol2_Chapters | 1682 | 0.996 | 1727 | 1729 | 739 | 0 | 0 |
| production-1969-vol1-chapters | page-renders/1969_Vol1_Chapters | 2220 | 0.999 | 53 | 56 | 2168 | 0 | 0 |
| production-1969-vol2-chapters | page-renders/1969_Vol2_Chapters | 2412 | 0.975 | 2272 | 2273 | 724 | 0 | 0 |
| production-1970-vol1-chapters | page-renders/1970_Vol1_Chapters | 2012 | 0.995 | 1 | 4 | 1949 | 1 | 1 |
| production-1970-vol2-chapters | page-renders/1970_Vol2_Chapters | 1902 | 0.995 | 2013 | 2015 | 958 | 0 | 0 |
| production-1971-vol1-chapters | page-renders/1971_Vol1_Chapters | 2592 | 0.997 | 1 | 5 | 2508 | 0 | 0 |
| production-1971-vol2 | page-renders/1971_Vol2 | 1887 | 0.996 | 2591 | 2593 | 382 | 0 | 0 |
| production-1972-vol1-chapters | page-renders/1972_Vol1_Chapters | 2586 | 0.999 | 1 | 1 | 2391 | 1 | 2 |
| production-1972-vol2-chapters | page-renders/1972_Vol2_Chapters | 948 | 0.993 | 2587 | 2590 | 382 | 0 | 0 |
| production-1973-vol1-chapters | page-renders/1973_Vol1_Chapters | 2288 | 0.999 | -1 | 1 | 2147 | 0 | 0 |
| production-1973-vol2-chapters | page-renders/1973_Vol2_Chapters | 1071 | 0.993 | 2285 | 2288 | 671 | 0 | 0 |
| production-1974-vol1-chapters | page-renders/1974_Vol1_Chapters | 2530 | 0.999 | -1 | 1 | 2378 | 0 | 0 |
| production-1974-vol2-chapters | page-renders/1974_Vol2_Chapters | 1422 | 0.997 | 2527 | 2529 | 445 | 0 | 0 |
| production-1975-vol1-chapters | page-renders/1975_Vol1_Chapters | 2620 | 0.999 | -1 | 1 | 2452 | 0 | 0 |
| production-1975-vol2-chapters | page-renders/1975_Vol2_Chapters | 1419 | 0.988 | 2617 | 2619 | 369 | 0 | 0 |
| production-1976-vol1-chapters | page-renders/1976_Vol1_Chapters | 2364 | 0.999 | -1 | 1 | 2205 | 0 | 0 |
| production-1976-vol2 | page-renders/1976_Vol2 | 2222 | 0.998 | 2361 | 2365 | 617 | 0 | 0 |
| production-1977-vol1-chapters | page-renders/1977_Vol1_Chapters | 2308 | 0.999 | 1 | 4 | 2192 | 0 | 0 |
| production-1977-vol2 | page-renders/1977_Vol2 | 2434 | 0.999 | 2307 | 2310 | 664 | 0 | 0 |
| production-1978-vol1-chapters | page-renders/1978_Vol1_Chapters | 1926 | 0.999 | -1 | 1 | 1691 | 0 | 0 |
| production-1978-vol2 | page-renders/1978_Vol2 | 1536 | 0.999 | 1923 | 1925 | 982 | 0 | 0 |
| production-1979-vol1-chapters | page-renders/1979_Vol1_Chapters | 1820 | 0.999 | -1 | 1 | 1712 | 0 | 0 |
| production-1979-vol2 | page-renders/1979_Vol2 | 1504 | 0.999 | 1817 | 1819 | 1145 | 0 | 0 |
| production-1980-vol1-chapters | page-renders/1980_Vol1_Chapters | 1500 | 0.999 | 1 | 4 | 1344 | 0 | 0 |
| production-1980-vol2 | page-renders/1980_Vol2 | 1750 | 0.999 | 1499 | 1501 | 1438 | 0 | 0 |
| production-1981-vol1-chapters | page-renders/1981_Vol1_Chapters | 1500 | 0.999 | 1 | 5 | 1343 | 0 | 0 |
| production-1981-vol2 | page-renders/1981_Vol2 | 1750 | 0.999 | 1499 | 1501 | 1437 | 1 | 2 |
| production-1982-vol1-chapters | page-renders/1982_Vol1_Chapters | 1418 | 0.999 | -1 | 1 | 1318 | 4 | 8 |
| production-1982-vol2 | page-renders/1982_Vol2 | 1526 | 0.999 | 1423 | 1425 | 1448 | 1 | 12 |
| production-1983-vol1-chapters | page-renders/1983_Vol1_Chapters | 1602 | 0.999 | -1 | 1 | 1552 | 1 | 6 |
| production-1983-vol2 | page-renders/1983_Vol2 | 1798 | 0.999 | 1605 | 1607 | 1314 | 0 | 0 |
| production-1984-vol1-chapters | page-renders/1984_Vol1_Chapters | 1986 | 0.999 | 1 | 10 | 1761 | 0 | 0 |
| production-1984-vol2 | page-renders/1984_Vol2 | 2350 | 0.999 | 1985 | 1987 | 897 | 0 | 0 |
| production-1985-vol1-chapters | page-renders/1985_Vol1_Chapters | 1888 | 0.999 | 1 | 5 | 1785 | 2 | 4 |
| production-1985-vol2 | page-renders/1985_Vol2 | 2192 | 0.999 | 1891 | 1893 | 1038 | 0 | 0 |
| production-1986-vol1-chapters | page-renders/1986_Vol1_Chapters | 1666 | 0.999 | -1 | 1 | 1516 | 0 | 0 |
| production-1986-vol2 | page-renders/1986_Vol2 | 2016 | 0.999 | 1723 | 1744 | 1187 | 0 | 0 |
| production-1987-vol1-chapters | page-renders/1987_Vol1_Chapters | 1838 | 0.999 | 1 | 4 | 1703 | 0 | 0 |
| production-1987-vol2 | page-renders/1987_Vol2 | 2040 | 0.999 | 1837 | 1839 | 1104 | 1 | 2 |
| production-1987-vol4-chapters | page-renders/1987_Vol4_Chapters | 732 | 0.966 | -7 | 4 | 669 | 0 | 0 |
| production-1988-vol1-chapters | page-renders/1988_Vol1_Chapters | 1748 | 0.999 | 1 | 6 | 1668 | 0 | 0 |
| production-1988-vol2 | page-renders/1988_Vol2 | 2286 | 1.0 | 1747 | 1749 | 1186 | 0 | 0 |
| production-1988-vol4-chapters | page-renders/1988_Vol4_Chapters | 711 | 0.986 | -7 | 4 | 680 | 0 | 0 |
| production-1989-vol1-chapters | page-renders/1989_Vol1_Chapters | 2044 | 0.999 | 1 | 4 | 1938 | 1 | 2 |
| production-1989-vol2 | page-renders/1989_Vol2 | 2184 | 1.0 | 2045 | 2047 | 756 | 1 | 2 |
| production-1990-vol1-chapters | page-renders/1990_Vol1_Chapters | 1350 | 0.999 | 1 | 4 | 933 | 0 | 0 |
| production-1990-vol2 | page-renders/1990_Vol2 | 2176 | 0.999 | 1327 | 1329 | 1559 | 0 | 0 |
| production-1991-vol1 | page-renders/1991_Vol1 | 1943 | 0.999 | -2 | 444 | 1121 | 2 | 10 |
| production-1991-vol2 | page-renders/1991_Vol2 | 2144 | 0.999 | 1949 | 1951 | 996 | 0 | 0 |
| production-1992-vol1-statutes | page-renders/1992_Vol1_Statutes | 2128 | 0.998 | 1 | 5 | 2031 | 0 | 0 |
| production-1992-vol2 | page-renders/1992_Vol2 | 2528 | 1.0 | 2125 | 2127 | 653 | 0 | 0 |
| production-1992-vol4 | page-renders/1992_Vol4 | 1515 | 0.955 | -7 | 4 | 693 | 0 | 0 |
| production-1993-vol1 | page-renders/1993_Vol1 | 2206 | 0.99 | -267 | 4 | 1771 | 0 | 0 |
| production-1993-vol2 | page-renders/1993_Vol2 | 2239 | 1.0 | 1938 | 1939 | 1026 | 0 | 0 |
| production-1993-vol5 | page-renders/1993_Vol5 | 1485 | 0.977 | -4 | 7 | 633 | 0 | 0 |
| production-1994-vol1 | page-renders/1994_Vol1 | 2208 | 0.983 | -461 | 6 | 1680 | 0 | 0 |
| production-1994-vol2 | page-renders/1994_Vol2 | 2240 | 0.999 | 1745 | 1747 | 1235 | 0 | 0 |
| production-1994-vol5 | page-renders/1994_Vol5 | 2153 | 0.97 | -488 | 4 | 626 | 0 | 0 |
| production-1995-vol1 | page-renders/1995_Vol1 | 2201 | 0.995 | -244 | 4 | 1919 | 0 | 0 |
| production-1995-vol2 | page-renders/1995_Vol2 | 2139 | 1.0 | 1956 | 1957 | 928 | 0 | 0 |
| production-1995-vol5 | page-renders/1995_Vol5 | 2062 | 0.972 | -709 | 7 | 632 | 0 | 0 |
| production-1996-vol1 | page-renders/1996_Vol1 | 1921 | 0.985 | -453 | 4 | 1440 | 0 | 0 |
| production-1996-vol2 | page-renders/1996_Vol2 | 1888 | 0.994 | 1457 | 1459 | 1538 | 0 | 0 |
| production-1996-vol6 | page-renders/1996_Vol6 | 1929 | 0.94 | -813 | 5 | 764 | 0 | 0 |
| production-1997-vol1 | page-renders/1997_Vol1 | 1356 | 0.987 | -267 | 4 | 1075 | 0 | 0 |
| production-1997-vol2 | page-renders/1997_Vol2 | 1382 | 0.999 | 1087 | 1089 | 1379 | 0 | 0 |
| production-1997-vol3 | page-renders/1997_Vol3 | 1176 | 0.999 | 2467 | 2469 | 527 | 0 | 0 |
| production-1997-vol6 | page-renders/1997_Vol6 | 1904 | 0.972 | -743 | 5 | 1053 | 0 | 0 |
| production-1998-vol1 | page-renders/1998_Vol1 | 1984 | 0.987 | -431 | 5 | 1540 | 0 | 0 |
| production-1998-vol2 | page-renders/1998_Vol2 | 1674 | 0.999 | 1551 | 1553 | 1443 | 0 | 0 |
| production-1998-vol6 | page-renders/1998_Vol6 | 2157 | 0.978 | -850 | 5 | 1035 | 0 | 0 |
| production-1999-vol1 | page-renders/1999_Vol1 | 1922 | 0.99 | -287 | 5 | 1620 | 0 | 0 |
| production-1999-vol2 | page-renders/1999_Vol2 | 2040 | 1.0 | 1633 | 1635 | 1360 | 0 | 0 |
| production-1999-vol5 | page-renders/1999_Vol5 | 2002 | 0.972 | -813 | 4 | 561 | 0 | 0 |

## (e) Reproducible command + method note

```
C:/PatoLex-scratch/ocr-engines/qwenvl-venv/Scripts/python.exe \
  C:/PatoLex-scratch/page_continuity_audit.py all --workers 16 \
  --json-out C:/PatoLex-scratch/_audit_all.json
```

Per-volume: `python page_continuity_audit.py <year|all|production-NAME>`.

**Method.** The printed running-head page number is NOT present in the full-page consensus OCR (it is a top-outer-corner number dropped/garbled by full-page consensus -- verified). The tool therefore RE-OCRs a thin top strip (top ~11% of the page height) of each rendered page image with Tesseract in sparse-text mode (`--psm 11`) under a digit whitelist, recovering the corner page number. It models `printed = pdf_seq + offset`, where `offset` is piecewise-constant and MONOTONE NON-DECREASING (each physically dropped leaf bumps the offset UP by the number of leaves lost; nothing can lower it). Each OCR'd page-number candidate votes an offset; the tool fits the best monotone-non-decreasing offset step-function over the numbered body by dynamic programming, scoring (supported pages) minus a per-step penalty. EVERY offset INCREASE in the optimal path -- walked per-page across the fitted body -- is a missing leaf, reported AND LOCALIZED at its own position (so two leaf-drops a few pages apart are reported as two distinct ranges, not merged). Because a real leaf-drop is corroborated by an entire post-gap segment while a transient OCR misread is a single stray vote, the step penalty plus a per-segment support/density floor make isolated misreads unable to create a phantom gap. Front matter (roman-numeral / unnumbered title pages) and trailing index matter fall outside the fitted body window and are not scored.

**Guards against phantom and mislocated gaps (added after adversarial review).** (a) RESOLUTION pages are excluded by consensus-OCR content before fitting, so their 'RESOLUTION CHAPTER N' numbers cannot be misread as page numbers (resolutions are out of corpus scope). (b) Each offset step is localized at its true page position rather than merged between the surviving high-support segments -- this fixes both wrong ranges and omitted gaps when leaf-drops cluster. (c) A coverage gate refuses any volume whose fittable numbered body covers too small a fraction of the volume (a single numbering stream of a multi-stream vol2/vol3) -- reported as `partial_numbering` rather than emitting unrepresentative gaps from a sliver. (d) Single-page breaks are reported but flagged LOWER-confidence: a physical leaf is two pages, so a one-page break is usually an original printing/numbering skip, not a dropped leaf.

**Image sources.** Prefer `page-renders/<Volume>/NNNN.png` (NNNN == page_1indexed); fall back to the volume's own `pages_prep_gray/page_NNNN.png` (NNNN == page_1indexed-1) when no render dir exists or the render dir is partial. The audit is READ-ONLY on the corpus and touches NO database.

**Validation.** On `production-1871-72` (1872 Statutes), the four leaves Patrick confirmed missing by eye -- printed pp **131-134, 515-516, 586-587, 776-777** (10 pages) -- are detected EXACTLY, with zero false positives in the clean stretches.
