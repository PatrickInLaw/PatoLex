# Correction & Display Layer — Architecture Sketch + Open Decisions

**Status:** DESIGN — decisions to be finalized BEFORE corpus finalization / ingestion / UI.
**Date opened:** 2026-06-11 (cc007). Owner: Patrick.

## The principle (settled)
The OCR `consensus_text` is the **immutable source-of-record**. Nothing is ever
destructively edited. Every correction — deterministic, model/vision, OR community —
is stored as a **reversible overlay** with full provenance, and is auditable/revertible.

## The shape (Patrick's proposal, 2026-06-11)
A **single materialized "display" layer** per text unit holds the *current best* text,
with the **layer stack stored behind it** for review/revert:

```
display_text  =  original_OCR  +  [ layer 1: deterministic auto-correct ]
                               +  [ layer 2: model / vision resolution   ]
                               +  [ layer 3: community wiki edits         ]
```

- **99.99% of reads hit only the materialized display layer** (fast, denormalized,
  full-text indexed). The derivation history is present but cold — pulled only for
  audit / review / revert.
- Each overlay entry carries provenance: `method`, `confidence`, `actor`,
  `timestamp`, `original_value`, `corrected_value`, and a stable anchor.

## Layers (sources, in precedence order — to confirm)
1. **Original OCR** (immutable).
2. **Deterministic** (Pass A rejoin, scored de-merge, corpus-freq spell) — high precision subset only.
3. **Model / vision** (LLM-with-context + vision-on-scan) for the hard residual.
4. **Community wiki edits** (the crowdsource-correction feature; trust-tiered, moderated —
   see `CROWDSOURCE_CORRECTION.md`).

## OPEN DECISIONS (must resolve before ingestion)
1. **Anchor granularity.** Token-position is fragile across a re-OCR; prefer anchoring
   corrections to a stable unit (char span within a versioned page? content hash + offset?).
   This determines whether corrections survive a future re-OCR pass.
2. **Materialization & sync.** How/when the display layer is rebuilt when any underlying
   layer changes (on-write vs scheduled projection). Keep it denormalized for serving + FTS.
3. **Layer precedence / conflict resolution.** When two layers touch the same span
   (e.g. deterministic said X, a community editor says Y) — what wins, and how is the
   loser preserved/surfaced?
4. **Provenance & reversibility schema.** Exact columns; one-row revert guarantee;
   audit trail for legal defensibility.
5. **Search semantics.** FTS indexes the corrected display layer, but must the *original*
   also be searchable (attorney wants "what the scan literally said")? Likely both.
6. **Trust tiers for community edits.** Who can edit, moderation queue, reputation —
   intersects the existing crowdsource design.
7. **Point-in-time interaction.** Corrections are about *text fidelity*; the statute's
   *as-of-date* versioning is a separate axis. Confirm they compose cleanly (a correction
   applies to a source page; the page underlies many point-in-time statute states).

## Layer-2 in practice — chapter-number vision resolution (RESULTS, 2026-06-11, cc007)
The first real layer-2 (model/vision) artifact is the **chapter-number** overlay. The
deterministic chapter pass (`chapter_corrections.py`, monotonic-sequence reconstruction)
left **215 REVIEW** garbled chapter numbers it would not silently override. Those were
resolved by **reading the source-page scans directly** — Claude vision validated against
Sonnet-vision-at-scale:

- **Validation gate:** Sonnet returns the *printed numeral as it appears* (e.g. `CCCCXLIII`);
  Roman→int conversion is done deterministically in `aggregate_chvis.py` (Sonnet reads
  reliably but does Roman arithmetic unreliably). On the 7-case overlap with Claude's own
  hand-reads, **agreement was 7/7** — the basis for trusting the Sonnet batch.
- **Result:** **129 of 215 resolved** (61 first batch / 68 second batch) →
  `run-logs/chapter_vision_final.tsv` (`vol, order, resolved_chapter, source`).
- **3 Sonnet-UNKNOWN** (1971-vol1 o1034, 1982-vol3 o72, 1999-vol4 o159): Claude read the
  staged images directly and confirmed they are **body-text pages, not chapter-heading
  pages** — the parse's `source_page` for these points one or more pages off the heading.
