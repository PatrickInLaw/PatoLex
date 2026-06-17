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
- **certify_chapters.py committed (Hans-cleared + hardened); certify run NON-DRY on 5090** to regenerate the corrected `parsed_acts_certified.json` scratch outputs (fixes the 1853 dups the pre-gate C97 run shipped). 3,213 flagged→confident, 0 introduced dups. Early era **26.5%→62.2%**.
- **Multi-engine header re-extraction (`recover_multiengine_headers.py`, NEW) — built, big-lever, Hans NO-GO → fix cycle.** Recovers parser-missed acts by reading clean `CHAPTER <arabic>.` headers from per-engine surya/doctr/tess where the parse used garbled consensus. First (buggy) run: 1915 36→63%, 1911 52→89%, 1941 69→78% (+602, 0 dups). **Hans NO-GO:** (CRIT-1) consensus_text was counted as a 4th independent engine in the agreement vote — it's derived from the other 3, so it manufactures false "2-engine agreement"; (CRIT-2) gate A accepted on numeral-agreement alone with NO body witness → TOC lines become corrupt acts; (MAJOR-1) floor read only confident_acts, not flagged_acts (the recover_chaptered CRITICAL-B1 bug); (MAJOR-2) oracle_N=9999 fallback disabled the range gate; (MAJOR-3) resolution check scanned 2 of 3 engines. **LESSON: consensus_text is NOT an independent OCR witness — never let it vote in cross-engine agreement.** Fix cycle: all 5 defects fixed; trustworthy re-run = 1915 36→56%, 1911 53→81%, 1941 69→77% (+455, 0 dups vs confident+flagged floor and recovered set). **Re-Hans (2nd pass) = CONDITIONAL GO** — 5 fixes correctly implemented, no new precision hole; 2 cheap residuals (DEFECT-A floor_max_fallback range-gate audit gap; DEFECT-B unhandled missing-OCR-JSON aborts batch) being patched before the corpus-wide run. Then ran corpus-wide on modern (≥1900) volumes: **170 processed, +3,554 chapters recovered, SUMMED dups = 0** (precision holds at scale). Biggest payoff 1900-49. 8 SKIPPED (no-oracle + empty `recovered`-floor vols) + 3 `floor_max_fallback` (1948/1950/1966 truncated floors) flagged for a real oracle — NOT data loss. **CAVEAT: the worker's completeness % (0.339→0.355) is UNRELIABLE — it summed oracle_N per VOLUME (ΣN=231,077 vs true 119,157), double/quad-counting multi-volume sessions. Trust the +3,554/0-dup gain; the honest % comes from a session-grouped chapter_vs_oracle.py re-measure (next). recover_multiengine_headers.py committed (Hans-validated, corpus-run clean).**
- **★★ HONEST RE-MEASURE (session-grouped, multi-engine folded in): OCR corpus 1850–1999 = 87.6% → 91.2% confident.** 87,146/95,555, missing 11,822→8,409, +3,413 distinct (0-dup). Per-era: 1900-19 72→85%, 1920-49 82→89%, 1950-88 93→95%, 1989-99 99%. **Early era 1850–79 UNCHANGED at 62.5% (multi-engine handles modern arabic only, not early roman) → now the #1 deficit (3,048 missing), largely cheap surya-recoverable.** Next lever = roman-aware early-era multi-engine pass. Updated residual: 29 reg sessions <85%, 4,407 ch. Durable: §3a.
- **Early-era roman multi-engine path built → Hans NO-GO (CONTAMINATED, not committed).** First run claimed +1,410 (1850-79), but Hans found **CRITICAL-1: the glyph-tolerant `C[A-Za-z]{1,6}` regex matches Title-Case legal C-words** (Civil/Code/Court/Clerk/County/Claims/Charter…) — so a wrapped body line "Civil IX. An Act…" emits chapter 9 from a SENTENCE, displacing the real ch.IX to needs_review, INVISIBLE to the 0-dup self-check (a wrong-*location* emission). Also CRIT-2: the `max(oracle_N, max(floor))` ceiling propagated early over-extraction (1865-66 floor 463 > oracle 280). **+1,410 NOT trusted.** LESSON: a 0-duplicate self-check does NOT prove correctness — a false-positive header can emit a unique, in-range, wrong-location number that passes every dup gate; for an OCR-garble-tolerant detector, the real-act-body witness must be COLOCATED with the header (1850s format), not 8 lines away. Fix cycle: same-line An-Act requirement + legal-C-word blocklist + cap ceiling at oracle_N. The published 91.2% never included early-era, so it stays clean.
- **Early-era fix round 1 (Hans NO-GO→fix): +1,304 (corrected), CRITICAL-1/2 closed**, modern 1915 unchanged, 1865-66 capped at oracle 280 (212→needs_review). **Re-Hans (3rd pass) = NO-GO on ONE narrow defect:** the +1-line OCR-split guard only broke on a *valid* adjacent roman; a *garbled* adjacent roman let a see-reference stub borrow the next act's body (wrong-content, dup-check-invisible). One-line fix (`if nn is None or nn != chapter_num: break`) + body-attribution spot-check in progress. CRITICAL-2 ceiling, above_oracle_count, and arabic path all CLEAN per re-Hans.
- **Early-era FINAL (one-line fix applied + verified): +1,300 chapters (1850-79), 0 dup every volume, modern 1915 unchanged (153).** Spot-check: 1,300 recovered, **0 legal-word-glyph hits**, 10/10 sampled = genuine `CHAPTER <ROMAN>. An Act…` with correct roman→int + [Approved] footers. Round-1's 1,304 → 1,300 (−4: garbled-adjacent stubs correctly moved to needs_review). Committed. **NOTE (pre-existing, NOT introduced): 1865-66 certified FLOOR = 463 vs oracle 280 (>100%) — early-era over-extraction in the floor (~183 phantom), flagged for pre-ingest cleanup (doc §4); recovery added only 16, all ≤280.** (API note: ~40-min back-off during a 529 overload; agents kept dying, so the one-line fix was applied directly + verified via SSH.)
- **★★★ RE-MEASURE with early folded in: OCR corpus 1850–1999 = 91.2% → 92.5% complete** (88,370/95,555, missing 7,185). Cumulative precision-clean gains: certify +3,213, modern ME +3,413, early ME +~1,224. Durable: §3a.
- **recover_lost_header.py (bucket ii, garbled-numeral position-fill) — hardened (5 Hans fixes + multi-engine floor integration), Hans CONDITIONAL GO.** Corpus-wide +239, summed dup=0 (vs floor+flagged+multiengine AND recovered). Slot distribution: **224 single-slot (gap_open_slots=1, trivially sound → trusted) + 15 multi-slot (12×2,3×3 — MAJOR-1 off-by-one risk if a stray resolution-with-garbled-An-Act inflates candidates → QUARANTINED pending manual scan verify; the 15 are in 1917/1919/1921/1935/1943).** So trusted gain = +224. Recovers the all-engine-garble subclass multi-engine can't (e.g. 1910-11 "076"→575). Committed (multi-slot quarantine documented).
- **★ RESIDUAL SIZING (§3f): 84% of the residual is CHEAP-recoverable, only 16% re-OCR (upper bound).** 8-session diagnostic: 47% consensus-text re-extraction (header in surya/doctr, parse used garbled consensus) + 38% position/garbled-numeral + 16% genuine re-OCR. **1915 (the 36% outlier) = PARSER-STAGE FAILURE** (surya 451 headers, parse got 278) — modern outliers 1915/1911/1941 share ONE fix (~1,133 cheap ch). Early oracle_N inflated (1860: 455 vs ~374 historical) → re-OCR figure overstated. OCR JSON: `production-<label>/ocr_consensus/page_ocr_results.json` (surya/doctr/tess/consensus text all retained). **Expensive re-OCR likely NOT needed at scale — defer to Patrick.** Durable: §3f.
- **★ AUTHORITATIVE completeness (chapter_vs_oracle.py, biennium-correct):** OCR corpus 1850–1999 = **87.6% confident / 88.8% all-extracted** (83,733 / 95,555). Per-era: 1850-79 62.5% (weakest), 1880-99 85.5%, 1900-19 69.8%, 1920-49 79.9%, 1950-88 90.7%, 1989-99 96.7%; 2000-24 = non-OCR DB era. Genuine residual = 42 regular sessions / 8,155 ch (<85%), top: 1915 (miss493, 36% — worst outlier), 1941, 1911, 1951, 1971. The 71.37% certify-internal was the even-year artifact. Durable: §3a.
- **KEY FINDING — the recurring "~20k missing" is a DENOMINATOR ARTIFACT (§3e), proven & resolved.** Even-year Budget/Extra-session volumes (small, tens of acts, bound in odd-year `NNchapters` volumes) are mis-stamped by certify's `oracle_N` with the odd-year Regular N (~1900-2400) → false ~0-4% completeness, deflating the total to 71.37%. The acts are PRESENT. Authoritative oracle denominator = 119,157 (215 sessions; 88 small sessions = only 1,475 chapters). True coverage = mid-to-high 80s. Measure authoritatively with `chapter_vs_oracle.py`, not certify internals. 6th false-missing alarm dissolved.

