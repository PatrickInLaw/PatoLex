# Chapter-Sequence Completeness — Findings (cc007, 2026-06-14)

**Question:** are any acts/chapters missing in the parsed corpus, and is it ready for ingestion?

> ## ⚑ ROOT-CAUSE UPDATE (2026-06-16) — the early-era "OCR loss" is a CONSENSUS BUG, NOT lost data (visual diagnosis)
> A vision-model pass over the actual page scans **overturns the earlier "genuine OCR loss / re-OCR territory" conclusion** (which was inferred from text-census heuristics WITHOUT looking at the images — it was wrong).
> **Finding:** the 1861–1865-66 volumes print "CHAP." headers in an **italic/display typeface** that **Tesseract** misreads (`Chap.`→`Cuap./Crap./Cnap.`…), while **Surya AND DocTR read them correctly**. The token-majority **consensus then picked Tesseract's garbage over the two correct engines**, so **zero** headers survived into the consensus text (e.g. 1862: 0 in consensus, but Surya read 236, DocTR 174). The scans are CLEAN; the headers are LEGIBLE; **the correct headers already exist in the `surya_text` field of the existing OCR JSON.**
> **Fix is CHEAP — no re-scan, no re-OCR:** re-run consensus for the ~6 affected early volumes with Tesseract down-weighted/excluded on header lines (Surya+DocTR agree), or extract the `CHAP…` headers directly from `surya_text` and patch the consensus, then re-parse. This should also kill the 1865-66 OVER-extraction (the phantom 442-vs-280 was Tesseract's garbled numbers; Surya's are clean).
> **Affected:** 1861, 1862, 1863, 1863-64, 1865-66 (italic era); **check 1850–1860 (likely same typeface).** 1867-68+ switched to upright Roman type → all engines correct, no problem. The earlier "1873-74 has ~270 genuinely-lost headers" claim (finding #6) is also suspect — the visual pass found 1873-74 headers read correctly by all engines.
> **Implication:** the early-era gap is largely **cheaply recoverable from data we already have**, not a re-OCR/re-scan campaign. Lesson: validate OCR findings against the IMAGES, and consensus voting can let one garbling engine override correct ones for a given typeface.


**Tools (committed):** `pipeline/analysis/extract_chapters.py` (emits a small TSV of chapter_int/iso_date/source_page per act from the 197-volume aggregated parse on the 5090) → `pipeline/analysis/chapter_completeness.py` (per-session gap triage). Input: `chapters.tsv` (76,691 acts).

## Method (fixes the old report's false positives)
The old `completeness-report.json` counted 122,475 "gaps" — meaningless, dominated by: multi-volume sessions split by page range, the `NNchapters` suffix (real statute year ≠ physical-volume year), independent extra-session numbering, and OCR-garbled chapter numbers. The new check: groups by true legislative session (suffix-aware), drops provably-corrupt chapter numbers (only **0.7%**, 507/76,691, are > the CA hard ceiling), and triages sessions CLEAN / SMALL_GAP / LARGE_GAP / ANOMALY.

## Key findings (durable)
1. **No source data is lost.** OCR page-completeness was independently verified (0 missing body pages across all 205 volumes, `verify_volume_completeness.py`). Every act is present in the scanned text.
2. **The parser is correct on CLEAN OCR.** 1996 parsed to a perfect contiguous Chapters 1–1171; the authoritative leginfo data in Postgres confirms 1996 max chapter = 1171. Exact match.
3. **The parser UNDER-EXTRACTS on noisy mid-century OCR.** Calibration: California Statutes of **1957 had 2,424 chapters** (confirmed externally AND by our own OCR, which found chapter headers up to 2424); our parser extracted ~1,990 (~82%). The ~430 shortfall is acts present in the OCR text that the parser did not cleanly segment/number — a **parse deficiency, not lost data and not a re-OCR problem.**
4. **Internal sequence analysis cannot CERTIFY completeness alone — two blind spots:**
   - *Trailing truncation:* a session parsed cleanly as 1..N looks "CLEAN" even if the real session ran to N+k. Example: our 1997 parse is a clean 1..951, but the authoritative max is higher — the tail is silently missing.
   - *Misnumber vs missing:* an OCR-misread chapter number creates a fake gap (missing) and a fake collision (dupe); these are indistinguishable from a truly absent act without an external reference.
   Therefore a trustworthy "nothing is missing" claim **requires an external per-session chapter-count oracle** (CA publishes chapters-per-session via the Chief Clerk archive / leginfo) or the referential cross-check vs current codified law (the `COVERAGE_CERTIFICATION.md` design, currently unbuilt).

## State by era
- **Modern (1991→present):** authoritative leginfo data already in Postgres; 1996 OCR cross-validates. Effectively complete (modulo per-year trailing-tail verification).
- **OCR era (≈1850–1990):** all OCR pages present, but current parse extracts only ~80–85% of true chapters as cleanly-numbered acts (calibrated on 1957 = 82%). The already-ingested 1850–1876 segment carries the same chapter-number OCR noise (e.g. DB shows 1863 max chapter 1120, 1869-70 max 1092 — impossible, OCR errors in already-loaded data).

## MEASURED completeness vs the authoritative oracle (2026-06-14, "before recovery")
Gate 2 produced an authoritative per-session chapter-count oracle: `docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv`
(215 sessions 1850–2024, validated against 1957=2424 and 1996=1171; method = highest chapter number in the
session ToC). `pipeline/analysis/chapter_vs_oracle.py` joins our parse against it (oracle total as the cap).

**Result (OCR era 1861–1999): 72,562 of 91,153 authoritative chapters parsed = 79.6% complete; ~18,591 missing.**
- The deficit is systematic (most sessions 70–88%), not random → parser under-extraction on noisy OCR, consistent
  with the 1957 calibration (79% here). 1996–1999 = 100% (clean OCR); earliest hand-set volumes worst (1861 47%, 1915 33%).
- Caveats: 1850–1860 came from the ORIGINAL 1850–75 ingest (not the 197-vol parse set) → not scored here, scored
  separately; a few biennial volumes spanning two sessions (e.g. 1907-09) add minor per-session noise; OCR-garbled
  high chapter numbers (e.g. 90623) are neutralized by the oracle cap.
- This is the BEFORE-recovery baseline. After the Gate-1 parser completion/renumber pass, re-run chapter_vs_oracle.py
  to measure how much of the 18,591 is recovered.

## AFTER-recovery completeness (2026-06-14, full-corpus run)
`pipeline/ingest/recover_all.py` ran the Hans-audited recovery+renumber (recover_acts.py) over all 205 volumes /
108 sessions on the 5090 (0 failed), output to new `parsed_acts_recovered.json` per volume + `chapters_recovered.tsv`
(86,584 acts, up from 76,691). Re-measured with chapter_vs_oracle.py:

**Corpus (1861–1999): 72,562 → 80,893 of 91,154 = 79.6% → 88.7% complete; missing 18,591 → 10,261 (~8,300 acts
recovered, ~45% of the gap), precision-clean (uncertain renumbers demoted to flagged, not ingested).**
- **Chaptered era (1880–1999): ~91% complete** — the segment the pass targets. 1957 79→94%, 1880 79→94%, 1959 80→96%,
  1947 86→95%; modern 1996–99 = 100%.
- **Pre-1880 (1861–1877): ~56%, unchanged** — those volumes have no per-act CHAPTER headers in the OCR; the
  header-recovery pass cannot help them. **Next follow-on: a header-free (date + "An act" sequence) detector for 1850–1879.**
- Residual noisy chaptered sessions (1915 35%, 1933 72%, 1987–88 83%) are targeted-cleanup candidates.
- Recovery data lives in PatoLex-scratch (parsed_acts_recovered.json, chapters_recovered.tsv) — not committed (data, not code).

## Pre-1880 header-form recovery (2026-06-14, `recover_early.py` v2)

The "next follow-on" above is now built: `pipeline/ingest/recover_early.py` (header-FORM
detector, not header-FREE — see below). It runs READ-ONLY on the 5090 and writes a NEW
`parsed_acts_early.json` per volume (never touches `parsed_acts_fixed/recovered.json`, no DB).
Validated against the same oracle (`ca_chapter_counts.tsv`). BEFORE = what production
`parse_volume` actually KEEPS (header_starts_act + flush_act criteria), AFTER = recover_early.

| session | before | after | oracle | before% | after% |
|---------|-------:|------:|-------:|--------:|-------:|
| 1861    | 258 | 360 | 538 | 48% | **67%** |
| 1862    | 122 | 261 | 455 | 27% | **57%** |
| 1863-64 | 242 | 340 | 476 | 51% | **71%** |
| 1865-66 | 315 | 442 | 280\* | 112% | 158%\* |
| 1867-68 | 408 | 410 | 545 | 75% | 75% |
| 1869-70 | 296 | 336 | 583 | 51% | **58%** |
| 1871-72 | 399 | 401 | 637 | 63% | 63% |
| 1873-74 | 340 | 340 | 679 | 50% | 50% |
| 1875-76 | 303 | 405 | 613 | 49% | **66%** |
| 1877-78 | 328 | 458 | 673 | 49% | **68%** |

**Durable findings:**
1. **Two layout eras, not one.** ERA-1 (1861-1872, also 1875-76/1877-78) prints the header
   JOINED on one line: `Cuap. VIII.—An Act to ...` (glyph + numeral + EM-DASH + title).
   ERA-2 (1873-74, 1880) prints it SPLIT: `CHAPTER IX.` alone, title on the next line.
   The big recovery (1861/62/63/75/77) is ERA-1 mid-page em-dash headers the production
   HEADER_RE drops; ERA-2 volumes were already near production's ceiling so recover_early
   is a no-regression superset there (it REUSES `header_starts_act` for the split form).
2. **The detection key is a TRIAD, not the glyph.** The glyph OCRs unpredictably
   (Cuap/Cuarrer/Crap/Coav/Caar/Cnav/Onar/Car/Cuoar/...). Precision comes from requiring a
   REAL numeral (roman/arabic, not a stray 'to'/'y'/'o' English fragment) + an em-dash +
   "An Act". The DRAFT's bug was a loose glyph (any C-word) + loose numeral, which counted
   body lines ("County **to** levy ...", "Court of the State ...") as acts (1865-66 hit 145%
   of a *correct* oracle in the draft). The real-numeral + dash + An-Act triad removed
   essentially all of those false positives.
3. **"entitled"/"of an act" in a title is NOT a body-ref for the joined form.** A genuine
   header legitimately reads "An Act to amend an Act entitled an Act ...". Blanket BODYREF
   rejection (carried over from recover_acts) was deleting real acts; removing it for the
   joined triad added ~15-25 pts of recall on 1862/1863-64. Only the QUOTED-title cue
   (opening quote right before "An Act") is rejected.
4. **\*CORRECTED 2026-06-16: the 1865-66 oracle (280) is RIGHT, not an undercount.** The CA
   Chief Clerk archive page explicitly states the 1865-66 Statutes = **Chapters 1–280** (with
   SEPARATE resolution series: Assembly 1–35, Senate 1–41). The earlier "~640 acts / numerals
   to DCXXVII" claim was **OCR-garble inflation** (the same garbled-high-number effect that
   produced impossible values like 90623 in the chaptered era) — NOT real chapters. **This means
   recover_early OVER-extracted 1865-66 (442 distinct chapter_int vs a true 280): ~160 phantom/
   false-split acts (or resolution/amendment contamination).** That contradicts finding #5's
   "75/75, 0 false positives" — the 75-sample spot-check did not catch this systematic
   over-extraction. **PRECISION of recover_early needs re-examination before its early-era output
   is trusted** (a confidently-wrong/duplicated act is worse than a flagged gap). Do NOT change
   ca_chapter_counts.tsv — 280 is correct.
