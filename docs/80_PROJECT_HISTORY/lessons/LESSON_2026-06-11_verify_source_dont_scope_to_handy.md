# LESSON 2026-06-11 — Verify the source file; don't narrow scope to what's handy

## What happened
While finishing the chapter-number REVIEW cases, I needed the source scan for
`production-1883-84-regular` chapter o42. My render step's `resolve_pdf()` chose the volume's
PDF by **filename keyword** (preferring `*_Statutes.pdf`). For 1883-84 that grabbed
`1883-84_Statutes.pdf` — a **15-page** file — and rendering page 329 failed. I then declared
the case **"blocked — source file missing / archive is a stub"** after checking only that one
folder on the one machine I was on.

That conclusion was wrong on two counts:
1. **The OCR bundle proved a complete source existed.** `production-1883-84-regular` has 80
   acts with `source_page` up to 428 and a `page_classification` body max of **448**. A
   15-page file cannot have produced that. I had the evidence in hand and didn't check it.
2. **The full volume was right there, under a different name.** `1883-84_Code.pdf` is **448
   pages** — an exact match to the bundle. The 1883-84 regular-session statutes were OCR'd
   from the file *named* "Code". Nothing was missing; my resolver picked the wrong file.

o42 = **CHAPTER LIV (54)**, read cleanly from `1883-84_Code.pdf` p329 once the right file was
used. Final chapter REVIEW result: **215/215**.

## Root causes
- **Inferring a file from a convenient name instead of verifying it against the artifact that
  references it.** The authoritative signal is the bundle's own `page_classification` /
  max `source_page`, not the filename.
- **Narrowing scope to the machine/folder I was already in.** Patrick's framing: "files
  scattered across two computers and you insisting on narrowing your scope to just what is
  handy for you to grab." Declaring something "missing" is a corpus-wide claim and requires a
  corpus-wide check (both boxes + all candidate names), not a single-folder glance.

## Fixes / rules
- **Map a `production-*` bundle to its source PDF by page-count match**: choose the candidate
  whose `page_count` ≥ the bundle's max `source_page` (ideally == its `page_classification`
  body count). Never by filename keyword alone. (`verify_mapping.py` does this check; it
  confirmed 1883-84 was the ONLY mismapped volume of the 16.)
- **Before declaring any file "missing":** search BOTH machines and ALL plausible names, and
  reconcile against what downstream artifacts prove must exist. A "missing" call is a last
  resort backed by an exhaustive sweep, not a first impression.
- **The 1883-84 regular-session statutes live in `1883-84_Code.pdf` (448pp)**; the
  `1883-84_Statutes.pdf`/`_1E.pdf` (15pp each) belong to the tiny `production-1883-84` bundle.

## Cross-refs
`docs/30_SYSTEM_DESIGN/CORRECTION_AND_DISPLAY_LAYER.md` ("Chapter REVIEW closeout"),
`ocr-bundles-image-free-source-in-archive` memory.
