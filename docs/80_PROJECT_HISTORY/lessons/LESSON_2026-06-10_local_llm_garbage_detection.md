# LESSON: Local LLM Garbage Detection — NO-GO

**Date:** 2026-06-10
**Session:** cc007 (local LLM validation)
**Status:** Investigation complete, recommendation: NO-GO

---

## Summary

A validation experiment was run to determine whether a free local Ollama model on the 5090 GPU box could replace paid API calls for sweeping 75,340 corpus acts for OCR garbage. The answer is **NO** — every model tested achieved 0% garbage recall, and the root cause is a fundamental calibration gap between the API labeler's definition of "garbage" and what local models consider "garbage."

---

## What Was Tested

**Hardware:** RTX 5090 (32 GB VRAM), 30,231 MB free. Ollama running on port 11434 (PID 7360).

**Models available (Ollama, GGUF):**
| Model | Size | Params | Quant |
|-------|------|--------|-------|
| SaulLM-54B-Instruct | 28.4 GB | 46.7B | Q4_K_M |
| qwen3:32b | 20.2 GB | 32.8B | Q4_K_M |
| aya-expanse:32b | 19.8 GB | 32.3B | Q4_K_M |
| gemma3:27b | 17.4 GB | 27.4B | Q4_K_M |
| aya-expanse:8b | 5.1 GB | 8.0B | Q4_K_M |
| nemotron-cascade-2 | 24.3 GB | 31.6B | Q4_K_M |
| deepseek-r1:32b | 19.9 GB | 32.8B | Q4_K_M |
| (+ 15 more vision/embedding models) |

**Validation sample:** 300 acts stratified as all 100 "garbage"-labeled acts + 200 random non-garbage (from 4,415 API-labeled acts). Sample located at `C:\Users\PatrickKolasinski\PatoLex-scratch\_coherence\local_llm_validation_sample.json`.

**Models run to completion on full 300-item sample:**
- gemma3:27b — 0.80 s/act
- aya-expanse:8b — 0.37 s/act

**Models spot-tested (5-20 items):**
- aya-expanse:32b (0.94 s/act), qwen3:32b (~5-14 s/act), SaulLM-54B (~12 s/act), deepseek-r1:32b (~8-14 s/act), nemotron-cascade-2 (~2 s/act)

---

## Results

| Model | Garbage Recall | Garbage Precision | 3-way Agreement | Avg s/act |
|-------|---------------|-------------------|-----------------|-----------|
| gemma3:27b | **0%** | 0% | 45.7% | 0.80s |
| aya-expanse:8b | **0%** | 0% | 26.0% | 0.37s |
| aya-expanse:32b (20-item pilot) | **0%** | 0% | 0% | 0.94s |

**All other models spot-tested also failed to call any garbage act "garbage"** with any of the prompts tried.

---

## Root Cause: Calibration Gap

The API labels define "garbage" using a **legal-citation-precision threshold**, not a readability threshold:

- An act is "garbage" if **section numbers are corrupted** (e.g., `5707` → `oTOT`), even if the surrounding prose is readable
- An act is "garbage" if **chapter citation is mangled** (e.g., `CCLVITII` for a valid Roman numeral), even if the body is intact
- An act is "garbage" if **approval date is corrupted** in a date-specific way, not just noisy

**What these "garbage" acts actually look like in the 300-char text snippets:** Most look like `noisy_but_coherent` or even `clean` to any model reading the prose. The garbage signal is in the citation-precision layer (section numbers, chapter numbers), not in the readability of the prose.

**Examples of API-labeled "garbage" that look readable:**
```
CHAPTER 1387 — An act to amend Seclion 5707 of the Elections Code...
SEcTION 1. Section 5707 is amended to read: oTOT. In order tu prevent...
```
→ "oTOT" is the corrupted `5707.` section number. API says garbage (correct: section reference unrecoverable). Local model says noisy_but_coherent (also defensible: prose is readable).

**This is not a prompt engineering problem.** Every variant tried (zero-shot, few-shot with examples, binary YES/NO framing, system prompt with explicit garbage definition) failed because:
1. Local models don't have the legal-precision instinct to flag corrupted section numbers as "unrecoverable"
2. The prose surrounding the corrupted citations is often fluent, masking the issue
3. 2.3% garbage rate makes the class extremely rare — models default to the majority class

---

## Throughput (if it had worked)

| Model | s/act | 75,340-act sweep |
|-------|-------|-----------------|
| aya-expanse:8b | 0.37s | ~7.7 hours |
| gemma3:27b | 0.80s | ~16.8 hours |
| aya-expanse:32b | 0.94s | ~19.7 hours |
| qwen3:32b | ~7-14s | ~145-290 hours |
| deepseek-r1:32b | ~8-14s | ~165-290 hours |
| SaulLM-54B | ~12s | ~250 hours |

The 8B models are fast enough (~8 hours), but accuracy is disqualifying.

---

## Recommendation: NO-GO

**Local model garbage sweep: NOT viable at any model size tested.**

The fundamental blocker is calibration, not capability. The API labeler used for the L2 ground truth has legal-precision calibration that requires understanding what a corrupted section number means for legal recoverability — a concept local models don't express without fine-tuning or extensive few-shot context.

**Alternative approaches if garbage sweep matters:**

1. **Deterministic Rule_E approach** (already analyzed in `garbage_predictor_analysis.md`): P=2.4%, R=44% at free compute cost. Catches 44/100 garbage acts. Misses the 56% "pure OCR degradation" garbage (corrupted section numbers in readable-prose acts). May be good enough if the goal is flagging, not exhaustive recall.

2. **Continue with API calls** (Claude haiku): The L2 labeling workflow cost is the baseline. At ~$0.003/act (estimate) × 75,340 acts = ~$225 for the full corpus. Given the calibration complexity, this is the only reliable path to high recall.

3. **Re-define "garbage" more narrowly** for the sweep: if the goal is only "prose too corrupted to read" (ignoring citation precision), then local models like gemma3:27b at 0.80s/act would work — but that's a different (lower-value) classification than what the L2 labels capture.

4. **Fine-tune approach**: A local model fine-tuned on 200-400 labeled examples from the L2 labels would likely learn the calibration. Not evaluated in this session.

---

## Artifacts

- `C:\Users\PatrickKolasinski\PatoLex-scratch\_coherence\local_llm_validation_sample.json` — 300-item stratified sample
- `C:\Users\PatrickKolasinski\PatoLex-scratch\_coherence\local_llm_metrics_gemma3_27b.json` — gemma3:27b full metrics
- `C:\Users\PatrickKolasinski\PatoLex-scratch\_coherence\local_llm_metrics_aya-expanse_8b.json` — aya-expanse:8b full metrics
- `C:\Users\PatrickKolasinski\PatoLex-scratch\_coherence\run_local_llm_validation.py` — validation harness (can be reused for future model tests)
- `C:\Users\PatrickKolasinski\PatoLex-scratch\_coherence\build_sample.py` — stratified sample builder