## Session close (2026-06-17, overnight autonomous run ended on Patrick's return)
- Heartbeat cron `860810ea` stopped by Patrick. Final: **OCR corpus 92.7% confident**, ~8,070 chapters recovered this run (certify +3,213, modern ME +3,413, early ME +1,224, lostheader +224), all Hans-gated, 0 dup. Capstone residual decomposition (§3g): ~95.9% reachable cheaply; irreducible re-OCR floor ~1,100–3,920 chapters (need a NEW engine — the existing 3 never read those headers).
- Recovery outputs are STAGED as separate per-volume scratch JSON on the 5090 (`parsed_acts_multiengine.json`, `parsed_acts_lostheader.json`) — NOT merged into one canonical per-volume parse, and NOT ingested (no DB writes; ingest is NOT a current task).
- Untracked throwaway/diagnostic scripts (`pipeline/analysis/residual_profile.py` etc.) left uncommitted on purpose — `residual_profile.py`/`residual_after_certify.py` carry the biennium bucketing bug; do not adopt them as measurement tools.
- Open for Patrick (NOT autonomous): re-OCR engine choice (VLM) + page targeting; oracle-row fixes (1883/1887 + even-year low-N rows); early-floor over-extraction cleanup; 15 quarantined multi-slot lostheader recoveries (manual scan check). Handoff: `docs/00_Inbox/MORNING_SUMMARY_2026-06-17.md`.
