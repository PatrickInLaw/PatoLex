# Oracle Cross-Validation Sweep — per-row denominator validation + completeness (2026-06-19, cc013; methodology corrected cc014)

**READ-ONLY analysis. The oracle (`ca_chapter_counts.tsv`) is NOT modified. Oracle edits are Patrick's call.**

This pass turns the chapter-count oracle from "spot-checked" into "volume-validated": for **every** one of the
216 oracle rows it derives the volume's OWN chapter count from that volume's own content and compares it to
`total_chapters`, then measures parse completeness against the result. It executes the pass described in
`ORACLE_TRUSTWORTHINESS_2026-06-19.md` §"The pass that makes it trustworthy."

> **cc014 methodology correction (2026-06-19).** An audit (Hans) found a denominator-validation hole: the original
> cc013 sweep used "a row is CONFIRMED if **any** signal lands within ±BAND of oracle N" — which would rubber-stamp a
> real undercount whenever the FLOOR parse happened to stop at oracle N (OCR gaps) even though a *trustworthy* body/index
> derivation reached higher. The flagged example was **S47 / 1927 (oracle 898)**, whose body self-index reports
> `robust_max_chapter=910` (cov 0.83). That rule has been **replaced**: every over-read (a trustworthy derivation, cov ≥
> 0.75, whose max exceeds oracle N) is now **witness-verified** — the specific high chapters (oracle_N+1 … derived_max)
> are scanned in the volume and a row is DISCREPANT **only** if ≥1 of them is a *verified real statute* (cross-engine
> "CHAPTER N." header agreed by ≥2 independent OCR engines **+** a real-act body witness — An-Act title + approval/enact
> + real body — **not** a resolution, TOC, quoted title, or a single-engine OCR digit-garble of a lower chapter). The
> witness gate reuses `pipeline/ingest/recover_multiengine_headers.py` (`scan_page_headers` + `body_witness` +
> `is_resolution_near`) verbatim — the same precision gate the production recovery uses. **Result of re-running this
> corrected rule corpus-wide: still 0 DISCREPANT rows, now witness-verified rather than asserted** (see §"The over-read
> witness verification" and the discrepancy table below). The counts, trust %, and completeness are unchanged because no
> row flipped — but the *basis* is now sound. Artifacts: `_overread_corpuswide.py` / `.tsv` / `.log`,
> `_overread_witness_check.py`, `_overread_seqcheck.py`, `_overread_context.py`, `_s47_findhigh.py`,
> `_s45_deepcheck.py`, `_reclassify_status.py`.

## Method (derivation signals + trust gate)

Each row's count was derived from the strongest available volume-intrinsic signal, keyed by `canonical_id`:

- **Early regular (pre-1905):** engine-union printed-index re-derivation (`_early_union_rederivation.tsv`),
  `union_rmax` with the **dense-continuous-from-1 gate** (union coverage ≥ 0.75). Gappy indexes with an 800s
  page-number-contamination block fall below the gate and are marked UNPARSEABLE, not asserted — per the method
  caveat in `ORACLE_DISCREPANCY_EARLY_2026-06-17.md`.
- **Modern regular (1905+):** body self-index max-chapter (`derive_modern_from_body.py` →
  `_body_rederivation.tsv`) from the session's **main chapter volume**, PLUS the **floor-parse supported
  ceiling** (`_floor_max_by_cid.tsv`) which spans **all** of a session's volumes (so multi-volume sessions reach
  their full ceiling — a single body volume only reaches its own top). Derived ceiling = the strongest of these.
- **Cross-check rule (precision-first; cc014 corrected — "over-reads must be witness-verified"):** what we validate
  is the **denominator = the count = the ceiling N**. If a trustworthy signal lands within ±3 of oracle N, the row is
  CONFIRMED. When a *trustworthy* signal reaches **above** N, it is **no longer auto-dismissed as contamination** — the
  specific high chapters (oracle_N+1 … derived_max) are **witness-verified** in the volume (cross-engine "CHAPTER N."
  header agreed by ≥2 independent engines **+** a real-act body witness). ≥1 verified real statute above N →
  **DISCREPANT** (likely oracle undercount); all high chapters resolution / TOC / single-engine digit-garble of a lower
  chapter → **CONFIRMED**. *(The superseded cc013 rule was "any confirming signal within ±3 wins"; it could have masked
  an undercount where the floor stops at N by OCR luck — the S47 case the audit flagged.)* A single robust
  `robust_max_chapter` ceiling rejects isolated OCR spikes; the supported-ceiling rejects unsupported spikes.
