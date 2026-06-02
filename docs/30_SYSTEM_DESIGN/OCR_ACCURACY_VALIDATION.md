# OCR Accuracy Validation — the path to legal-grade

**Status:** cc002, 2026-06-01. **Directional** result on a small human-gold set (1 full session-law page + 5 short code pages). Establishes that the multi-vector ensemble architecture (`VERIFICATION_TOOL.md`) reaches legal-grade on the *hardest* material (faded 1850 session-law); the numbers need 10+ session-law gold pages to firm. **The ~0.5% / ~1.5% accuracy figures here are directional and NOT yet human-gold certified** (a ~10-20 page human-gold audit is still owed).

> **As-built note (2026-06-02): production consensus is 3 engines, not 4.** This page records the original engine **bake-off**, which *measured* four classical engines including PaddleOCR. The **production consensus committed to the DB uses 3 engines — Tesseract + docTR + Surya** (`pipeline/consensus.py`, `N_MAX_ENGINES=3`; method tags `token_majority_3` / `token_majority_2`). **PaddleOCR is NOT a production consensus voter** (it failed to run reliably on the Windows OCR boxes — see the bake-off run logs — and is not in `consensus.py`). The 4-engine numbers below are the bake-off measurement, not the as-built voter set; the 1850-1875 corpus was committed via the 3-engine consensus (4057 `token_majority_3` + 205 `token_majority_2`, zero 4-engine acts in the DB).

## The question

Can OCR of California's earliest, faded session-law scans (the primary source) reach **legal-grade accuracy** (~1–2% silent error)? Single-engine OCR cannot — but single-engine CER is the wrong metric for our architecture, which commits a **consensus** of faithful engines and routes their **disagreements** to human review.

## The measured cascade (page `early_1850_p90`, 602 tokens)

| Stage | Silent-error rate | Review queue | Notes |
|---|---|---|---|
| Best single engine (Surya 0.13, v2-grayscale) | 12.71% CER | — | |
| **classical-engine consensus** (bake-off measured 4: Surya + Tesseract + docTR + PaddleOCR; **production = 3, PaddleOCR dropped** — see as-built note) | **4.36%** | 16.1% | ~3× better than single |
| **+ qwen2.5-VL + GOT-OCR as flagging vectors** | **0.50%** ✅ | 32.9% | legal-grade |

## Why it works — independent vs shared failures

- **Word-drops are engine-independent.** Where Surya drops "judgments," / "shall be delivered" / "one County Clerk," Tesseract keeps them (and vice-versa). Consensus rescues these (55–73% rescue rate). These never reach the committed text silently — the alignment gap becomes a flagged review item.
- **Glyph confusions are *shared* across all four classical engines.** A ~6.5% hard floor (39 of 602 tokens) where all four agree on the *wrong* answer: the `e→o` antique-typeface confusion (each→cach, be→bo, he→ho, next→noxt, lies→lics) and the section symbol `§→8`. Majority voting cannot escape an error all four make.
- **VLMs break the shared floor.** qwen2.5-VL and GOT-OCR — trained on modern text, fundamentally different architecture — do **not** share the classical glyph confusion. Both correctly read the `e→o` and `§` tokens where all four classical engines failed (37 of 39 floor errors caught). Used as **flagging vectors only** (never committed text, because they modernize), their dissent converts a *silent* classical-consensus error into a *flagged* review item.

## The cost and the optimization

- VLMs inflate the review queue (~16% → ~33%) with an **~80% false-flag rate** — they "correct" faithful archaic spelling/punctuation and dissent where the classical consensus was right.
- **Next optimization: a dissent filter** that ignores known VLM-modernization patterns (spelling/punctuation normalization) and flags only *content-character* disagreements → should cut the false-flag rate sharply and shrink the queue without losing real catches.

## Faithfulness — verified against human gold

The "kidnaping" litmus is confirmed against Patrick's hand-keyed gold: the **1872** Penal Code page genuinely prints **"kidnapping"** (double-p) and the **1903** code prints **"kidnaping"** (single-p); the faithful engines reproduce each page's actual spelling. The earlier qwen/GOT disqualification was on the 1903 page (source "kidnaping" → they modernized to double-p). Faithful engines reproduce the page; VLMs modernize — hence VLMs flag, never source.

## What firms this up

- **10+ full session-law pages** (400+ tokens) across 1850–1870, diverse print runs and condition, to put a confidence interval on the 0.50% silent rate and the ~80% false-flag rate.
- Build + measure the **dissent filter** (queue reduction).
- The **scan-quality lever**: cleaner source scans (or image restoration / super-resolution) shrink the shared floor at the source → smaller queue, lower cost.

## Throughput (for the production run)

5090 vs 5080 benchmark (warmup-discarded, batched): **Surya batched on the 5090 = 0.70 s/page** (the 5080's 16 GB OOMs on Surya batching; the 5090's 32 GB is required). docTR ~0.23 s/page on either. Production split: **Surya batched / 5090 + docTR / 5080 + Tesseract / spare CPU**, VLM vectors (qwen via Ollama / GOT) on the 5090. Corpus-scale OCR is tractable at these rates.

---

## Revision History

| Date | Change |
|------|--------|
| 2026-06-01 | cc002: Directional OCR accuracy cascade (single → consensus → +VLM flagging) on the small human-gold set. |
| 2026-06-02 | cc002 (doc rewrite): Added as-built note — **production consensus = 3 engines (Tesseract+docTR+Surya), PaddleOCR dropped/not a voter** (the 4-engine numbers are the bake-off measurement, not the as-built voter set). Flagged the ~0.5%/~1.5% figures as directional, **not yet human-gold certified**. |
