# Lesson: the OCR pipeline is CPU-prep-bound, not GPU-bound (worker-count tuning)

**Date:** 2026-06-02 · **Source:** worker-count benchmark (3/1 vs 4/2), cc002.

## Finding

The 5090 OCR pipeline runs a heavy **CPU-bound PREPROCESS stage** (300-DPI render +
grayscale + page classification) *before* the GPU OCR stage, per volume.

Benchmark result: **4 workers on the 5090, started together (lockstep), is NET-NEGATIVE
vs 3.** All 4 landed on fresh prep-heavy 1920s volumes simultaneously, saturated CPU at
**91–94%**, per-worker prep throughput **collapsed ~10× (≈50 → ≈5 pg/min)**, GPU util
stayed **0–3%** (starved), and **zero OCR pages** were produced in 23+ min. Reverted to 3/1.

At **3 workers** the CPU has headroom — a worker reaches the GPU stage within ~3 min.
**3/1 (3×5090 + 1×5080) is the proven optimal config, ~50 pg/min realized** → ~4.3 days
to the ~1999 OCR target (~306k pages).

## Root cause / the real lever

The bottleneck is the **CPU prep stage, NOT the GPU.** Adding GPU workers does not add
capacity once CPU prep is the limiter — it adds contention. The real throughput lever is
getting prep **off the critical path**:
- **Prep-offload:** render+preprocess on CPU-heavy / lesser-GPU machines (the 3060) and
  reserve the 5-series GPUs for GPU-only OCR. (Matches Patrick's earlier instinct: "do
  Tesseract/preprocessing on lesser hardware, save the over-the-top models for the 5-series.")
- **Intra-worker pipelining:** overlap prep(volume N+1) with GPU-OCR(volume N).

## Nuance — lockstep vs desynced (do not over-generalize)

The catastrophic 10× collapse was measured for workers in **LOCKSTEP** (all prepping at
once). The **desynced** case — a 4th worker added mid-run to a phase-spread set of 3, so at
any moment some workers are in CPU-prep and others in GPU-OCR — was **NOT measured.**
Staggering avoids the simultaneous-prep CPU spike and a desynced 4th could even be
net-positive (filling GPU idle gaps while others prep). But it is **not guaranteed
contention-free**: 4 overlapping workers still demand more total CPU-prep/sec than 3, so if
the *average* number prepping at once exceeds CPU capacity, prep still slows — gracefully,
not off the 10× cliff. Whether 4-desynced is net-positive depends on the prep:OCR time ratio
and CPU headroom, which is unmeasured. The symmetric-scaling supervisor (add one worker live
to a running set) is the safe way to test 4-desynced and measure GPU util + prep rate.

## 5080 note

Its OCR model (Surya) uses only ~1–5 GB VRAM; 16 GB easily holds 2 workers — OOM is not a
constraint. The 5080 is also compute-bound.

## Operational guidance

**Keep the 5090 at 3 workers** until prep-offload (or intra-worker pipelining) is built.
Do not chase a 4th GPU worker as a throughput win.
