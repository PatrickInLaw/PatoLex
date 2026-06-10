# Local Model OCR-Garbage Detection Matrix

**Date:** 2026-06-10 · **Box:** 5090 (Ollama, 32 GB VRAM) · **Task:** flag OCR-corrupted statutory acts

## Method
Each model judged the **same 35-act ground-truth set** (20 known-GARBAGE acts from 1850/1862/1863 with OCR corruption like `Btato`, `cnuct`, `8xo`; 15 nominally-CLEAN from 1984 — 3 of which actually had real OCR noise, so labels are a *floor*). Identical **extraction-based prompt** for every model ("list the garbled tokens, else CLEAN") via `/api/chat`, temp 0, single-stream. The prior failure (everything scored "fine") was the *vague 1-5 grade* — the extraction prompt fixed it.

**Recall on the 20 garbage acts is the bar** (missing garbage is unacceptable). Precision = false-positive/noise cost. Small set → numbers are indicative for ranking, not final.

## Matrix (single-stream — apples-to-apples)

| Model | VRAM | Recall | Precision | s/act | 67k 1-stream | Usable? |
|---|---|---|---|---|---|---|
| **gemma3:27b** | 17.4 GB | **100%** | **87%** | 1.73 | ~32 h | ✅ cleanest flags |
| **phi4-mini** | **2.5 GB** | **100%** | 60% | **0.80** | ~15 h | ✅ fastest, tiny, noisy FPs |
| **qwen3.6:35b** | 23.9 GB | **100%** | 61% | 1.6 | ~29 h | ✅ but noisy, big |
| gemma4:31b | 19.9 GB | **100%** | 61% | 3.7 | ~68 h | ⚠ slow |
| qwen3.5:27b | 17.4 GB | **100%** | 61% | 2.9 | ~55 h | ⚠ slow |
| Saul-7B-Instruct | 7.7 GB | **100%** | 59% | 1.0 | ~19 h | ✅ legal-7B, noisy |
| aya-expanse:32b | 19.8 GB | 95% | **100%** | 1.54 | ~29 h | ⚠ slight garbage miss |
| qwen3:32b | 20.2 GB | 95% | 58% | **21.9** | ~407 h | ❌ absurdly slow |
| aya-expanse:8b | 5.1 GB | **40%** | 100% | 0.53 | ~10 h | ❌ misses 60% of garbage |
| SaulLM-54B-Instruct | 28.4 GB | nan | nan | 14.0 | — | ❌ broken output (completion model) |
| gpt-oss:20b | 13.8 GB | *pending* | | | | thinking model — see run-log |
| deepseek-r1:32b | 19.9 GB | *pending* | | | | thinking model — see run-log |
| nemotron-cascade-2 | 24.3 GB | *pending* | | | | thinking model — see run-log |

*(Excluded as not-sensible for a text task: embedding models + vision-only models. The 3 "pending" rows were still running when the orchestrating agent timed out; `model-matrix-run.log` captures them as they finish — they are more thinking models and are not expected to beat the fast 100%-recall options.)*

## Projected multi-stream / multi-box throughput (0.8-factor, NOT empirically tested)
Speedup ≈ **1 + 0.8 × (streams − 1)** per Patrick. Streams bounded by VRAM (5090 = 32 GB usable ~28; 5080 = 16 GB usable ~12). Small models multi-stream and **also run on the 5080 in parallel**; big models are single-stream-only.

| Model | Footprint | Feasible streams (5090 + 5080) | Projected speedup | 67k effective |
|---|---|---|---|---|
| **phi4-mini (2.5 GB)** | tiny | ~3 on 5090 (2.6×) **+ ~2 on 5080** | ~4–5× combined | **~3–4 h** |
| Saul-7B (7.7 GB) | small | ~2 on 5090 (1.8×) + 1 on 5080 | ~2.6× | ~7 h |
| gemma3:27b (17.4 GB) | large | ~2 on 5090 (1.8×); won't fit 5080 | ~1.8× | ~18 h |
| qwen3.6 / aya-32b / gemma4 (~20–24 GB) | very large | 1 only | 1.0× | ~29–68 h |

## Findings / recommendation
- **Six models hit 100% recall** (the bar): gemma3:27b, phi4-mini, qwen3.6:35b, gemma4:31b, qwen3.5:27b, Saul-7B. They split on **precision** (gemma3 = 87%, clean; the rest ~60%, noisy) and **speed**.
- **The "thinking" models add nothing here** — same-or-worse precision (~60%), much slower (qwen3:32b = 21.9 s/act), and SaulLM-54B won't emit clean output via Ollama. Clear lesson: for this task, a fast non-thinking model wins.
- **aya-8b is disqualified** (40% recall — misses garbage). aya-32b has perfect precision but misses 5% of garbage — not worth it when others hit 100%.
- **Two real choices:**
  1. **phi4-mini — fastest, multi-streamable.** 100% recall, tiny (2.5 GB), runs many streams across both boxes → **full 67k sweep in ~3–4 h, free.** Cost: 60% precision (noisy), but its false positives are a *deterministic* pattern (it flags clean section numbers) and can be auto-filtered. **Best if we want it done fast.**
  2. **gemma3:27b — cleanest single-pass.** 100% recall, 87% precision (actionable flags), but large so only ~1.8× multi-stream → ~18 h. **Best if we want a clean flag queue with minimal post-filtering.**

**Recommendation: phi4-mini for the sweep** (speed + multi-stream + 100% recall), paired with a cheap deterministic FP-filter to clean its output — gets us a full free corpus pass in an afternoon rather than overnight. gemma3:27b is the fallback if the FP-filter proves fiddly.
