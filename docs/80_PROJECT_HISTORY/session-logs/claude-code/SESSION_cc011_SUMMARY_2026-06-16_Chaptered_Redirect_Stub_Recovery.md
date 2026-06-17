# SESSION cc011 — Chaptered-era redirect-stub recovery (approval-footer witness)

**Date:** 2026-06-16
**Scope:** Build the diagnosis-recommended chaptered-era (1880-1999) recovery detector.
**Constraints honored:** no Postgres writes; existing `parsed_acts*.json` untouched;
NEW output files only (`parsed_acts_chaptered_v2.json`); nothing committed.

## What was built
`pipeline/ingest/recover_chaptered.py` (v2) — READ-ONLY recovery pass implementing
`run-logs/chaptered-detection-diag.md`:
- Detect act starts **only at a LINE-HEAD uppercase `CHAPTER <arabic>`** (kills
  mid-sentence body cross-reference false misses).
- **Approval-footer witness** replaces the enacting-clause keep-gate: keep on
  header + "An Act" + `[Approved…]`/"Filed with Secretary of State"/"In effect",
  even without "do enact". Widened An-Act lookahead past Note/margin lines; tolerant
  of a trailing garbled numeral glyph.
- **Flag redirect-stubs** `status="codes_redirect"` (An Act + approval + no enact +
  "see Stats. … Ch." note) — real chapters whose text is in the Codes volume.
- **Exclude resolutions** (no "An Act"; separate restart-at-1 sequence).
- **Additive / non-regressing:** starts from BEFORE (`parsed_acts_recovered` confident)
  as a FLOOR, adds only line-head approval-witness acts whose clean numeral is not in
  BEFORE → AFTER ⊇ BEFORE. (A line-head detector ALONE regressed 1931 because that
  volume's gap is OCR header-garble, recoverable only by the An-Act-opener approach.)
- **OCR-garbled numerals quarantined** (`chapter_number_suspect`, routed to flagged)
  when numeral > 1.25×before_max+50 — kept as real acts, never trusted/counted.

The pre-existing sequence-numbering draft of this filename was archived to
`pipeline/ingest/_archived_recover_chaptered_v1_seqnum.py.txt` (it still required an
enacting clause — the exact gate the diagnosis says drops redirect-stubs).

## Results (biennium-correct, distinct-in-[1,N] vs oracle N)
| session | N | before | after | redirect | dup | suspect |
|---|--:|--:|--:|--:|--:|--:|
| 1931 Reg | 1220 | 977 (80%) | 993 (81%) | 0 | 0 | 2 |
| 1933 Reg | 1059 | 742 (70%) | **869 (82%)** | 82 | 1 | 2 |
| 1915 (v1) | 771 | 263 (34%) | 282 (37%) | 0 | 0 | 1 |
| 1925 (v1) | 480 | 432 (90%) | 444 (92%) | 0 | 1 | 1 |
| 1945 (v1) | 1527 | 1255 (82%) | 1278 (84%) | 0 | 0 | 5 |
| 1885-86/1893/1905 | — | (no change — roman-numeral era, detector no-op) |

**Precision:** 0 duplicate chapter numbers in any AFTER set; 25-act (1933) + 18-act
(1931) spot-checks — all real line-head "An act …" acts.

## Honest gap statement
The redirect-stub + production-header-walk-miss slice of the chaptered gap is now
closed at high precision. The residual 1933 gap (~234 of 276) is chapters with NO
recognizable "CHAPTER n" anywhere in the OCR (numeral garbled / header lost) — out of
scope for a precision-first text detector; needs numeral repair / re-OCR. ~80
resolutions/volume excluded are NOT real statute misses.

## Durable docs updated
- `docs/30_SYSTEM_DESIGN/CHAPTER_COMPLETENESS_FINDINGS.md` — new section with the
  detector design, measured before/after table, precision verification, scope boundary,
  honest gap statement.
- `docs/80_PROJECT_HISTORY/run-logs/chaptered-recover-v2-run.log`

## Left for review + Hans (uncommitted)
- `pipeline/ingest/recover_chaptered.py` (v2) + archived v1 `.txt`.
- `pipeline/analysis/_probe_chaptered*.py`, `_diag_chaptered*.py`, `_diag_gap_region.py`,
  `_diag_stub_notes.py`, `_score_chaptered_v2.py`, `_precision_chaptered_v2.py`.
- `parsed_acts_chaptered_v2.json` per volume (PatoLex-scratch on 5090).
