# Structural fix for the prep OOM explosion — a RAM-governed prep dispatcher

**Date:** 2026-06-08 · **Status:** design (pre-implementation) · **Applies to:** every box that runs CPU prep (5080 16 GB, 3060 32 GB, 5090 64 GB).

## The real shape of the problem

There is **no 25 GB file.** The peak memory of the prep stage is:

```
peak_RAM  ≈  OS/baseline  +  (concurrent_preps  ×  peak_per_prep)
```

- `peak_per_prep` is **small and bounded** — a `--stage prep` process renders + preprocesses
  **one page at a time** (it does NOT load torch/surya/docTR; those imports are in STAGE 4).
  Measured/estimated peak ≈ **0.5–1.5 GB** regardless of whether the volume is a 12-page 1850
  pamphlet or 511 MB / ~6000-page `1996_Vol1.pdf`. Streaming already guarantees this.
- `concurrent_preps` is **unbounded** today: `prep_runner.py --parallel 16` (default) runs 16
  renders at once. 16 × ~1 GB + OS + file-cache ≈ the ~25 GB that OOMs a 16 GB box — and would
  OOM the 32 GB 3060 too (it already carries 10–13 GB of other load).

**So the explosion is uncontrolled CONCURRENCY, not object size.** The structural fix is to make
`concurrent_preps` a function of a **hard RAM budget**, never a fixed number.

## The fix — five layers (defense in depth)

### 1. Stream, never materialize a volume (invariant to hold)
Keep prep page-by-page; never build a Python list of decoded pages, never `convert_from_path` a
whole PDF. Audited: the OCR scripts already comply. This caps `peak_per_prep` independent of
volume size — the single most important property. Add a regression test/assert so it stays true.

### 2. RAM-governed admission gate (the core change)
Replace `prep_runner.py`'s fixed `--parallel N` with a dispatcher that starts a new prep **only
when** `free_RAM − safety_margin ≥ peak_per_prep_budget`, and otherwise waits. Concurrency then
**self-scales to each box**:

| Box | Free RAM | margin | budget/prep | safe concurrent preps |
|-----|----------|--------|-------------|-----------------------|
| 5080 | ~6–10 GB | 3 GB | 1.5 GB | **1–2** |
| 3060 | ~20 GB | 4 GB | 1.5 GB | **~6–8** (cap lower to be safe) |
| 5090 | ~46 GB | 4 GB | 1.5 GB | **many** (cap by CPU, not RAM) |

Same code on every box; no per-box constant that is wrong somewhere. The gate also covers the
GPU OCR workers via the supervisor (don't launch/relaunch a worker below the floor; drain the
newest if RAM goes critical).

### 3. Hard per-process memory cap via Windows Job Objects (backstop)
Wrap each prep/OCR worker in a **Job Object with a committed-memory limit** (e.g. 2–3 GB). If a
pathological volume blows its budget, Windows kills **only that process** (poison-volume
containment) — the box never goes down. This is the guarantee that even a wrong estimate or a
future regression cannot OOM the machine.

### 4. Shrink `peak_per_prep` at the source (multiplies the headroom)
- **Render 1-channel grayscale, not 3-channel BGR.** Today STAGE 1 renders GRAY then
  `cvtColor(GRAY2BGR)` before `imwrite` (3× the pixels). Keep it single-channel end-to-end where
  the engines allow → ~3× less per-page image RAM and ~3× smaller PNGs on disk.
- **Sauvola in float32, not float64**, and/or a tiled/windowed integral image → halves the
  integral-image buffers (the largest transient in preprocess).
These don't change the *structure* but materially raise how many preps fit in a budget.

### 5. Queue-depth bound (orthogonal, already in the SQL design)
`queue_worker_sql.py` `PREP_BUFFER_MAX = 3` stops prep running unboundedly **ahead** of OCR. That
bounds **disk** and work-in-flight, not RAM — keep it, but it is not a substitute for layers 2–3.

## Topology this enables (Tier-3 prep-offload)

With layers 1–4 in place, prep can move to the **3060 (32 GB)** as the SQL design intends: the
3060 runs the RAM-governed prep dispatcher (its own free-RAM budget → ~4–6 concurrent), writes
prepped pages to the shared inbox/midbox, and the **16 GB 5080 + 64 GB 5090 run GPU-only OCR**,
whose RAM footprint is ~one worker's worth. The 16 GB box stops being the bottleneck because it
no longer does heavy CPU prep at all. Crucially, the governor means even the 3060 cannot be
OOM'd by prep — concurrency there is also RAM-bounded, answering "a 25 GB load would OOM even the
32 GB box": with the governor, prep never *reaches* 25 GB on any box.

## What changes, concretely

1. New `prep_dispatcher.py` (RAM-governed) **replaces** `prep_runner.py --parallel N`. No
   `--parallel` knob; a `--max-concurrent` *ceiling* plus the RAM gate (whichever is lower wins).
2. A small shared helper (`mem_budget.py`): free-RAM read, per-prep budget, Job-Object wrapper.
3. Supervisor (`supervisor_5090.ps1` + 5080 equivalent): add the admission gate + critical-RAM
   drain (Tier 2).
4. STAGE 1 render → 1-channel; Sauvola → float32 (Tier 4) — shared OCR scripts; Hans-review
   twice (schema/pipeline rule) and A/B the OCR output before/after to confirm no accuracy loss.

## Risks / review gates

- Tier-4 image changes touch OCR accuracy → **A/B consensus comparison required** before rollout.
- Supervisor changes touch live scaling logic → **Hans review**, deploy to the 5080 first, then
  the 5090.
- Job-Object limits must be generous enough not to kill legitimate large-volume preps.