- **86 still open** = 81 whose volume bundle has no cached page image + 3 wrong-page + 2
  out-of-range. These are **render-from-PDF jobs, NOT lost scans** (see finding below).

**Finding (root cause of "missing" scans — corrected 2026-06-11):** the per-volume OCR
output bundle **does NOT retain page images**. The pipeline renders the source PDF to a
`pages_prep_gray` working intermediate, runs consensus OCR, banks only the *text* artifacts
(`ocr_consensus/`, `parsed_acts_fixed.json`, `page_classification.json`, `sha256.txt`), then
**purges the page rasters to reclaim disk**. Early-processed volumes (1850–1875) have already
been cleaned, which is why their REVIEW heading pages couldn't be staged. **The source scans
are intact** in the master archive `…\PatoLex-scratch\chief-clerk-archive\{vol}_Statutes.pdf`
(verified: 1873-74 = 1086 pp, 1869-70 = 1027 pp, 1867-68 = 828 pp) — any heading page is
**re-renderable on demand with PyMuPDF**. So the remaining limit is a cheap local render +
re-run of the Sonnet-vision pass, **not** image loss or model capability. When applied, vision
results land as overlay tier **`VISION`** keyed by `(source_document_id, in_act_order)` (same
key as the deterministic overlay), precedence above deterministic.

