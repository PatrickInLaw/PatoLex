# Gate C — Penal Code Slice Proof (1872–1903)

**Status:** Complete (cc002, 2026-05-31). Data-first spike run autonomously via sonnet subagents; synthesized + adversarially reviewed here. Scratch artifacts in `C:\Users\PatrickKolasinski\PatoLex-scratch\gate-b-historical\`.

**Question the proof had to answer:** Can we reconstruct California statute history from 19th-century scans *to a trustworthy standard*, and validate it against independent ground truth — before committing to a schema or scale-out?

---

## Verdict: QUALIFIED-GO

The **reconstruction-and-validation *method* is sound and was confirmed against an independent source.** The remaining risk is **text-extraction quality**, which is a known, bounded engineering problem with hardware we already have — not a fundamental unknown. Risk-first goal met: the thing most likely to be impossible (trustworthy reconstruction + validation) is demonstrably achievable; what's left is execution quality.

**Be precise about what is and isn't proven** (correcting subagent optimism):
- **PROVEN:** the *amendment-timeline* method — parse the explicit history notes from a good annotated edition, cross-check against an independent index. On the overlapping sample, **85% agreement (Jaccard ≥ 0.5, mean 0.80)** between the 1903 Deering history notes and the *Index to the Laws 1850-1893*.
- **NOT YET PROVEN:** the *point-in-time text layer* — i.e., reliably producing *what each section said* at each version. Raw Google OCR is inadequate for this (see below). This needs the vision-LLM re-OCR pass we scoped (5090) but have not yet tested.
- **CAVEAT on strength:** the validated overlap was only **27 sections** and section-level extraction recall was **~30%**. The result is genuinely encouraging but is a promising signal on a modest sample, not a finished accuracy guarantee.

---

## What was done (steps 1–4)

1. **Pulled** OCR text of six Penal Code editions from Internet Archive (1872 baseline + Desty 1881/1883/1885/1889 + Deering 1903) — public-domain, clean channel.
2. **Extracted** each edition to JSON `{section_num, text, history_notes}` with one uniform parser.
3. **Reconstructed** per-section timelines two ways and compared methods.
4. **Validated** the annotation-driven timeline against the independent *Index to the Laws 1850-1893*, plus section-number integrity and marquee spot-checks.

## Key empirical findings

- **Inter-edition OCR text-diffing FAILS.** Median normalized similarity for the *same* section between the 1872 and 1881 scans was **0.07** — independent scans of different physical copies diverge almost completely. You cannot separate real amendments from OCR noise this way; only ~8% of diff-detected changes had any corroboration. **Method rejected.**
- **Annotation-driven reconstruction WORKS.** The 1903 Deering edition carries explicit credits ("En. February 14, 1872. Am'd. 1875-6, 110; 1880, 23."). Parsing these gives the amendment timeline directly, and it agrees with the independent Index at 85% on the tested overlap. **Method adopted.**
- **Section-number integrity** on the parsed 1903 set: 0 duplicates, 0 out-of-range — but coverage is the problem, not corruption.

## Real flaws found (both fixable, pre-implementation)

1. **Predecessor-statute contamination (~13%).** Annotated editions interleave pre-1872 Criminal Practice Act history with Penal Code history → some entries show amendment years < 1872 (impossible). Fix: filter years < code-enactment year.
2. **Section bundling / low recall (~30%).** The parser grouped multiple contiguous sections into one record (361 records for ~1,200 sections). Fix: finer section-boundary detection (`§ NNN.` header regex), and/or vision-LLM re-extraction.

---

## Implications for the plan

- **Adopt annotation-driven reconstruction** (a good annotated edition's history notes) as the primary method for the historical era, cross-validated against an independent index — rather than diffing noisy OCR across editions. This mirrors how the published annotated codes already encode history, and it gives a built-in validation oracle.
- **The text layer is the next risk to retire:** test a **vision-LLM re-OCR pass on the 5090** against a sample of these pages and measure whether it lifts section-level recall and text fidelity to a trustworthy bar. This is the one unproven piece, and we have the hardware.
- **Schema (Gate D) can now be informed by real data shape:** sections need a synthetic identity (numbers bundle/shift), versions carry `{operative_year(s), source citation, text, trust-level}`, and amendment events parse from credit notes. Build it from these JSON artifacts.

## Recommended next steps (Gate C → D)

1. Re-extract the 1903 edition at section-level granularity + apply the <1872 contamination filter; re-run the Index cross-check on a **larger** overlap to firm up the 85% number.
2. **Vision-LLM re-OCR spike (5090)** on ~20 pages → measure recall + text fidelity vs. raw Google OCR. This retires the text-layer risk.
3. Only then design the era-aware schema (Gate D) from the validated artifacts.

---

## OCR Benchmark (5090 + 5080) — text-layer risk NOT yet retired

First-cut benchmark: 20 Penal Code page images (1872 + 1903), 5 with hand-verified gold; models via Ollama on both boxes. Artifacts: `PatoLex-scratch/gate-b-historical/ocr_benchmark_{results.csv,report.md}`.

**Quality (vs gold):** best model = `qwen2.5vl:7b` at **~55% mean page-CER** (34-43% on substantive law pages, >70% on title pages). `minicpm-v` disqualified (hallucination/repetition loops, CER >300%). `llama3.2-vision:11b` ~76%. **None is legal-grade** (need CER well under 5%, realistically <1% for served text).

**Infra (answers the hardware question):** BOTH machines usable. 5090 ~**3× faster** (5.1s/pg vs 14.5s/pg) and the only box with VRAM headroom for >7B models (5080 maxes 16GB at 7B). **Batching (4-concurrent) is WORSE (~0.3×)** — Ollama serializes on one GPU; use sequential. Combined throughput ~**23K pages/day**.

**Critical caveats (adversarial review of the subagent's read):**
1. **CER is whole-page**, including marginal notes, running heads, case-citation numerals, and library stamps — content vision-LLMs routinely omit/reorder/normalize. It **likely overstates error on the statutory text itself** (the part we serve). Must re-measure CER on **section-text-only**.
2. The "0.0% mutual CER" the subagent cited as proof of "genuine OCR difficulty" compared the **same model on two machines** — it only proves determinism, **not** that independent OCRs agree. The intended cross-*model* diagnostic (Q1) was not actually run.
3. **The dedicated OCR engines were never tested:** Falcon-OCR failed to load (transformers API mismatch), Tesseract isn't installed, no cloud Document AI ceiling reference. A general vision-LLM is not the tool most likely to win verbatim transcription.

**Verdict:** vanilla local vision-LLM OCR is **not legal-grade** on 1870s pages out of the box; the text-layer risk is **active, not retired**. Path to retire it: (a) re-measure body-text-only CER; (b) test Tesseract + fix Falcon-OCR + a cloud ceiling reference; (c) multi-model consensus/voting with disagreement-flagging; (d) likely fine-tuning on period legal typography and/or higher-quality source scans; (e) human-verified baseline + per-section trust levels. The reconstruction *method* (annotation-driven, §ahead) still holds; the *exact-text* layer needs real work.

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc002: Gate C slice proof (PC 1872-1903). Inter-edition OCR diffing rejected (median sim 0.07); annotation-driven method adopted + validated vs Index 1850-1893 at 85%/27-section overlap. QUALIFIED-GO: method proven, text-layer (vision-LLM re-OCR) is the remaining bounded risk. |