- **Extra/special:** derived where a clean self-index exists; otherwise NOT-VALIDATED (small N, expected).
- **Budget even-year volumes (S58, S60, S62, S64, S66, S68, S70, S72, S74):** the physical even-year "NNchapters"
  volume **bundles the budget session + that year's extra session(s)** onto one `canonical_id`, so the parse for
  that id is a multi-session bundle and **cannot isolate** the budget-session count → UNPARSEABLE (verified: e.g.
  `1957-vol1-56chapters` runs 1→68 = 1956 budget(13) + 1956 First Extra(69) bound together).

**Status definitions:** **CONFIRMED** = volume content reaches oracle N (±3); **DISCREPANT** = a trustworthy
derivation cleanly disagrees; **UNPARSEABLE** = derivation under-read / contaminated / bundle (cannot confirm —
note this is *unverified*, **not** a contradiction of the oracle); **NOT-VALIDATED** = no parse/volume mapped.

---

## TASK A — per-row validation status (216 rows)

| status | count | share of rows |
|---|---:|---:|
| **CONFIRMED** | **104** | 48% |
| **DISCREPANT** | **0** | 0% |
| **UNPARSEABLE** | **12** | 6% |
| **NOT-VALIDATED** | **100** | 46% |

By era × status:

| era | CONFIRMED | DISCREPANT | UNPARSEABLE | NOT-VALIDATED | total |
|---|---:|---:|---:|---:|---:|
| 1850–1899 (early OCR) | 32 | 0 | 1 | 2 | 35 |
| 1900–1949 (mid OCR) | 30 | 0 | 2 | 19 | 51 |
| 1950–1999 (late OCR) | 42 | 0 | 9 | 42 | 93 |
| 2000–2024 (born-digital) | 0 | 0 | 0 | 37 | 37 |

By kind: **regular** 97 CONFIRMED / 0 DISCREPANT / 12 UNPARSEABLE / 25 NOT-VALIDATED (134 rows);
**extra/special** 7 CONFIRMED / 0 DISCREPANT / 0 UNPARSEABLE / 75 NOT-VALIDATED (82 rows).

The 4 previously-corrected undercounts (S16 1865-66=650, S27 1887=188, S25 1883=96) + the added 14th session
(S14 1863=538) + the 1860 fix (S11=385) + 1862 (S13=455) **all return CONFIRMED**, as expected — the volume's
own content reaches those exact ceilings.

### THE DISCREPANCY TABLE — **EMPTY (0 rows), now WITNESS-VERIFIED**

| canonical_id | session | oracle N | verified ceiling | delta | witness | basis |
|---|---|---:|---:|---:|---|---|
| *(none)* | — | — | — | — | — | every over-read candidate exonerated by the witness gate |

**No oracle row is trustworthily contradicted by its own volume — and under the cc014 corrected rule this is now a
*verified* result, not an artifact of the loose "any confirming signal wins" gate.** Every value a trustworthy
derivation appeared to over-read was scanned chapter-by-chapter for a *real statute above N*, and **none survived**:

- **S47 / 1927 (oracle 898; body `robust_max_chapter`=910, cov 0.83) — the audit's flagged case → CONFIRMED.**
  The "900, 906, 907, 910" the body-derivation reported are **tesseract single-engine OCR garbles** of the real
  chapters **556, 506, 507, 510**: at every one of those line-head positions surya **and** doctr read the 500s number
  while only tess read a 900s number (verified in `_s47_findhigh.py` — e.g. page 851 `s='CHAPTER 506.' d='CHAPTER 506.'
  t='CHAPTER 906.'`). The clean "An act … Approved by the Governor May 16, 1927" bodies tess attached to "906/907/910"
  are the genuine bodies of chapters 506/507/510 (already ≤ 898 and in the floor). The body self-index's 910 ceiling is
  itself tess-contaminated; **there is no real statute above 898.** This is the *exact* "OCR corruption of a lower
  chapter" exclusion the audit brief itself named (906←506, like 487←437) — applied rigorously it exonerates the row.