5. **PRECISION (spot-check, 75 joined-form recoveries across 1861/1862/1865-66): 75/75 real
   act starts, 0 false positives → ≈99%+.** This is an EMPIRICAL result, not a structural
   guarantee: the triad + the SANITY enacting-clause/[Approved] gate make body-line false
   positives **unobserved** (75/75), not impossible — a prose line carrying both the
   C-word+numeral+em-dash+"An Act" pattern AND an enacting clause would slip through; none
   has been seen in the early era. The numerals carry display-only OCR noise
   (L↔D, dropped strokes), as designed — numbering is positional (`in_act_order`), the
   numeral is best-effort display only.
6. **Recoverable vs genuine OCR loss (honest floor).** For the SPLIT-form 1873-74, a census
   (`_diag_early8.py`) found only **337 glyph-alone `CHAPTER` headers physically present in
   the OCR (313 real + 22 code-amendment stubs)**, yet **~583 acts are present** (enact-clause
   count ÷ 2). So ~270 acts of 1873-74 have NO recoverable header line at all — the CHAPTER
   line merged with adjacent text or lost its glyph in OCR. That is **genuine header-OCR loss**,
   not a parser miss; no header-form detector can recover it. Likewise 1862's dash+AnAct
   ceiling is ~311 header lines vs oracle 455 → ~140 acts have no single-line header in the
   OCR. **Bottom line: recover_early lifts the pre-1880 segment from ~48% to ~60-70% of the
   header-bearing acts; the remaining gap is dominated by header-OCR-loss (recoverable only by
   re-OCR or a riskier date+enacting-clause sequence detector), plus, for 1873-74+, code-
   amendment STUB chapters whose bodies live in the companion `-code` Amendments volume.**
   The `-code` companion volumes are CODES (Civil/Penal/etc. sections), NOT extra session-law
   chapters (0 `CHAPTER—An Act` headers), so the oracle totals for 1873-74+ count chapters
   whose text is not in the statutes volume at all.

