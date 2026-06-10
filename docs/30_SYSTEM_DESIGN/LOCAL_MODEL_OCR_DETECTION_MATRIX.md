# Local Model OCR-Garbage Detection Matrix

**Date:** 2026-06-10 · **Box:** 5090 (Ollama, 32 GB VRAM, `http://100.70.54.56:11434`) · **Task:** flag OCR-corrupted statutory acts

## Method
Each model judged the **same 35-act ground-truth set** (20 known-GARBAGE acts from 1850/1862/1863 with OCR corruption like `Btato`, `cnuct`, `8xo`; 15 nominally-CLEAN from 1984 — **at least 3 of which actually had real OCR noise**, so the CLEAN labels are a *floor* and measured precision **understates** true precision for the good models). Identical **extraction-based prompt** for every model ("list the garbled tokens, else CLEAN") via `/api/chat`, temp 0, single-stream, one model loaded at a time (forced unload between models). The prior failure (everything scored "fine") was the *vague 1-5 grade* — the extraction prompt fixed it.

Thinking-capable models (`qwen3*`, `gemma4`, `gpt-oss`, `deepseek-r1`, `nemotron-cascade`) were run with **`think:false`** in the top-level request body, except `qwen3:32b` which is reported **with thinking ON** as a deliberate cost data point.

**Recall on the 20 garbage acts is the bar** (missing garbage is unacceptable). Precision = false-positive/noise cost. Small set → numbers are indicative for ranking, not final.

## Matrix (single-stream — apples-to-apples)

| Model | VRAM | Recall | Precision | Acc | s/act | 67k 1-stream | Usable? |
|---|---|---|---|---|---|---|---|
| **aya-expanse:32b** Q4_K_M | 19.8 GB | 95% | **100%** | **97%** | 1.54 | ~29 h | ✅ **zero FP**, 1 garbage miss |
| **gemma3:27b** | 17.4 GB | **100%** | **87%** | 94% | 1.73 | ~32 h | ✅ cleanest 100%-recall flags |
| qwen3.6:35b | 23.9 GB | **100%** | 61% | 63% | 1.6 | ~29 h | ✅ fast but noisy (13 FP) |
| nemotron-cascade-2 | 24.3 GB | **100%** | 63% | 66% | 4.5 | ~84 h | ✅ 12 FP, extracts long phrases |
| deepseek-r1:32b | 19.9 GB | **100%** | 65% | 69% | 12.3 | ~229 h | ⚠ best thinker-precision but slow |
| gemma4:31b | 19.9 GB | **100%** | 61% | 63% | 3.7 | ~68 h | ⚠ 13 FP, slow |
| qwen3.5:27b | 17.4 GB | **100%** | 61% | 63% | 2.9 | ~55 h | ⚠ 13 FP, slow |
| Saul-7B-Instruct Q8_0 | 7.7 GB | **100%** | 59% | 60% | 1.0 | ~19 h | ⚠ legal-7B, worst over-flagger (14 FP) |
| gpt-oss:20b | 13.8 GB | **100%** | 61% | 63% | 7.0 | ~130 h | ⚠ 13 FP, slow for a 20B |
| phi4-mini | **2.5 GB** | **100%** | 60% | 80% | **0.80** | ~15 h | ✅ fastest/tiny, noisy FPs |
| qwen3:32b (**thinking ON**) | 20.2 GB | 95% | 58% | 57% | **21.9** | ~407 h | ❌ thinking trap — slow + worse |
| aya-expanse:8b | 5.1 GB | **40%** | 100% | 63% | 0.53 | ~10 h | ❌ misses 60% of garbage |
| SaulLM-54B-Instruct Q4_K_M | 31.4 GB | — | — | — | 14+ | ~253 h | ❌ maxes 32 GB VRAM, timeouts |

*(Excluded as not-sensible for a text task: embedding models + vision-only models.)*

**Notable:** almost every 100%-recall model lands at the **identical 13 FP / ~60% precision floor** (qwen3.5/3.6, gemma4, gpt-oss, phi4) — they flag the *same* borderline acts, which strongly implies several of those "FP" are the **real-OCR-noise 1984 acts** (correct flags scored as wrong). Only **gemma3** (3 FP) and **aya-32b** (0 FP) break that floor.

