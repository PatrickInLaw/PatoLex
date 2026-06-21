# SESSION cc015 — 1854 Dual-Series Contents-Anchored Parse Fix (+ corpus relocation)

**Date:** 2026-06-20
**Focus:** Resolve OCR-era residual rows; fix the 1854 parse; bank the corpus relocation.

## What Was Done

- **Residual-row investigation (opened SOURCES, not derived OCR).** Installed PyMuPDF and opened actual source PDFs / page images instead of trusting garbled derived OCR.
  - **1989 vol3:** the *source PDF itself* ends mid-CHAPTER 1428 (2,174 pp ≈ our bundle) — an **acquisition/truncation gap**, not an OCR loss. Oracle 1467 uncontradicted; needs a complete re-acquired vol3, not a re-parse.
  - **1854:** established it is a **DUAL-SERIES** volume (General Laws 1–71 + Special Acts 1–103 = **174**); verified via the page images that the scan is **complete** (the Special Acts bodies are present, pp.129–215) — *not* missing pages.
- **Corpus relocation banked.** The 5080 moved the corpus out of `C:\Users\patolex\PatoLex-scratch` → **`C:\PatoLex-scratch`** (any-account `Modify`, machine-wide `PATOLEX_LOCATION_ROOT`, `config.py` resolves it) and synced all **653 source PDFs incl. every printed `*_Index.pdf` (1850→modern)** to the 5090. (A mid-session "data deleted" alarm was a **false alarm** from a Glob false-negative during the move — corrected on the raw disk.)
- **Fixed the 1854 parse via contents-anchoring.**
  - v1 re-parse **force-fit to 174**: dropped real General ch18 (County Judges), invented a phantom ch23 ("an Act supplementary thereto" fragment), off-by-one ch18–24 — the drop + phantom canceled, hiding the defect behind a clean count.
  - v2 anchors numbering to the **printed Contents** (chapter→title→page) → **General 71/71 + Special 103/103, zero missing, phantom rejected**.
- **Verification.** Orchestrator independently verified the canonical Contents list at 3 sampled regions (exact); **Hans (verify-auditor) audited body-matching → SOUND** (~42 chapters opened + full header census). Cosmetic ch50/ch70 `source_page` micro-fix applied.
- **Durable docs + hygiene.** Wrote `LESSON_2026-06-20_dualseries_contents_anchored_parse.md` + indexed it; updated `STORAGE_AND_BACKUP.md` and `CLAUDE.md` to the `C:\PatoLex-scratch` / `PATOLEX_LOCATION_ROOT` canonical root.

## Decisions Made

- **Dual-series / garbled-roman volumes: derive numbering from the printed Contents/Index, NOT body roman headers.**
- **A parse total that exactly equals a known target is a RED FLAG** (force-fit risk), not reassurance — require per-chapter body witnesses + Hans gate.
- **Oracle 1854 = 174 unchanged** — it was already correct; the defect was the *parse*, not the oracle.
- Output is an **additive** corrected parse (`parsed_acts_dualseries_v2.json`); **no ingest** (not a current task), no overwrite of v1/source.

## Files Changed

- **NEW** `docs/80_PROJECT_HISTORY/lessons/LESSON_2026-06-20_dualseries_contents_anchored_parse.md`
- **NEW** `docs/80_PROJECT_HISTORY/run-logs/dualseries-1854-reparse-run.log`
- **EDIT** `docs/80_PROJECT_HISTORY/lessons/LESSONS_OVERVIEW.md` (index + revision)
- **EDIT** `docs/60_OPERATIONS/STORAGE_AND_BACKUP.md` (canonical path → `C:\PatoLex-scratch`)
- **EDIT** `CLAUDE.md` (corpus data-root note + revision)
- **NEW** this session log
- **SCRATCH (not in repo)** `C:\PatoLex-scratch\production-1854\{parsed_acts_dualseries.json (v1), parsed_acts_dualseries_v2.json (CORRECTED, verified), _canonical.py, _finalize_v2.py}`
- **REMOVED** this session's throwaway probes in `pipeline/analysis/` (`_check1854`, `_pdf_open`, `_pdf_check`, `_residual_pages`, `_early_raster_status`, `_pathcheck`, `_index_open`, `_fix_v2_sourcepage`)

## Systematic OCR-era index-anchoring sweep (cc015, IN PROGRESS)

**Goal (Patrick-chosen):** validate OCR-era denominators against the printed indexes — the definitive "make the OCR-era trustworthy" pass. Early era first; modern subject-index completeness cross-check after (belt-and-suspenders).

