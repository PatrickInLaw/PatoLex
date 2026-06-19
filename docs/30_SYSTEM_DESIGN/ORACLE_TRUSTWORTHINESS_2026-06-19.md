# Oracle Trustworthiness — status + path to "validated" (2026-06-19, cc013)

After the session-number remodel the denominator (`ca_chapter_counts.tsv`, 216 rows, total 120,205) is
**structurally sound and much more trustworthy than before — but NOT yet fully verified.** This doc records
exactly where the trust is and the pass that earns the word "validated."

## High confidence (verified)
- **Structure:** canonical session keying is audited (4 Hans gates). The 1863 collision and the biennium-bucketing
  bug class are fixed; the S1..S134 sequence is contiguous; the +1 ordinal offset (~28 anchors 1863-1945)
  independently proves the session count.
- **The rows we cross-checked against the printed volumes** (~25–30 of 216): the 4 corrected undercounts
  (1865-66=650, 1887=188, 1883=96, 1863=538), the 1860 over-count fix (385), the ~12 early controls that MATCHed,
  and the early-roman volumes recovered by engine-union.
- **Modern era rough shape:** body-self-index matched on the two controls checked (1931=1220, 1945≈1527).

## Open questions (residual risk)
1. **~85% of rows still carry their original clerk-web-index values, UNVERIFIED by us — on a source we PROVED is
   fallible** (it undercounted 5–13× in the four cases we caught, yet matched the printed volume in every control).
   So the clerk numbers are "mostly right with scattered, sometimes-severe errors." We fixed the worst *early* ones
   we found; **we do not know how many other wrong rows exist**, early or modern, because we only looked where the
   index happened to parse.
2. **The corrected values are index-DERIVED estimates, not hand-counts** (±~10): 538 (1863), 385 (1860; historical
   ~374). Strong evidence, not certainty.
3. **Modern per-session denominators were spot-validated, not swept** (2 of ~80 sessions).
4. **A few volumes are entirely unverified** — Tier-6 (1850–54, 1861, the `-code` volumes) — plus the known
   `1949-vol1-49chapters-prior`→S59 mis-map and possibly other extra-session mappings not swept.

## Verdict
**Not yet trustworthy enough to call a completeness % "validated."** A re-measure now is far better than before but
its denominator is only spot-checked → an unquantified error bar, which violates the "no guessing" bar.

## The pass that makes it trustworthy (and yields the re-measure)
Cross-validate EVERY row against its own volume, then measure against the result:
1. **Sweep the whole corpus volume-by-volume:** engine-union printed-index re-derivation (early) + body-self-index
   max-chapter (modern), canonically keyed → per-row status: **confirmed / discrepant / unparseable**. Use the
   dense-continuous-from-1 gate (gappy indexes with 800s page-number contamination are NOT trustworthy — see
   `ORACLE_DISCREPANCY_EARLY_2026-06-17.md`).
2. **Discrepancy table** — every oracle value the volume disagrees with — for Patrick's oracle decisions (edits stay
   his call; do NOT overwrite the oracle).
3. **Measure completeness** against the volume-validated denominator → the first % with a denominator checked
   end-to-end, with the residual "unparseable" rows explicitly flagged, not silently trusted.

Tools already exist (`rederive_index_counts.py` + engine-union, `derive_modern_from_body.py`) — this is running them
comprehensively + reconciling, orchestrated via subagents with Hans gating the reconciliation.

## STATUS — pass EXECUTED (cc013 sweep → cc014 witness-verified → cc015 budget range-split)

The pass above has been run and is recorded in `sources/ORACLE_VALIDATION_SWEEP_2026-06-19.md`. Result:

- **OCR-era regular sessions (1850–1999): 105 / 109 volume-CONFIRMED (96.3% by row, 97.0% by chapter); 0 DISCREPANT.**
- **Full denominator: 78.1% volume-CONFIRMED, 0 DISCREPANT, 2.4% UNPARSEABLE, 19.5% NOT-VALIDATED** (the latter is
  overwhelmingly the born-digital 2000–2024 era, out of OCR scope — denominator-trustworthy on its own SOS source).
- **No oracle row is contradicted by its own volume** — every apparent over-read was scanned chapter-by-chapter with the
  production cross-engine + body-witness gate and shown to be contamination / a resolution / a single-engine digit-garble /
  a **bundled foreign-session statute**. This is *witness-verified*, not rule-dependent.
- **The 9 even-year budget bundles** (budget session + that year's extra bound on one cid) are resolved by
  **range-based attribution** (`pipeline/analysis/split_budget_bundle.py`): the budget session = the volume's first
  statute-body run; its witness-checked ceiling = the budget oracle N for 8 of 9. **S74 (1964, oracle 1) is the lone
  exception** — its volume binds the 151-chapter 1964 First Extra, not a 1-chapter budget run, so the budget statute is
  not isolable.
- **Residual UNPARSEABLE (4 rows): S5/1854, S54/1941, S74/1964, S99/1989** — all parse-recall / missing-OCR-content
  under-reads (the OCR'd volume stops short of the oracle ceiling or doesn't isolate the session), oracle uncontradicted,
  no witnessed over-read. These 4 = 2,926 chapters (2.4% of the denominator). They are *unverified*, **not** wrong.

**Remaining to close the loop:** (1) a DB-side completeness + denominator pass for the born-digital 2000–2024 era
(no DB driver on the 5090 sweep host); (2) re-OCR of the S5/S99/S54 tails (and the 1927 body, the S47 contamination
source) would let the self-index reach the oracle ceiling and retire the 4-row residual.
