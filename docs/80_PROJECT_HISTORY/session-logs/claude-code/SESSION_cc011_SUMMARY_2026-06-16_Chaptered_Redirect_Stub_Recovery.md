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

---

## Evening work-units (2026-06-16, autonomous run toward 100% coverage)

**Certify Hans-fix + precision gate (work-unit on `certify_chapters.py`).** Applied the 4
Hans NO-GO fixes (write-gate aborting `sys.exit(2)` on precision PASS=False [CRITICAL-3B];
R2 all-witness guard [MAJOR-2A]; 200-char `is_real_act` body guard [MAJOR-1C]; R2 stale-N
docstring [MAJOR-5B]). The data lives ONLY on the 5090 (`C:/github/PatoLex`, scratch
`C:/Users/patolex/PatoLex-scratch`); verification runs over SSH. Running `--dry` now
**correctly FAILS** the gate on **3 introduced duplicate confident chapters in 1853**
(ch 105/107/140) — the volume's **TOC front matter (pp.9–11)** parsed as acts and certified
to the same numbers as the real bodies (pp.151/152/197, roman `CHAPTER CV/CVII/CXL`). The
**pre-gate C97 run had no gate and shipped these dups silently** → early-era certified output
must be re-generated after the fix. Dispatched a fix worker (R2 `is_cand`→require `is_real_act`;
open-slots exclude ALL confident-held numbers, not just anchors). **Durable:** `CORPUS_COMPLETENESS_STATE.md` §3c.

**Numeral-repair / lost-header recovery (`recover_lost_header.py`, built on 5090).** Header-
independent boundary (An-Act + `[Approved…]`) + position numbering. **+578 acts recovered,
0 dups introduced corpus-wide, 20/20 spot-check correct** (arabic 1907–1989; roman early era
= 0, future extension). Recovery is GO (pending Hans). **BUT its residual SIZING is tainted:**

**5th false "unparsed volumes" alarm — RESOLVED as a bucketing artifact (durable §3b).** The
pass's NEW `residual_profile.py` reported "22,197 whole unparsed volumes" (1956/1954/1960/1962
@ ~2–3%). VERIFIED FALSE by direct 5090 probe: those are **even-year special/budget sessions
bound in the adjacent ODD-year volume**, labeled with a `NNchapters` suffix encoding the true
year (1954→`production-1955-vol1-54chapters`, 1956→`-1957-...-56chapters`, 1960→`-1961-...-60chapters`,
1962→`-1963-...-62chapters`). The new tool keyed off the leading 4 digits and **reintroduced the
biennium bug C96 fixed in `chapter_vs_oracle.py`.** ⇒ Re-OCR sizing MUST use the biennium-correct
`chapter_vs_oracle.py`, not a fresh year-keyed tool. Recovery is valid; the 71.33%/33,886/11,109
numbers are not.

### Left for review + Hans (this work-unit)
- `pipeline/ingest/certify_chapters.py` (Hans fixes + TOC/dup fix in progress) — local 5080 + scp'd to 5090, uncommitted.
- `pipeline/ingest/recover_lost_header.py` + `pipeline/analysis/residual_*.py` etc. (uncommitted on 5090; `residual_profile.py` has the biennium bug — do not trust its sizing).

### Hans review outcomes (2026-06-17)
- **certify_chapters.py — CONDITIONAL GO → cleared.** 1853 TOC dup fix precision-clean; 0 introduced dups corpus-wide; 3,213 certified. Applied hardening MAJOR-1 (`all_taken.add(slot)`) + MAJOR-3 (delete dead `restore_sacred`). 200-char `is_real_act` guard empirically validated (drops exactly 1 act corpus-wide, a flagged 1861 garble) — well-calibrated.
- **recover_lost_header.py — NO-GO (hardening, not a live precision hole).** +578/0-dup recovery is sound; queued fixes: re-run overwrite guard (CRITICAL silent-clobber), exclude flagged-act numbers from open-slots, `<` not `<=` page filter, real `volume_year` for iso_date. **SCOPE: it's garbled-NUMERAL repair (glyph present), NOT truly-lost-glyph headers — those are the real re-OCR population.**
- **Measurement bug located:** `residual_after_certify.py` `__noleg__` bucketing (not `residual_profile.py`); `LEG` confirmed to contain the `NNchapters` labels, so even-year volumes ARE mapped/present. Agent's "unparsed" sizing = artifact.
- Durable: `CORPUS_COMPLETENESS_STATE.md` §3d (review outcomes + residual decomposition refinement: numeral-garbled-glyph-present vs glyph-entirely-lost vs mis-keyed-present).
- **certify_chapters.py committed (Hans-cleared + hardened); certify run NON-DRY on 5090** to regenerate the corrected `parsed_acts_certified.json` scratch outputs (fixes the 1853 dups the pre-gate C97 run shipped). 3,213 flagged→confident, 0 introduced dups, biennium-correct.