**Key scoping finding (DURABLE):** the printed `*_Index.pdf` files are **page-keyed SUBJECT indexes, NOT chapter tables** (verified 1899 + 1957: entries cite pages e.g. "ABANDONMENT … 2998"; the 1957 index spans 3 sessions and ends in a Table of Proposed Constitutional Amendments). Modern chapters volumes have **no front-matter table of acts** (1957 Vol1: title → "CHAPTER 1"). So **"OCR the _Index → denominator" does NOT work for the modern era** — its denominator is already double-sourced (Chief Clerk stated ranges = the oracle's own source + body self-index = 96.3% confirmed) and needs no index.

**Where index-anchoring adds value = the EARLY era (1850–1899):** pre-1900 statutes volumes carry a front-matter **"CONTENTS" Table of Acts** (No. of Chapter | Title | Date | Page), chapter-ordered → last entry = the count. Verified in 1854 (scan) and 1899_Statutes.pdf (archive PDF, table starts ~p3). This is an INDEPENDENT denominator, strongest exactly where the oracle was least certain (the 1854=71 error; the 1860/1862/1863/1865-66/1883/1887 corrections).

**Plan & status:**
1. **Early era (1850–1899, 33 regular rows): DONE.** Fan-out (6 sonnet batches + orchestrator finish/verify) anchored each denominator to its printed Table of Acts. **Result: 31/33 CONFIRMED exact; 2 FLAGGED (oracle > printed table — likely over-counts): 1860 (S11) oracle 385 vs table 371 (−14); 1863 (S14) oracle 538 vs table 536 (−2).** Both FLAGs orchestrator-verified; **both edited per Patrick's delegation — 1863→536 (clean), 1860→371** (volume complete at 453pp/single-series; ⚠️ unresolved CLERK-CONFLICT: clerk archive lists 1860 as 1-455, doesn't fit our volume — flagged `toa-verified-CLERK-CONFLICT` for Patrick). Net oracle −16 ch (120,205→120,189). Sweep independently RE-CONFIRMED prior corrections 1865-66=650, 1883=96, 1887=188, 1889=290, 1861=538, 1862=455. Full report: `docs/30_SYSTEM_DESIGN/sources/EARLY_ERA_TOA_SWEEP_2026-06-20.md`. (Source: production-185x scans 1850–1860; `chief-clerk-archive/*_Statutes.pdf` 1861–1899; 1883 in `1883-84_Code.pdf`.) 1854 (S5) done separately (174, dual-series).
2. **Modern era (1900–1999): DONE** (parallel subagent). Primary-source belt-and-suspenders: opened scanned volumes → **ZERO denominator contradictions** (body-self-index derivation confirmed sound; 1975 Vol1→Vol2 "Ch.1071→1072" a clean direct confirm). Structural finding (lesson addendum): modern volumes have NO table of acts + carry dual CHAPTER series (statutes + resolution/ConstAmend) + relocated flagship acts → "last printed CHAPTER" is meaningless; body-self-index is the correct denominator source. Modern parse completeness ≈92.4% (parse-recall gaps on the longest volumes, NOT denominator). **Born-digital 2000–2024 NOW MEASURED** (DB access wired by the 5080 over Tailnet; psycopg3 installed; DSN in `.env.local`): **94.5%** (20,271/21,455) — 2000–2008 ~100%, **2009–2024 ~90% (~1,180 chapters short — a Gate-F ingest gap, not a denominator issue)**; 2000 & 2005–2008 have ~2× duplicate rows. Early-era DB rows have attribution noise (1860 shows ch up to 531 vs true 371). See `BORN_DIGITAL_DB_COMPLETENESS_2026-06-20.md`. **1860 oracle conflict RESOLVED:** the official clerk `1860_Statutes.pdf` (453pp) also ends at Ch.371 → 371 confirmed by two primary sources; the clerk catalog "1-455" is a metadata error. Row now `official-pdf-verified`.

## cc015 continued (2026-06-20) — 1863 title-page-verified, born-digital diagnosed

