# OCR-Era Per-Year Recall Recovery — Campaign Working Doc

**Status:** ACTIVE (cc015+). **Goal (Patrick, GATE):** 100% per-year chapter coverage for the OCR era
(1850–1999) before the project moves forward. "Any omissions will break the entire project." Worst
year first (1915), polish the approach to completion, then generalize to all OCR years.

## The premise (PROVEN on-page — do not re-litigate)
The per-year shortfall is **parse-recall**, NOT missing source. Every sampled "missing" 1915 chapter's
BODY is present in the OCR, unparsed, because the OCR garbled the act-head markers (the `CHAPTER N`
header, the "An act" title, and often the enactment clause). Evidence: ch103 "ln act to amend sections
2152, 2154, 2156 of the Political Code" @ p182; ch128 @ p231; ch234 "…San Diego State Normal School"
@ p461; ch250 "CHLAPTER 247 Anoacl…" @ p466. **Zero re-OCR is needed for these.** Re-OCR is a LAST
resort, only after proving on the rendered page image that a chapter's body is genuinely absent.

## Plan (Patrick-approved staging)
1. **Stage 1 — recover the text-present "OCR ones."** Header-independent; each recovered act carries
   real body text. → `pipeline/ingest/recover_clause_seq.py` (DRAFT). 1915: 62% → **85.7%**.
2. **Stage 2 — aggressive header-independent recovery** for the ambiguous gaps; Hans-gated.
3. **Stage 3 — fill the remaining slots + heavy per-act verification.**
Then Hans-SOUND → wire into the merge/ingest → generalize to every OCR year.

## Method (Stage 1, implemented)
- **Anchors:** chapters whose number is header-confirmed on their merged `source_page` (merge_passes
  fuzzy headers), reduced to the longest **page-monotonic** backbone via LIS (drops stray garbled-header
  anchors that create impossible gaps).
- **Boundaries:** per-act enactment clause ("…people of the State of California do enact as follows")
  OR head approval bracket "[Approved <date> … In effect …]", fuzzy/garble-tolerant, deduped per act
  head, **LINE-LEVEL** (splits short appropriation acts that share a page).
- **Fill:** between two adjacent anchor header-lines holding K open slots, fill iff exactly K+1
  boundaries fall in range (anchor-lo's own clause + one per missing act); assign the K slots in line
  order. Each recovered act = real buffer text → text-verified.

## Current numbers — 1915 (N=771)
- Merge (post-dedup): 477 (62%). **Stage-1+2 recover_clause_seq.py: 740 (96.0%)**, 263 recovered, 167
  gaps filled (9 via the gap-local loose pass), 17 ambiguous, ~31 slots unfilled. **All fills
  alignment-VALIDATED** (every present chapter in a filled gap lands on its known page within 2pp).
- Progression: 85.7% (line-level) → 87.3% (+Theil-Sen anchor slope filter, +tighter clause) → 95.3%
  (+per-chapter checkpoint alignment) → 94.3% (+checkpoint VALIDATION rejecting broken-alignment gaps)
  → **96.0% (+Stage-2 gap-local LOOSE pass: under-filled gaps retried with the 'An act' title signal
  scoped to the gap, still checkpoint-gated)**.

## DONE in Stage-1 polish (this session)
- [x] **Anchor-slope outliers** → Theil-Sen robust line fit + residual filter (`theil_sen_filter`);
  killed the 57-page mega-gaps (e.g. stray "CHAPTER 90"@p113 when ch90≈p225).
- [x] **Body-citation false boundaries (partial)** → tightened clause matcher: bare "people of the
  State" now needs a nearby "enact"/"follow"; "An act" title deliberately NOT used (over-fires on
  amendment cross-refs "an act entitled 'An act to…'" — tested, dropped 94%→71%).
- [x] **Per-chapter checkpoint alignment** → expect one boundary per chapter in [c_lo,c_hi); present
  chapters are checkpoints; assign each missing slot its positional boundary; REJECT the gap if any
  checkpoint mis-aligns. This is the big lever (87%→94%).

## Remaining work to 100% on 1915 (Stage 2 / 3 — next)
- [ ] **Stage 2 — targeted gap completion (44 slots, 26 gaps): 17 under-detect** (clause+approval
  both garbled → missing boundary) — search ONLY that gap's page range with a relaxed signal (knowing
  the exact count needed + checkpoints constrain it); **6 over-detect** (residual body citations);
  **3 CKFAIL** (alignment broken). Global signal-adding fails — must be per-gap/surgical.
- [ ] **source_page = act START** (currently clause page) — walk back to the "An act" title line.
- [ ] **Stage 3** residual + heavy per-act verify (on-page render for anything not text-anchored).
- [ ] **Hans-gate** (twice; pipeline) → wire into merge → generalize to all OCR years.

## Artifacts
- `pipeline/ingest/recover_clause_seq.py` — Stage-1 recovery (additive `parsed_acts_clauserec.json`;
  DRAFT, not Hans-gated, not wired into merge).
- `pipeline/ingest/merge_passes.py` — best-of merge + OCR-header same-act dedup (Hans-SOUND, shipped).
- `pipeline/analysis/_moderngap.py` — reproducible per-session completeness metric.
- Lessons: `lessons/LESSON_2026-06-20_ocr_header_garble_dedup.md`,
  `lessons/LESSON_2026-06-14_chapter_recovery_header_loss_and_renumber.md`.
- Scratch prototypes (not in repo): `C:\PatoLex-scratch\_stage1.py`, `_census1915.py`, etc.
