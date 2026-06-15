# Session 010 Summary

| Field | Value |
|-------|-------|
| Session | cc010 |
| Date | 2026-06-14 |
| Agent | Claude Code (Opus) |
| Context | Diagnose + recover the ~18% mid-century act-extraction shortfall (text-recoverable, not re-OCR) and renumber chapters by sequence; validate on calibration volumes. |
| Branch | main (changes left UNCOMMITTED in working tree for review, per task constraints) |

---

## What Was Done

**Diagnosis (numbers first).** Instrumented the production parser
(`pipeline/ingest/ingest_from_ocr.py`) without modifying it. Found the ~18% shortfall is
**page-top `CHAPTER`-header loss**, not a flush-gate or OCR-completeness problem:
- On 1957 (true 2424), `header_starts_act` fires only **1995** times — that IS the prior
  ~1990 figure. Almost all survive `flush_act` (no_enact_marker dropped only 5). So
  **header DETECTION is the bottleneck.**
- Of the missed "An act" starts: **313 at page-top with no header in the prior 3 lines**
  (real act-starts whose `CHAPTER NN` was dropped/garbled), 37 with a header just out of the
  4-line window, ~34 mid-page **body citations** that must not be recovered (precision trap).
- Secondary mode: OCR-misread chapter NUMBERS (2387 for 237, 5838 for 583) inflating the
  sequence (1957 max read as 24138).
- Generalizes 1880-forward (1931, 1893). **Early era differs:** 1863 OCR has only 30 `CHAP`
  tokens in 855 pages — pre-~1880 has no per-act top header; this pass cannot help it.

**Implementation (additive, new files).** `pipeline/ingest/recover_acts.py`:
- Tolerant, body-ref-safe act-start detector (page-top OR fuzzy `CHAPTER` within 8 lines +
  enact/approval marker within 14 lines + "An act" at line start + not a citation).
- Session-wide **chapter-renumber-by-sequence**: longest-increasing-chain anchors,
  deterministic inter-anchor fill only when act-count == numeric gap, conservative
  self-numbered rescue, otherwise flag. Processes all physical volumes of a session as one
  page-ordered stream. Writes `parsed_acts_recovered.json` per volume; never overwrites
  `parsed_acts_fixed.json`; never touches the DB.

**Validation.** Built `pipeline/analysis/validate_recovery.py` + precision tools.

| Session | True | Before | After | Gap recovered | Dupes | Held-to-flagged |
|---|---|---|---|---|---|---|
| 1957 | 2424 | 1629 | **2284** (94.2%) | 82.4% | 24→0 | 2 |
| 1931 | 1220 |  622 | **992** (81.3%)  | 61.9% | 8→0  | 4 |
| 1893 |  244 |  199 | **226** (92.6%)  | 63.3% | 10→0 | 6 |
| 1863 |  476 |  154 | **160** (33.6%)  | 2.1%  | 3→0  | 3 |

Precision: 0 duplicate chapter numbers in every session. For `filled` acts with a readable
`CHAPTER NN` witness (1957): 322 agree / 44 disagree, and disagreements are overwhelmingly
the renumber **correcting** OCR-misread printed numbers. No false splits / fabricated acts.

**Bug found + fixed:** `CA_HARD_CEILING` was 2300 < 1957's true max 2424, silently capping
97 real chapters. Raised to 2500 in `recover_acts.py` and `validate_recovery.py`.

---

## Files Changed

**New files (all uncommitted, in working tree):**
- `pipeline/ingest/recover_acts.py` — the recovery + renumber pass (the deliverable).
- `pipeline/analysis/diagnose_misses.py` — per-volume gate-attrition + miss diagnostic.
- `pipeline/analysis/diagnose_flush.py` — where each act-start is dropped in `flush_act`.
- `pipeline/analysis/inspect_missing.py`, `why_header_fails.py`, `inspect_nochap.py`,
  `inspect_pagetop.py` — OCR-text inspection of missed headers (read-only).
- `pipeline/analysis/validate_recovery.py` — before/after completeness scoring.
- `pipeline/analysis/diagnose_renumber.py`, `precision_check.py`, `header_witness.py`,
  `dup_text_check.py`, `vol_ranges.py`, `residual_gap.py` — precision/structure audits.
- `pipeline/ingest/recover_acts.py` writes `production-<label>/parsed_acts_recovered.json`
  per processed volume (1957 x2, 1931, 1893, 1863) — data artifacts, not in repo.
- `docs/80_PROJECT_HISTORY/run-logs/chapter-recovery-run.log` — run log.
- `docs/80_PROJECT_HISTORY/lessons/LESSON_2026-06-14_chapter_recovery_header_loss_and_renumber.md`

**Modified files:**
- `docs/80_PROJECT_HISTORY/lessons/LESSONS_OVERVIEW.md` — index entry for the new lesson.

**NOT modified (by constraint):** `ingest_from_ocr.py`, the DB, any `parsed_acts_fixed.json`.

---

## Decisions Made

| Decision | Detail |
|----------|--------|
| Recovery is additive | New `parsed_acts_recovered.json` per volume; production parser + `parsed_acts_fixed.json` untouched. |
| Confidence does not require a parsed date | A deterministically-renumbered "An act" with no OCR-parseable approval date is still confident on its NUMBER (ingest already defaults the date). Recovered 379 acts in 1957. |
| Renumber is conservative | Fill only when sequence + page order agree exactly; otherwise flag, never guess. |
| `CA_HARD_CEILING` raised 2300 → 2500 | 1957 genuinely reaches ch. 2424. |
| Early era out of scope | 1850-~1879 needs a separate header-free detector; flagged for a future pass. |

---

## Open Items at Close

| Item | Priority |
|------|----------|
| Review-and-promote the small `ambiguous`/flagged residue (1957: 2, etc.) rather than dropping it before any ingest | Med |
| Sync `chapter_completeness.py` `robust_max` cap (still 2300) with the 2500 ceiling | Med |
| Build a header-free early-era (1850-1879) act detector (1863 only 34% even after recovery) | High |
| Confirm whether 1931 has a vol2 (data tops at the true max 1220, so vol1 = whole session — likely fine) | Low |
| Decide whether to fold `recover_acts.py` into the canonical parse path or keep as a post-pass | Med |

---

## Next Session Should Start With

1. A Hans (verify-auditor) adversarial pass on `recover_acts.py` (renumber edge cases, body-ref precision) before any ingest decision.
2. Running `recover_acts.py` across the full 1880-forward set and scoring with `validate_recovery.py`.
3. Designing the early-era (1850-1879) header-free detector.

---

## Lessons Learned

- The "~1990 extracted" number people quoted IS `header_starts_act`'s fire count — the loss
  is upstream of flush, in header detection. Always instrument the actual gate before tuning.
- True chapter totals must come from the Chief Clerk archive TOC, not memory: I initially
  guessed 1931=1442 and 1893=305; both were wrong (1220, 244). Captured in the lesson file.
- The renumber-by-sequence doesn't just fill gaps — it **corrects OCR-misread chapter
  numbers**, which is a bonus precision win (verified against readable headers).
- Full detail in `LESSON_2026-06-14_chapter_recovery_header_loss_and_renumber.md`.
