# Corpus Completeness — State of the Corpus & Path to Ingest-Ready
**Snapshot: 2026-06-16.** Consolidates the cc007 completeness investigation. Supersedes scattered claims in the run/session logs; for method detail see `docs/30_SYSTEM_DESIGN/CHAPTER_COMPLETENESS_FINDINGS.md`.

---

## 1. The one-paragraph truth
**The source corpus is COMPLETE and verified — every volume is acquired and on disk, the OCR is page-complete, and the authoritative chapter-count oracle is now trustworthy.** Nothing needs re-acquiring or re-scanning. The corpus is NOT yet ingest-ready, but every remaining gap is a **parse/OCR-extraction problem recoverable from data we already hold** — plus a bounded slice of genuinely OCR-garbled headers. We are validating and refining extraction, not chasing missing material.

## 2. What is VERIFIED solid
- **Source acquisition is complete.** Spot-verified against the CA Chief Clerk archive: 1915–1949 are single-volume sessions (no missing "Vol 2"); multi-volume sessions from 1951 on have every volume. The OCR for sampled sessions runs to the full oracle chapter count (1931 OCR→1220=oracle; 1933→1059=oracle).
- **OCR is page-complete** — 0 missing body pages across all 205 volumes (`verify_volume_completeness.py`).
- **The oracle is authoritative** (`docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv`, 215 sessions 1850–2024). Audited 2026-06-16: 1854 corrected (71→174, dual series); 1852/1853/1865-66 confirmed correct.
- **Infrastructure**: single canonical store on the 5090 + tiered offsite backup on the 3060 (F: SSD warm, D: HDD cold), hash-verified. See `docs/60_OPERATIONS/STORAGE_AND_BACKUP.md`.

## 3. The nature of the "gap" (the key reframe)
The raw ~88.7%-complete figure conflated FOUR different things. Separating them is the main result of this investigation:

| Component | What it is | Fix | Status |
|---|---|---|---|
| **Recoverable extraction** | real acts the parser missed (early italic headers; chaptered redirect-stubs; mis-numbered acts) | better detection / renumber from data we have | passes built; in Hans-fix cycle |
| **Measurement noise** | resolutions (~80/vol) + mid-sentence chapter *references* + non-statute series counted as "missing" or over-counted | exclude (line-head only; statutes-series only) | identified; folds into re-measure |
| **Genuine OCR-garbled headers** | real acts whose `CHAPTER n` header is broken in OCR (e.g. "CHAPTER 12"→"G JAC TET 12") | numeral/header repair vs the page-complete OCR, or targeted re-OCR of the worst pages | **the one big lever not yet built** |
| **Oracle errors** | wrong denominators (1854) | authoritative re-derivation | **DONE** |

## 3a. MEASURED completeness (2026-06-16 re-measure — `corpus-remeasure-2026-06-16.md`)
First trustworthy number after the recovery passes, vs the CORRECTED oracle, biennium-correct (OCR corpus 1850–1999):
- **84.4% confident / 88.7% all-extracted** — ~80,600 of 95,555 chapters. Per era: 1880-99 90%, 1950-79 93%, 1980-99 95%; weakest 1860-79 (36% conf, the italic consensus bug) + 1900-19 (71%).
- **Residual = 14,940 chapters, and 98.7% are GARBLED HEADERS, not missing content — "missing headers, not pages."** The text is present in the OCR; only the `CHAPTER n` token is lost. Split: **~4,138 already-parsed-but-flagged (need CERTIFICATION)** + **~10,603 interior numeral loss (need header/numeral repair)** + ~200 genuinely uncertain + ~0 over-extraction noise.
- **=> literal 100% is achievable entirely from data on disk** (certify 4,138 + repair 10,603 garbled headers); no re-OCR of pages, no re-acquisition.
- Two tool findings: (1) `chapter_vs_oracle.py` biennium-bucketing BUG mis-files 1900-01/1906-07/1907-09/1910-11 (the odd-year session) — fix placed ~2,300 chapters; (2) `early_v2` certifies 0 (all flagged) — its acts need certification, so use best-of(recovered, early_v2) on the confident count, not early_v2 alone. (3) scope: production-* = 1850–1999; 2000–2024 = separate leginfo path (84.4% is the OCR figure; 67.7% vs the full 1850–2024 oracle).