Output is NOT committed (data, lives in PatoLex-scratch as `parsed_acts_early.json`); the
detector + diag scripts are the committed deliverable, left uncommitted in the working tree
for review + Hans audit.

## Cheap-cleanup pass (2026-06-16) — what the gaps actually are

**1880–1999 gap decomposed (≈10.1% / 8,870 "missing" chapter-slots):**
- **~54% (4,777) GENUINELY ABSENT** — and the dominant cause is **entire UN-PARSED vol2/vol3 of multi-volume
  sessions** (e.g. 1915/1917/1919/1921 have only `-vol1-chapters` present; 1915 N=771, only ~350 acts = vol1).
  This is a **missing-VOLUMES problem, not OCR header-loss** → must determine which multi-vol sessions are missing
  later volumes and whether those scans were ever acquired/OCR'd. **NEW completeness gap, needs follow-up.**
- **~46% (4,093) MISNUMBERED-but-present** — acts extracted but with garbled/out-of-range/duplicate chapter
  numbers (2,835 out-of-range + 574 in-range dupes confirmed). Recoverable by a better renumber pass (cheap).
- Verdict: NOT mostly a numbering problem — real extraction loss (missing volumes) is the larger share.

**Measurement bug found in `chapter_vs_oracle.py`:** its session key = leading 4 digits of the label, which
mis-buckets biennial spanning labels (`1900-01`, `1907-09`, `1910-11`) → oracle sessions 1901/1909/1911 (1,757 ch)
falsely showed as 100% absent. Biennium-bucketing (Agent's `gap_biennium.py`) recovers 1,442 acts. **Fix
chapter_vs_oracle.py to bucket by biennium before re-quoting any per-session early/biennial numbers.**

**Flagged-act residue (must be reviewed at ingest, never silently dropped):** 4,166 of 86,584 acts (~4.8%) are in
`flagged_acts` (uncertain renumber / witness-disagree / ambiguous). Era-skewed: 1870s ~25%, 1860s ~11%, 1910s ~13–16%;
modern ~1.5–2%. These are mostly real acts with a low-confidence chapter number, recoverable on review.

**Oracle 1865-66 = 280 CONFIRMED correct** (Chief Clerk archive) — see finding #4 above; earlier "undercount" claim
withdrawn. The actionable item it surfaced: **recover_early over-extracts on garbled volumes (1865-66: 442 vs 280)
→ early-era recovery precision needs re-examination.**

## Ingestion readiness: NOT READY (OCR era)
Ingesting the mid-century parse as-is would under-populate it by ~15–20% and carry chapter-number noise. Before full ingestion:
1. **Parser completion/repair pass for the OCR era** — recover the ~15–20% of acts the segmenter misses + a chapter-number reconstruction pass (re-number from sequence/page order, since OCR pages are complete).
2. **Acquire an external per-session chapter-count oracle** to certify completeness (separate "missing" from "misnumbered"/"trailing-truncated").
3. Carry-overs: re-parse the 13 timing-stale 1996–99 volumes on the 5080 (OCR present; already parsed on the 5090), add non-statute "BILL CHAPTERS" digests (e.g. 1998-vol6) to `SKIP_LABELS`, back up the DB before the one-pass ingest.
