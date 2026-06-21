# OCR-Era Per-Year Chapter-Recall Recovery — Campaign Final Report

**Date:** 2026-06-21 (overnight + morning autonomous run, cc015)
**Goal (Patrick, GATE):** 100% per-year chapter coverage for the OCR era (1850–1999) before the
project moves forward — "any omissions will break the entire project."

---

## Headline result

| | Chapters | % of mapped OCR-era oracle (eff N = 89,788) |
|---|---|---|
| **Start (best-of merge only)** | 84,653 | 94.3% |
| **End (merge + clause-recovery + visual)** | ≥ 89,423 | **≥ 99.6%** (scoreboard undercounts — see Caveat A) |
| **Missing at start** | ~5,150 | |
| **Residual now (by scoreboard)** | 365 | of which most is prep-blocked, not lost |

**~52 of 91 mapped years driven to full coverage** (most image-verified). The remainder is dominated by
a handful of large/blocked years, not a broad shortfall.

---

## What was built (durable, in the repo)

**Algorithmic pipeline (Goal A — done, Hans-hardened over 3 review rounds):**
- `pipeline/ingest/merge_passes.py` — best-of merge of all parse passes + OCR-header same-act dedup
  (Hans-SOUND, 2 passes). Fuzzy `CHAPTER` anchoring, body/title/phantom collapse, never drops a
  header-anchored act.
- `pipeline/ingest/recover_clause_seq.py` — header-INDEPENDENT recovery: LIS anchor backbone +
  enactment-clause/approval boundaries + checkpoint-validated sequence fill (modern); roman-header-
  direct recovery with canonical + sequence-position validation (early era). Three Hans rounds caught
  & fixed real bugs: misnumbered duplicates, garbled-roman misparse (CLII→CLIL→199), body-citation
  ghosts, buffer-bleed over-rejection. Additive `parsed_acts_clauserec.json`, never wired into the DB.
- `pipeline/analysis/_recall_allyears.py` (scoreboard, effN-aware, counts only verified) +
  `_residual_manifest.py` (per-year missing-chapter manifest with page brackets for visual agents).

**Visual run (Goal B):** dozens of subagents read the actual scanned page images, confirming each
missing chapter's printed number against the scan (multi-OCR-engine assist). Each recovery is an
additive per-volume `parsed_acts_visual.json` (draft) + a timestamped run log under
`docs/80_PROJECT_HISTORY/run-logs/visual-<year>-run.log`.

**Root cause (the lesson that unifies everything):** the OCR pipeline systematically **drops the
page-top `CHAPTER N` running-header** (it lives in a zone the OCR skips) while capturing the act body.
That single fact explains the "missing" chapters, the phantom duplicates, and why image verification
was essential. Documented in `lessons/LESSON_2026-06-20_ocr_header_garble_dedup.md` and
`lessons/LESSON_2026-06-21_early_era_roman_cccc_additive.md`.

---

## Honest confidence tiers (NOT all "100%" is equal)

1. **Image-verified** (printed number read off the scan): the bulk of the ~52 done years. Solid.
2. **OCR-text / sequence-located** (number inferred by counting acts or multi-engine OCR consensus,
   because the volume has **no page images** or the header is unreadable): early-era image-less
   volumes (1880, 1883, 1895, 1951-vol1 …) and the late-1980s vol3s (1987 ~105, 1988 ~97, …). Very
   likely correct but NOT image-confirmed.
3. **Confirmed legislative gaps** (~15): chapter numbers the printed volume genuinely SKIPS (never
   enacted) — e.g. 1857 ch54/232, 1853 ch123 (in the ToC but never printed). These correctly REDUCE
   the true denominator.

---

## What remains, and WHY (this is mostly PREP, not more OCR work)

**A. ACCOUNTING / NORMALIZATION (do first — cheap, and it raises the headline):**
- Agents used inconsistent `status` strings (`image_verified`, `ocr_text_verified`, sequence-located-
  as-`image_verified`-with-`printed_number_confirmed=false`, and a few MISLABELED sequence-located
  chapters as `legislative_gap` — e.g. 1986 ch1301/1303/1304). The scoreboard therefore **undercounts**
  (true coverage > 99.6%) AND a few real recoveries are mis-classed as gaps (wrongly shrinking effN).
  → Normalize statuses to a 3-tier scheme + recount.

**B. SOURCE PREP (needed before those chapters can be image-verified or recovered at all):**
- **Missing page images** (NOT migrated in the corpus relocation; OCR `img_path` points to the dead
  `C:\Users\PatrickKolasinski\PatoLex-scratch`): 1895, 1951-vol1, 1982-vol3, 1986-vol3, 1880, 1883,
  and the late-1980s vol3s (1987/1988/1989-vol3) → **re-extract page images from the source PDFs in
  `chief-clerk-archive`**, then image-verify the tier-2 chapters.
- **Truncated / physically-absent scans** (re-acquire/re-scan): 1989 vol3 ch1440-1467 (scan ends
  p2173), 1985 ch505-506 (p1854→1855 jump), 1970 ch906-907 (leaf 1648), 1905 ch389-397, 1929 ch881,
  1859 ch51. These are genuine acquisition gaps — not recoverable by OCR.

**C. SPECIAL CASES:**
- **1854 dual-series** (78 residual): the contents-anchored 174/174 parse already exists in
  `parsed_acts_dualseries_v2.json` (built at the start of this session) — just needs WIRING into the
  merge/scoreboard. Not a recovery problem.
- **Merge misnumbered-duplicate audit:** the visual run surfaced a latent class of PRESENT-chapter
  errors the recovery can't catch (it only fills *missing* slots) — e.g. 1919 ch432 is a `8→3`
  digit-misread duplicate of ch482, inflating the count and hiding the real ch432. Needs a targeted
  audit/correction pass across the merge.

**D. THIN RECOVERABLE TAIL (still doable by the same visual method, ~10 small years 2–5 chapters):**
1913, 1897, 1917, 1927, 1881, 1925, 1931, 1967, 1975, 1993, 1994, 1959, 1935 + the "append" years
1858/1863/1905/1968/1991 (re-run with the now APPEND-SAFE agent so prior work isn't overwritten).

**E. SCOPE QUESTION for Patrick:** some recovered "chapters" are concurrent/joint resolutions or
constitutional amendments (e.g. 1883 ch9/14, 1887 ch79/83), not enacted statutes. Confirm whether
these belong in the statute corpus or should be tracked separately.

---

## Guardrails honored throughout
NOTHING was written to Postgres or any existing parse file. All recovery output is **additive draft**
JSON (`parsed_acts_clauserec.json`, `parsed_acts_visual.json`) — fully reversible, nothing wired into
the merge or ingest. Survived **three session-token-limit hits** (agents relaunched/banked each time;
the runbook + per-year run logs made every restart clean).

## Recommended next sequence
1. Normalization/recount (A) — fast, reveals the true headline.
2. Re-extract missing page images from source PDFs (B) → image-verify the tier-2 chapters.
3. Wire in 1854 v2 (C); finish the thin tail (D, append-safe).
4. Merge misnumbered-duplicate audit (C).
5. Re-acquire the truncated-scan pages (B) — the only truly external dependency.
6. Patrick decides the resolution/amendment scope (E).
Then, and only then, is the OCR era at a defensible 100%-per-year (or the documented, justified
exceptions where the source itself is incomplete).