**Operational note:** `chief-clerk-archive\` is the durable source-of-record for the scanned
historical volumes; per-volume `production-*` bundles are *derived text* and intentionally
image-free. Never treat an absent `pages_prep_gray` as data loss — render from the archive PDF.

## Chapter REVIEW closeout — 214/215 (RESULTS, 2026-06-11, cc007)
The 86 open REVIEW cases were finished by **rendering each heading page from the archive PDF**
(`source_page − 1` = PDF page index; calibrated 1:1 on 1862 = 660pp == 660 prep images) and
resolving deterministic-first per Patrick's direction:
- **Deterministic re-OCR (fresh Tesseract on the rendered heading, accept only if a clean
  numeral fits the clean-neighbour bracket):** RELIABLE for **modern Arabic** chapters
  (1971-vol1 o1034 = 1235, 1982-vol3 o72 = 830 — both confirmed by eye), but **NOT for
  19th-century Roman numerals** — single-engine Tesseract drops strokes (`CXIII`→`CXI`),
  and range-fit lets the wrong value through (caught a false 1869-70 o82=111 where the page
  says 113). So deterministic is gated to Arabic-numeral volumes only; Roman → vision.
- **Vision (Sonnet, 4 agents over 84 rendered pages) + bracket validation:** 48 answers fit
  the clean-neighbour bracket and were accepted; **35 were flagged by the bracket as not
  fitting — and the bracket was right**: those were Sonnet stroke-drops on long Roman
  numerals (`CCXLI`→`CXLI` dropping a C, `CXCIII`→`XCIII`, etc.). All 35 were hand-read by
  Claude against the page (the bracket usually pinpointed the value). This is the key method
  result: **vision + sequence-bracket cross-validation catches vision misreads that neither
  signal catches alone.**
- **Total: 215 of 215 resolved** → `run-logs/chapter_corrections_GRAND.tsv` (129 first
  campaign + 86 this round: 48 vision-fit, 36 hand-read, 2 Arabic-tesseract).
- **`1883-84-regular` o42 — initially mis-called "missing source," actually a resolver bug
  (corrected 2026-06-11).** The render step's `resolve_pdf()` mapped the volume to its source
  PDF by *filename keyword* (preferring `*_Statutes.pdf`), and silently grabbed the 15-page
  `1883-84_Statutes.pdf` — which is really the *other*, tiny bundle (`production-1883-84`,
  2 acts). The full 1883-84 regular-session volume was OCR'd from `1883-84_Code.pdf`
  (**448 pages**, matching the bundle's `page_classification` max of 448). The file was never
  missing — the resolver picked the wrong one. o42 = **CHAPTER LIV (54)** (Napa Asylum
  amendment), read from `1883-84_Code.pdf` p329. **Fix:** map a `production-*` bundle to its
  source PDF by checking the candidate PDF's `page_count` ≥ the bundle's max `source_page`
  (and ideally == its `page_classification` body count) — NEVER by filename keyword alone.
  An integrity sweep (`verify_mapping.py`) confirmed this was the ONLY mismapped volume of
  the 16 open; every other chosen PDF's page count comfortably exceeds its bundle's max
  source_page. **Lesson: do not infer a source file from a convenient name — verify it
  against what the bundle was actually built from.**

## Text-correction overlay — Sonnet adjudication expanded + residual characterized (2026-06-11, cc007)
**Sonnet adjudication consolidated** (`text_corrections_overlay.tsv`): the 2,655 freq≥10
ambiguous types, expanded past the timid 541 both-models-agree floor to Sonnet's full
authoritative set (Sonnet wins disagreements ~27/30). Tiers: AUTO_SAFE 538 / SONNET_FIX 909 /
SONNET_NAME 257 / KEEP 587 / GARBAGE_FLAG 361 / FRAGMENT_HOLD 2. **Applied corrections: 1,704
types covering 58,700 occurrences** (vs 16,506 under the old floor). A guard holds "fixes" whose
*output* is itself a non-word (line-split fragments mis-cast as substitutions, e.g.
`gation→igation`); the wordfreq-based guard must run on a box with `wordfreq` (the 5080
orchestrator interpreter lacks it) before application.

**Residual fully characterized** (`residual_triage.tsv`, 467,978 types = 385,131 singletons +
80,192 freq 2–9 + 2,655 freq≥10). Triage categories: NAMELIKE 243,441 (52%!), TYPO 146,770,
NOISE 38,513, GARBLE 36,644, FRAGMENT 2,610.
- **Structural garbage ("eeee"/cons-run/no-vowel): 67,201 types (63,695 singletons).** NOISE+
  GARBLE (~75K) quarantine most of it, BUT **~6,785 garbage tokens still leak into TYPO (2,166)
  + NAMELIKE (4,619)** — the procedural garbage filter is real but not airtight; tighten it so
  no `eeee`-class token rides in a fixable/real bucket.
- **NAMELIKE (243K, 52% of residual) is a heuristic label — and it is MOSTLY WRONG.** A name
  gazetteer was built and MEASURED against the residual (2026-06-11): **370,183 names** = US
  Census 2010 surnames (162,253) + SSA given names (88,297) + GeoNames US place tokens (119,619)
  + ca_gazetteer. Result: **only 5,438 residual types / 17,929 occurrences (1.2% of types,
  2.4% of occ) match a real name** — and even that includes coincidental matches (`repressuring`,
  `agricul`, `meanor` = OCR fragments equal to some place token). **Correction of an earlier
  overclaim:** the name gazetteer is NOT "the highest-leverage move," and the residual is NOT
  "mostly rare real names." The 243K NAMELIKE bucket is overwhelmingly pronounceable OCR garble,
  not real vocabulary. **The residual really is mostly OCR damage / typos / line-split fragments
  — names explain only ~1–2% of it, so a name dictionary does NOT materially lower the true-error
  rate.** What the gazetteer IS good for: a high-confidence KEEP list of genuine names being
  wrongly flagged (real CA legislators `ducheny`/`karnette`/`escutia`/`migden`/`poochigian`,
  places `islais`/`fricot`) — apply it (esp. the high-freq, cross-checked subset:
  `gazetteer_keep.tsv`) so corrections never overwrite a real name, but it is a precision
  cleanup, not a residual-slasher. Gazetteer build: `build_gazetteer.py`; GNIS per-state URLs
  are dead (404/503) — GeoNames `US.zip` is the working place source.

## The residual is measured PRE-overlay (2026-06-11) — fragments like `agricul`/`ramento` are already solved
Diagnostic from Patrick ("`agricul` is a fragment of agricul|tural; `ramento` of sac|ramento — why
are these in the residual?"). Answer: they ARE line-split fragments, and the **line-reunify overlay
already fixes them** — `agricul+tural→agricultural` and `sac+ramento→sacramento` are both in
`line_split_corrections.tsv` (**11,156 rejoin corrections**, HYPHEN + NOHYPHEN + margin-interleaved).
They still appear in `residual_triage.tsv` because **the residual/garble metric was computed on text
BEFORE the line-reunify (and Sonnet text, and chapter) overlays were applied.**
- Measured: **1,104 residual types / 14,792 occ (~2% of residual) are already-solved line-split
  fragments** (`erty`, `superin`, `pensation`, `priation`, `retary`, `legisla`, `munici`, `terest`…).
- **Implication: the 0.44–0.56% "residual" OVERSTATES the true post-correction error rate** — it
  reflects none of the three computed overlays (chapter, Sonnet text 58,700 occ, line-reunify 11,156).
  A faithful residual number requires re-measuring AFTER the overlays are applied (which happens at
  mass-ingest). Until then, treat 0.56% as an upper bound inflated by already-solved items.
- **Gap this exposes:** the reunify pass still MISSES some fragments (margin-interleaved / cross-page
  / cross-column breaks where adjacency is broken). Those are recoverable by the neighbour-
  concatenation + dictionary check Patrick described (a fragment + its real neighbour → a real word).
  Worth extending the reunify pass to the missed cases before the residual is re-measured.

## The REAL number — residual AFTER overlays (2026-06-11, `post_overlay.py`)
Applying every computed overlay (Sonnet text-fix + line-reunify + gazetteer-KEEP) to the
post-ABC residual (467,978 types / 737,115 occ = the 0.5568% figure):
| disposition | types | occ |
|---|---|---|
| FIXED_sonnet | 1,704 | 58,700 |
| FIXED_linesplit | 840 | 4,138 |
| NOT_ERROR_name (gazetteer) | 5,228 | 10,444 |
| UNRESOLVED_still_suspect | 378,379 | 565,729 |
| TRUE_GARBAGE_unrecoverable | 81,827 | 98,104 |

**Post-overlay residual = 0.5014%** (663,833 occ) — down only from 0.5568%. Of that:
**0.0741% (98k occ) is confirmed unrecoverable garbage**, and **0.4273% (565k occ) is
"unresolved still-suspect"** — a MIX, NOT a measured error rate: it contains (a) rare REAL words
the gazetteer misses, (b) freq 2–9 + singleton typos never adjudicated, and (c) fragment classes
the reunify doesn't cover (below). The true error rate sits between 0.07% and 0.50% and is not
yet pinned, because the 0.43% mass is unprocessed.

## Reunify gap (Patrick directed margin/line-wrap handling — it's implemented but INCOMPLETE)
`line_split_reunify.py` DOES look beyond adjacency (`LOOKAHEAD=3`, emits margin + blank-gap
splits — 11,156 total, 1,507 margin). But the residual still carries high-freq fragments
(`superin` 464, `pensation` 346, `priation` 210, `retary` 169…), so classes slip through:
1. **Cross-page splits** — the pass scans `consensus_text` PER PAGE, so a word broken across a
   page boundary (`superin-` end of page N / `tendent` top of N+1) can never be joined.
2. **Same-line spurious-space splits** — `superin tendent` / `com pensation` on ONE line is a
   mid-word space insertion, not a line break; the line-oriented reunify can't see it. Needs a
   space-rejoin pass (adjacent same-line tokens whose concatenation is a known word, neither half
   known).
3. **Gaps > 3 lines** (long margin notes) exceed `LOOKAHEAD`.
**Honest failure:** the reunify was declared done without verifying its completeness against the
residual — the directed margin/line-wrap work exists but covers only the per-page line-break case.
Fix: sample the uncovered fragments to confirm classes, add cross-page + same-line space-rejoin +
larger lookahead, re-run, then RE-MEASURE the residual (the number above is not final).

## Cross-refs
`CROWDSOURCE_CORRECTION.md` (community tier), `SCHEMA_DESIGN` / `docs/40_SCHEMA/`
(event-sourced model), the correction pipeline (`pipeline/correction_passes.py`),
and the dictionary-membership lesson (`docs/80_PROJECT_HISTORY/lessons/`).
