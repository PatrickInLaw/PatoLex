# Phase B — Fix the Pipeline Right (plan for review)

**Trigger:** Hans audit (`HANS_AUDIT_PIPELINE_2026-06-02.md`) — 7 Severity-1 findings; pipeline not fit for the 176-year campaign as-is. Patrick: stop at 1875 (single-engine = A/B version-A), then fix it right.

**Non-negotiables:** (1) Do NOT disrupt the running version-A build (finishing ~08:20) — all Phase B code work is offline on **banked data** (`page_ocr_results.json`: full UTF-8 text from all 3 engines + image, per page) and the repo scripts; the DB re-ingest happens only AFTER version-A completes + the ingest loop is stopped. (2) Nothing requires re-OCR. (3) Faithfulness absolute. (4) Determinism: same input → same output, every run.

## The fixes (mapped to Hans findings)
1. **Real token-aligned consensus committed text (F1, F2).** Replace `three_engine_consensus`'s "return tess_text + bag-of-words ratio" with: align the 3 engines' text per page (line then token sequence-alignment), **majority-vote per token** for the committed text, and a **real per-token confidence** (agreement among aligned tokens, position-aware). Honest provenance: store the actual method + which engines; `trust_level` reflects reality (no false "consensus" label).
2. **Clean, parameterized, UTF-8 ingest (F5).** Drop `safe_str`'s ASCII `errors="replace"` (it was stripping §, long-s, em-dashes from committed legal text) and the hand-escaped SQL string-concat. Use **psycopg parameterized inserts** preserving full UTF-8.
3. **Transactional, fail-loud, one canonical key (F6, F7).** Each act ingests in a transaction; on any per-act failure → rollback + **FAIL the volume (do NOT mark it `done`/`ingested`)** so it's revisited, never a silent gap. **One canonical physical-act key everywhere:** `(source_document_id, in_act_order)` — the ordinal position, which survives garbled chapter numbers. Collapse the three ingest scripts (`production_pipeline` STAGE6 / `re_ingest_fixed` / `ingest_from_ocr`) into ONE.
4. **Honest quality + flags (F8, F11, F13).** No hardcoded `ocr_cer_estimate=0.015`/`scan_quality='good'` — compute a real per-volume estimate. **Flag (`confident=False`) any act whose chapter number required OCR-substitution or whose date was fabricated** (the `{year}-01-01` fallback gets an explicit `date_unknown` flag, never masquerades as a parsed operative_date).
5. **Page-classification sanity gate (F12).** Persist the classification + add a loud FAIL if body-page count is implausible vs the volume — no silently-dropped (never-OCR'd) pages.
6. **Determinism for future OCR (F3, F4) — for 1876+ runs, not the banked 1850-1875.** Pin **identical** docTR config on both boxes (`fast_base`+`crnn_vgg16_bn`, orientation off — the 5090 currently uses bare `ocr_predictor`), set torch determinism flags + seeds. (The 1850-1875 banked data already exists with the cross-box variance; noted, accepted — the consensus is derived from the banked text either way.)
7. **Deterministic RUNBOOK + single orchestration entry.** `pipeline/RUNBOOK.md` + one entry (`run-campaign <year-range>`) that deterministically builds the queue, launches workers + the ingest loop, and a `deploy` step (repo = source of truth → boxes). A future session resumes/extends by running ONE documented thing.
8. **Second Hans pass** on the fixed pipeline (data pipeline = Hans twice).

## The A/B (text-level, from banked — no dual DB)
From each page's banked outputs derive **version-A = clean Tesseract-only** and **version-B = 3-engine consensus**, both via the fixed UTF-8 ingest path (so the ONLY variable is consensus-vs-single). Score both against **OpusGold** (+ inter-version diff) → quality delta. Measure the consensus-derivation overhead. → cost-benefit. **Key cost insight:** the 3-engine OCR is already paid + benchmarked; the consensus is a near-free re-derivation, so the consensus upgrade is almost certainly a clear win. The genuine cost trade is the VLM layer (below).

## DECISIONS FOR PATRICK
- **D1 (the real one) — does the VLM-flagging (qwen) belong in Phase B, or Phase C?** Recommendation: **Phase C.** Phase B commits the 3-engine consensus + a real confidence signal; the qwen VLM-flagging (which broke the shared-glyph floor to reach ~1% in validation) is the *verification* layer that targets low-confidence regions to feed the crowd/human queue — it's slow per-page and belongs with the crowd-correction build, not the committed-text pass. So the first A/B = single vs 3-engine-consensus; VLM is a later, separately-measured layer.
- **D2 — canonical act key = `(source_document_id, in_act_order)`**, chapter number kept as best-effort *display* (flagged if garbled), never a key. (Recommend yes.)
- **D3 — the fixed re-ingest REPLACES the lossy single-engine text in the DB** with the consensus (version-A stays preserved in banked data + the A/B report, not as a parallel DB). (Recommend yes.)

## Sequence (non-disruptive)
1. **Now (code only, no DB writes):** build the fixed consensus + clean parameterized ingest + canonical key + flags + sanity gate as ONE reviewed module; build the A/B comparison tool; pin determinism config; write the RUNBOOK. All in repo.
2. **After version-A completes (~08:20) + ingest loop stopped:** run the A/B comparison (report), then the clean consensus re-ingest of 1850-1875.
3. **Second Hans pass** on the fixed module; fix; commit.
4. **Then** resume 1876→present on the fixed, deterministic, runbook-driven pipeline.
