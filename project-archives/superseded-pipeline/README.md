# Superseded pipeline scripts (archived 2026-06-12, cc007)

These OCR-correction scripts were **archived, not deleted** — they hold provenance and the lineage of how
the correction cascade was built. Each was superseded by the ordered cascade (`pipeline/correction_cascade.py`)
or folded into it. Verified to have ZERO live imports before moving (grep clean). See
`docs/30_SYSTEM_DESIGN/PIPELINE_REFACTOR_PLAN.md` for the full inventory.

| archived file | superseded by |
|---|---|
| `correction_passes_v2.py` | `pipeline/correction_passes.py` (was a stray copy in the repo ROOT) |
| `correction_passes_v3.py` | `pipeline/correction_passes.py` |
| `word_splitter.py` | cascade `stage_split` |
| `autocorrect_pass.py` | cascade `stage_autocorrect` + `pipeline/symspell_e2.py` |
| `line_split_reunify.py` | cascade `stage_reunify` (incl. A4 positional window) |
| `garbage_filter.py` | cascade `classify_residual` (folded in) |
| `line_split_finder.py` | cascade per-stage instrumentation (measure-only; served its purpose) |

Nothing here is on the active path. Kept for history / open-source provenance.
