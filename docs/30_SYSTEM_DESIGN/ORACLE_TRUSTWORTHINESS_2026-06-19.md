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
