# LESSON 2026-06-23 — The `production-<year>*` glob-vs-alias bug lived in THREE tools, not one

## One-line
Any tool that resolves a session-year to its production directory by the greedy glob
`production-<year>*` **must** exclude `BUDGET_OWNED_DIRS` and defer to `pipeline/year_dir_alias.py`,
or it silently grabs the wrong physical volume — and this guard had only ever been added to the
scoreboard, leaving two downstream tools quietly mis-targeting.

## What happened
Closing out the OCR-era recall campaign, 12 "missing" chapters across 4 transition/budget years
(1907×7, 1911×3, 1953×1, 1956×1) were sitting in the residual, bucketed vaguely as "misc." They had
*never been put through recovery* because the tooling that feeds the recovery could not see them.

Root cause: three different tools resolve a year → production dir, and the greedy glob
`glob("production-<year>*")` matches **sibling** volumes whose leading year coincides:
- `production-1907-09` is the **1909** regular session (N=729), NOT 1907 — 1907 lives in
  `production-1906-07`. (1907-09 is listed in `BUDGET_OWNED_DIRS` precisely to be excluded.)
- `production-1953-vol1-52chapters` is the **1952 budget** session, NOT the 1953 regular session
  (`production-1953-vol1-chapters` / `-vol2-chapters`).

The scoreboard `_recall_allyears.py` had been fixed (2026-06-21) to exclude `BUDGET_OWNED_DIRS` and
consult the alias. But the SAME resolution logic, unguarded, still lived in:

1. **`pipeline/analysis/_residual_manifest.py`** (committed) — its glob swept `production-1907-09`
   into year 1907, saw all chapters 1..539 present in the 1909 volume, and reported **`missing=0`**.
   So the recovery tool (which reads this manifest) had no targets → the 7 real gaps were invisible.
2. **`C:\PatoLex-scratch\_vlm_apply.py`** (scratch tool) — its glob landed the recovered candidates
   into the WRONG year's `parsed_acts_visual.json`: 1907's 7 chapters went to `production-1907-09`
   (1909), 1953 ch.34 went to `production-1953-vol1-52chapters` (1952 budget). The recovery ran
   correctly but **credited the wrong volume** — scoreboard residual didn't move for those years
   (91 → 87, not → 79), which is how the mis-apply was caught.

## The fix
Add the exact guard the scoreboard already uses to BOTH tools:
```python
dirs = [d for d in glob.glob(os.path.join(SCR, f"production-{yr}*"))
        if os.path.isdir(d) and os.path.basename(d) not in BUDGET_OWNED_DIRS]
# ... then consult YEAR_DIR_ALIAS when the (now-filtered) glob is empty
```
`BUDGET_OWNED_DIRS` and `YEAR_DIR_ALIAS` are imported from the single source of truth
`pipeline/year_dir_alias.py`. After the fix, `_residual_manifest.py 1907` correctly reports
`missing=[1,131,137,237,352,356,377]` and `_vlm_apply.py 1907` lands in `production-1906-07`.

Also: `_vlm_header_recover.py` needed the 4 source-PDF mappings added to `PDF_FOR_YEAR`
(1906-07/1910-11/1953_Vol1/1957_Vol1_56Chapters), and `BIENNIAL_YEARS` was **decoupled** from
`PDF_FOR_YEAR.keys()` to an explicit `{1866,1868,1870,1872,1874,1876,1878}` so the new single-series
years use the legacy manifest-range page-finder, not the dual-series sequence-finder (which can
over-window a 1000+-chapter multi-volume year).

## Outcome
All 12 recovered + correctly credited. Residual **91 → 79** (95,923/96,002 = 99.9%). The "misc"
bucket is eliminated; residual 79 = 71 biennial human-review + 8 archivist, cleanly.

## The rule (durable)
**Never resolve a production dir by raw `production-<year>*` glob.** Route every such resolution
through `pipeline/year_dir_alias.py` (exclude `BUDGET_OWNED_DIRS`, then alias-fallback). When you fix
a dir-resolution bug in ONE tool, grep the whole tree (`pipeline/` AND `C:\PatoLex-scratch`) for the
same `production-` glob pattern and fix EVERY occurrence in the same session — a shared bug fixed in
only one consumer is a latent bug, not a fixed one. The correct long-term shape is a single shared
`resolve_dirs(year)` helper in `year_dir_alias.py` that all three consumers call.

## Related
- `pipeline/year_dir_alias.py` (single source of truth)
- `LESSON_2026-06-22_biennial_volume_offset_merge_cap.md` (the original `n_for()` mis-cap)
- run-log `docs/80_PROJECT_HISTORY/run-logs/vlm-pilot-run.log`
