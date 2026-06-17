# Early-Era Oracle Discrepancy Table (printed-index re-derivation) — 2026-06-17 (cc013)

**READ-ONLY analysis. The oracle (`ca_chapter_counts.tsv`) is NOT modified. Oracle changes are Patrick's decision.**

Each pre-1903 volume's chapter count was re-derived from its **own printed index** (the authoritative
internal source) and compared to the oracle. Two methods combined:
1. `rederive_index_counts.py` — parses the printed index from `consensus_text`.
2. **Engine-union recall fix (cc013)** — the early italic typeface garbles Tesseract, and the token-majority
   `consensus` inherits the garble and drops index lines. Unioning the four OCR engine fields
   (`consensus`/`tess`/`doctr`/`surya` — Surya reads lines the others drop) lifts index coverage from
   ~0.55–0.70 to ~0.81–0.99, recovering many volumes that were previously NO_INDEX. *(This recall fix is
   to be folded into the canonical tool under a Hans ×2 gate — deferred during the 2026-06-17 classifier
   outage; numbers here are from the analysis pass `_early_union_rederivation.tsv`.)*

Verdicts use union coverage ≥0.75 as the trust gate and ±2 as the MATCH band (OCR can clip the last row).

---

## TIER 1 — CONFIRMED oracle UNDERCOUNTS (recommend correcting the oracle) ✅ read-verified

Printed index shows **far more** chapters than the oracle; verified by reading the actual `An Act` index
lines (continuous real-act run past the oracle N). Same signature across all four. **The clerk web index
that seeded the oracle undercounts these sessions.**

| volume | oracle N | printed-index N | Δ | union cov | evidence |
|---|---|---|---|---|---|
| **1865-66** | 280 | **~650** | **+370** | 0.92 | continuous real acts ch 1→650; floor already holds 463 distinct |
| **1887** | 51 | **~188** | **+137** | 0.89 | acts continue past 51 (ch53 "Branch State Normal School") to 188 |
| **1883-84-regular** | 23 | **~96** | **+73** | 0.99 | acts continue past 23 to 96 |
| **1863** | 476 | **~538** | **+62** | 0.89 | acts continue 475→538 |

**Net denominator impact if approved: ~+642 chapters** (all early era). NOTE: 1865-66 was previously
mis-filed as a "parser artifact" (now disproven — see `CORPUS_COMPLETENESS_STATE.md` §3h).

---

## TIER 2 — Marginal / within OCR noise (no action; treat as MATCH)

| volume | oracle N | index N | Δ | note |
|---|---|---|---|---|
| 1873-74 | 679 | 688 | +9 | union cov 0.81; minor, could be OCR over-read or a tiny real undercount — low priority |
| 1858 | 358 | 360 | +2 | within ±2 band |
| 1891 | 280 | 282 | +2 | within ±2 (modal_year=1872 was an old-code-citation red herring) |

---

## TIER 3 — Session-mapping artifacts (NOT undercounts; resolve to MATCH)

My quick diagnostic keyed the oracle on the leading year only; the canonical tool's `refine_oracle_match`
maps these to the correct session row, where they MATCH. **No oracle change.**

| volume | naive oracle | correct row | index N | resolution |
|---|---|---|---|---|
| 1900-01 | 15 | 1901 Regular = 275 | 275 | MATCH under correct mapping |
| 1881 | 77 | 1881 Extra = 103 | 103 | MATCH under correct mapping |

---

## TIER 4 — Possible oracle OVER-counts (review — index reads FEWER than oracle)

Index runs cleanly but stops **below** the oracle N. Either the oracle is too high or the index truncated.
Flag for your review; **do not act without a page check.**

| volume | oracle N | index N | Δ | union cov | note |
|---|---|---|---|---|---|
| 1860 | 455 | 385 | −70 | 0.82 | `CORPUS_COMPLETENESS_STATE.md` already notes ~374 historical → oracle may be inflated |
| 1856 | 152 | 99 | −53 | 0.91 | index complete to 99; oracle high OR index truncated early |
| 1871-72 | 637 | 412 | −225 | 0.81 | likely an index TRUNCATION (run cut at 412), not oracle-high — re-check |
| 1880-code | 126 | 121 | −5 | 0.94 | OCR clipped last few; not actionable |

---

## TIER 5 — Newly VALIDATED by the engine-union fix (oracle CONFIRMED) ✅

These were previously NO_INDEX (under-read on `consensus` alone). The engine-union recovered the index and
it **matches the oracle** — confirming the denominator for these sessions.

`1855=231, 1857=277, 1862≈455, 1869-70≈583, 1875-76≈613, 1877-78=673` — plus the already-confirmed controls
`1859, 1863-64, 1867-68, 1880, 1885-86, 1889, 1895, 1897, 1899, 1903`.

---

## TIER 6 — Still unresolved (NO_INDEX / under-read even with engine-union)

| volume(s) | oracle N | status | likely cause / next step |
|---|---|---|---|
| 1850, 1851, 1852, 1853, 1854 | 146–231 | no index entries found | different early index layout — regex/format work or targeted re-OCR |
| 1861 | 538 | union cov 0.45 | catastrophic index-page OCR — candidate for re-OCR |
| 1873-74-code, 1875-76-code, 1877-78-code | — | cov 0.17–0.31 | CODE-amendment volumes (different structure); low priority |
| 1883-84 (non-regular) | 23 | cov 0.38 | the amendments sibling of 1883-84-regular |
| 1893 | 244 | union cov 0.73 | borderline (just under gate; index N 242 ≈ oracle 244 — likely MATCH with a small nudge) |

---

## DECISION REQUESTED

1. **Approve the TIER 1 oracle corrections** (1865-66→~650, 1887→~188, 1883-84→~96, 1863→~538)? These are
   read-verified. On approval I will produce the exact corrected `ca_chapter_counts.tsv` rows for your sign-off
   (I will NOT edit the oracle without it).
2. **TIER 4 over-counts** (1860/1856/1871-72): want a page-level check before any decision?
3. **TIER 6**: defer (separate re-OCR / format work) — confirm.

*Generated by cc013. Method + per-volume data: `_early_union_rederivation.tsv` (5090 scratch). The engine-union
recall fix is pending a Hans-gated merge into `rederive_index_counts.py`.*
