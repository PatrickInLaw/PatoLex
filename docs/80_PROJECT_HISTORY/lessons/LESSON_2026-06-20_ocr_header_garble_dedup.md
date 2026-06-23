# LESSON 2026-06-20 — OCR `CHAPTER`-header garble is the shared root cause of "missing" chapters AND phantom-duplicate chapters

**Context:** Closing the 1900–1999 OCR-era parse-recall gap. After best-of-merging the parse passes (`merge_passes.py`), the union was inflated by OCR digit-garble **same-act duplicates** — one physical act parsed under two chapter numbers (e.g. 1915 ch203 ≡ ch208). Building a reliable collapse exposed a deeper truth.

## The finding

**The page's own `CHAPTER N` header is ground truth** for which chapter physically occupies a page (`ocr_consensus/page_ocr_results.json` → `consensus_text` per `page_1indexed`). But that header is itself frequently OCR-garbled, and that single fact explains BOTH failure modes we had been chasing separately:

1. **"Missing" chapters** — the parser never emitted the chapter because its `CHAPTER N` header didn't OCR cleanly. Examples (1915): page 11 reads **"UHAPTER 9"** (C→U); page 462 reads **"CHAPTER 2338"** (a spurious doubled digit for 238). The chapter body is present; only the header token is corrupt, so the header-driven parser skipped it.
2. **Phantom-duplicate chapters** — a low-recall pass grabbed a stray/garbled number and emitted a **bodyless stub** under a wrong chapter number on a page that really belongs to a different (correctly-headed) chapter (e.g. ch203 stub on page 448, whose real header is `CHAPTER 208`).

They are the same phenomenon viewed from two sides. Treating them with number/regex heuristics is what produced the project's recurring "suggest re-OCR, then don't need it" and "force-fit to a target count" errors.

## What works (the safe dedup)

- **Fuzzy-anchor on the word CHAPTER (≤2 edit distance)**, not exact match, so "UHAPTER"/"CIIAPTER" still anchor a real chapter and protect it from deletion. Clean the digits (`O→0`, `I/l→1`) and cap header numbers at the oracle N (a 4-digit "header" is noise).
- **Collapse a same-page pair ONLY on strong, body-level evidence:** near-identical **bodies** (Jaccard ≥0.6) = same physical act; OR a **bodyless STUB** (<15 body tokens) whose **title** matches a real-bodied sibling (the stub is the garble label). **Never** collapse two acts that BOTH carry a substantial unique body merely because their titles are similar — 19th/20th-c. appropriation acts share boilerplate titles ("An act to appropriate money for…") and a pure title-similarity rule deletes real chapters (it killed real ch6 San Quentin in testing).
- **A header-anchored act is never dropped.** Weak signals (0.3–0.6 similarity, or two anchored similars) are **flagged for human/Hans review, not auto-deleted.**

## Rule of thumb (carries the user's standard)

The data is present until proven absent **on the actual page**. A chapter number that looks "missing" or "duplicated" in the parse is, far more often than not, an OCR-garbled `CHAPTER` header — recover/keep it; do not assert absence or re-OCR from a regex. Every automated collapse must be logged with its page + evidence so an auditor can re-check it against the scanned page.

## Page-image lookup: the `source_page` ↔ filename off-by-one (verified twice)

When a visual-recovery pass locates a chapter and you need to open the scanned page to confirm a garbled header, watch the indexing. In `ocr_consensus/page_ocr_results.json`:

- The **dict key `K`** (the string the entries are keyed by) maps directly to the page-image basename: **`pages_raw/page_{K:04d}.png`** (same basename in `pages_prep_gray/`). The entry's own `img_path` field confirms this — key `"193"` carries `…/page_0193.png`.
- The entry's **`page_1indexed` field is `K + 1`** (e.g. key `"193"` → `page_1indexed: 194`). It is NOT the image index.

So if your manifest/recovery uses the **dict key** as `source_page` (the 1907 and 1979 passes both did), the correct image is **`page_{source_page:04d}.png`** — **not** `page_{source_page-1:04d}.png`. Both candidate files exist on disk, so a wrong `-1` does not error; it silently points one printed page too early. Verified empirically for 1907: `page_0193.png` is printed page 142 = `CHAPTER 94`, while `page_0192.png` is printed page 141 (the ch92/93 sewage act). Two independent visual-recovery agents (1979, then 1907) hit this same off-by-one — always confirm the mapping by reading one known page before trusting a batch of `img_path`s.

## Where it lives

- Implementation: `pipeline/ingest/merge_passes.py` (`fuzzy_headers`, `_editle2`, `_has_own_garbled_header`, `dedup_header`, `merge_dir`). Collapses logged in each volume's `parsed_acts_merged.json` → `_merge_meta.collapsed_pairs` / `flagged_for_review`.
- Result (post Hans round 1): 1900–1999 completeness over the 66 exact-year-mapped sessions (denominator **83,550**): **all-distinct 79,547/83,550 = 95.2%**, **content-complete (≥15 body tok) 76,255/83,550 = 91.3%** (honest floor). 302 same-act dups collapsed, 1133 pairs flagged across 178 volumes; 10 biennium/even-year sessions (1,831 ch = 2.1%) not yet dir-mapped, stated not counted. Worst residuals (1915 62%, 1941 77%) are genuine header-dropout recall gaps, not denominator errors.

## Hans-hardened details (round 1 fixes)

- **False-anchor suppression is required.** A naive `CHAPTER\s+\d+` match false-anchors on **body cross-references** ("chapter 877 **of** the statutes of 1921" — 10,058 in the corpus) and **roman code-chapter headings** ("CHAPTER II." → ch11 — 141 in the corpus). `fuzzy_headers` rejects a token followed by " of " and rejects all-letter (roman) tokens. Direction of a false anchor is *safe* (it over-protects → under-collapses, never wrong-drops), but left unfixed it lets phantoms survive.
- **The near-phantom-stub collapse needs a garbled-header guard.** Dropping every unanchored bodyless stub that shares a page with an anchored sibling would kill real chapters whose *own* header digit-garbled (e.g. ch238, header "CHAPTER 2338"). `_has_own_garbled_header` keeps a stub if the page carries a header equal to its number or its number plus one inserted/doubled digit. Residual gap: substitution garbles (S→5, B→8) in a header are not matched — those stubs are flagged `unanchored-stub-review`, not dropped.
- **Report completeness reproducibly.** State the exact denominator (sum of oracle N over the *mapped* sessions), a content-complete floor (chapters with ≥15 body tokens, so bodyless stubs don't inflate it), and the unmapped weight — never a single bare % over a silently-pruned session set.
- **A near-phantom stub is a garble of a chapter NUMBER, not of a page neighbor's content.** When it collapses, attribute it to the anchored sibling whose *title* best matches (its true content parent may be a different chapter on the same page, e.g. 1943 ch958 belongs to ch908, not the page-adjacent ch959). Picking `anchored_sibs[0]` gives misleading forensic metadata.
- **Known residual limitation (Hans round 2, MINOR, accepted):** the near-phantom-stub collapse gates on page co-presence + `ntitle≤3` + no-own-header, NOT a Jaccard content-overlap check (unlike the body/title-stub branches). A real act with a genuinely truncated body AND a ≤3-token title sharing a page with an anchored chapter could in theory over-collapse; not observed in any of the 34 corpus cases. The `ntitle≤3` gate is the safeguard. Also: substitution garbles in a header (S→5, B→8) are NOT recognized by `_has_own_garbled_header` (only exact + one-extra-digit) — such stubs are flagged `unanchored-stub-review`, not dropped.
