# LESSON 2026-06-16 — Certifying parsed-but-flagged chapters (precision-first)

**Context:** A re-measure flagged ~4,138 acts as parsed-but-flagged (we have the act body +
text; only the chapter number is low-confidence). Built `pipeline/ingest/certify_chapters.py`
to promote a flagged act → confident ONLY when its number is certain. Reused
`renumber_repair.py`'s anchor-fill idea and `ingest_from_ocr.LEGISLATURE_MAP`.

## Durable findings (these are facts about the data/pipeline, not just run notes)

1. **The early-era `parsed_acts_early_v2.json` files are 0-confident / all-flagged**, yet
   nearly every flagged act carries a clean Surya `chapter_int` straight off its own header.
   They are the single biggest cheap certification win: certifying them lifted the
   1850–1879 era from **26.9% → 62.5% confident completeness (+2,860 distinct chapters)**.

2. **TWO precision traps make naive "has a clean chapter_int" certification wrong:**
   - **TOC/index fragments.** Early volumes parse table-of-contents lines as "acts" whose
     `chapter_int` duplicates the real act's number. Filter on a real-body signal
     (`has_enact`, or `has_an_act AND has_approved`). TOC fragments lack the enactment clause.
   - **Spillover buffers.** A single act buffer sometimes contains TWO printed `CHAPTER NN`
     headers (the next act's header spilled in). Its number is NOT cleanly determined →
     leave flagged. Guard: count chapter headers in the body; >1 ⇒ skip.
   After both guards, certify only when the numeral is **unique among real-act candidates**
   and **not already held by a confident act**, and where a readable own-header numeral
   exists it must AGREE with `chapter_int` (witness agreement).

3. **Oracle session-key mismatch (pre-1880).** `LEGISLATURE_MAP[label][0]` for the early era
   returns keys like `'1854'`, `'1863-64 adjourned'`, `'1849-1850'` that do NOT match the
   oracle's `'<year> Regular Session'` form, so `oracle_N` silently returned None and the
   in-range guard was bypassed. Fix: a `_norm_session_label` fallback that strips
   vol/code/NNchapters suffixes and appends the session-type phrase. Without this the early
   era gets no range bound. (renumber_repair only covers 1880–1999 so it never hit this.)

4. **The oracle TSV has anomalous-low "high-confidence" rows: 1854=71, 1883=23, 1887=51**
   while the source parses hold ~87 / ~82 / ~169 confident acts (max 96 / 185). These are
   pre-existing oracle-vs-source conflicts (suspected oracle data-entry errors). A wrong-LOW
   N only makes certification MORE conservative (it never fabricates a wrong number), so it
   is precision-safe — but it depresses measured completeness for those sessions and should
   be reconciled in the oracle separately. **The prompt's "1854=174" was wrong; the file says 71.**

5. **`renumber_repair.repair_session` asserts on pre-existing source duplicates** (in-range
   determined non-anchor act carrying an anchor number). Because certification must NEVER
   demote a pre-existing confident act (so source dups stay), calling rr directly crashes.
   R2 (single-open-slot position fill between confident anchors, with witness + spillover
   guards) was reimplemented in-house, robust to source dups and non-demoting.

## Result (validated)

- **3,170 acts certified** (R1 own-header 2,928 / R2 position-fill 242).
- Same-volume-set confident completeness **68.81% → 71.40%** corpus-wide.
- Official `chapter_vs_oracle` corroborates: confident-parsed **79,354 → 82,420 (+3,066)**.
- **Precision: 0 introduced duplicates, 0 introduced out-of-range, 0 confident acts demoted
  or renumbered; 0 duplicate confident chapter numbers within any session** (global check).
- 27-act spot-check (all eras): every assigned number provably matches the printed header or
  a uniquely-determined position (e.g. 1850 ch85: Surya misread "500", neighbors 84/86 left
  exactly one open slot).

## Artifacts

- Script: `pipeline/ingest/certify_chapters.py` (path-portable via `config.path_for`).
- Output: `production-<label>/parsed_acts_certified.json` (NEW; sources untouched, mtimes verified).
- Audit: `<data_root>/_certify_audit/report.json` + `audit_examples.json`.