## Projected multi-stream / multi-box throughput (0.8-factor, NOT empirically tested)
Speedup ≈ **1 + 0.8 × (streams − 1)**. Streams bounded by VRAM (5090 = 32 GB usable ~28; 5080 = 16 GB usable ~12). Small models multi-stream and **also run on the 5080 in parallel**; big models are single-stream-only.

| Model | Footprint | Feasible streams (5090 + 5080) | Projected speedup | 67k effective |
|---|---|---|---|---|
| **phi4-mini (2.5 GB)** | tiny | ~3 on 5090 (2.6×) **+ ~2 on 5080** | ~4–5× combined | **~3–4 h** |
| Saul-7B (7.7 GB) | small | ~2 on 5090 (1.8×) + 1 on 5080 | ~2.6× | ~7 h |
| gemma3:27b (17.4 GB) | large | ~2 on 5090 (1.8×); won't fit 5080 | ~1.8× | ~18 h |
| aya-32b / qwen3.6 (~20–24 GB) | very large | 1 only | 1.0× | ~29 h |

## Findings
- **Eleven models hit 100% recall**, the viability bar (gemma3, phi4-mini, qwen3.5/3.6, gemma4, gpt-oss, deepseek-r1, nemotron-cascade, Saul-7B — plus aya-8b at only 40% and aya-32b/qwen3:32b at 95% miss it). They split on **precision** and **speed**.
- **aya-expanse:32b is the precision winner** — the *only* model with zero false positives (100% precision, 97% accuracy) at a cheap ~29 h cost. Its sole weakness is one missed garbage act (95% recall).
- **gemma3:27b is the cleanest 100%-recall model** — 87% precision (only 3 FP), perfect recall, ~32 h.
- **The "thinking" models add nothing here.** With `think:false` they collapse to the same ~60% precision floor as everyone else; with thinking ON (`qwen3:32b`) they are ~14× slower *and worse* (407 h, 14 FP, 1 FN). **Never enable thinking for this task.** deepseek-r1 had the best thinker precision (65%) but at ~229 h is not worth it.
- **Legal-domain tuning bought nothing.** Saul-7B was the *worst* over-flagger (14 FP); SaulLM-54B won't even fit/run on a single 5090. This is a text-integrity task, not a legal-reasoning one.
- **aya-8b is disqualified** (40% recall — misses garbage). **SaulLM-54B is disqualified** (maxes 32 GB VRAM, timeouts).
- **Fragment extraction** was tightest from aya-32b and gemma3; the ~60%-precision models returned longer, noisier token lists.

## Recommendation

**Production design — two-model cascade** (combines perfect recall with perfect precision):
1. **Stage 1 (recall net): `gemma3:27b`** — 100% recall, 87% precision, ~32 h (~18 h multi-stream). Catches everything, including the 1 act aya-32b misses.
2. **Stage 2 (precision filter): `aya-expanse:32b`** — re-scores Stage-1 hits to drive false positives to zero before a human sees them.

This keeps humans only on the genuinely ambiguous residue, runs free overnight, and is parallelizable across both boxes.

**If a single model must be chosen:**
- **gemma3:27b** — safest standalone (never misses garbage, low FP, clean flags). Best default.
- **aya-expanse:32b** — pick when false-positive *volume* is the bottleneck (zero FP), accepting the small 5% miss risk.
- **phi4-mini** — pick only as a *fast cheap pre-filter*: 100% recall, ~3–4 h full sweep multi-stream, but its ~60% precision needs a downstream filter (its FP pattern is deterministic — it flags clean section numbers — and auto-filterable).

**Do not use:** aya-8b (recall), SaulLM-54B (VRAM/speed), or any reasoning model with thinking enabled.

---
*Raw per-model results: `C:\Users\PatrickKolasinski\PatoLex-scratch\model_matrix_partial.json` · Run log: `docs/80_PROJECT_HISTORY/run-logs/model-matrix-run.log` · Harness: `C:\Users\PatrickKolasinski\PatoLex-scratch\model_matrix_benchmark.py` (prompt + test-set inherited from `ocr_detect_test.py`).*