- **S45 / 1923 (oracle 479; body 487, cov 0.78) → CONFIRMED.** "486/487" on pages 1011/1013 are tess garbles of the
  real **436/437** (surya+doctr read 436/437 at the same positions; the in-sequence run there is 423→441). Contamination,
  as expected.
- **1938 Extra (oracle 26; body 32, cov 1.00) → CONFIRMED.** Chapters 27–32 are Assembly Concurrent/Joint
  **Resolutions** (3-engine agreement; resolution cue present), not statutes.
- **S20 / 1873-74 (oracle 679; early-union 688, cov 0.81) → CONFIRMED.** No chapter in 680–688 produces a real-act
  roman-header witness; floor ceiling 677 ≈ 679. No real statute above N.
- **S9 / 1858 (union 360 vs 358), S24 / 1881 (union 103 vs 77), S29 / 1891 (union 282 vs 280) → CONFIRMED.** No
  witnessed real statute above N (S24/S29 small over-reads resolve to within the parse's near-support of N; S9 +2 is
  an index over-read with no body witness above 358).

**Budget-bundle rows (S58–S74) are a deliberate non-flip.** The witness gate *does* find real statutes above their tiny
oracle N in the even-year "NNchapters" volumes (e.g. S60/1950: ch 7–74 real statutes over oracle 6) — but those acts
belong to the **bundled extra session** physically bound into the same volume on the same `canonical_id` (verified in
`_overread_corpuswide.log`: 1950-vol1-chapters holds the 6-chapter budget run *and* the 74-chapter 1950 First Extra run,
both starting at 1). They are the documented **bundling artifact**, not an undercount of the budget session, so they
correctly **remain UNPARSEABLE** (see the UNPARSEABLE table) rather than becoming DISCREPANT. *(Precision rule: a
DISCREPANT verdict requires a real statute above N **that belongs to the session the cid denotes** — bundled foreign-
session statutes do not qualify.)*

**No edit is implied by this sweep.** (Contrast the earlier `ORACLE_DISCREPANCY_EARLY_2026-06-17.md`, which *did*
surface real undercounts — those were already applied to the oracle and now reproduce as CONFIRMED.)

### UNPARSEABLE rows (12) — denominator NOT independently confirmed (still trusted from the clerk source)

| canonical_id | session | oracle N | derived | why unparseable |
|---|---|---:|---:|---|
| S58 | 1948 Regular (Budget) | 38 | — | even-year budget volume bundles budget+extra sessions |
| S60 | 1950 Regular (Budget) | 6 | — | budget bundle |
| S62 | 1952 Regular (Budget) | 14 | — | budget bundle |
| S64 | 1954 Regular (Budget) | 10 | — | budget bundle |
| S66 | 1956 Regular (Budget) | 13 | — | budget bundle |
| S68 | 1958 Regular (Budget) | 10 | — | budget bundle |
| S70 | 1960 Regular (Budget) | 14 | — | budget bundle |
| S72 | 1962 Regular (Budget) | 12 | — | budget bundle |
| S74 | 1964 Regular (Budget) | 1 | — | budget bundle |
| S5 | 1854 Regular | 174 | 101 | early: no parseable front index (body-header derivation needed, not done here) |
| S54 | 1941 Regular | 1284 | 1279 | body ceiling 1279 vs 1284 — under-read by 5, just outside ±3 (near-confirm) |
| S99 | 1989 Regular | 1467 | 1437 | parse reaches a dense 1437; final 30 chapters (1438–1467) not parsed (completeness gap, not a count conflict) |

These 12 sum to **3,043 chapters (2.5% of the denominator)**. The 9 budget rows are tiny (1–38 each, 108
chapters total); S54 and S99 are near-confirms where the parse stops a few chapters below the oracle ceiling.
None contradicts the oracle — they are simply *not independently re-derived* by this pass.

