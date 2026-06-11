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

## Cross-refs
`CROWDSOURCE_CORRECTION.md` (community tier), `SCHEMA_DESIGN` / `docs/40_SCHEMA/`
(event-sourced model), the correction pipeline (`pipeline/correction_passes.py`),
and the dictionary-membership lesson (`docs/80_PROJECT_HISTORY/lessons/`).
