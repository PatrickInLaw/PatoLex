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

## TIER 1 — CONFIRMED oracle UNDERCOUNTS

**✅ APPLIED to the oracle 2026-06-17 (Patrick-approved):** 3 of 4 rows. Oracle total 119,157 → **119,737 (+580).**
Verified by reading the actual `An Act` index lines (continuous real-act run past the old oracle N).

| volume | old oracle N | **new oracle N** | Δ | union cov | status |
|---|---|---|---|---|---|
| **1865-66** (`1866 regular`) | 280 | **650** | +370 | 0.92 | ✅ APPLIED — real acts ch 1→650; floor holds 463 distinct |
| **1887** (`1887 regular`) | 51 | **188** | +137 | 0.89 | ✅ APPLIED — acts continue past 51 (ch53 "Branch State Normal School") to 188 |
| **1883** (`1883 regular`) | 23 | **96** | +73 | 0.99 | ✅ APPLIED — acts continue past 23 to 96 (resolves the handoff "amendments?" caution by reading) |

**⏸ HELD — 1863 is NOT a clean undercount (session-identity issue).** The oracle has a *single* row
`1863-64 Regular Session = 476` (15th session). Two production volumes exist: `production-1863-64`
(index→475 ≈ 476, MATCHes the row) and `production-1863` (index→538, no ordinal). So 538 is **either the
14th session (1863) that the oracle is MISSING, or a second scan** — NOT a wrong value in the 476 row.
Editing 476→538 would corrupt the 15th session's correct count. **Needs session disambiguation (read both
title pages) before any edit.** Not applied.

> Audit note: the `source_url` for the 3 edited rows still points to the clerk archive (which undercounts).
> Values were overridden from the printed-volume index; the clerk URLs are retained as the original (now
> superseded) source. Consider updating those URLs/confidence in a follow-up.

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

## TIER 4 — Possible oracle OVER-counts (checked 2026-06-17 — index reads FEWER than oracle)

Checked via index end-marker + independent body cross-check. Result: only **1860** is a plausible
over-count; the other two are index under-reads where the oracle is probably right. **None auto-applied.**

| volume | oracle N | index N | check result | recommendation |
|---|---|---|---|---|
| **1860** | 455 | 385 | index ran 1→385 then hit a resolutions marker; all 4 engines find nothing above 385; `~374 historical` noted in state doc | **LIKELY OVER-COUNT (~385).** A downward edit is sensitive — do a quick visual page read of the index tail before I change it. |
| 1856 | 152 | 99 | body cross-check hints ch ~150; index just truncated at 99 | **NO ACTION** — oracle ~152 probably right (index under-read) |
| 1871-72 | 637 | 412 | huge gap; index OCR cut at 412 | **NO ACTION** — index under-read, oracle 637 likely right |
| 1880-code | 126 | 121 | −5, OCR clipped last few | NO ACTION |

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

## STATUS (2026-06-17)

1. **TIER 1 — DONE (3 of 4 applied, Patrick-approved).** 1865-66→650, 1887→188, 1883→96 written to the
   oracle (+580; new total 119,737). **1863 HELD** — session-identity issue (14th-vs-15th / possible missing
   row); needs title-page disambiguation before any edit.
2. **TIER 4 — checked.** Only **1860** is a plausible over-count (~385); recommend a visual page read before a
   downward edit. 1856 / 1871-72 are index under-reads (oracle likely right) — no action.
3. **TIER 6 — DEFERRED** (Patrick's call): separate pass — 1850-54 (different index format), 1861 (re-OCR),
   `-code` volumes (exclude — not chapter volumes), 1893 (minor nudge).

### Remaining decisions for Patrick
- **1863:** want me to disambiguate the 14th-vs-15th session (read both volumes' title pages/ordinals)?
- **1860:** want the visual page read to confirm the ~385 over-count before editing down?

*Generated by cc013. Method + per-volume data: `_early_union_rederivation.tsv` (5090 scratch). The engine-union
recall fix is pending a Hans-gated merge into `rederive_index_counts.py`.*
