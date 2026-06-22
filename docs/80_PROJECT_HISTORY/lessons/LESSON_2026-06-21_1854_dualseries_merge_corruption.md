# LESSON 2026-06-21 — 1854 dual-series merge corruption (special local roman read as oracle number)

## Summary

The pre-existing **1854 merged corpus (`parsed_acts_merged.json`) is content-corrupt** and
**MUST NOT be ingested as-is.** For ingest, 1854 is **SUPERSEDED by
`parsed_acts_dualseries_v2.json`** (surfaced through the additive
`parsed_acts_visual.json` channel, which now carries all 174 oracle chapters).

## The corruption

The 1854 printed volume contains **two independently numbered series**:

- **General Laws** — local chapters 1..71
- **Special Laws** — local chapters 1..103, printed with their own **local roman numerals
  (I..CIII)** starting over at I after the special divider (printed page 129).

The **old merged parser read the SPECIAL series' LOCAL roman numerals as if they were
oracle (volume-wide) chapter numbers.** Result: **61 of 96 merged chapters hold the WRONG
act.** Example: merged "ch12" was a Plumas-area **special** act, not the real General Ch12
("An Act to prevent the sale of Fire-Arms and Ammunition to Indians in this State").

Compounding it, the earlier `_build_visual_1854.py` only filled oracle slots the corrupt
merged file did **not** already claim (it skipped on `already_in_merged`). So the CORRECT
General acts for ~35 oracle slots in 1..71 were **absent from the pipeline output
entirely** — neither the (wrong) merged entry nor any visual entry held the right act.

## The fix (Hans-confirmed SOUND mapping)

The correct oracle numbering is a clean concatenation of the two series:

```
general_acts  local N  ->  oracle N        (1..71)
special_acts  local N  ->  oracle N + 71   (72..174)   # "+71 mapping"
```

`parsed_acts_dualseries_v2.json` holds all 174 acts correctly under this mapping
(`general_acts`: 71, `special_acts`: 103; oracle_total 174). Numbering is derived from the
printed front-matter **CONTENTS** (scan pages 0002-0012), NOT from body roman headers, and
bodies are located by distinctive-title-token overlap against the OCR consensus.

On 2026-06-21 `parsed_acts_visual.json` was **rebuilt (full, not additive)** to carry the
correct dualseries_v2 act for **every oracle chapter 1..174** — the `already_in_merged`
skip was removed. The additive visual channel now supersedes the 61 corrupt merged entries.
`_residual_manifest.py 1854` reports `present=174 missing=0`.

Spot-checks confirming corrected General slots (previously corrupt):
- oracle ch12 = General local 12 = "An Act to prevent the sale of Fire-Arms and Ammunition to Indians in this State"
- oracle ch35 = General local 35 = "An Act amendatory of an act to create the county of Stanislaus, approved April first 1854"
- oracle ch71 = General local 71 = "An Act concerning Public Ferries and Toll Bridges"

## Ingest directive

**Any ingest of 1854 must take its content from `parsed_acts_dualseries_v2.json` (via the
rebuilt `parsed_acts_visual.json`), and must IGNORE / OVERRIDE the 61 wrong
`parsed_acts_merged.json` entries.** Do not ingest the 1854 merged file as authoritative.
(`parsed_acts_merged.json` and the DB were NOT modified by this fix — the correction is
additive in the file corpus only.)

## Generalizable warning

When a session-law volume splits into multiple locally-numbered series (General vs. Special
is common in the 1850s), **body roman headers restart per series** and cannot be read as
volume-wide oracle numbers. Always anchor numbering to the printed CONTENTS front matter and
apply an explicit per-series offset (here +71 for Special).
