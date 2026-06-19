# SESSION cc014 — Oracle over-read denominator-validation methodology fix (witness-verified)

**Date:** 2026-06-19 | **Scope:** READ-ONLY analysis on the 5090. Oracle NOT edited (Patrick's call). No git commit.

## Problem (Hans audit finding)
The cc013 oracle cross-validation sweep used "a row is CONFIRMED if ANY signal lands within ±BAND of oracle N."
That rubber-stamps a real undercount whenever the FLOOR parse happens to stop at oracle N (OCR gaps) even though a
trustworthy body/index derivation reached higher with real statutes above N. Flagged case: **S47 / 1927 (oracle 898;
body robust_max=910 cov 0.83)**.

## Fix
Replaced the rule with **witness-verified over-reads**: for every oracle row whose trustworthy derivation (cov ≥ 0.75)
exceeds oracle N, scan the specific high chapters (N+1…derived_max) in the volume and flip to DISCREPANT only if ≥1 is a
**verified real statute** — cross-engine "CHAPTER N." header agreed by ≥2 independent OCR engines **+** a real-act body
witness (An-Act title + approval/enact + real body), excluding resolutions / TOC / quoted / single-engine digit-garbles.
Witness gate reuses `pipeline/ingest/recover_multiengine_headers.py` (`scan_page_headers`+`body_witness`+
`is_resolution_near`) verbatim. Ran corpus-wide (`_overread_corpuswide.py`).

## Result — 0 flips; discrepancy table still empty, now witness-verified
- **S47 / 1927 → CONFIRMED (reverses the audit's premise).** "900/906/907/910" are **tess single-engine garbles** of
  556/506/507/510 — surya AND doctr read the 500s number at every one of those line positions; only tesseract reads 900s
  (verified `_s47_findhigh.py`). No real statute above 898.
- **S45 / 1923 → CONFIRMED.** "486/487" are tess garbles of real 436/437 (surya+doctr read 436/437). Matches brief.
- **1938X1 → CONFIRMED** (27–32 are Assembly Resolutions). **S20/1873-74, S9, S24, S29 → CONFIRMED** (no witnessed
  real statute above N).
- **Budget-bundle S58–S74:** witness gate finds real statutes above their tiny budget N, but they belong to the
  **bundled extra session** on the same canonical_id (e.g. 1950-vol1 holds the 6-ch budget run AND the 74-ch 1950 First
  Extra run). Documented bundling artifact → **remain UNPARSEABLE**, not DISCREPANT.

## Counts (unchanged — no flip): CONFIRMED 104 / DISCREPANT 0 / UNPARSEABLE 12 / NOT-VALIDATED 100.
Trust % = **78.02%** (S47 did NOT flip, so no ~0.7pt drop). Completeness 92.1% (OCR era) unaffected (caps at N).

## Durable findings recorded
- Report `docs/30_SYSTEM_DESIGN/sources/ORACLE_VALIDATION_SWEEP_2026-06-19.md` updated: cc014 methodology note, new
  cross-check rule, witness-verified (still-empty) discrepancy table, S47 worked in full, budget-bundle non-flip policy,
  corrected caveat #3.
- **Key durable fact:** the 1927 body self-index `robust_max_chapter=910` is *tesseract-contaminated* (9←5 digit
  confusion); a future 1927 re-OCR would report 510 not 910 and remove the phantom ceiling at source.

## For Hans / orchestrator to re-verify
1. Confirm `_s47_findhigh.py` shows surya+doctr=5xx / tess=9xx at pages 851/852/856/941 (the exoneration of S47).
2. Confirm the budget-bundle non-flip policy (S58–S74 over-reads are foreign bundled-session statutes).
3. Note: this outcome **contradicts the brief's expectation that S47 flips** — the brief author saw tess's clean
   "CHAPTER 906. An act… Approved by the Governor" without checking that the other two engines read 506. Precision-first,
   S47 is CONFIRMED.

## Artifacts (5090 scratch `C:/Users/patolex/PatoLex-scratch/`)
`_overread_corpuswide.py|.tsv|.log`, `_reclassify_status.py`, `_overread_witness_check.py`, `_overread_seqcheck.py`,
`_overread_context.py`, `_s47_findhigh.py`, `_s45_deepcheck.py`; updated `_oracle_validation_status.tsv` (+witness_note).
