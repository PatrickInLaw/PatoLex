# Hans Adversarial Audit — Pass 2 (Phase B fix modules, 2026-06-02)

Scope: the Phase B fix (`pipeline/consensus.py`, `pipeline/ingest_clean.py`, `pipeline/ab_compare.py`) before it becomes the canonical 1850-1875 corpus. Read-only. **Verdict: NO-GO as-is** — direction is right, two blockers remain.

## Metric dispute — adjudicated INDEPENDENTLY (Hans re-ran from banked data)
**Consensus IS genuinely better.** Headline reproduced exactly (A=4.63% / B=2.81% gold-token error, net +132 fixed). The token metric is genuinely furniture-immune (verified by construction). The windowed-CER +0.59 IS a real measurement artifact — `era1899_p162` byte-checked: the contiguous-window aligner latches onto a different occurrence of near-duplicate title/body text; content didn't rot. So the corrected conclusion (consensus better) stands.

## BLOCKERS (NO-GO)
- **S1-A (corruption the A/B can't see) — `consensus.py:217-222,314-361`.** Spine = "engine with most tokens" privileges the WORST-segmented engine (OCR word-splits like `Weights`→`W eights` inflate token count). Majority vote can't merge two spine positions, so the committed text gets phantom fragments: reproduced **`Sealer of Weights eights and Measures`**. Both A/B metrics score this ~wash. → Banking version-B as-is injects a NEW corruption mode. FIX: fragmentation-robust spine (median token count / char-length / per-segment) + collapse adjacent spine tokens when ≥2 engines agree they're one word; add a duplication metric; re-run A/B.
- **S1-B (F8/F11 are docstring-only) — `ingest_clean.py:233,243-244` computed, `:459-471` commit ignores them.** `confident` / `chapter_ocr_substituted` / per-volume quality are computed but NOT written — every act commits as uniform `ocr_uncertain`, and **no schema column exists** for the act-level flags. The advertised confidence-signal persistence is unfulfilled. FIX (needs a SCHEMA decision): add a column (e.g. `change_event.confident boolean`) + write it, and write per-volume `scan_quality`/`ocr_cer_estimate` (existing columns) onto `source_document`.

## SEVERITY 2 (close before any --commit)
- **S2-A** — the canonical key `(source_document_id, in_act_order)` has NO DB unique constraint (SELECT-then-INSERT, not atomic). FIX: add `UNIQUE` index + `ON CONFLICT DO NOTHING` (schema migration).
- **S2-B** — per-act `conn.commit()` → a mid-volume failure leaves acts 0..N-1 durably committed (not the "abort whole volume" the docstring claims). FIX: one transaction per volume.
- **S2-C** — `ocr_cer_estimate=-1.0` unknown-sentinel would violate the `>=0` CHECK. FIX: NULL.

## CORRECT (verified)
A/B numbers reproduce; `find_best_aligned_span` is a faithful port of `score_opusgold.py`; token metric furniture-immune; era1899 artifact real; consensus FUNCTION deterministic (50-run, 1 unique output) + honest confidence; inserts truly parameterized + UTF-8-lossless (F5 real); F13 date-NULL real + reaches DB; schema column names + enums all valid; `--commit` double-guard real.

## Disposition
- Fix agent dispatched for **S1-A + S2-B + S2-C + A/B re-run with a duplication metric** (code/dry-run only, no DB, no schema).
- **S1-B + S2-A need a SCHEMA decision** (where the per-act confidence flag lives + the unique index) → Patrick. Recommendation: add `change_event.confident boolean` + a `UNIQUE(source_document_id, in_act_order)` index, write per-volume quality onto `source_document.scan_quality`/`ocr_cer_estimate`.
- Then a 3rd verify pass, THEN the canonical re-ingest (post version-A completion).
