# `pipeline/analysis/` — corpus measurement & recovery diagnostics

Read-only (or report-only) analysis tools for the OCR-era corpus build. None of these write to the
Postgres DB. Tools resolve paths via `config.py` (`PATOLEX_LOCATION_ROOT`) — they are **not**
year-pinned or hardcoded to a machine. A few write `_`-prefixed **report** JSONs to the scratch root
(never a `parsed_acts_*.json`); those are noted below.

Convention: a leading `_` marks a scratch/diagnostic script (vs. a pipeline-stage module). It does
**not** mean "uncommittable" — committed `_`-prefixed tools exist (`_recall_allyears.py`,
`_residual_manifest.py`, `_inspect_ocr_fields.py`). One-off, year-pinned, hardcoded probes that are
superseded go to `archive/` (see `archive/README.md`), not here.

## Canonical scoreboards / oracles (the authorities)
- **`_recall_allyears.py`** — the OCR-era recall **scoreboard** (effN-aware, anti-double-count,
  biennial/budget alias via `../year_dir_alias.py`). The authority on residual counts.
- **`_residual_manifest.py`** — per-year list of still-missing chapters with page brackets (feeds
  visual/VLM recovery). Same alias guard as the scoreboard.
- **`chapter_vs_oracle.py`**, **`chapter_completeness.py`**, **`residual_gap.py`** — committed
  oracle-comparison / sequence-gap measures.

## The lost-header recovery toolchain (9 tools, added/tracked 2026-06-23, cc018)
A coherent **measure → profile → size → score → dump → spot-check** set over the productionized
lost-header recovery artifact (`parsed_acts_lostheader.json`). All parameterized or corpus-wide,
`config.py`-resolved. (These generalize the now-archived `_visual_recovery_*` 1850/1971 prototypes —
see `archive/README.md`.)

| tool | role | output |
|------|------|--------|
| `residual_after_certify.py` | post-certification residual vs oracle N per session (`--parse NAME --worst N`) | stdout + report `_residual_after_certify.json` |
| `residual_profile.py` | classify residual by shape (dense/mid/sparse; interior vs leading/trailing/block) | stdout (reads #1's report) |
| `reocr_sizing.py` | bucket residual into recovered / ambiguous / no-boundary to size a re-OCR pass | stdout (JSON) |
| `rescore_with_lostheader.py` | biennium-correct BEFORE/AFTER scoring of lost-header recovery vs oracle | stdout + report `_rescore_lostheader.json` |
| `lostheader_stats.py` | corpus-wide `gap_open_slots` distribution, numeral match/mismatch, witness split, needs_reocr reasons | stdout |
| `dump_lostheader.py` | per-volume pretty-print of recovered + needs_reocr (`<label> [--needs]`) | stdout |
| `dump_multislot.py` | list recovered acts with `gap_open_slots>1` (the riskier multi-slot subclass) | stdout |
| `inspect_gap.py` | dump OCR lines between confident anchors bracketing each open slot (`<session> [--max N]`) | stdout |
| `spotcheck_lostheader.py` | stratified adversarial sample of recovered acts + their OCR header region (`[N]`) | stdout |

## archive/
Dead, superseded one-off probes (hardcoded 1850/1971 investigations). Preserved in history, not for
re-use. See `archive/README.md`.