## 4. State by era
- **Modern (1991→present):** from California's structured leginfo data; authoritative; in the Postgres DB. Effectively complete.
- **Chaptered OCR (1880–1999):** source complete; OCR holds the full chapter range. Gap = redirect-stubs (recovered, flagged — text lives in the companion Codes volume) + misnumbering (renumber-repairable) + garbled headers (residual) + noise (resolutions/body-refs, excludable). Upright-Roman headers read fine; the misses are gate/parse failures, not OCR loss, except the garbled-header slice.
- **Early OCR (1850–1879):** source complete. Two issues: (a) the 1861–1865-66 italic typeface — Tesseract misreads "CHAP." and the token-majority consensus picked its garble over correct Surya/DocTR (recoverable from the Surya field; bounded gain); (b) our early parse **OVER-extracts** — it counts resolutions, special-acts, and garbled/cross-volume-bleed numerals as statute chapters (a precision problem to tighten). Plus the same garbled-header residual.
- **DB today** (`localhost:5432/patolex`): 35,332 enactments = 1849–1876 OCR (early, ~half-complete & noisy) + 1991→present (authoritative). **The 1877–1990 middle era is parsed-and-staged but NOT ingested.**

## 5. Recovery work built this campaign
| Pass | File | Result | State |
|---|---|---|---|
| Chaptered renumber | `renumber_repair.py` | +257 safe position renumbers (+0.3 pts); self-Hans'd | done (small top-up) |
| Early consensus (Surya headers) | `recover_early_consensus.py` | +~180–220 acts on italic volumes (bounded) | **GO (re-Hans cleared 2026-06-16; precision-first)** |
| Chaptered detection | `recover_chaptered.py` | 1933 70→82%; redirect-stubs flagged; noise excluded | **GO (re-Hans cleared 2026-06-16; 0 dups across combined set)** |
| Garbled-header / numeral repair | — | the residual lever | **not yet built** |
| Early-era over-extraction tightening | — | exclude resolutions/special-acts/bleed | **not yet built** |

## 6. Process lessons (hard-won this session — adopted as rules)
1. **Verify "missing data" against the SOURCE extent + the OCR content before reporting it.** Four "missing"/"acquisition-gap" alarms this session ALL dissolved into recoverable-from-data-we-have. Never infer "missing" from a folder listing or a leading-digit label.
2. **Validate OCR findings against the IMAGES,** not text-census heuristics (the early-era "OCR loss" was a consensus bug invisible to text census).
3. **Token-majority consensus can let one garbling engine override correct ones** for a given typeface — consider per-typeface/per-engine weighting.
4. **Commit the baseline before editing; orchestrate + Hans-review every pass** — every first-build recovery pass had a precision defect Hans caught.

## 7. Path to ingest-ready
1. **Finish the recovery fix-cycle** (early-consensus + chaptered fixes → re-Hans clean).
2. **Build the garbled-header/numeral repair** (residual lever) + **tighten early-era over-extraction** (exclude non-statute series).
3. **Corpus-wide re-measure** vs the corrected oracle, with noise separated out → the first trustworthy completeness number, per era.
4. **Ingestion prep** (then, on explicit go): review the flagged residue (don't silently drop); handle redirect-stubs (text in companion Codes volumes); namespace 1854's dual series; **back up the DB**; one-pass ingest 1850→present; compare to backup.

## 8. Open decisions for Patrick
- **Completeness bar to launch:** how close to 100% (per era) is "complete enough" — and whether the genuinely OCR-garbled residual that resists text repair warrants targeted re-OCR of the worst pages, or is accepted as flagged.
- **Ingest sequencing:** all-at-once after full validation vs. ingest-in-tranches (e.g. the clean chaptered era now, early era after its precision tightening).
- **Redirect-stub policy:** ingest the stub chapters (real chapters, text in the Codes volume) with a pointer, or resolve their text from the companion volumes first.