- **1863 (S14) = 536, TITLE-PAGE-verified.** Official `1863_Statutes.pdf` title page reads "Fourteenth Session of the Legislature, 1863" (Jan 5–Apr 27, 1863); its Table of Acts ends at Ch.536. `1863-64_Statutes.pdf` is a SEPARATE 644pp volume = the **15th session** (Dec 1863–Apr 1864) = **476** (`S15`). So 1863 (14th) and 1863-64 (15th) are TWO distinct sessions — the oracle correctly carries both. The clerk web "1863" page's "Statutes 1-476" is a metadata error (same bug as 1860=455). Oracle 1863 row regraded `official-pdf-titlepage-verified`; corrected `ca_chapter_counts_NOTES.md` (it wrongly stated 1863=1863-64=one session).
- **Born-digital 2009–2024 diagnosed (DEFERRED per Patrick — finish OCR era first).** DB real data stops at 2024 (junk dates 1831/2030 = OCR mis-attribution); 2025 not ingested, 2026 in-progress. The 2009–2024 ~10% gap is SCATTERED missing chapters (2024 missing 98 of 1017 — not a tail) → a Gate-F ingest skip, not a source gap. Later fix: re-run/extend Gate-F ingest 2009–2026 from CA SOS.
- **NEXT (active): close the 1900–1999 OCR ~8% parse-recall gap** — OCR header dropout (bodies present in OCR, page-top "CHAPTER N" header didn't OCR → parser missed the chapter). Worst: 1915 (56%), 1919 (58%), 1941 (76%), 1943 (83%). Use the existing header-recovery pipeline (`pipeline/ingest/recover_*.py`; LESSON_2026-06-14).

## cc015 — 1900–1999 parse-recall gap: best-of MERGE (IN PROGRESS)

- **Diagnosis:** the modern-OCR "8% gap" was largely **unmerged parse passes** — certified / chaptered_v2 / repaired / recovered / multiengine / lostheader each catch a DIFFERENT subset; none was ever unioned. (1915: certified alone 278/771 = 36%; union 482.)
- **`pipeline/ingest/merge_passes.py` (NEW):** per-volume best-of merge — for each chapter №, the act from the highest-precedence pass; capped at oracle N; precision filter (low-pass add needs page-monotonicity OR a real "An act" title). **Result: 1900–1999 raw union ≈ 95.5%** (79,821/83,550 mapped), up from the measured ~88–92%. Additive `parsed_acts_merged.json` per volume.
- **Hans verdict on the raw merge: UNSOUND** — OCR digit-garble **same-act duplicates** (one act under two chapter numbers): 5 proven in 1915 (203≡208, 296≡256, 438≡488, 610≡619, 636≡686), similar elsewhere incl. the *trusted* passes. ~1% inflation → would become 2 DB rows per statute at ingest.
- **Auto-dedup FAILED (documented honestly):** title-similarity over-flags boilerplate (2,556 flagged, mostly two-different-acts-on-one-page false positives); page-arithmetic "which twin to keep" picked the garble twice. Switched to **flag-only** (no wrong removals). True completeness ≈ 94–94.5%.
- **OCR-header dedup — BUILT & VALIDATED (see next section).**

## cc015 — OCR-page-header same-act dedup (DONE, Hans-gated)

**The reliable fix shipped in `merge_passes.py`.** Ground truth = each page's own `CHAPTER N` header in `ocr_consensus/page_ocr_results.json` (`consensus_text` per `page_1indexed`). New functions: `fuzzy_headers` (extracts chapter headers, **fuzzy on the word CHAPTER ≤2 edits** so OCR garbles like "UHAPTER 9", "CIIAPTER" still anchor; digit-cleaned `O→0 I/l→1`; capped at oracle N to ignore noise like "CHAPTER 2338"), `load_headers`, `dedup_header`, `_editle2` (bounded Levenshtein).

**Conservative collapse rule (never deletes a real chapter):** for acts sharing a `source_page`, remove one ONLY when — (a) **bodies** ≥0.6 Jaccard-identical (same physical act, e.g. 1915 ch745≡740 body=1.0), or (b) a **bodyless STUB** (<15 body tokens) whose **title** ≥0.6 matches a real-bodied sibling (the stub is the garble label, e.g. 203→208 t=0.71, 296→256 t=1.0), or (c) a **pure phantom** (empty title AND body) not header-anchored (610→619). A **header-anchored** act is NEVER dropped. Weak signals (0.3–0.6, or two anchored similars) are **FLAGGED for review, not deleted**.

**Why the stub-gate matters (the trap avoided):** the earlier title-only auto-dedup wrongly killed real chapters that share boilerplate appropriation titles. Proven on 1915: ch6 (San Quentin appropriation, real, header didn't OCR), ch9 ("UHAPTER 9"), ch238 ("CHAPTER 2338"=238) all have real bodies → **SURVIVE**; only the 4 true garble dups collapse. The "missing chapters" and "phantom stubs" turned out to be largely the SAME phenomenon — **OCR garble of the CHAPTER header itself.**

**Results (post Hans round 1):** 1915 raw 482 → 477 (all **5** proven dups: 203→208, 296→256, 610→619, 636→686, 745→740). Corpus-wide 1900–1999: **178 vols, 302 same-act dups collapsed, 1133 pairs flagged for review.** Honest, reproducible completeness over the **66 exact-year-mapped sessions (denominator 83,550)**: **all-distinct 79,547/83,550 = 95.2%**; **content-complete (≥15 body tok) 76,255/83,550 = 91.3%** (the honest floor excluding bodyless stubs). **10 biennium/even-year sessions (1,831 ch = 2.1% of era) are not yet dir-mapped and are NOT counted** (stated explicitly, not silently dropped). Worst residuals are genuine parse-recall (OCR header dropout): 1915 62%, 1941 77%, 1943 83% — NOT denominator issues. Every collapse logged in `_merge_meta.collapsed_pairs` `[dropped, kept, page, score, reason]`.

**Hans round 1 (verify-auditor) — 3 MAJOR fixed:** (1) ch636≡686 (a proven dup) slipped a 3-vs-4 title-token boundary → added a **near-phantom-stub** collapse (unanchored, <15 body & ≤3 title tokens, anchored sibling on page, no own header) that catches it; ch238 protected because its garbled header "CHAPTER 2338" extra-digit-matches 238 (`_has_own_garbled_header`). (2) `fuzzy_headers` false-anchored 10,058 body cross-refs + 141 roman code-headings → now rejects `CHAPTER N of …` cross-refs and all-letter (roman) tokens. (3) the 95.2% denominator wasn't reproducible → `_moderngap.py` rewritten to state the exact 83,550 mapped denominator, the content-complete floor, and the unmapped weight.

**Hans round 2 — verdict SOUND (safe to ship).** All 4 fixes verified against actual OCR page text; no real chapter dropped in any of the 34 near-phantom-stub collapses (5 manually checked on-page). Two MINOR (non-data-loss) findings, both addressed: (1) keeper attribution — a near-phantom stub is a garble of a chapter NUMBER, so the recorded keeper now picks the anchored sibling whose TITLE best matches the stub (fixed 1943 ch958: keeper 959→**908**, its true content parent); (2) the near-phantom-stub branch gates on page co-presence + `ntitle≤3` + no-own-header rather than a Jaccard content-overlap check — accepted design tradeoff (the ≤3-title-token gate excludes real substantive-titled acts; not triggered in any observed case), documented as a known limitation in the lesson.

## HARD REQUIREMENT (Patrick, 2026-06-20) — 100% per-year coverage is a GATE

**Patrick: "We cannot move forward until we have 100% coverage in each year. 62% in 1915 is completely unacceptable. Any omissions will break the entire project."** The merge + dedup made the count HONEST (95.2% all-distinct / 91.3% content-complete over mapped sessions), but honest ≠ complete. The per-year recall gap (1915 62%, 1941 77%, 1943 83%, …) is now the **blocking** work item — every year must reach its oracle N with real, on-page-verified acts.

- These are **parse-recall** gaps (OCR `CHAPTER`-header dropout: the body is in the OCR, the page-top header garbled so the parser skipped the chapter) — NOT missing source. Recover from existing OCR using the fuzzy-header census (the same `fuzzy_headers` ground truth built for dedup); only after proving a chapter's body is genuinely absent ON THE PAGE may re-OCR be considered. **No "missing"/"re-OCR" claims from heuristics.**
- **NEXT (active, blocking):** drive 1915 from 62% → 100% as the template: (1) census ALL fuzzy `CHAPTER` headers in the OCR to get the true recoverable ceiling; (2) recover each chapter present-as-header-but-missing-from-merge by extracting its body from the OCR page(s); (3) for any chapter with NO header AND no body anywhere in the OCR, prove the absence on the rendered page image before any re-OCR. Then generalize the recovery across all years.

## Open Items at Close

- **NEXT:** point the contents/index-anchoring method at the next target — the other residual rows / the modern-era **NO_INDEX denominator gap** (now solvable on-box: all `*_Index.pdf` are local).
- Hardcoded old-path references remain in many pipeline scripts + historical logs; they resolve via `PATOLEX_LOCATION_ROOT`/`config.py` — **not** mass-rewritten (historical logs are point-in-time records, intentionally left).
- 1854 v2 is **parse-level corrected + verified**; not ingested (ingest not a current task).
- 1989/1941/1964 residuals: 1989 confirmed a source-truncation gap; 1941/1964 PDFs on-box but not yet opened.
