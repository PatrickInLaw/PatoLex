# Pipeline Ingest Benchmarks

**Generated:** 2026-06-01  
**Task:** cc003 Gate-B benchmark spike  
**Script:** `scripts/ingest/benchmark-pipeline.ts` (TypeScript/postgres-js spike — NOT the eventual C# production pipeline)  
**Database:** PostgreSQL 16, local (`localhost:5432/patolex`)

---

## Summary

End-to-end ingest + materialize + validate of the 1872 Penal Code baseline (720 sections)
plus the 1883 amendment events (12 directives across 3 acts) ran in **541 ms avg over 3 runs**
(std dev 32 ms). The pipeline is local-machine DB-bound; network/serialization overhead dominates
for small batches. See ETA section for full-corpus projections.

---

## Input Files Used

| File | Description |
|------|-------------|
| `pc_extract_1872.json` | 1872 CA Penal Code baseline — 720 sections, section_num → text |
| `method_a_final_validation.json` | Method-A spike output — 12 directives found (9 in results; 3 reconstructed from `directives_1883.json`) |
| `directives_1883.json` | Partial earlier extraction — used to reconstruct §§627, 628, 629 repeal events not in `method_a_final_validation` results |
| `pc_extract_1883.json` | 1883 annotated edition — 596 sections — ground truth for validation |
| `pc_extract_1881.json` | 1881 annotated edition — loaded but not used in this run (reserved for cross-check) |

---

## Per-Stage Benchmark (Average of 3 Runs)

Tables were `TRUNCATE ... RESTART IDENTITY CASCADE` between runs.  
Batch strategy: `jsonb_to_recordset` with batch size 100 (postgres-js template literal with `sql.json()` typed parameter).

**Cold-connect note:** Run 1 included a cold DB-connection cost (~22 ms overhead) that runs 2-3
did not. The 541 ms 3-run average includes this cold-connect hit; steady-state (runs 2-3 only)
is ~519 ms. The per-unit rates in the table below are computed from the 3-run average.

| Stage | Rows | Avg Wall ms | ms/unit | Notes |
|-------|------|-------------|---------|-------|
| ingest-sources | 4 | 2.0 | 0.51 | Single multi-row INSERT |
| ingest-enactments | 4 | 1.2 | 0.31 | Single multi-row INSERT |
| ingest-provisions | 1,440 | 19.6 | 0.014 | 720 provision + 720 designation_history rows; 16 round-trips (batch=100) |
| ingest-change-events | 732 | 46.4 | 0.063 | 720 1872 enact + 12 1883 amend/repeal/add; 8+1 = 9 round-trips |
| materialize | 732 | 146.2 | 0.200 | Single SQL CTE + LEAD() fold; no per-provision round-trips |
| validate | 596 | 324.3 | 0.544 | JS-side CER (Levenshtein) over 596 GT sections; DB read is fast, CPU-bound in Node |
| **TOTAL** | | **540.6** | | |

**Per-run totals:** 584 ms, 511 ms, 527 ms. Std dev: 32 ms.

### Row Counts Ingested (Final State)

| Table | Rows |
|-------|------|
| source_document | 4 |
| enactment | 4 |
| provision | 726 (720 baseline + 6 late-added sections) |
| designation_history | 726 |
| change_event | 732 (720 enact + 12 amend/repeal/add) |
| provision_version | 732 |

---

## Validation Results (1883-12-01 Query Date vs. pc_extract_1883.json)

Query date: `1883-12-01` (after all three 1883 amendment acts became operative).  
GT sections compared: 596.

| Category | Count | Pct of GT | Interpretation |
|----------|-------|-----------|----------------|
| EXACT | 11 | 1.8% | Character-identical match (both sources happen to have same OCR) |
| NEAR | 1 | 0.2% | Match after whitespace normalization |
| PARTIAL | 12 | 2.0% | CER < 0.30 (same content, OCR noise) |
| MISMATCH | 309 | 51.8% | CER ≥ 0.30 — expected (see note below) |
| NULL_TEXT | 3 | 0.5% | Correctly captured repeals (§§299, 300, 301) |
| NO_PV | 260 | 43.6% | GT section has no provision_version at query date — explained below |

**Why 260 NO_PV?** The 1883 annotated edition (596 sections) contains many sections added to the
Penal Code between 1872 and 1883 that are not present in the 1872 baseline extract. Our pipeline
only ingested the 720 sections from the 1872 extract; sections added in 1873-74, 1875-76, and
other intervening sessions are not yet in the database. The NO_PV count (260/596 = 43.6%) is an
artifact of the limited scope of this benchmark, not a pipeline bug.

**Why 309 MISMATCH (92.8% of comparable sections)?**  
This was expected and does NOT indicate a pipeline bug. The 1872 OCR source
(`penalcodecalifo00burcgoog`, ABBYY-djvu, ~8% CER) and the 1883 annotated edition
are different source artifacts with different OCR renderings of the same sections.
Even for sections that were not amended between 1872-1883, the text strings differ
due to: (a) OCR transcription differences, (b) annotation formatting added in the
1883 edition, (c) cross-reference numbers printed in the 1883 margin text.
The **structurally correct** validations are the 3 NULL_TEXT matches (repeals confirmed)
and the 11+1+12 = 24 EXACT/NEAR/PARTIAL matches where OCR quality happened to align.

**What this validation DOES and DOES NOT prove:**

The text-similarity comparison above does NOT prove reconstruction fidelity. It compares
the 1872 OCR text (carried forward by the pipeline) against a *different edition's* OCR
(the 1883 annotated volume). Since the two sources are independently OCR'd, any divergence
is an unresolvable mix of reconstruction error and OCR noise — the comparison cannot
separate the two. A high MISMATCH rate here is expected and uninformative about whether
the pipeline applied change events correctly.

**What IS genuinely proven by this benchmark:**
- **Schema mechanism:** point-in-time queries return correct date-ranges (verified on
  §§299/300/301 repeals, which appear as NULL_TEXT at `1883-12-01` as expected).
- **GiST exclusion constraint:** enforces non-overlapping `provision_version` dateranges
  (no constraint violations observed).
- **Recursive-CTE lineage query:** traverses the act_section → code_section edge correctly
  (2.8 ms, correct result set).

**What is NOT yet proven:** text-accuracy of the OCR + parse output. Real text-accuracy
validation requires same-source ground truth (e.g., a human-gold transcription of the
same scan) or a human spot-audit. The 1883 annotated edition is NOT suitable for this
because it is a different artifact with its own OCR rendering.

---

## Batch Strategy Notes

| Stage | Strategy | Round-trips | Why |
|-------|----------|-------------|-----|
| Provisions | `jsonb_to_recordset`, batch=100 | 16 | Need RETURNING id to build sec→provId map |
| Change events (enact) | `jsonb_to_recordset`, batch=100 | 8 | 720 rows / 100 per batch |
| Change events (amend) | `jsonb_to_recordset`, single batch | 1 | Only 12 rows |
| Materialize | Single SQL CTE with LEAD() | 1 | Entire fold in one server-side statement |
| Validate | One SELECT + JS CER loop | 1 DB + N CPU | DB read fast; CER is JS-side CPU |

The materialize stage (1 round-trip for 732 rows) is clearly the right approach.
The validate stage is 324 ms avg because the Levenshtein CER is computed in Node.js
for 596 string pairs — this is **not** a production code path (validation is offline tooling).

---

## ETA Extrapolation

### Assumed Full-Corpus Scale

These are **planning estimates** with significant uncertainty — labeled as such:

| Corpus element | Estimate | Confidence |
|----------------|----------|------------|
| CA codes covered | ~29 | Medium |
| Current sections (modern era) | ~150,000 | Medium |
| Historical change-events, 1991–present (leginfo digital) | ~500,000 | Low-medium |
| Historical change-events, 1872–1991 (session-law reconstruction) | ~1–3 million | Low |
| Total change-events, full corpus | ~1.5–3.5 million | Low |
| Provision-version rows (roughly 2–4x change-events) | ~3–14 million | Very low |

### Stage Projections (from measured per-unit rates)

| Stage | Per-unit rate | Full corpus (150K sections) | Full corpus (3M events) |
|-------|--------------|------------------------------|--------------------------|
| ingest-provisions | 0.014 ms/row | **4.1 s** (2×150K rows) | n/a |
| ingest-change-events | 0.063 ms/row | n/a | **3.2 min** |
| materialize | 0.200 ms/version | n/a | **10–47 min** (3M–14M versions) |
| validate (offline) | 0.544 ms/section | **1.4 min** (150K sections) | n/a |

**Important caveats on extrapolation:**

1. **These rates are localhost single-machine measurements.** Real throughput depends on
   connection latency, batch size optimization (larger batches = better throughput),
   and whether a PgBouncer pooler is in the path.

2. **The materialize stage will not scale linearly** at 3M+ events. The single CTE approach
   works at 732 rows; at millions of rows it will need to be chunked by code/session or
   run as a streaming fold. The 146 ms for 732 rows = 0.20 ms/row, but query plan costs
   grow with the table size.

3. **Stages NOT measured here** (acquire/OCR/parse):
   - Internet Archive download rate: **measured 4.26 MB/s** (1850 vol, 30.67 MB in 7.2 s);
     ~50–200 MB/min per volume is a reasonable planning range (network-bound).
   - OCR: see **OCR ETA** section below for measured production rates and full-corpus estimates.
   - Parse (rule-based NLP): ~5–30 ms/directive
   - These stages dominate the wall-clock time for pre-1992 historical depth.
   The ingest pipeline itself is fast relative to data acquisition.

4. **The leginfo modern-era XML path (1991–present) is much faster**: structured XML
   import will skip OCR entirely and run at ~0.01–0.02 ms/section for parse + ingest.
   The ~500K modern-era change-events would ingest in under 1 minute.

### OCR ETA (Pre-1992 Session-Law Corpus)

**Measured production OCR rates (on real source material):**

| Engine | Rate | Notes |
|--------|------|-------|
| Tesseract 5, CPU (first pass) | **1.1 sec/page (54 p/min)** | Measured on 1850 Chief Clerk scan (~4,376 chars/page). Production first-pass engine. |
| qwen2.5vl, 5090 GPU (second-opinion) | **5 sec/page (12 p/min)** | Measured during prior spike. Runs in parallel with Tesseract as the ensemble pass. |

**Page-count estimate for full pre-1992 corpus** (ESTIMATE — not yet inventoried in detail):
~150,000–300,000 pages covering session-law volumes + annotated editions needed for
the 1849-1991 reconstruction. This is a planning estimate with medium-low confidence.

**Single-thread OCR ETA at 54 p/min:**

| Page count | Single-thread (Tesseract) | Parallelized (8 CPU cores + 2 GPUs, rough) |
|------------|--------------------------|---------------------------------------------|
| 150,000 pages (low estimate) | ~46 hours (~2 days) | ~6–8 hours |
| 300,000 pages (high estimate) | ~93 hours (~4 days) | ~12–16 hours |

**Honest headline: OCR is the dominant cost — roughly 2–4 days single-thread, well under that
parallelized across multiple CPU cores and both GPUs. "Days to weeks" was based on failed/slow
VLM models tested during research (30–120 sec/page); those figures do NOT reflect the production
Tesseract 5 engine and should not be used for planning.**

The qwen2.5vl second-opinion pass adds ~5x the per-page cost but runs in parallel with Tesseract,
so wall time is bounded by the faster CPU pass plus GPU queue drain — not additive.

### First-Cut ETA Summary

| Phase | Bottleneck | Estimated wall time |
|-------|-----------|---------------------|
| Modern era (1991–present, ~500K events) | leginfo XML ingest | **< 5 minutes** |
| Historical reconstruction (1872–1991, ~2M events) | OCR + parse, then ingest ~7 min | Ingest-only: **< 10 min**; OCR: **~2–4 days single-thread, < 1 day parallelized** |
| Full materialize (14M provision-version rows, pessimistic) | DB write + GiST index | **< 1 hour** (rough lower bound — see caveat 2 above; single-CTE will need chunking at this scale) |
| Full corpus from scratch (data already acquired) | Ingest + materialize | **< 2 hours** (excluding OCR) |
| Data acquisition + OCR (pre-1992 session laws) | CPU/GPU OCR | **~2–4 days single-thread; well under that parallelized** |

The ingest pipeline is NOT the bottleneck. OCR is the bottleneck, but it is tractable at measured rates.

---

## Assumptions and Caveats

1. **1872 operative date = 1872-07-01.** Standard CA Penal Code effective date. Well-established.
2. **1883 "effective immediately" = operative on chaptered date.** Pre-1900 CA practice; correct.
3. **Chapter numbers for 1883 acts:** ch.2 confirmed (from `directives_1883.json` "chapter:II").
   ch.38 and ch.92 are ESTIMATES based on session sequence position. The `(operative_date,
   chapter_number, in_act_order)` ordering logic for §9605 conflict resolution is implemented
   correctly in the schema, but has **NOT been stress-tested** — the 12-event sample contains
   no two acts amending the same section on the same operative date, so the disambiguation
   path never actually fired. Correctness of tie-breaking at scale remains unverified.
4. **Sections 626, 627, 628, 629, 632, 636:** NOT in the 1872 baseline extract. These game/fish
   sections were added to the PC in an intervening session (likely 1873-74 or 1875-76). The
   pipeline created "stub" provisions for them when processing the 1883 amend/repeal events.
   The amend/repeal change_events for these sections have no prior 1872 baseline row — they
   represent the state of law at 1883 with limited pre-history depth. **Known data-quality
   issue:** these stub provisions have `designation_history.valid_range` starting `1872-07-01`,
   which is incorrect — they did not exist until a later session. The `valid_range` start date
   should be set to the actual add-event date. Flagged for correction in the real build.
5. **new_text for 1883 amend/add events = `rec_snippet` from method_a_final_validation.json.**
   These are PARTIAL OCR fragments (truncated at 200 chars in the validation output), not full
   section texts. The production pipeline must extract complete section text from the session
   law source.
6. **Sections 627/628/629 repeals** are from `directives_1883.json` (not present in
   `method_a_final_validation.json` results, which only covers sections that could be
   evaluated against the GT). These are correctly included.
7. **Validate stage wall time (324 ms)** includes JS-side Levenshtein CER for 596 string pairs.
   This is offline QA tooling, not a production code path.

---

---

## 1850 Pre-Code Act Ingestion

**Task:** cc003 1850-start sample ingested (first exercise of `act_section` + `lineage_edge`)  
**Script:** `scripts/ingest/ingest-1850-acts.ts`  
**Input:** `C:\Users\PatrickKolasinski\PatoLex-scratch\gate-b-1850\acts_1850_sample.json` (11 acts)  
**Date:** 2026-06-01  
**Strategy:** Additive — no TRUNCATE; act_section rows added to existing code_section data.  
**Note:** Single run (not averaged). Stage 1 (ingest-source) includes ~48 ms cold DB-connection overhead.

> **TIMING PROVENANCE CAVEAT:** The `ingest-1850-acts.ts` script crashed before writing its
> timing JSON output. The per-stage millisecond figures below were hand-transcribed from stdout
> and then backfilled via `patch-benchmark-1850.ts`. **Treat these timings as UNVERIFIED
> estimates, not measured benchmarks.** The 1850 DB data itself (rows inserted, schema
> state) is complete and correct; only the timing provenance is weak.

### Per-Stage Benchmark (Single Run)

| Stage | Rows | Wall ms | ms/unit | Notes |
|-------|------|---------|---------|-------|
| ingest-source | 1 | 50.0 | 50.0 | Single INSERT; cold connection overhead dominates |
| ingest-enactments | 11 | 2.3 | 0.21 | Single `jsonb_to_recordset` batch |
| ingest-provisions | 22 | 15.8 | 0.72 | 11 provision + 11 designation_history rows |
| ingest-change-events | 11 | 7.3 | 0.66 | One `enact` event per act, `trust_level='ocr_uncertain'` |
| lineage-edge | 1 | 3.1 | 3.1 | One synthetic demo edge + query to resolve enactment FK |
| **TOTAL** | | **78.5** | | |

Excluding cold-connect overhead (stage 1 = 2 ms warm), estimated steady-state total: ~30 ms for 11 acts.

### Rows Added (Additive to Existing Data)

| Table | Rows Added |
|-------|-----------|
| source_document | 1 |
| enactment | 11 |
| provision (act_section) | 11 |
| designation_history | 11 |
| change_event | 11 |
| lineage_edge | 1 |

### Final DB State After 1850 Ingest

| unit_type | count |
|-----------|-------|
| act_section | 11 |
| code_section | 726 |

Total change_events: 743 (732 existing + 11 new)  
Total lineage_edges: 1

### Lineage Edge

The 1850 sample contains **civil governance acts only** (State Translator, Attorney General office, public funds, Sacramento City incorporation, pilot regulations, county creation, court supersession, etc.) — none are a subject-matter predecessor of a specific 1872 Penal Code section in the ingested dataset.

**A SYNTHETIC DEMO EDGE was created** (as specified in the task):

- **Predecessor:** `Stats. 1850 ch. 23` — "An Act to supersede certain Courts" (provision id=736, unit_type=`act_section`)
- **Successor:** `Penal Code § 1` — structural provision (provision id=1, unit_type=`code_section`)
- **edge_type:** `repeal_reenact`
- **note:** `SYNTHETIC DEMO — mechanism validation only, not a real legal disposition`

The edge exercises the `lineage_edge` FK constraints, the `lineage_edge_type` enum, and the recursive CTE traversal. It makes no legal claim.

### Recursive CTE Lineage Query

The bidirectional ancestor+descendant query (see `scripts/ingest/query-1850-lineage.ts`) uses two separate recursive CTEs (`descendants` and `ancestors`) unioned together — required because PostgreSQL does not allow a recursive reference inside a `UNION` in the non-recursive term. Query ran in **2.8 ms**, returned **2 rows**:

```
provision_id | current_designation    | unit_type    | edge_type       | linked_from         | direction  | depth
-------------|------------------------|--------------|-----------------|---------------------|------------|------
1            | Penal Code § 1         | code_section | repeal_reenact  | Stats. 1850 ch. 23  | descendant | 1
736          | Stats. 1850 ch. 23     | act_section  |                 |                     | start      | 0
```

The query correctly traverses from the 1850 act_section node to its descendant Penal Code provision. The ancestor walk returns no additional rows (the synthetic act_section has no predecessors). **The recursive CTE design works as intended.**

### GiST Exclusion Constraint

No overlapping `provision_version` dateranges were detected. The GiST constraint did not fire spuriously.

### Notes and Caveats

1. **act_section provisions have no materialize stage** — they have no successor amendment events in this dataset, so `provision_version` rows are not needed for them.
2. **trust_level = `ocr_uncertain`** for all 1850 rows (CER estimate 5–15%).
3. **chapter 11 (Attorney General act)** had a blank `approved_date` in the source JSON; `operative_date` defaulted to `1850-01-01`.
4. **Lineage edge is SYNTHETIC** — clearly labeled. No legal claims are made.
5. **`clean_channel = true`** for the 1850 source document — the specification required it even though the OCR quality is uncertain.

---

## Known Data-Quality Issues in This Sample (Found by Adversarial Review)

These are issues to resolve in the real build, not schema bugs. They indicate places where the
benchmark data should not be used as a positive correctness proof.

### (a) §1388 contradictory events

§1388 has both an 1872 baseline `enact` event (from `pc_extract_1872.json`) and an 1883 `add`
event (from `method_a_final_validation.json`). These are mutually contradictory: a section
cannot be both present in the 1872 baseline *and* added fresh in 1883.

Likely cause: either the Method-A spike mislabeled an 1883 `amend` directive as an `add`, or
the 1872 extract wrongly included §1388 (e.g., OCR hallucination or section-numbering artifact).

**Do NOT use §1388 as a correctness proof.** Flag for human review before production ingest.

### (b) 16 baseline sections with NULL text (§§894–909)

Sixteen sections from the 1872 baseline (§§894–909) were ingested with `NULL` text due to
gaps in the OCR/extract in `pc_extract_1872.json`. In a point-in-time query these silently
appear as repeals. The schema mechanism is fine; the source data is incomplete. These must be
re-extracted or manually filled before using this range in production.

### (c) Stub provisions with incorrect `valid_range` start dates

Sections added after 1872 (§§626–629, 632, 636) were created as stub provisions with
`designation_history.valid_range` starting `1872-07-01`. This is wrong — they did not exist
until a later session. The `valid_range` start date must be set to the actual add-event
operative date when those change events are ingested. (Also noted in Assumptions §4 above.)

---

## Revision History

| Date | Change |
|------|--------|
| 2026-06-01 | cc003: Initial benchmark from 1872 baseline + 1883 amendments (3 runs) |
| 2026-06-01 | cc003: 1850 pre-code act ingestion — first act_section + lineage_edge exercise |
