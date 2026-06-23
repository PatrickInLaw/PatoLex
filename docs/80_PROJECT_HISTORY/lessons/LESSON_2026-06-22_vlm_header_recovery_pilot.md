# LESSON 2026-06-22 — Local VLM (Qwen2.5-VL-7B) recovers multi-act-cluster chapter headers Surya/Tesseract miss

## Context
The biennial 1866–1878 session-law volumes have a stubborn residual: ~187 chapters still
missing after Tesseract + docTR + Surya consensus + clause-seq recovery. These cluster on
**multi-act pages** (several `CHAPTER <n>` headings on one plate) where the printed heading
word is degraded enough that the OCR engines drop or mis-segment it. A local OCR-capable
vision-language model was piloted on the RTX 5090 to read these headers directly. **Zero
Claude vision tokens** — all reading done by the local model.

## What was installed
- **Model:** `Qwen/Qwen2.5-VL-7B-Instruct` (strong on degraded small print + Roman numerals).
- **Venv:** `C:\PatoLex-scratch\ocr-engines\qwenvl-venv` (separate from surya-venv).
  Built from Python 3.12.10. Stack: **torch 2.7.0+cu128** (the proven Blackwell/5090 build,
  same as surya-venv), **transformers 5.12.1**, `accelerate`, `qwen-vl-utils[decord]`, `pymupdf`.
- **Invocation:** `Qwen2_5_VLForConditionalGeneration` + `AutoProcessor`, `torch_dtype=bfloat16`,
  `device_map="cuda"`. These class names ARE present in transformers 5.x (verified).
- **Perf:** ~12s warm load (~200s cold first download of ~16GB weights), **16.6 GB VRAM** (of
  32 GB — fits with large headroom), **~4.0 s/page** at 350 dpi.

## Findings (durable)
1. **The VLM reads what Surya could not.** Pilot on 10 hard 1870 chapters → **9/10 recovered**.
   The single non-hit (ch143 / CXLIII) is genuinely **not printed** in its manifest page range
   (the page sequence jumps 142→144 with a stray 163 anchor) — a manifest page-anchor artifact,
   NOT a model miss. Effective read-lift = **9/9 of chapters actually on the page**.
2. **CRITICAL PARSER LESSON — the VLM transcribes the scan FAITHFULLY, broken ligatures and all.**
   On degraded 19th-c. plates the printed word "CHAPTER" comes through the model as
   **CHIAPTER / CITAPTER / CHAPTEER / OHAPTER**. A strict `\bCHAPTER\b` regex silently drops
   these → lift was only 7/10 before the fix. The heading token MUST be matched fuzzily
   (`CHAP_TOK = [CO][HI]{0,2}[AT]{1,3}PTE+R`) while the chapter NUMBER stays strict (so we never
   invent a number). This is the same garble class already seen in the stored OCR (`CITAPTER XXIX`).
3. **source_page mapping:** the residual manifest's `source_page` == `page_1indexed` in
   `ocr_consensus/page_ocr_results.json` == the source-PDF page (1-indexed). PDF page 0-index =
   `source_page - 1`. The biennial `*_Statutes.pdf` under `chief-clerk-archive` is a pure image
   scan (no text layer) — render with PyMuPDF `get_pixmap(dpi=350)`.
4. **`production-<vol>/` dirs hold OCR consensus JSON, NOT page rasters.** The manifest's
   `<vol>/pages_raw/page_*.png` pattern does not exist on disk for these volumes; render pages
   from the source PDF instead.

## Reusable tool (for the full ~187 run)
`C:\PatoLex-scratch\_vlm_header_recover.py` — year-driven, `--confirm`-gated (dry summary
otherwise), append-safe merge into `C:\PatoLex-scratch\_vlm_out\vlm_<year>.json`, **NO DB writes /
no deletes / no mutation of parsed_acts_*.json**, and **self-logs** each run to
`docs/80_PROJECT_HISTORY/run-logs/vlm-pilot-run.log` (per the project rule that tools self-log).

Full run (launch as background commands, one per year; run `_residual_manifest.py <year>` first):
```
C:/PatoLex-scratch/ocr-engines/qwenvl-venv/Scripts/python.exe \
  C:/PatoLex-scratch/_vlm_header_recover.py <year> --confirm
# years: 1866 1868 1870 1872 1874 1876 1878
```
Output is a CANDIDATE header list for downstream review/merge — it is NOT auto-applied to the corpus.

## GO/NO-GO
**GO** on running the full ~187. ~30–45 min GPU wall total, well within VRAM, ~100% read-lift on
present chapters. Caveat: a handful of "missing" chapters are manifest page-anchor artifacts
(chapter genuinely not in the bracketed range) — those will show as non-recoveries and need the
manifest range widened or the cross-volume anchor fixed, not more model effort.
