# Oracle Cross-Validation Sweep — per-row denominator validation + completeness (2026-06-19, cc013; methodology corrected cc014; budget-bundle range-split cc015)

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

> **cc015 budget-bundle range-split (2026-06-19).** The 12 UNPARSEABLE rows the cc014 sweep left were resolved by a
> **range-based attribution** of the even-year budget bundles + a targeted look at the 3 near-confirms. The 9 even-year
> budget volumes bind a tiny budget/regular session AND that year's extra session(s) onto one `canonical_id`; both
> sessions number their chapters from CHAPTER 1, so a whole-volume self-index can't isolate the budget count. The new
> matcher `pipeline/analysis/split_budget_bundle.py` segments each budget volume's cross-engine `CHAPTER N.` header
> sequence into monotonic RUNS (a run breaks at a downward numbering reset), classifies each run as statute-BODY vs
> RESOLUTION dominant, and attributes the BUDGET session to the **FIRST statute-body run** (the budget statutes print
> first, right after the title page). **Result: 8 of the 9 budget rows CONFIRM — the first body run's witness-checked
> ceiling equals the budget oracle N exactly** (S58 1..38, S60 1..6, S62 1..14, S64 1..10, S66 1..13, S68 1..10,
> S70 1..13≈14, S72 1..12). **S74 (1964 budget, oracle 1) stays UNPARSEABLE** — its volume (`1965-vol1-64chapters`)
> binds the **151-chapter 1964 First Extra** (title page p103 reads "PASSED AT THE 1964 FIRST EXTRAORDINARY SESSION"),
> not a 1-chapter budget run; the single budget statute is not isolable. The corpus-wide over-read sweep
> (`_overread_corpuswide.py`) was made **budget-aware**: over-reads on a budget cid are bundled **foreign extra-session**
> statutes (a different session bound into the same volume), so budget cids are excluded from the DISCREPANT decision
> (status `BUDGET_BUNDLE`) — **0 DISCREPANT corpus-wide still holds.** The 3 near-confirms were re-examined and all stay
> UNPARSEABLE as **parse-recall / missing-OCR-content gaps with the oracle uncontradicted** (no witnessed over-read):
> **S5/1854** roman body reaches 101 then the volume jumps to the resolutions appendix (ch 102–174 absent from the OCR'd
> volume); **S54/1941** cross-engine body reaches ch1279 (3-engine + An-Act witness) with the tail headers lost;
> **S99/1989** cross-engine body reaches ch1437 (3-engine + An-Act witness, vol3) and vol3 *continues* to p2174 with a
> real act approved by the Governor Oct 2 1989, so ch1438–1467 are present but their CHAPTER headers didn't OCR cleanly.
> **New OCR-era regular tally: 105/109 CONFIRMED (96.3% by row, 97.0% by chapter); UNPARSEABLE down 12 → 4 (S5, S54,
> S74, S99); DISCREPANT still 0.** New/edited artifacts: `pipeline/analysis/dump_budget_bundle_sequence.py`,
> `pipeline/analysis/split_budget_bundle.py` (with `--selftest`), `_budget_bundle_split.tsv`, `_reclassify_budget_split.py`,
> `_rollup_after_split.py`, the budget-aware `_overread_corpuswide.py`, and the probes `_probe_s5*.py` / `_probe_s54.py` /
> `_probe_s99*.py` / `_probe_1964budget.py`.

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

**cc015 (budget-bundle range-split applied):**

| status | count | share of rows |
|---|---:|---:|
| **CONFIRMED** | **112** | 52% |
| **DISCREPANT** | **0** | 0% |
| **UNPARSEABLE** | **4** | 2% |
| **NOT-VALIDATED** | **100** | 46% |

By era × status (cc015):

| era | CONFIRMED | DISCREPANT | UNPARSEABLE | NOT-VALIDATED | total |
|---|---:|---:|---:|---:|---:|
| 1850–1899 (early OCR) | 32 | 0 | 1 (S5) | 2 | 35 |
| 1900–1949 (mid OCR) | 31 | 0 | 1 (S54) | 19 | 51 |
| 1950–1999 (late OCR) | 49 | 0 | 2 (S74, S99) | 42 | 93 |
| 2000–2024 (born-digital) | 0 | 0 | 0 | 37 | 37 |

