# OCR-Era Per-Year Recall Recovery — Campaign Working Doc + AUTONOMOUS CONTROL

**Status:** ACTIVE (cc015+). **Goal (Patrick, GATE):** 100% per-year chapter coverage for the OCR era
(1850–1999) before the project moves forward. "Any omissions will break the entire project." Worst
year first (1915), polish the approach to completion, then generalize to all OCR years.

---
## ⚙️ AUTONOMOUS CAMPAIGN CONTROL (read FIRST on any heartbeat / after compaction / crash)

**Authorized 2026-06-20 ~22:12 PT by Patrick to run AUTONOMOUSLY overnight while he sleeps (back
before 8am PT). Directive: drive to (A) full ALGORITHMIC run across all OCR years, then (B) full
VISUAL run. Do NOT ask for authorization — figure it out. NO irreversible changes (additive files
only; NO DB writes, NO overwrites of existing parse files, NO deletes).**

**⚠️ COMMS ROUTE (the PowerShell *tool* is BROKEN in this environment — returns exit 1 on everything;
use the Bash tool to call powershell.exe instead):** send Telegram with the Bash tool:
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:/GitHub/PatoLex/.claude/scripts/telegram.ps1" send "MESSAGE"` (chat 8525048490 = Patrick). Verified working 22:17 PT.

### Heartbeats (set this session)
- **One-shot ~03:13 PT (June 21)** — safety wakeup: if stalled/out of tokens, resume per CURRENT
  STATE below; if A done and B not, start B; if both done, write final report + Telegram.
- **Recurring every ~20 min (:09/:29/:49)** — ucp nudge: commit+push progress; relaunch dead
  subagents; when the whole campaign is done, CronDelete both jobs + Telegram "complete" + stop.
- (Session-only crons: they fire while this Claude process is alive — covers token-window
  exhaustion. If the process fully crashes, Patrick restarts and this doc is the resume point.)

