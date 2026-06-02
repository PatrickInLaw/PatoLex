# Hans Adversarial Audit — OCR + Ingest Pipeline (2026-06-02)

Verdict: **NOT fit for a deterministic 176-year campaign. Stop at the 1850-1875 slice and fix before scaling.** (Aligns with Patrick's "stop at 1875, fix it right" call.) Read-only audit of `pipeline/5080/` + `pipeline/5090/` against the live Drizzle schema.

**Crucial mitigant:** the banked per-page JSON (`page_ocr_results.json`: full **UTF-8** `tess_text` + `doctr_text` + `surya_text`) + page images are INTACT. Every fix below is a **re-derivation from banked data — no re-OCR**. The lossy/single-engine problems are at the *ingest/commit* layer, not the banked OCR.

## SEVERITY 1 — produces wrong/misleading data
- **F1. "three_engine_consensus" commits Tesseract only (CONFIRMED).** All branches `return tess_text`; Surya/docTR are run at full GPU cost then discarded into a scalar ratio. Worse: the DB provenance writes `ocr_engine='surya+doctr+tesseract-5'` — a **false consensus label** baked into provenance. (`production_pipeline.py:589-636`, `ocr_only_5090.py:412-435`, ingest `:322/:908`.) → This single-engine output IS the A/B version-A.
- **F2. agreement_ratio is bag-of-words `set()` overlap, not token-aligned.** Cannot see transpositions, dropped lines, duplicated paragraphs, or misread numbers (numbers read as low-confidence even when correct). The whole confidence/teleport/review-flag strategy rides on this worthless statistic.
- **F3. Cross-machine non-determinism:** 5090 runs **bare `ocr_predictor(pretrained=True)`** (default arch, orientation ON); 5080 runs **pinned `fast_base`+`crnn_vgg16_bn`, orientation OFF**. Same corpus, different docTR, decided by a claim-lock race. Harmless today (docTR discarded) → **fatal the moment consensus is real.**
- **F4. No determinism controls anywhere** (no seed, no `use_deterministic_algorithms`, no `cudnn.deterministic`). Neural OCR on CUDA is not bit-reproducible across runs/cards. "Deterministic" is only accidentally true for Tesseract-the-only-engine-that-counts.
- **F5. `safe_str` is ASCII-lossy + SQL string-concat.** `encode("ascii", errors="replace")` turns §, long-s, em-dash, accents, fractions → `?` in the **committed** `change_event.new_text` — a faithfulness violation. Plus hand-escaped `'`→`''` concatenated into psql `-c` = injection/corruption risk. (Banked raw text is clean; only the DB ingest is lossy.) **Fix: parameterized, UTF-8-preserving inserts (psycopg/COPY).**
- **F6. Silent act loss + volume still marked done.** On a per-act INSERT failure: log WARN, `continue` (act dropped), no rollback; `ingest_watcher` marks the volume `ingested` because it only checks `source_document.page_count IS NOT NULL` → the volume is **permanently skipped**, DB silently under-counts the law. Per-act inserts are non-transactional (enactment can succeed, provision fail → orphan). **Fix: per-act transaction, FAIL-loud, never mark a lossy volume done.**
- **F7. Three ingest scripts, three different dedup keys** (`(citation, src_doc)` / `(src_doc, in_act_order)` / none) → final corpus depends on which script touched which volume. Compounded by garbled chapter numbers collapsing distinct acts onto one citation (F11). **Fix: one canonical physical-act key everywhere.**

## SEVERITY 2 — races / resumability / fabrication
- **F8.** `ocr_cer_estimate=0.015` + `scan_quality='good'` hardcoded for every volume = fiction in a provenance column.
- **F9.** 60s stale-lock theft can clobber a legitimately-held claim under load/SSH stall → double-claim or lost `done`.
- **F10.** Cross-machine SCP-then-mark has a lost-update window; pushed JSON not validated (size/hash) before the marker is written.
- **F11.** Garbled-Roman chapter parser silently mis-numbers acts and cites the guess authoritatively; "faithful to the printed numeral" is false. Should set `confident=False` whenever a substitution fired.
- **F12.** Body-start/page-classification are float-threshold cliffs; a misclassified page is never OCR'd/ingested — a **silent gap**, no logged failure, no sanity gate on plausible body-page count.
- **F13.** Date heuristics fabricate `operative_date` (the point-in-time key): `"L"→1`, `Mav→May`, and a no-date fallback to `{year}-01-01` stamped as if real. Fabricated legally-load-bearing dates masquerading as parsed.

## SEVERITY 3 — fragile
F14 brittle psql-text parsing (use a driver); F15 hardcoded per-box paths + `patolex`/`PatoLex` case; F16 inconsistent citation-form lookup across scripts; F17 flagged acts never DB-tracked (gap invisible to queries); F18 fail doesn't clear worker_id (slow reclaim); F19 watcher "chronological" comment contradicts code.

## CORRECT (fair is fair)
Schema INSERTs match the live Drizzle schema (prior column bug genuinely fixed); `content_sha256` source-doc idempotency coherent; O_EXCL is the right lock primitive; resumable per-page checkpoint + marker-driven done are sound in the happy path; banked OCR not deleted on normal reclaim; the TOC-exclusion enactment-marker gate is legitimate.

## FIX ORDER (Phase B — "fix it right", from banked data, no re-OCR)
1. **F1/F2** — real token-ALIGNED 3-engine consensus as committed text + a real per-token confidence; honest provenance (don't label "consensus" unless it is).
2. **F3/F4** — pin IDENTICAL engine configs + determinism flags on both boxes; then re-run one volume on both and diff committed text byte-for-byte.
3. **F5** — parameterized, UTF-8-preserving ingest (psycopg/COPY).
4. **F6/F7** — transactional per-act ingest, ONE canonical act key, FAIL-loud, reconcile to a single ingest path.
5. **F8/F11/F12/F13** — real per-volume quality estimate; flag garbled chapters + fabricated dates (confident=False); page-classification sanity gate.
6. Deterministic **RUNBOOK + single orchestration entry**; then a **second Hans pass** (pipeline gets Hans twice).

This is also the A/B "treatment": version-A = current single-engine (re-derived clean from banked, with the fixed UTF-8 ingest, to isolate the consensus variable); version-B = real consensus. Compare quality + overhead → cost-benefit.