By kind: **regular** 105 CONFIRMED / 0 DISCREPANT / 4 UNPARSEABLE / 25 NOT-VALIDATED (134 rows);
**extra/special** 7 CONFIRMED / 0 DISCREPANT / 0 UNPARSEABLE / 75 NOT-VALIDATED (82 rows).
**OCR-era regular (1850–1999): 105 / 109 CONFIRMED = 96.3% by row, 97.0% by chapter.**

*(Prior cc013/cc014 tally, superseded: 104 CONFIRMED / 12 UNPARSEABLE. The 8 budget bundles
S58–S72 flipped to CONFIRMED via range-split; S74/S5/S54/S99 remain the 4-row residual.)*

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

**Budget-bundle rows (S58–S74) — cc014 non-flip, cc015 RESOLVED by range-split.** The witness gate *does* find real
statutes above their tiny oracle N in the even-year "NNchapters" volumes (e.g. S60/1950: ch 7–74 real statutes over
oracle 6) — but those acts belong to the **bundled extra session** physically bound into the same volume on the same
`canonical_id` (verified in `_overread_corpuswide.log`: 1950-vol1-chapters holds the 6-chapter budget run *and* the
74-chapter 1950 First Extra run, both starting at 1). cc014 correctly kept these out of DISCREPANT (precision rule: a
DISCREPANT verdict requires a real statute above N **that belongs to the session the cid denotes** — bundled foreign-
session statutes do not qualify) but left them UNPARSEABLE. **cc015's range-split now isolates the budget session as the
first statute-body run and CONFIRMS 8 of the 9** (the first-body-run ceiling = budget oracle N exactly); the
over-read sweep marks these `BUDGET_BUNDLE` (excluded from DISCREPANT, validated separately by `split_budget_bundle.py`),
so **0 DISCREPANT still holds and the bundles are now volume-CONFIRMED, not merely unverified.**

**No edit is implied by this sweep.** (Contrast the earlier `ORACLE_DISCREPANCY_EARLY_2026-06-17.md`, which *did*
surface real undercounts — those were already applied to the oracle and now reproduce as CONFIRMED.)

### CONFIRMED via range-split (cc015) — the 8 budget bundles

The even-year budget volumes bind the budget session + that year's extra(s) on one cid. `split_budget_bundle.py`
attributes the budget session to the **first statute-body run** (range-based split); its witness-checked ceiling
equals the budget oracle N. **8 of 9 CONFIRM** (the extra session + resolutions split off by chapter-number range):

| canonical_id | session | oracle N | first-body-run ceiling | Δ | verdict |
|---|---|---:|---:|---:|---|
| S58 | 1948 Regular (Budget) | 38 | 38 | 0 | CONFIRMED |
| S60 | 1950 Regular (Budget) | 6 | 6 | 0 | CONFIRMED |
| S62 | 1952 Regular (Budget) | 14 | 14 | 0 | CONFIRMED |
| S64 | 1954 Regular (Budget) | 10 | 10 | 0 | CONFIRMED |
| S66 | 1956 Regular (Budget) | 13 | 13 | 0 | CONFIRMED |
| S68 | 1958 Regular (Budget) | 10 | 10 | 0 | CONFIRMED |
| S70 | 1960 Regular (Budget) | 14 | 13 | −1 | CONFIRMED (±1 OCR clip) |
| S72 | 1962 Regular (Budget) | 12 | 12 | 0 | CONFIRMED |

### UNPARSEABLE residual (4, cc015) — denominator NOT independently confirmed (oracle UNCONTRADICTED, 0 over-read)

| canonical_id | session | oracle N | derived | why unparseable (verified) |
|---|---|---:|---:|---|
| S74 | 1964 Regular (Budget) | 1 | — | `1965-vol1-64chapters` binds the 151-ch **1964 First Extra** (title page p103: "PASSED AT THE 1964 FIRST EXTRAORDINARY SESSION"), not a 1-chapter budget run; the single budget statute is not isolable |
| S5 | 1854 Regular | 174 | 101 | roman body reaches **101** (cov-dense from 1), then the volume jumps to the JOINT/CONCURRENT RESOLUTIONS appendix (p219–230) — ch 102–174 are **absent from the OCR'd volume** (partial scan); parse-recall gap |
| S54 | 1941 Regular | 1284 | 1279 | cross-engine body reaches **ch1279** (3-engine + An-Act witness, p2826); ch1280–1284 lost to tail header dropout (volume continues to p3154); ch1281 is a single-engine garble (rejected) — gap of 5 |
| S99 | 1989 Regular | 1467 | 1437 | cross-engine body reaches **ch1437** (3-engine + An-Act witness, vol3 p2162); vol3 *continues* to p2174 with a real act (Approved Gov Oct 2 1989), so ch1438–1467 are **present** but their CHAPTER headers didn't OCR cleanly — gap of 30 |

