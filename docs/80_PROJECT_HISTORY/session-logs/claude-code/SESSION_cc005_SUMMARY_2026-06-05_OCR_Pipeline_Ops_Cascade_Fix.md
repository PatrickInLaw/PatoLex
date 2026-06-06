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

**Queue state at first close (June 5 ~21:00 PT):** 169 done / 37 pending / 4 in-progress / 0 failed (of 210 total).

**5090 went offline at ~00:42 PT June 6 — all OCR stopped.** 1993-vol3 OCR completed successfully on the 5080 GPU but the SCP push to 5090 timed out. Worker marked it "reclaimable" (left as in_progress in queue), attempted three more claim SSHs, all timed out, and exited at 00:45 PT with "queue drained / no claimable volume." 5090 TCP/22 confirmed closed at 4:42am June 6. Root cause unknown (sleep/crash/Tailscale loss). No OCR has run since 00:45 PT. Both workers idle. ETA pushed to ~midnight June 7 once 5090 is restored.

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
| **BLOCKED: 5090 offline since 00:42 PT June 6** — needs physical check (wake/restart/Tailscale); 5080 worker has exited | URGENT |
| Once 5090 is back: restart prep_runner, verify 5080 schtask fires, manually mark 1993-vol3 done or let worker reclaim | High |
| Monitor OCR queue draining — ~41 volumes left, ETA ~midnight June 7 once 5090 restored | Ongoing |
| Acquire pubinfo_2025 for 2025-2026 Gate F coverage gap | Medium |
| Run provision_version materialization batch at publish time | At publish |

---

## Next Session Should Start With

1. **Restore 5090** — physically wake/restart; confirm Tailscale is up; SSH test from 5080
2. Once SSH restored: check queue state, restart prep_runner with `--parallel 16 --ramp-delay 30`, verify 5080 schtask auto-fires
3. Manually mark 1993-vol3 done on queue (OCR output is on 5080 scratch; SCP it over, then update queue JSON)
4. Check for any new cascade failures (watch for failed > 0) after workers resume

---

## Lessons Learned

- **Queue worker subprocess monitoring bug is a known risk.** The schtask wrapper can lose track of its child OCR subprocess, marking it "failed" while the subprocess continues as an orphan. If this happens while the orphan still has GPU models loaded, a new worker starting on the same device can OOM. Mitigation: disable the schtask task until the orphan completes, then re-enable and reset failed statuses.
- **bat file overrides script defaults.** When a .bat passes `--parallel N`, the script-level `PARALLEL = X` default is irrelevant. Always verify the bat file's arguments match intent before running — don't assume the script default is what's running.
- **5090 availability is the single point of failure for both workers.** The 5080 worker depends on 5090 for queue claims (SSH) and result delivery (SCP). If 5090 goes offline, the 5080 worker exhausts retries and exits. Consider adding a local queue fallback or health-check restart logic in a future session.
- **Decoupled prep = overlap, not speed.** Prep itself takes the same time (CPU-bound, ~20 min/volume). The savings are purely from running CPU prep concurrently with GPU OCR for a different volume. If GPU is idle, adding more prep workers doesn't help — it's the GPU step that determines throughput.
