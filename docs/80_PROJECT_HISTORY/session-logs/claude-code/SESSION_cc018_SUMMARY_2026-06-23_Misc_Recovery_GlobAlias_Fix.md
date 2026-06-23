# SESSION cc018 — 2026-06-23 — "Misc" residual recovery + the three-tool glob-vs-alias fix

## Summary
Closed out the OCR-era recall residual from **91 → 79** by recovering the 12 chapters that had been
vaguely bucketed as "~11 misc," and root-caused why they were invisible to the recovery tooling.
Local Qwen2.5-VL only; **zero Claude vision tokens**; additive scratch JSON only; **no DB writes**.

## What Was Done
- **Characterized the "misc" bucket precisely** (it was a poor label): 12 genuinely-missing chapters
  in 4 transition/budget years — **1907×7 (1,131,137,237,352,356,377), 1911×3 (90,252,356),
  1953×1 (ch.34), 1956×1 (ch.10)** — none in the 71-chapter human-review list.
- **Root-caused the `production-<year>*` glob-vs-alias bug in THREE tools** (the scoreboard had been
  fixed earlier; two downstream tools had not):
  - `_residual_manifest.py` swept `production-1907-09` (the **1909** session) into 1907 →
    reported `missing=0` → hid the 7 real gaps from recovery.
  - `_vlm_apply.py` landed recovered candidates in the **wrong** year's `parsed_acts_visual.json`
    (1907→1909 vol, 1953→1952-budget vol) → scoreboard didn't move (91→87, not →79) → caught.
- **Fixed all three:** added the `BUDGET_OWNED_DIRS` exclusion (sourced from `year_dir_alias.py`) to
  `_residual_manifest.py`, `_vlm_apply.py`, and the dormant superseded scoreboard `_moderngap.py`
  (Hans-flagged latent gun). Added the 4 source-PDF mappings to `_vlm_header_recover.py` and
  decoupled `BIENNIAL_YEARS` to an explicit set so the new single-series years use the legacy
  page-finder (not the dual-series sequence-finder).
- **Ran the recovery** (sequential driver, 50 pages, ~no VRAM blowup): 12/12 true targets read
  correctly by Qwen2.5-VL. First apply mis-targeted 1907+1953 → surgically reverted via
  `_vlm_unapply.py` → re-applied to correct dirs.
- **Verified:** scoreboard residual **79** (95,923/96,002 = 99.9%); 1907/1911/1953/1956 all at 0;
  residual 79 = **71 biennial human-review + 8 archivist** (archivist corrected from 9 → 8: 1927 and
  1986/1359 were already recovered).
- **Hans (verify-auditor, Opus) verdict: SHIP** — fix correct, all 12 in right dirs, cleanup total,
  no double-count, no over-cap, no invented chapters. Two non-blocking follow-ups (one done).

## Decisions Made
- The "misc" bucket is **eliminated**, not deferred — these were real gaps recoverable with the
  already-proven local-VLM tooling, so we recovered them rather than handing them to the archivist.
- New single-series recovery years stay **off** `BIENNIAL_YEARS` → legacy manifest-range page-finder.
- Apply `BUDGET_OWNED_DIRS` guard to `_moderngap.py` too (Hans follow-up a) — fix every occurrence of
  the bug class in the same session, per the new lesson.

## Files Changed (repo)
- `pipeline/analysis/_residual_manifest.py` — BUDGET_OWNED_DIRS exclusion (the fix).
- `pipeline/analysis/_moderngap.py` — same guard + alias-fallback (dormant-bug cleanup).
- `docs/80_PROJECT_HISTORY/lessons/LESSON_2026-06-23_glob_vs_alias_three_tools.md` (new) + index.
- `docs/80_PROJECT_HISTORY/OCR_RECOVERY_CAMPAIGN_FINAL_2026-06-22.md` — 91→79 update banner.
- run-logs `vlm-pilot-run.log`, `ocr-recall-campaign-run.log`.
- (scratch, not repo) `_vlm_header_recover.py`, `_vlm_apply.py`, `_vlm_unapply.py`, `_vlm_misc_recover.py`,
  the 4 regenerated `_manifest_<year>.json`, and the corrected `parsed_acts_visual.json` files.
- (memory) `production-dir-resolution-via-alias.md` + MEMORY.md index.

## Open Items at Close
- **Residual 79** = 71 biennial human-review (off existing page images, no re-scan) + 8 archivist
  (truly-missing leaves). Both already documented (`HUMAN_REVIEW_LIST_2026-06-22.md`,
  `ARCHIVES_SCAN_REQUEST_2026-06-22.md`). Archivist doc says 9; live residual is 8 (1927 + 1986/1359
  already recovered) — minor doc staleness, flagged.
- **Hans follow-up (b), non-blocking:** the Qwen2.5-VL pass on 1953/1956 ran ~20× slower
  (~109s/page vs ~4.8s) with no image-size explanation — smells of VRAM thrash/GPU contention. Reads
  were still correct (monotone, no invented chapters). Root-cause before running the VLM tool at scale.
- Larger pending threads unchanged: proposition/initiative parser track (gated), DB ingest of the
  recovered scratch JSON into Postgres, constitution parallel archive.