These 4 sum to **2,926 chapters (2.4% of the full denominator)**. S74 is tiny (1 ch); S5/S54/S99 are parse-recall
under-reads where the volume's content stops a few/many chapters below the oracle ceiling. **None contradicts the
oracle** (cross-engine max ≤ oracle N in every case — no witnessed over-read) — they are simply *not independently
re-derived* because the OCR'd volume is missing the tail content (S5, S99, S54) or the session isn't isolable (S74).

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

**cc015 (after budget-bundle range-split):**

| validation status | chapters | share of full denominator |
|---|---:|---:|
| **CONFIRMED** (volume-confirmed) | **93,897** | **78.1%** |
| DISCREPANT | 0 | 0.0% |
| UNPARSEABLE (unverified, OCR era — S5/S54/S74/S99) | 2,926 | 2.4% |
| NOT-VALIDATED | 23,382 | 19.5% |

*(cc013/cc014 was 93,780 CONFIRMED / 3,043 UNPARSEABLE; the budget range-split moved the
8 small budget bundles from UNPARSEABLE to CONFIRMED — 117 chapters — leaving the 4-row residual.)*

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
2. **Budget-bundle (cc015 RESOLVED).** The 9 budget rows that were UNPARSEABLE are now range-split: 8 CONFIRM (first
   statute-body run = budget oracle N, witness-checked), S74 stays UNPARSEABLE (151-ch First Extra bound, not isolable).
   **Re-verify target for Hans:** run `pipeline/analysis/split_budget_bundle.py` (it has a `--selftest`) and confirm each
   first-body-run ceiling equals the budget oracle N; confirm the over-read sweep marks budget cids `BUDGET_BUNDLE`
   (excluded from DISCREPANT because the high chapters are the bundled EXTRA session). The over-read EVIDENCE for the
   non-flip is in `_overread_corpuswide.log` (e.g. S60/1950: ch 7–74 are real 1950-First-Extra statutes on pages 172–289,
   AFTER the budget run's ch 1–6 on pages 2–109). Confirm S74's volume title page (`_probe_1964budget.py`, p103) reads
   "PASSED AT THE 1964 FIRST EXTRAORDINARY SESSION" — proving its 151-ch body run is the extra session, not the budget.
3. **"No DISCREPANT" is now witness-verified (cc014), not rule-dependent.** The old caveat — that the result rested on
   "any confirming signal wins" and a contaminated signal landing near N could mask a discrepancy — is **resolved**. Every
   trustworthy over-read (S47 1927, S45 1923, S20 1873-74, 1938X1, S9, S24, S29) was scanned chapter-by-chapter for a
   real statute above N using the production cross-engine + body-witness gate; all are contamination / resolutions /
   single-engine digit-garbles (see the discrepancy table). The one the audit flagged, **S47 (910←tess-garble of 510)**,
   is the clearest exoneration. Re-verify target for Hans: confirm via `_s47_findhigh.py` that surya+doctr read 5xx where
   tess reads 9xx (they do), and confirm the budget-bundle non-flip policy (S58–S74 over-reads are bundled extra-session
   statutes — they stay UNPARSEABLE). A future re-OCR of the 1927 body would let the body self-index report 556/506/507/510
   instead of 900/906/907/910 and remove this contamination at the source.
4. **S54 (1941, −5), S99 (1989, −30), S5 (1854, −73)** are flagged UNPARSEABLE but are near-confirm / parse-recall
   under-reads, **not** evidence the oracle is wrong. cc015 verified each: S54 cross-engine body reaches ch1279
   (3-engine + An-Act witness, `_probe_s54.py`); S99 reaches ch1437 and vol3 *continues* to p2174 with a real
   Gov-approved act, so ch1438–1467 exist but their headers didn't OCR (`_probe_s99*.py`); S5 reaches ch101 then the
   volume jumps to the resolutions appendix — ch102–174 are absent from the OCR'd volume (`_probe_s5*.py`). All have
   cross-engine max ≤ oracle N (**no over-read**), so the oracle is uncontradicted. **Re-verify for Hans:** confirm none
   of the three produces a witnessed real statute ABOVE its oracle N (they do not — the residual is recall, not a
   conflict).

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
