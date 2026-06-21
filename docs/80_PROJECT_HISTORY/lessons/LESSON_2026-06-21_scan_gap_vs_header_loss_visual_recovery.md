# LESSON 2026-06-21 — A missing chapter can be a PHYSICAL SCAN GAP, not a header/OCR miss; only the running-head PAGE NUMBER tells them apart

**Context (1970 visual-recovery campaign):** Year 1970 had 6 residual-missing chapters
(707, 733, 906, 907, 1013 in vol1; 1139 in vol2). Visual verification against the scanned
page images recovered 4 cleanly. The remaining two (906, 907) turned out to be a failure
mode the existing recovery tooling does **not** model and would have mis-diagnosed.

## The four "ordinary" misses (all image-verified, recovered)

These matched the known mid-century modes (see
`LESSON_2026-06-14_chapter_recovery_header_loss_and_renumber.md`):

- **707** (H&S Code §7117, burials) and **1139** (Gov. Code §69893.5, superior courts) —
  page-top header-loss: body text present, `CHAPTER NNN` line lost to the page break.
- **733** (Veh. Code §13353, chemical tests) — header-loss on a multi-page act.
- **1013** (Ed. Code §14101, STRS, urgency) — **OCR consensus error, not header loss.**
  docTR and Surya both read "CHAPTER 1013" correctly; Tesseract misread "1015"; the
  majority-vote consensus wrongly sided with Tesseract, so the parser never saw 1013 and
  a phantom duplicate 1015 was produced. **Mining all 4 engines individually (not just
  `consensus_text`) surfaces these — the 2-engine majority was right.** OCR `high_confidence`
  was false (agreement ~0.57) on that page, a useful flag for "go look at the image."

## The new failure mode: a physically un-scanned printed leaf

Chapters 906 and 907 are **genuinely absent from the corpus** — not lost headers, not OCR
errors. The original printed **leaf for page 1648 was never scanned**.

How it presents, and how to confirm it (this is the durable rule):

- The `pages_raw` image **filenames are perfectly contiguous** (`page_1640.png` …
  `page_1659.png`, no gap). So a missing leaf is **invisible** at the filename/file-count
  level. Do not trust contiguous filenames as proof of complete pages.
- The tell is in the **running-head printed page number**, which you can only read from the
  IMAGE (OCR routinely garbles/drops it): `page_1646.png` shows printed **1647** (end of
  Ch. 905) and the very next file `page_1647.png` shows printed **1649** (Ch. 908). Printed
  **1648 is skipped** — and that leaf is exactly where the short Chapters 906 and 907 (and
  the start of the Ch. 908 Gov. Code §6103 act) were printed. The §6103 body tail appears
  orphaned at the top of `page_1647.png` above the CHAPTER 908 heading, with no heading of
  its own — the giveaway of a dropped preceding leaf.
- An OCR-text-only analysis **mis-diagnosed this as "lostheader"** because it only inspected
  body text and never compared the running-head page numbers across consecutive images. The
  text-only signal is identical to header-loss; **only the printed page-number jump
  distinguishes a scan gap from a header miss.**

## Image-to-source mapping (1970 production volumes)

Image file is `page_{source_page-1:04d}.png`, indexed by **SOURCE (PDF) page**, NOT the
printed page number. The printed-vs-source drift grows through a volume (e.g. printed 1820
at source 1819 in vol1; vol2 restarts its own source index while printed numbers continue
~2022). Use `source_page` (= file index + 1) for the record; treat the printed number as a
verification witness only.

## Durable rules

1. **Distinguish three causes before labeling a residual-missing chapter:** (a) header-loss
   / OCR-miss (body present → recover), (b) OCR consensus/engine error (mine all 4 engines,
   not just consensus → recover), (c) **physical scan gap (printed leaf never digitized →
   NOT recoverable from current images; needs re-scan).** Only (a) and (b) are fixable in
   software.
2. **Contiguous image filenames do NOT prove all printed pages are present.** Verify the
   running-head printed page numbers are sequential across consecutive images when a chapter
   is unexpectedly absent and its neighbors are intact.
3. **A scan gap is NOT a legislative gap.** 906/907 are real enacted chapters; they are
   recorded `status="not_found_needs_reocr"`, `printed_number_confirmed=false`, with a note
   that printed leaf 1648 must be re-sourced/re-scanned (or titles pulled from a 1970
   legislative index). Do not mark them `legislative_gap`.
4. **Visual output is additive:** per-volume `parsed_acts_visual.json` with
   `recovered_acts[]` + `_visual_meta`; never overwrites parsed/certified artifacts or the DB.

## Result for 1970

6 residual-missing → **4 image_verified** (707, 733, 1013, 1139), **0 legislative_gap**,
**2 not_found scan-gap** (906, 907 on un-scanned printed leaf 1648). Outputs:
`C:\PatoLex-scratch\production-1970-vol1-chapters\parsed_acts_visual.json` and
`...\production-1970-vol2-chapters\parsed_acts_visual.json`.
