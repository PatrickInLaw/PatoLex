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

## Reinforcement from the 1959 campaign (2026-06-21) — OCR-text-only "gap" calls are NOT trustworthy

1959 had 7 residual-missing chapters (857, 1000, 1001 in vol1-59chapters; 1332, 2123, 2128,
2159 in vol2-chapters). A first pass that relied **only on OCR text** (searching all 4 engines
for `CHAPTER NNN`) concluded **5 legislative gaps + 2 scan gaps, 0 verified**. Image
verification proved that conclusion almost entirely **WRONG**: **6 of the 7 were actually
present** and image-verified; only **1** (ch1001) is a real scan gap.

Every false "gap" had the same root cause flagged in the campaign brief: the page-top
**running head was systematically OCR-garbled/dropped**, so a text search for the heading
found nothing even though the chapter is plainly on the page. Three sub-patterns:

- **Dense multi-chapter pages** (ch857: ch857+858+859 all on one printed page; ch1332, ch2128
  share their page with the next chapter). OCR latched onto one heading and dropped the
  others.
- **Long preceding act** (ch2123 follows the ~13-page Nevada County Water Agency act; ch2159
  follows a long B&P-Code act) — the missing heading sits deep in a run of body pages.
- **Last chapter of a volume** (ch1000 is the final chapter of vol1-59chapters, printed pages
  3021–3022) — easy to mistake for "volume ends at ch999."

Additional correctness traps seen in 1959:
- The residual manifest's neighbor pages came from the **same garbled OCR** and were
  cross-contaminated / out of order (e.g. ch856 and ch858 reported at swapped pages around
  ch857). **Do not trust manifest neighbor pages to bound the search — render and read.**
- A claimed "pattern of legislative gaps 848–896" was a pure OCR artifact; those chapters are
  present on dense multi-chapter pages.

**Hardened rule:** never emit `legislative_gap` (or `not_found`) from OCR text absence alone.
A residual-missing chapter is only a gap after the **page image** at the expected location has
been rendered and read and the heading is confirmed absent AND the printed running-head page
numbers are sequential across the boundary (ruling out a scan gap). In practice, mid-century
"missing" chapters are overwhelmingly **present-but-header-garbled**, not gaps.

### 1959 image-to-source mapping note
1959 volumes use the OCR `page_1indexed` convention (consensus JSON key + 1 = `page_1indexed`,
= PDF page index + 1). The printed page number drifts far from `page_1indexed` (e.g. ch1000 at
`page_1indexed` 2430 is printed page **3021**). Records use `source_page` = `page_1indexed`;
the printed number is a verification witness only. vol1-59chapters has `pages_raw/`;
vol2-chapters does **not** — pages were rendered on demand from
`chief-clerk-archive/1959_Vol2_Chapters.pdf` (PyMuPDF, PDF idx = consensus key) to temp images
under `C:\PatoLex-scratch`.

## Result for 1959

7 residual-missing → **6 image_verified** (857, 1000, 1332, 2123, 2128, 2159),
**0 legislative_gap**, **1 not_found scan-gap** (1001, between vol1-59's last chapter ch1000
and vol2's first chapter ch1002 — no available PDF covers it). Outputs:
`C:\PatoLex-scratch\production-1959-vol1-59chapters\parsed_acts_visual.json` (857, 1000, 1001)
and `...\production-1959-vol2-chapters\parsed_acts_visual.json` (1332, 2123, 2128, 2159).

## Reinforcement from 1861 + 1968 (2026-06-21) — a LONG ACT looks like a gap; OCR CORRUPTS the number

Two more sub-patterns hardened across the early-roman (1861) and modern (1968) rebuilds:

- **Wide page-span = a long act, NOT a gap.** When the bracket between two recovered chapters
  spans 8–10+ pages, the natural (wrong) inference is "the chapters in between were never
  enacted." In every observed case it was a single long multi-code/omnibus act: 1861 ch493
  (CCCCXCIII, the SF Consolidation Act amendments, printed pp544–553), 1968 ch1460 (Human
  Resources Development Act) and ch1473 (Public Records Act, pp1219–1226). The wide span is the
  act's LENGTH; the next chapter number appears correctly right after it. **Never call a
  legislative_gap from a wide span — render the page at the expected position and read.** A
  worker agent made exactly this false-gap call twice on 1861 (ch140, ch493) and it was caught
  only by re-reading the images.
- **OCR corrupts the chapter NUMBER, not just drops the header.** Beyond header-loss, the
  running head's digits get mangled so the act is indexed under the WRONG number and looks
  missing: 1968 ch502→"902", 1963 ch1174→"J174", 1978 ch1432→"1482", 1935 ch329→"328", 1921
  ch796 (OCR "757"→"797"). Corollary for the MERGE: the corrupted number can land as a phantom
  PRESENT chapter (e.g. 1919 ch432 is really ch482; 1986 ch1301 carried ch1300's title) — these
  are invisible to gap-fill (which only fills *missing* slots) and require a separate
  misnumbered-duplicate audit of the merged output.
- **Volume-boundary placement:** chapters can sit at the START of the next volume, not the end
  of the current one (1968 ch918/919/920 are at vol2 source_pages 3/7/10; the manifest's
  volume-spanning page_range [10,1636] is an artifact, not a gap).

## CRASH-SAFETY (orchestration, 2026-06-21, observed on 1861)

A visual agent that writes an INITIAL all-`not_found` visual.json (the full target list seeded
as not_found) and then dies mid-run **clobbers** any prior session's good `image_verified`
entries (1861 regressed 423→383 counted chapters). Rule for agent prompts: **never write an
all-not_found initialization**; only ever write a MERGED SUPERSET of prior-good + newly-verified,
and for large years re-write the full file every ~25 chapters so an interruption preserves
progress. Recovery from a clobber is a full re-run (source images are intact, so no permanent
loss — but the measured count regresses until rebuilt).
