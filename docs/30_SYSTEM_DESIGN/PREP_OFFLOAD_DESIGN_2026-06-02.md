# Prep-offload design + profiling (2026-06-02)

**Status:** ANALYSIS + options (decision pending). Companion to the CPU-prep-bottleneck lesson
(`docs/80_PROJECT_HISTORY/lessons/LESSON_2026-06-02_ocr_cpu_prep_bottleneck.md`).

## Measured numbers (profiling agent, 2026-06-02)

### M1 — where per-volume time goes (5090, per-page medians)
| Stage | s/page | s/vol (~1400pp) | resource |
|---|---|---|---|
| STAGE1 render | ~0.06 | ~76 | CPU (cheap) |
| STAGE2 preprocess (grayscale v2) | ~0.95 | ~1080 | **CPU — 94% of prep cost** |
| STAGE3 classify | negligible | — | CPU |
| STAGE4 OCR | ~3.0 | ~3400 | GPU + CPU |

- **Prep : OCR ≈ 0.34 : 1** → prep ~25% of wall, OCR ~75%.
- OCR runs **3 engines serially per page**: Tesseract (CPU) → docTR (GPU) → Surya (GPU) → cheap 2-of-3 CPU consensus (`ocr_only_5090.py:466-486`). No per-engine timing is logged; structural estimate: **Tesseract ~0.8–1.2 s/page (CPU, ~30–40% of OCR wall)**, docTR+Surya ~1.8–2.2 s/page (GPU).
- **Consequence: the 5-series CPU is busy throughout BOTH phases** — preprocess during prep (0.95 s/pg) AND Tesseract during OCR (~1 s/pg).

### M2 — handoff cost (volume 1907-09, real test)
- `pages_prep_gray`: 1403 files = **1289 MB**; classification json ~14 KB.
- tar -czf: **37 s → 969 MB** (only ~25% shrink — binarized PNGs near-incompressible).
- scp -O over Tailscale, unthrottled: **16.7 s → ~58 MB/s**. Raw ship ~22 s (compression barely helps).
- **Handoff ≈ 22–54 s vs ~19 min (1156 s) of CPU prep offloaded → ~2–5%. Handoff is noise.**

## What the numbers mean

1. **Offloading is cheap** — the handoff is ~1 min against ~19 min of prep saved. No bandwidth objection.
2. **Prep-offload ALONE does not free the 5-series CPU.** Tesseract (CPU engine, ~30–40% of the 75%-of-wall OCR stage, serial per page) stays resident. To fully free the CPU you must move **Tesseract too** → full role-split.
3. **Reframe of the lockstep catastrophe:** the benchmark's 91–94% CPU saturation was 4 workers doing **preprocess simultaneously** (cold lockstep). Preprocess is only ~25% of a worker's cycle. In **steady-state desync** (workers spread across phases — which the new live-scaling feature produces by adding workers one at a time), only ~25% of workers preprocess at once, so the simultaneous-prep spike largely disappears. The persistent steady-state CPU load is then ~N × Tesseract (~1 core per ~3 workers) — modest. **So a *desynced* 4th worker may run fine with no offload at all.**

## Options

**A — Desync test first (cheap).** Deploy the live-scaling feature (one clean cutover), then add a 4th 5090 worker LIVE into the running, desynced 3 and measure. Likely the prep spike is gone and 4 works. Cost: 1 cutover + a measurement. May deliver the throughput with zero new architecture.

**B — Full role-split prep-offload (bigger lever).** 3060 does render + preprocess + classify **+ Tesseract**; 5090/5080 become GPU-only (docTR + Surya + consensus). Prepped pages + Tesseract output ship back cheaply. Frees the 5-series CPU entirely → scale GPU workers freely. Cost: real build (two-phase queue `pending→prepping→prepped→ocring→done`, handoff protocol, Tesseract relocation, consensus assembly), Hans ×2.
- **Open risk to size FIRST:** the 3060 at ~2 s/page (preprocess + Tesseract) must feed ~5 GPU workers consuming ~2 s/page each (GPU-only). That needs ~5 parallel prep+Tesseract streams on the 3060 → **the 3060 could become the new bottleneck.** Size its core/thread count before committing; may need prep spread across >1 box.

**C — Intra-worker pipelining (weakest).** Prep vol N+1 while OCR'ing vol N. Hides prep latency but does not reduce CPU *load* (preprocess + Tesseract still on the 5-series CPU). Least attractive given M1.

## Recommendation
**A then B.** Desync is nearly free and may suffice for a 4th worker; if its ceiling isn't enough, build B — but size the 3060 CPU first, since the role-split only pays off if the 3060 can sustain ~5 prep+Tesseract streams.

---

## REFINED DESIGN (Patrick, 2026-06-02) — supersedes the fixed role-split above

Two insights reframe B into something better and cheaper:

1. **The 5-series CPUs are mostly idle during OCR.** During the OCR phase a worker uses the CPU only for Tesseract (~1 s/pg) out of a ~3 s/pg cycle ≈ ⅓ of one core; 3 workers ≈ ~1 core. On a many-core box that leaves most cores idle while the GPU is pinned. The lockstep saturation was an artifact of COUPLING prep+OCR in one worker (a prepping worker isn't OCR'ing; 4 prepping at once = 4 cores + idle GPU). **Decouple prep from OCR and run prep AHEAD on the idle local cores → GPU never waits, ZERO data movement, no 3060 needed.**

2. **Prep should load-balance across whatever CPU is free, by policy.** Once prep is a decoupled task feeding a buffer, it runs wherever there's spare CPU — 5-series idle cores AND the 3060 (off-hours / when it has room). An orchestrator assigns by real-time capacity + time-of-day/thermal policy; the 3060 becomes an opportunistic CONTRIBUTOR, not a single point of dependency (dissolves the bottleneck risk in B's open-risk note). Prep falls back to GPU-box spare CPU when the 3060 is unavailable.

### Target architecture: decoupled prep buffer + opportunistic prep pool + adaptive orchestrator
- **Two-phase queue** `pending -> prepped -> done` = the buffer that decouples prep from OCR.
- **Prep workers at LOW (BelowNormal) priority** on any spare CPU (local 5-series idle cores first = no movement; 3060 when available = cheap handoff, measured). Low priority so prep never steals cycles from OCR's Tesseract.
- **Bounded buffer depth** (don't prep N volumes ahead and exhaust the SSD — archiver already showed disk pressure).
- **GPU OCR workers** just drain the `prepped` buffer.
- The **live worker-scaling feature** (`supervisor_5090.ps1`, this session) is the orchestrator's GPU-side ACTUATOR (scale workers up/down by policy).

### Phasing
1. **Decouple + local prep-ahead** — two-phase queue + a low-priority prep-ahead worker per GPU box, bounded buffer. No 3060, no network. Likely keeps the GPU fed and unlocks more GPU workers on its own. Cheapest, biggest bang.
2. **3060 as opportunistic prep contributor** — pulls prep when it has room/off-hours, ships prepped pages back; optionally relocate Tesseract prep-side here.
3. **Adaptive orchestrator + policy** — time-of-day, thermal, capacity-aware assignment driving the scaling actuator.

**Build Phase 1 first** (captures most of the win, least risk); 2 and 3 layer on. Phase 1 to be scoped + Hans-reviewed before implementation.
