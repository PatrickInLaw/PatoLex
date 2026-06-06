# Session cc005 Summary

| Field | Value |
|-------|-------|
| Session | cc005 |
| Date | 2026-06-05 |
| Agent | Claude Code |
| Context | OCR pipeline operational monitoring, cascade failure recovery, prep runner fix |
| Branch | main |

---

## What Was Done

**OCR pipeline monitoring and failure recovery (continuation from cc003/cc004 context).**

1. **Diagnosed 36-volume cascade failure on 5080.** Root cause: the 5080 queue worker's subprocess monitoring bug — it lost track of the 1993-vol1 OCR subprocess, marked it "failed," then rapid-failed all 36 subsequent volumes as the orphan subprocess crashes propagated through the queue state. No data was lost; the orphan ran to completion.

2. **Resolved OOM cascade risk on 5080.** The orphan 1993-vol1 subprocess still had GPU models loaded (~14950MB VRAM peak). Disabled the PatoLex_OCR_5080 schtask to prevent a new worker from launching and colliding with the orphan; let the orphan run to completion naturally; re-enabled schtask.

3. **Reset 36 failed volumes to "pending" on 5090.** Ran a Python script on 5090 to update all failed statuses back to pending so the queue workers could pick them up. Created stub `prep-*.log` files for two volumes (1999-vol2, 1999-vol4) that had in-flight preps, so the prep_runner's `already_prepped()` check would skip them correctly.

4. **Fixed prep_runner hardcoded at 3 workers instead of 8.** `run_prep_runner.bat` on 5090 had `--parallel 3` hardcoded — the 16-worker script default was irrelevant because the bat overrides it. Updated to `--parallel 8` on both 5090 and local scratch. Restarted prep_runner after the queue reset so it read the full 36 newly-pending volumes.

5. **Updated prep_runner.py for next run.** Changed default PARALLEL from 8→16 and added `--ramp-delay` CLI parameter (default 30s) with a stagger sleep between successive worker spawns to reduce disk contention at startup. Both changes already SCP'd to 5090 production location.

6. **Clarified prep/GPU decoupling semantics.** Decoupled prep does NOT make per-volume prep faster (~20 min stays ~20 min). The benefit is purely time-overlap: CPU preps volume N+1 while GPU OCRs volume N. Wall-clock savings come from that overlap, not from accelerating any individual step.

**Queue state at session close:** 169 done / 37 pending / 4 in-progress / 0 failed (of 210 total). ETA ~June 6 evening–early June 7 (depending on per-volume timing).

---

## Files Changed

**Modified files (in repo):**
- `docs/80_PROJECT_HISTORY/run-logs/worker-5080-run.log` — 5080 worker progress log, updated through 1993-vol3 start
- `docs/80_PROJECT_HISTORY/run-logs/phaseB-build-run.log` — minor updates

**Modified files (scratch, outside repo — NOT committed):**
- `C:\Users\PatrickKolasinski\PatoLex-scratch\prep_runner.py` — PARALLEL default 8→16, added --ramp-delay parameter and 30s stagger sleep
- `C:\Users\PatrickKolasinski\PatoLex-scratch\run_prep_runner.bat` — --parallel 3 → --parallel 8
- Both SCP'd to `C:\Users\patolex\PatoLex-scratch\` on 5090

---

## Decisions Made

| Decision | Detail |
|----------|--------|
| Disable then re-enable 5080 schtask (not kill orphan) | Let orphan 1993-vol1 finish naturally rather than risk data loss or VRAM corruption from hard-kill |
| Reset 36 failed→pending (not delete+re-queue) | Non-destructive; preserves queue ordering and avoids duplicate PDF inventory work |
| Prep parallelism 8 now, 16 next run | 8 is safe for current confirmed-pending list; 16+ramp for next larger batch |
| RAMP_DELAY=30s stagger | Reduces simultaneous PDF-open + PNG-write disk spikes at worker startup |
| run_prep_runner.bat stays at --parallel 8 | Next restart should use --parallel 16 --ramp-delay 30 — update bat before restarting |

---

## Open Items at Close

| Item | Priority |
|------|----------|
| Update run_prep_runner.bat to `--parallel 16 --ramp-delay 30` before next prep_runner restart | Medium |
| Investigate queue worker subprocess monitoring bug (root cause of cascade) — may need a fix in ocr_only_5080.py or the schtask wrapper | High (before next large batch) |
| Monitor OCR queue draining — 37 pending, ETA June 6 evening | Ongoing |
| Acquire pubinfo_2025 for 2025-2026 Gate F coverage gap | Medium |
| Run provision_version materialization batch at publish time | At publish |

---

## Next Session Should Start With

1. Check queue state: `python qs_tmp.py` on 5090 (or equivalent) — confirm all volumes done/0 failed
2. Check for any new cascade failures (watch for failed > 0)
3. Update run_prep_runner.bat to `--parallel 16 --ramp-delay 30` if restarting prep runner

---

## Lessons Learned

- **Queue worker subprocess monitoring bug is a known risk.** The schtask wrapper can lose track of its child OCR subprocess, marking it "failed" while the subprocess continues as an orphan. If this happens while the orphan still has GPU models loaded, a new worker starting on the same device can OOM. Mitigation: disable the schtask task until the orphan completes, then re-enable and reset failed statuses.
- **bat file overrides script defaults.** When a .bat passes `--parallel N`, the script-level `PARALLEL = X` default is irrelevant. Always verify the bat file's arguments match intent before running — don't assume the script default is what's running.
- **Decoupled prep = overlap, not speed.** Prep itself takes the same time (CPU-bound, ~20 min/volume). The savings are purely from running CPU prep concurrently with GPU OCR for a different volume. If GPU is idle, adding more prep workers doesn't help — it's the GPU step that determines throughput.
