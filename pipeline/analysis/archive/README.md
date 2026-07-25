# `pipeline/analysis/archive/` — dead one-off probes (preserved, not active)

These scripts were created during the OCR-era recovery work as **hardcoded, year-pinned
investigation probes**. They answered a single historical question, are superseded, and should
**not** be run as part of any current workflow. They are archived (kept in git history) rather than
deleted so the investigation trail is recoverable — but they are out of the active `analysis/` dir so
nobody mistakes them for tools.

**Provenance / why they were here:** they were created in a working session and left uncommitted
(a process miss — a dirty tree accumulated across commits because staging was done path-by-path
instead of sweeping the tree). Triaged and archived 2026-06-23 (cc018).

## The durable finding (why these are dead)
These probes were the **prototype** for what became the productionized **lost-header recovery
pipeline**. The flow `_probe_pages_1850(a→b→c)` → `_visual_recovery_1850.py` hand-curated, for one
volume, the exact thing the pipeline now does automatically: locate a chapter whose page-top
`CHAPTER` header didn't OCR by reading the OCR lines between confident anchor chapters and assigning
the open sequence slot. `_visual_recovery_1850.py`'s hand-maintained `CHAPTER_DATA` dict became the
automated `gap_open_slots` / anchor-fill logic that emits `parsed_acts_lostheader.json`. The 9 active
tools in `../` (dump_lostheader, lostheader_stats, reocr_sizing, rescore_with_lostheader,
residual_after_certify, residual_profile, dump_multislot, inspect_gap, spotcheck_lostheader) all
consume that productionized artifact — so the year-pinned `_visual_*` / `_probe_*` originals are
obsolete. (See also `docs/80_PROJECT_HISTORY/lessons/LESSON_2026-06-14_chapter_recovery_header_loss_and_renumber.md`.)

## Inventory

| file | what it did | inputs | superseded by |
|------|-------------|--------|---------------|
| `_check_env.py` | print `PATOLEX_LOCATION_ROOT` + probe 4 hardcoded candidate scratch paths | env var + hardcoded paths | committed `env_probe.py` / `config.py` resolution |
| `_find_1850_vol.py` | list `production-*1850*` dirs, count `pages_raw`/`ocr_consensus` | hardcoded scratch paths (incl. a stale `C:\Users\patolex\...`) | `config.py` path resolution |
| `_inspect_ocr_1850.py` | dump keys/structure of 1850 `page_ocr_results.json` | hardcoded 1850 path | committed `_inspect_ocr_fields.py` (general) |
| `_inspect_ocr_1850b.py` | iter-2 of the above: page-key range + `surya_text` presence | hardcoded 1850 path | committed `_inspect_ocr_fields.py` |
| `_list_scratch.py` | `ls` of `C:\PatoLex-scratch` top level | hardcoded scratch root | trivial; throwaway |
| `_probe_pages_1850.py` | dump tess/doctr text for 1850 pages 51–63 (ch1/5–7) | hardcoded 1850 ocr | `_probe_pages_1850c.py` |
| `_probe_pages_1850b.py` | iter-2: pages around ch78/92/111, Roman-vs-Arabic check | hardcoded 1850 ocr | `_probe_pages_1850c.py` |
| `_probe_pages_1850c.py` | comprehensive 1850 header scan over ~28 hardcoded missing-chapter regions | hardcoded 1850 ocr + baked missing-chapter table | productionized lost-header pipeline |
| `_visual_recovery_1850.py` | **the prototype**: hand-curated `CHAPTER_DATA` → emit recovered 1850 acts. **WROTE** `production-1850/parsed_acts_visual.json` + a run-log | 1850 ocr + `_manifest_1850.json` | productionized `parsed_acts_lostheader.json` pipeline |
| `_visual_recovery_1971.py` | 1971 variant: manifest-driven missing-chapter OCR scan. **WROTE** `_scan_results_1971.json` + a run-log | `_manifest_1971.json` + per-vol ocr | productionized lost-header pipeline |

**Note:** the two `_visual_recovery_*` scripts are the only ones that ever wrote a parse-side artifact
(1850's `parsed_acts_visual.json` / 1971's scan JSON). They are inert here — do not re-run them; the
current pipeline owns those outputs.
