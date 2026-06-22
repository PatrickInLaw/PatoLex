# LESSON 2026-06-22 — residual-manifest cross-volume anchor collapse (dual-series page-range corruption in header-OCR recovery)

## Summary

When a session-year is split across **two physical volumes that share the same
chapter-number range** (a main Statutes volume + a separately-paginated Code/Amendments
volume), `pipeline/analysis/_residual_manifest.py` **collapses both volumes into one
chapter -> source_page map** (`pages.setdefault(c, p)` across all dirs). For any missing
chapter whose nearest present neighbors come **one from each volume**, the emitted
`page_range` is **garbage** — it brackets a page in volume A with a page in volume B, which
have unrelated numbering and may even live in different PDFs. The 1874-style **dual-WINDOW
mis-anchor guard does NOT fix this**: it would faithfully scan the wrong volume's page
region (often in a PDF that doesn't even contain the target).

Discovered on **1876** (`production-1875-76` main + `production-1875-76-code`): 17 of 138
missing items had spans up to **820 pages** (e.g. ch467 lo_pg=751 from the main vol,
hi_pg=39 from the code vol).

## Why it happens

- The two volumes are real, distinct printings with **independent page numbering** but an
  **overlapping chapter-number range** (here both number within 1..613).
  - `production-1875-76` (main Statutes): maps into `1875-76_Statutes.pdf`,
    `source_page == PDF page` (offset 0, verified), pages ~65..978.
  - `production-1875-76-code` (Code Amendments): a **separate, smaller PDF**, own page
    numbering 13..129, 69 acts; **15 chapter numbers overlap** the main volume.
- `_residual_manifest.py` merges every `production-{year}*` dir (plus aliases) into one map
  and brackets each missing chapter by global nearest-present neighbors — blind to which
  physical volume / PDF a page belongs to.

## The fix (used in `_apply_1876.py`)

**Do not trust the residual manifest's `page_range` for anchoring when a code/amendments
sibling exists.** Instead, re-derive anchors from the **MAIN volume's present chapters
ONLY**, dropping the chapters that also appear in the code volume (ambiguous page), then
scan the **bounded sequential window (cap ~40 pp) between the nearest present main-volume
neighbors** of each missing chapter. Printing is sequential, so the true location is just
past the low neighbor.

Result on 1876: 820-pp bogus spans became tight **8–15 pp** windows; the formerly
mis-anchored cluster members were correctly recovered (419@646, 468/469@752, 496@824,
512@848, 519@859) while their genuine misses (417,418,452,467,497,498,518,522) stayed
residual. **CONFIRM-ONLY** held throughout (write only when the EXACT oracle number reads
as a clean in-range header; in-script post-check re-reads the found page; **0 spurious
entries** this run). Residual 138 -> 59 (79 recovered). No DB / merged / certified writes;
additive superset to `production-1875-76/parsed_acts_visual.json`.

## Generalizable directives

1. **Detect the split first.** Before a header-OCR recovery pass on any biennial early-era
   year, check for a `*-code` (or otherwise separately-paginated) sibling dir. The
   `YEAR_DIR_ALIAS` table in `_residual_manifest.py` already lists the known ones
   (1874/1876/1878 have `-code` siblings).
2. **Anchor within a single physical volume / single PDF.** Never bracket a missing
   chapter using a page from a different volume. Re-derive anchors per-volume; drop
   overlap chapters whose page is ambiguous between series.
3. The dual-window mis-anchor guard (from `_apply_1874.py`) handles *intra-volume*
   mis-paging; it is **not** sufficient for *cross-volume* collapse. Use main-volume-only
   anchoring (this lesson) on top of it.
4. **Possible upstream improvement (not yet done):** `_residual_manifest.py` could tag each
   present chapter with its source `vol` (it already tracks `vol`) and refuse to build a
   `page_range` spanning two different volumes — emitting per-volume candidate ranges
   instead. Until then, the apply script must re-derive anchors itself.

## Relation to the 1854/dual-series lesson

`LESSON_2026-06-21_1854_dualseries_merge_corruption.md` covers a *content* failure (per-series
roman headers read as oracle numbers -> wrong act). This lesson covers a *tooling* failure in
the recovery harness (cross-volume page-range collapse -> wrong page region scanned). Both
stem from the same structural fact — **multiple locally-numbered series in one session-year**
— and both are resolved by anchoring to a single, correctly-identified series/volume.