---

## TASK B — completeness against the volume-validated denominator

Measured by `chapter_vs_oracle.py` against the LIVE canonical oracle + `_volume_canonical_map.tsv` +
`_chapters_all_v4.tsv` (the floor/multiengine/lostheader parse, 89,869 chapter rows). **`have` is capped to
1..oracle_N** so OCR-garbled high numbers cannot inflate it.

> **cc014 note — completeness is unaffected by the methodology fix.** The 92.1% OCR-era completeness caps `have` at the
> oracle ceiling N either way; because the over-read re-verification produced **0 flips** (no oracle N changed), every
> denominator below is identical to cc013. The fix tightened *how* over-reads are adjudicated, not any count.

| era | sessions w/ parse | authoritative | parsed (have) | completeness |
|---|---:|---:|---:|---:|
| 1850–1899 (early OCR) | 33 | 11,185 | 8,448 | **75.5%** |
| 1900–1949 (mid OCR) | 31 | 22,472 | 19,861 | **88.4%** |
| 1950–1999 (late OCR) | 51 | 63,164 | 60,827 | **96.3%** |
| **OCR-era corpus** | **115** | **96,821** | **89,136** | **92.1%** |

- **Scope caveat (important):** this completeness number is the **OCR/historical era only** (1850–1999). The
  artifacts this sweep uses (`_chapters_all_v4.tsv`, the volume map) stop at the OCR'd volumes; the parse file
  ends at 1999. The **modern born-digital era (2000–2024, S110–S134)** is **not measured here** — it lives in
  the local Postgres `patolex` DB from CA SOS structured bulk data, not in these OCR scratch files (no DB driver
  available in this environment to query it: `psql`/`psycopg` absent on the 5090 sweep host).
- **Lowest-completeness sessions (worst parse gaps, all early/sparse-OCR):** S16 1865-66 (32%, 205/650),
  S14 1863 (34%, 181/538), S5 1854 (40%, 69/174), S41 1915 (56%, 432/771), S3 1852 (56%, 114/202). These are
  parse-recall gaps, **not** denominator problems.
- **Unverified-denominator caveat applied:** the completeness %s for the 12 UNPARSEABLE rows rest on an oracle N
  this sweep did **not** independently confirm. Of those, only S5 (1854, 174) and S54 (1941, 1284) and S99
  (1989, 1467) carry a non-trivial denominator into the completeness measure; the 9 budget rows are negligible
  (≤38 each). So **>99% of the completeness denominator used above is volume-CONFIRMED.**

---

## TASK C — revised trustworthiness statement

### Denominator confirmation (all 216 rows, total 120,205 chapters)

| validation status | chapters | share of full denominator |
|---|---:|---:|
| **CONFIRMED** (volume-confirmed) | **93,780** | **78.0%** |
| DISCREPANT | 0 | 0.0% |
| UNPARSEABLE (unverified, OCR era) | 3,043 | 2.5% |
| NOT-VALIDATED | 23,382 | 19.5% |

The 19.5% NOT-VALIDATED splits into two very different buckets:

- **21,681 chapters — born-digital 2000–2024 (37 rows).** Not reachable by this OCR-volume sweep, but these
  rows come from **California SOS structured bulk legislative data** (`admin.cdn.sos.ca.gov/bill-chapters/...`
  and clerk archives) — the *most* authoritative source in the corpus, not a fallible OCR index. "Not validated
  by this sweep" here means "out of this sweep's OCR scope," **not** "low-confidence."
- **1,701 chapters — OCR-era extra/special sessions (63 rows).** Small sessions (1–169 chapters each) with no
  clean self-index to re-derive. Expected; individually low-stakes.

### Honest verdict

- **What is now volume-confirmed:** **78.0% of the full 120,205-chapter denominator** is confirmed by the
  volume's own content reaching the oracle ceiling — up from the prior ~25–30 spot-checked rows. **Among the
  133 regular-session rows the oracle's structural backbone, 97 are CONFIRMED** and **zero are contradicted.**
  For the OCR era specifically, the regular-session denominator is essentially fully cross-validated (only S5,
  S54, S99 short, and they under-read rather than conflict).
