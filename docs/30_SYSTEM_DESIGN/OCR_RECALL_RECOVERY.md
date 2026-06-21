# OCR-Era Per-Year Recall Recovery — Campaign Working Doc + AUTONOMOUS CONTROL

**Status:** ACTIVE (cc015+). **Goal (Patrick, GATE):** 100% per-year chapter coverage for the OCR era
(1850–1999) before the project moves forward. "Any omissions will break the entire project." Worst
year first (1915), polish the approach to completion, then generalize to all OCR years.

---
## ⚙️ AUTONOMOUS CAMPAIGN CONTROL (read FIRST on any heartbeat / after compaction / crash)

**Authorized 2026-06-20 ~22:12 PT by Patrick to run AUTONOMOUSLY overnight while he sleeps (back
before 8am PT). Directive: drive to (A) full ALGORITHMIC run across all OCR years, then (B) full
VISUAL run. Do NOT ask for authorization — figure it out. NO irreversible changes (additive files
only; NO DB writes, NO overwrites of existing parse files, NO deletes). Communicate milestones via
Telegram: `powershell C:/GitHub/PatoLex/.claude/scripts/telegram.ps1 send "..."`.**

### Heartbeats (set this session)
- **One-shot ~03:13 PT (June 21)** — safety wakeup: if stalled/out of tokens, resume per CURRENT
  STATE below; if A done and B not, start B; if both done, write final report + Telegram.
- **Recurring every ~20 min (:09/:29/:49)** — ucp nudge: commit+push progress; relaunch dead
  subagents; when the whole campaign is done, CronDelete both jobs + Telegram "complete" + stop.
- (Session-only crons: they fire while this Claude process is alive — covers token-window
  exhaustion. If the process fully crashes, Patrick restarts and this doc is the resume point.)

### CURRENT STATE  ← keep this line block updated every checkpoint
- **Phase A (algorithmic, all OCR years): IN PROGRESS** — Phase-A subagent launched 2026-06-20 ~22:15 PT.
  1915 done standalone (62%→96.0%). Other years pending the subagent's run.
- **Phase B (visual residual): NOT STARTED.**
- Master run log: `docs/80_PROJECT_HISTORY/run-logs/ocr-recall-campaign-run.log`.
- Recovery tool: `pipeline/ingest/recover_clause_seq.py` (additive `parsed_acts_clauserec.json`).

### RESUME PROTOCOL (if you wake up unsure where you are)
1. Read CURRENT STATE above + the master run log (tail it) + any per-agent run logs in run-logs/.
2. `git log --oneline -15` to see what's committed; check `TaskList` for live/dead subagents.
3. Re-measure the truth: `python pipeline/analysis/_recall_allyears.py` (per-year before/after table,
   written by Phase A). If it doesn't exist yet, Phase A hasn't finished — continue/relaunch it.
4. Continue the lowest-numbered incomplete phase. ucp after each meaningful step.

### GUARDRAILS (non-negotiable)
- Additive only. Never overwrite `parsed_acts_*.json` inputs or write to Postgres. `clauserec` files
  are new/additive. The recovery is DRAFT and NOT yet wired into the merge or ingest.
- Every recovered chapter must be TEXT- or IMAGE-verified (alignment checkpoint, or on-page read).
  Never assert a chapter is "missing"/needs re-OCR from a heuristic — prove absence on the page image.
- Subagents MUST write a timestamped run log so progress is visible and resumable.
---

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

## Remaining work to 100% on 1915 — the precise residual (17 gaps, ~31 slots) for STAGE 3
Enumerated (c_lo..c_hi, pages, missing chapters, type) — target these surgically with on-page reads:
- **over-detect (10)** — residual body-citation false boundaries inside the gap (and 1-2 wrong-slope
  anchors): `93..95`(94), `149..153`(150,151,152), `153..155`(154), `249..252`(250),
  `254..259`(255,257,258), `484..489`(485,486,487), `497..500`(498,499), `526..529`(527),
  `568..573`(569-572; p949-988 = 39pp → 573 likely mis-anchored), `654..657`(655,656), `692..695`(693).
  Fix: per-SLOT localization (find each missing slot's boundary between its nearest *present*
  checkpoints, ignoring false boundaries elsewhere in the gap) — i.e. promote slope-consistent present
  chapters with an aligned boundary to sub-anchors, subdividing the gap.
- **under-detect (6)** — act markers ALL garbled, even the loose "An act" signal finds nothing:
  `380..382`(381, 2pp), `401..405`(402), `426..428`(427), `481..484`(482,483), `563..568`(566,567).
  Most are TIGHTLY bracketed (≤3pp) between two header-confirmed anchors → the act is provably there;
  position-fill + **render the page image** (PyMuPDF) to read/verify the chapter and capture text.
- **ckfail (1)** — `615..620`(616,617): count matches but a checkpoint mis-aligns → on-page resolve.

### Stage-3 method (do next)
1. Per-slot localization / sub-anchor subdivision to clear most over-detect gaps (text-verified, safe).
2. For the markerless under/ckfail residual: render the bracketed pages (PyMuPDF → PNG, read the
   IMAGE, not the OCR) to confirm the act + its true chapter number, then fill with that evidence.
3. **source_page = act START** (walk back to the "An act" title line).
4. **Hans-gate** (twice; pipeline) → wire into merge → generalize to all OCR years.

## STATUS CHECKPOINT (worst year)
1915: **62% → 96.0%, every fill alignment-validated (zero wrong fills proven).** The last ~4% (17
enumerated gaps above) is the hard residual requiring Stage-3 per-gap + on-page verification. Still
DRAFT/additive (`parsed_acts_clauserec.json`), NOT Hans-gated, NOT wired into the merge.

## Artifacts
- `pipeline/ingest/recover_clause_seq.py` — Stage-1 recovery (additive `parsed_acts_clauserec.json`;
  DRAFT, not Hans-gated, not wired into merge).
- `pipeline/ingest/merge_passes.py` — best-of merge + OCR-header same-act dedup (Hans-SOUND, shipped).
- `pipeline/analysis/_moderngap.py` — reproducible per-session completeness metric.
- Lessons: `lessons/LESSON_2026-06-20_ocr_header_garble_dedup.md`,
  `lessons/LESSON_2026-06-14_chapter_recovery_header_loss_and_renumber.md`.
- Scratch prototypes (not in repo): `C:\PatoLex-scratch\_stage1.py`, `_census1915.py`, etc.
