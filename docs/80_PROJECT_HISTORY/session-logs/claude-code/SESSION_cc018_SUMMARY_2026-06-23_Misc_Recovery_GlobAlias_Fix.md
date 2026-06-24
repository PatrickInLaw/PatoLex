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

- **Tree hygiene cleanup (Patrick-flagged).** 19 analysis scripts created earlier this session (pre
  autocompact) had been left untracked — a dirty tree accumulated because commits cherry-picked paths
  instead of sweeping. Triaged all 19: **9 KEEP** (a coherent config.py-resolved lost-header
  toolchain — measure→profile→size→score→dump→spotcheck, no committed dupes) committed to
  `pipeline/analysis/`; **10 DEAD** (hardcoded 1850/1971 one-off probes, superseded by the
  productionized lost-header pipeline) moved to `pipeline/analysis/archive/`. Documented both with
  READMEs (active-dir index + archive inventory incl. the durable prototype→production finding).

- **Scrivener Roman-numeral transposition finding** (Patrick, by eye): 1870 ch.143 printed `CLXIII`=163;
  OCR read the typo → act stored as ch.163 (hiding 143, masking the real ch.163 at p291-292). Targeted
  scan found exactly 1 corpus-wide. Lesson committed (`d0d6f24`).
- **Combined human-review PDF** (`C:\PatoLex-scratch\_archive_trip\PatoLex_HumanReview_71chapters.pdf`):
  one file, bookmark-per-chapter, each with a label page + just its source pages. Patrick reviewed first
  5 items, reported a bug → **fixed the window finder**: it was clamping wide brackets to 12p on one
  side and dropping chapters on the far side (ch.343 missed). Now uses the FULL sequence-consistent
  bracket; same-bracket clusters merged. Added real 1870 ch.163 as a flagged supplement. (523 pages.)
- **VLM review-assist** (`_vlm_review_assist.py`): re-runs Qwen2.5-VL over the CORRECTED full-bracket
  windows + typo reconciliation, writes a REPORT (no auto-apply). **1866 validation: 7/10 recovered,
  zero false reads**, recovered the 343 cluster the original pass missed (proving mislocation, not
  illegibility), and adjudicated Patrick's 197/198 (print is CXCVIII=198). 6-year pass running.
- **Duplicate-chapter triage** (62 within-vol dup numbers): **0 real typo collisions** — all are
  cross-file union artifacts (60 = 1854 stale-merged vs corrected dualseries_v2; 1 = 1861 clauserec; 1
  = same-act). Ingest-hygiene only.
- **GPU monitor**: first attempt (`nvidia-smi -l -f`) silently wrote 0 lines (block-buffered) — replaced
  with a python per-sample-flush monitor (`_gpu_monitor.py` → `gpu-monitor-run.log`). Diagnosed the
  near-full VRAM as the single VLM process (16.6GB weights + 350-dpi image activations), not a leak;
  Task-Manager-vs-nvidia-smi memory discrepancy explained by WDDM-vs-CUDA accounting under RDP.

## Decisions Made
- The "misc" bucket is **eliminated**, not deferred — these were real gaps recoverable with the
  already-proven local-VLM tooling, so we recovered them rather than handing them to the archivist.
- New single-series recovery years stay **off** `BIENNIAL_YEARS` → legacy manifest-range page-finder.
- Apply `BUDGET_OWNED_DIRS` guard to `_moderngap.py` too (Hans follow-up a) — fix every occurrence of
  the bug class in the same session, per the new lesson.
- **Process fix:** stop cherry-picking paths into commits and orphaning the rest — verify the tree is
  clean (zero untracked, or untracked is intentional + documented) at every commit. Archive dead
  scratch instead of letting it rot untracked.

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
- **Hans follow-up (b) — RESOLVED as WONTFIX (Patrick decision 2026-06-23):** the Qwen2.5-VL pass on
  1953/1956 ran ~20× slower (~109s/page vs ~4.8s, likely VRAM thrash). Reads were still correct
  (monotone, no invented chapters). Decision: **NOT root-causing** — the OCR-era VLM header-recovery
  is complete and there is **no remaining VLM-at-scale job** (the residual 79 is human-review + archivist,
  not VLM; the modern era is born-digital). The optional 72B pass at the 71 human-review chapters was
  declined in favor of human transcription off existing images. **The local-VLM header-recovery tool is
  retired** for this corpus segment; if it is ever revived at scale (e.g. constitution OCR), root-cause
  the perf first.
- Larger pending threads unchanged: proposition/initiative parser track (gated), DB ingest of the
  recovered scratch JSON into Postgres, constitution parallel archive.
- **VLM review-assist COMPLETE: 71 → 24** (47 machine-recovered, reliable exact-numeral reads; 1866
  ch.143 matches Patrick's hand-read). Re-pass after Patrick's "verify pagination first" steer:
  pagination verified ACCURATE (offset +0) → brackets were right → no wide-band re-render needed; cheap
  cached re-read at 250 dpi (after a 350-dpi/full-VRAM thrash at 156 s/page — killed, cleared, relaunched
  clean) lifted 29→47. Short PDF of the 24 remaining delivered (`PatoLex_HumanReview_REMAINING_24.pdf`).
  Findings → `LESSON_2026-06-23_vlm_recovery_ops_dpi_thrash.md` (VRAM-thrash, 250>350 dpi readability,
  typo false-positive, "TRUE-GAP" mislabel for consecutive chapters).
  - **APPLIED (Patrick approved):** 47 landed additively into the 7 biennial statutes
    `parsed_acts_visual.json` (image_verified, origin=vlm_review_assist; 1870 ch.143 noted as the
    CLXIII typo). Residual **79 → 32**. Verified vs Patrick's 5 ground-truth reads. Hans audit of the
    apply running. The 24 unrecovered are in `PatoLex_HumanReview_REMAINING_24.pdf`.
- **SCOREBOARD REPORTING FIX (Patrick caught):** `_recall_allyears.py` was `round(...,1)`-ing 99.967%
  UP to "100.0%" with 32 chapters still missing — a false-complete signal, dangerous for a corpus whose
  premise is "any omission breaks it." Added a `pct()` helper that FLOORS to 2 decimals and returns
  100.0 ONLY when num>=den exactly. Now prints **99.96% / RESIDUAL=32** honestly. Counts were always
  right; only the % was lying.
- **Corrections logged for the corrections/citation-re-derivation prereq (not applied):** 1870 relabel
  p210 163→143 + recover real ch.163 (p291-292); 1854 ingest from dualseries_v2; 1861 clauserec ch.18
  superseded by visual.
- Scratch tooling (not in repo, under `C:\PatoLex-scratch`): `_vlm_review_assist.py`, `_vlm_review_driver.py`,
  `_build71pdf.py`, `_win71.py`, `_scrivener_scan*.py`, `_gpu_monitor.py`, etc.
