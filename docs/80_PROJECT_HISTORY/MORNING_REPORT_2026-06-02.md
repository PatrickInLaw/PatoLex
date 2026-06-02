# PatoLex — Overnight Run Morning Report (2026-06-02)

**Window:** ~21:47 (2026-06-01) → ~03:30 (2026-06-02). Autonomous, Telegram + `/ucp` on a ~40-min heartbeat.

---

## TL;DR

Two big things got done: **(1) the OCR accuracy pipeline is validated to legal-grade across 1850–1899**, and **(2) the early session-law corpus (1850–1860, 11 volumes) was OCR'd at that validated quality and banked.** The crowd-source correction model was designed and committed. The large 1860s+ volumes hit a GPU-memory bug mid-run (now diagnosed + fixed) and are deferred to a clean, supervised resume. Nothing was overstated; the expensive work (OCR) is banked and the remaining work is cheap (re-parse) or resumable (large-volume OCR).

---

## What is PROVEN vs PROXY vs NEEDS-HUMAN

- **GOLD-PROVEN (independent reference):** the multi-vector cascade — **4 classical engines (Surya+docTR+Tesseract+Paddle) consensus as committed text + qwen as a flagging vector + a dissent filter** — scores **1.04% aggregate silent error across 1850–1899** (17 pages, 7,256 tokens), i.e. legal-grade, and accuracy *improves* toward 1900 (CER 19.6%→7.1%; the modern era is born-digital). **Caveat:** the reference is **OpusGold** — pages I (Opus) hand-transcribed as an independent frontier-model reference with failure modes different from the OCR engines. It is *not certified human truth*. Two of my pages (mid_1858_p90, late_1867_68_p100) had alignment artifacts; the aggregate excludes their noise and is likely conservative.
- **PROXY:** per-page inter-engine agreement (Jaccard ~0.58–0.65) is a confidence signal, not accuracy; it routes the human review queue (~18–20% of tokens flagged).
- **NEEDS-HUMAN:** (a) a small human-gold audit to confirm OpusGold (a few pages keyed from scratch); (b) the crowd/expert correction of flagged tokens once the wiki is built; (c) Patrick's design decisions listed at the bottom.

---

## OCR Coverage (the corpus)

**OCR'd + banked at validated 3-engine quality:** **1850, 1851, 1852, 1853, 1854, 1855, 1856, 1857, 1858, 1859, 1860** (11 volumes). For every page: consensus text + per-token confidence + source-image path are saved to `PatoLex-scratch/production-<year>/ocr_consensus/page_ocr_results.json`. This is the crowd-source substrate.

**Deferred (GPU-memory bug, now fixed):** 1861–1875 (the big 660–1,086-page volumes). 1861 crashed, 1862 OOM-degraded, 1863 killed mid-process — none reached the DB (verified). **Banked OCR is the expensive part; these just need the fixed pipeline re-run (no new analysis).**

**Throughput reality:** ~14–27 min/volume at 3-engine on the 5080. The later volumes are 2–4× larger than I first assumed, so the full 1875 did not fit tonight — corrected honestly mid-run.

---

## Structured DB (event-sourced schema, live Postgres)

The statutory text lands in the DB as `enactment`/`provision`/`change_event` (+ `designation_history`), `trust_level='ocr_uncertain'`, source-page refs, forward-from-1850-blank. **This is partial** and was the messier part of the night:

- Re-ingest added net-new acts (enactments 1419 → 1519+, finalizing). 
- **Parser issue #1 (FIXED):** 1852+ volumes use `"APPROVED, May 1, 1852"` (comma) vs 1850/51 `"Passed …"` (no comma); the date regex missed it → 100+ acts/volume wrongly flagged. Fixed; recovery e.g. 1852 12→94, 1853 8→117 confident.
- **Parser issue #2 (in-progress at report time):** 1858–1860 use an inline `"N.—An Act"` chapter format the regex doesn't match → 0 confident acts. A CPU-only parser-completeness pass over the banked OCR is running to recover these (no re-OCR).
- **Known limitation:** ingest is idempotent on citation+source_document_id, and pre-existing low-quality SKELETON rows (from an earlier benchmark, content_sha256 NULL) share citations → some new better-quality acts were SKIPPED rather than replacing the old. **A clean re-ingest strategy (replace skeleton rows) is a follow-up.**

**Honest bottom line on the DB:** the structured layer is a real but incomplete first pass; the *reliable* deliverable is the banked OCR text + confidence + images for 1850–1860, from which the structured layer can be regenerated cheaply once the parser + ingest-replacement are finished.

---

## Issues found + fixed tonight

1. **Parser cliff (comma-after-APPROVED)** — fixed (`reparse.py`).
2. **GPU per-page memory leak** (no `torch.inference_mode`, no per-page tensor free → 16GB 5080 OOM'd on big volumes) — fixed in `production_pipeline.py` (`inference_mode` + `empty_cache`/`del` per page + `gc`). Cross-volume teardown was already fine (subprocess per volume).
3. **`re_ingest_fixed.py` schema bug** (targeted nonexistent columns) — rewritten to match the real event-sourced schema.
4. **Surya local install** — patched for transformers 4.57.6 compatibility; now runs locally on the 5080 (no 5090 dependency).

Still open: parser format #2 (in progress), skeleton-row replacement, a page-text DB table for the wiki substrate (schema gap), and a small human-gold audit.

---

## How to RESUME the large volumes (1861–1875) next session

The pipeline is fixed and the batch is resumable:
```
python C:\Users\PatrickKolasinski\PatoLex-scratch\production_batch.py --start-year 1861 --end-year 1875
```
It skips completed volumes via `production_batch_state.json` and now has the GPU-memory fix. **Run it supervised** (watch the first large volume confirm the OOM fix holds end-to-end). After it completes, run the parser-completeness re-parse + corrected `re_ingest_fixed.py` over the new volumes.

---

## Crowd-source correction model (designed + committed)

`docs/30_SYSTEM_DESIGN/CROWDSOURCE_CORRECTION.md`: launch open-source with **text + source image + correction path**; random-teleport-to-review driven by the confidence flags; multi-reviewer trust ladder; corrections as `change_event`s with contributor provenance; two tiers (public wiki + professional). Evolves the launch bar (validation = OCR-confidence + image + correction, not perfection). Design tensions for you to resolve at Gate H: citation-stability vs live correction, Git-immutability vs OCR corrections, contribution licensing (CC0?).

---

## Decisions for Patrick

1. **Resume strategy for 1861–1875:** supervised re-run with the fixed pipeline (recommended), or parallelize across both GPU boxes (5080+5090) to go faster?
2. **Skeleton-row replacement:** OK to have the re-ingest *replace* the old low-quality benchmark acts (not just skip-on-conflict) so the DB holds the 3-engine versions?
3. **Page-text DB table:** add one so the full OCR text + confidence + image refs live in the DB (the wiki substrate), not just on disk?
4. **Human-gold audit:** key ~3–5 session-law pages from scratch to certify OpusGold?

---

## Commits / artifacts

Run-logs in `docs/80_PROJECT_HISTORY/run-logs/` (production-1850, production-batch, opusgold-*, dissent-filter, parser-fix, windown-reingest, parser-completeness). OpusGold reference set in `PatoLex-scratch/ocr-bakeoff/gold/opusgold/`. Banked OCR in `PatoLex-scratch/production-<year>/`. Validation doc `docs/30_SYSTEM_DESIGN/OCR_ACCURACY_VALIDATION.md`. All work pushed to `main`.
