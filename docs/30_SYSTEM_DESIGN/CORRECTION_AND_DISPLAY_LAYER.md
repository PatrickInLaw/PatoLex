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
- **Total: 214 of 215 resolved** → `run-logs/chapter_corrections_GRAND.tsv` (129 first
  campaign + 85 this round: 48 vision-fit, 35 hand-read, 2 Arabic-tesseract).
- **1 blocked: `1883-84-regular` o42** — the archive's `1883-84_Statutes.pdf` (and `_1E`) are
  **15-page stubs**, not the full ~600pp regular-session volume the OCR was actually built
  from. The complete 1883-84 regular-session source is missing from `chief-clerk-archive`;
  flagged as a real source-data gap to re-acquire. (The OCR consensus text for the volume
  exists; only the page scan needed to read this one garbled numeral is unavailable.)

## Cross-refs
`CROWDSOURCE_CORRECTION.md` (community tier), `SCHEMA_DESIGN` / `docs/40_SCHEMA/`
(event-sourced model), the correction pipeline (`pipeline/correction_passes.py`),
and the dictionary-membership lesson (`docs/80_PROJECT_HISTORY/lessons/`).