### ☀️ HANDOFF v2 (2026-06-21 ~09:10 PT, 3rd session-limit hit, budget resets 1:10pm PT)
**Corpus 94.3% → 99.5% (residual 426). ~40 years fully image-verified.** All the BIG years now
processed: 1860(106) 1861(~partial, 209 tool-uses before kill — verify/finish) 1862(128) 1987(50
img+105 seq-located) 1988(100, mostly seq-located). RESUME at 1:10pm: re-run `_recall_allyears.py`
years-short; agents are APPEND-SAFE now (won't overwrite). Remaining 426 = (a) the tail of small
years not yet run; (b) ~200 SEQUENCE-LOCATED chapters in late-80s vol3s (1987/1988/1989/1982 — vol3
has NO page images, need image re-extraction from source PDFs to truly image-verify); (c) SCAN/IMAGE
PREP gaps (1989 vol3 ch1440-1467 truncated; 1951-vol1/1982-vol3/1986-vol3 images not migrated; 1985
ch505-6, 1905, 1929, 1859); (d) 1854 dual-series (use its existing parsed_acts_dualseries_v2.json,
174/174). QUALITY CAVEATS for a normalization pass: some agents mislabeled sequence-located as
"legislative_gap" (1986 ch1301/1303/1304) — only ~a few are TRUE legislative gaps; and the merge has
latent misnumbered-duplicate errors (1919 ch432=ch482) needing an audit. Heartbeats LEFT ACTIVE.

### ☀️ MORNING HANDOFF (2026-06-21 ~05:30 PT, 2nd session-limit hit, budget resets 8:10 PT)
**Result this overnight run: OCR corpus 94.3% → 99.0% (residual 929, down from ~5,150 missing). 33
years driven to 100% image-verified.** Algorithmic (Goal A) DONE + Hans-hardened. Visual (Goal B)
~33/91 years done; the rest is mostly the BIG years.
- **DONE 100% (visual, image-verified):** 1850 1851 1852 1855 1856 1857 1858 1859 1860 1863 1885 1887
  1889 1891 1893 1899 1903 1905 1907 1915 1929 1933 1937 1939 1941 1943 1955 1971 1979 1982 1983 1990
  + algorithmic-complete modern years. (Some have a few documented gaps — see below.)
- **REMAINING (resume here — pick from `python pipeline/analysis/_recall_allyears.py` years-short):**
  big years 1862(128) 1988(101) 1861(155) 1987(155,4vol) 1854(78 DUAL-SERIES) + a thin tail. Launch
  one big-year visual agent at a time (template = the 1860 agent prompt: early=roman/multi-engine,
  modern=arabic/image; UPDATE run log AS YOU GO; image map: OCR dict key K -> page_{K:04d}.png).
- **SOURCE-ACQUISITION GAPS (cannot fix from existing scans — need re-acquire/re-scan, defer):**
  1989 vol3 ch1440-1467 (28, scan ends p2173), 1982 vol3 ch793+ch1088 (no page images), 1905
  ch389-397 (pp497-519 absent), 1929 ch881, 1859 ch51. ~7 confirmed LEGISLATIVE GAPS (never enacted).
- **Heartbeats LEFT ACTIVE** (campaign not complete) — they will keep nudging/resuming post-8:10 reset.
  NOTHING is wired into the merge/DB — all visual output is additive `parsed_acts_visual.json` (draft).
- **Cleanup deferred to end:** agent junk scripts in pipeline/analysis/ (untracked `_*`, `visual_*`)
  + temp images/page-renders in C:\PatoLex-scratch.

### CURRENT STATE  ← keep this line block updated every checkpoint
- **Phase A (algorithmic clause_seq, all OCR years): DONE** (subagent a6df9a2f, ~22:23 PT). Corpus
  **94.3% → 97.9%**, residual **1,873** chapters (mapped years). Scoreboard: `python
  pipeline/analysis/_recall_allyears.py` → `C:\PatoLex-scratch\_recall_allyears.json`. Run log:
  `run-logs/phase-a-algorithmic-run.log`.
- **KEY SPLIT:** modern 1900–1999 recovered well (per-year residual mostly 14–51; total ~470) → Phase
  B visual. **Early era 1850–1899 = ZERO recovery** (~1,400 residual): no per-act `CHAPTER` headers
  pre-1900 → no anchor backbone for clause_seq. Needs a DIFFERENT anchor source = the printed Table of
  Acts / Contents (chapter→title→page; we have these PDFs locally). Also 1903 (33) & 1905 (83) are
  1900s years with zero recovery → investigate (likely missing/odd structure).
- **17 unmapped biennium-named years** (1866…1964; oracle weight 6,211) not measured — real scope gap.
- **Phase A-early: roman-header-direct (FIXED, commit 2736cdd).** The first early-era mode
  (clause-from-present-pages) was Hans-UNSOUND (~25-45% misnumbered dups) → REPLACED with
  roman-header-direct: recover each pre-1900 chapter whose printed ROMAN header "CHAP. <roman>"
  survived OCR (validated by a nearby clause/An-act), number read off the numeral. Safe by
  construction, lower recall. **HONEST corpus = 98.3%, residual 1,546.** Re-Hans RUNNING (a2b2af51).
- **Algorithmic HARDENED via 3 Hans rounds** (early-era was the trouble): roman-direct now requires
  CANONICAL roman + SEQUENCE-POSITION sanity (rejects insert-L misparses + body-citation ghosts);
  modern body-dup guard REMOVED (over-rejected code-amendment gaps; checkpoint validation is the
  sound guard). Honest corpus ~97.9%, residual ~1844. 1915 control steady at 96% algorithmic.
- **Phase B (visual) — WORKING WELL. ~30 YEARS DONE 100%** (image+multi-engine verified): modern
  1907/1929/1933/1937/1939/1941/1943/1955/1971/1979/1983/1990 + 1915 + early 1850/1851/1852/1855/1856/
  1857/1858/1859/1863/1885/1887/1889/1891/1893/1899/1903/1905. Corpus **98.7%, residual ~1145**.
  RUNNING: big years 1982 (58, 5vol) + 1989 (73, 3vol). Scoreboard counts ONLY image_verified;
  legislative_gap (~12 confirmed) reduces effN. Documented SCAN-GAPS (physical pages absent, re-OCR
  later): 1905 ch389-397, 1929 ch881, 1859 ch51.
- **REMAINING RESIDUAL = the BIG years** (after 1982/1989): 1987(155,4vol) 1862(128) 1860(106)
  1988(101,4vol) 1854(78,dual-series) 1861(155) — these are the bulk (~720). Launch one big-year
  agent at a time (or split per-volume), tell it to UPDATE its run log AS IT GOES and group by vol.
  Pick targets from `python pipeline/analysis/_recall_allyears.py`. Image off-by-one: OCR dict key K
  -> page_{K:04d}.png (NOT K-1); confirm mapping per volume before a batch (lesson note).
- **DURABLE FINDINGS:** (a) root cause = OCR skips page-top CHAPTER headers (running-header zone) →
  image/multi-engine verify is essential. (b) **LEGISLATIVE GAPS**: some oracle chapters were NEVER
  ENACTED (printed volume skips the number, e.g. 1857 ch54/ch232) → oracle N OVER-counts; visual
  marks status="legislative_gap" — these are NOT recoverable and REDUCE the true denominator.
  (c) early-era agents should MINE all 4 OCR engines (doctr/surya read roman best). not_found/
  scan-truncated → status="not_found_needs_reocr" (re-OCR candidate, defer).
- **NEXT targets (confirmed residual>0 only — don't waste agents on 0-residual years like 1947):**
  early 1899/1850/1903/1905/1863/1889 then SPLIT the big ones one-agent-per-volume/range: early
  1861(155)/1862(128)/1860(106)/1854(78,dual-series); modern 1987(155,4vol)/1988(101,4vol)/1989(73,
  3vol)/1982(58,5vol). Pick targets from `python pipeline/analysis/_recall_allyears.py` years-short
  table. Agent junk scripts accumulate in pipeline/analysis/ (untracked `_*1850*` etc.) — clean at end.
- **Background:** final modern recover re-run (bkhwloi1a) for consistency (guard removed).
- **NEXT loop:** as each visual agent finishes → bank its run log + re-measure + launch next residual
  year (≤3-4 in flight). Targets: modern 1987(big,4vol)/1989/1982/1929 + the 15-35 tail, then early
  years (1850-1862 via roman-aware visual). not_found chapters = re-OCR candidates (defer).
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