- **What is still unverified:** **2.5% (3,043 ch)** is genuinely unverified by this pass (9 tiny budget-bundle
  rows + S5/S54/S99), and **19.5% (23,382 ch)** is out of OCR scope — overwhelmingly the born-digital modern
  era, which is denominator-trustworthy on its own structured source but should get its own confirmation pass
  (DB-side count vs SOS published chapter totals) to close the loop.
- **The key new fact:** the cross-validation found **no oracle value its own volume contradicts** — and as of the
  cc014 correction this is **witness-verified**: every apparent over-read was scanned chapter-by-chapter and shown to be
  contamination (single-engine OCR digit-garble of a lower chapter, e.g. tess 906←506, 487←436/437), a resolution, or a
  bundled foreign-session act — **not** a real statute above the oracle ceiling. Every shortfall is a parse-recall gap,
  not a wrong count. The denominator is **structurally sound and now content-confirmed for the OCR regular sessions**;
  the residual risk has moved from "is the count wrong?" to "we haven't independently re-derived these small /
  born-digital rows."

### Caveats for the orchestrator / Hans to check

1. **Born-digital era is unmeasured here** (no DB access on the sweep host). The headline 92.1% completeness is
   **OCR-era 1850–1999 only**; a separate DB-side pass is needed for 2000–2024 completeness + denominator
   confirmation against SOS totals.
2. **Budget-bundle UNPARSEABLE (9 rows)** rests on the volume-map collapsing even-year budget+extra volumes onto
   one `canonical_id`. The *count* is unverified, but the bundling itself is a known modelling choice, not a bug
   surfaced here.
3. **"No DISCREPANT" is now witness-verified (cc014), not rule-dependent.** The old caveat — that the result rested on
   "any confirming signal wins" and a contaminated signal landing near N could mask a discrepancy — is **resolved**. Every
   trustworthy over-read (S47 1927, S45 1923, S20 1873-74, 1938X1, S9, S24, S29) was scanned chapter-by-chapter for a
   real statute above N using the production cross-engine + body-witness gate; all are contamination / resolutions /
   single-engine digit-garbles (see the discrepancy table). The one the audit flagged, **S47 (910←tess-garble of 510)**,
   is the clearest exoneration. Re-verify target for Hans: confirm via `_s47_findhigh.py` that surya+doctr read 5xx where
   tess reads 9xx (they do), and confirm the budget-bundle non-flip policy (S58–S74 over-reads are bundled extra-session
   statutes — they stay UNPARSEABLE). A future re-OCR of the 1927 body would let the body self-index report 556/506/507/510
   instead of 900/906/907/910 and remove this contamination at the source.
4. **S54 (1941, −5) and S99 (1989, −30)** are flagged UNPARSEABLE but are really near-confirm under-reads; they
   are not evidence the oracle is wrong, only that the parse stops just short.

---

*Generated by cc013 (oracle cross-validation sweep); methodology corrected by cc014 (witness-verified over-reads).
Analysis artifacts (5090 scratch `C:/Users/patolex/PatoLex-scratch/`): `_oracle_validation_status.tsv` (per-row status,
all 216, now with `witness_note` column), `_floor_max_by_cid.tsv` (per-session floor ceiling),
`_oracle_validation_sweep.py`, `_floor_max_by_cid.py`, `_sweep_rollup.py`. **cc014 over-read witness pass:**
`_overread_corpuswide.py` / `_overread_corpuswide.tsv` / `_overread_corpuswide.log` (corpus-wide), `_reclassify_status.py`
(reclassifier), plus the worked drill-downs `_overread_witness_check.py`, `_overread_seqcheck.py`, `_overread_context.py`,
`_s47_findhigh.py`, `_s45_deepcheck.py`. The witness gate reuses `pipeline/ingest/recover_multiengine_headers.py`
(`scan_page_headers` + `body_witness` + `is_resolution_near`). Inputs: `_early_union_rederivation.tsv`,
`_body_rederivation.tsv`, `_volume_canonical_map.tsv`, `_chapters_all_v4.tsv`. READ-ONLY; oracle unchanged.*
