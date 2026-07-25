# Changelog

> **⚠ GAP — cc014 through cc018 (2026-06-20 → 2026-06-23) are NOT recorded below.** That span covered the entire
> OCR chapter-recall campaign (94.3% of 91 mapped years → **95,923 / 96,002 = 99.9%**, all 108 session-years
> 1850–1999 mapped), the 1854 dual-series contents-anchored parse (174/174), the corpus scratch-root relocation to
> `C:\PatoLex-scratch`, and the `production-<year>*` glob-vs-alias bug fix. Their session logs are in
> `session-logs/claude-code/`. **Not backfilled here by cc019** — writing five sessions' history from second-hand
> summaries would put unverified claims in the system of record, which is the failure this file exists to prevent.
> Backfill from the session logs themselves when convenient.

## 2026-07-24

- **cc019 — the residual "71 machine-unreadable chapters" were never an OCR problem; all 71 recovered, and three
  parser-grammar defects fixed.** The 71 biennial-era chapters (1866–1878) had been routed to human transcription
  or an archivist re-scan. Both were unnecessary. All seven volumes are **native 300 DPI, 1-bit, crisply legible**
  (300 DPI is the native ceiling — re-scanning gains nothing), and **71/71 were recovered** from each volume's own
  printed CONTENTS table via the contents-anchored technique cc015 used for 1854. Split: **62 ordinary acts + 5
  `[See volume of Amendments to the Codes.]` + 4 special enactment paths**. Full record:
  `RESIDUAL_71_CONTENTS_RECOVERY_2026-07-24.md`; root cause:
  `lessons/LESSON_2026-07-24_residual_71_is_parser_grammar_not_ocr.md`.
  - **THE RESIDUAL CAN NEVER REACH ZERO AS DEFINED.** 1874 ch.587/679 and 1876 ch.306/497/498 read
    `[See volume of Amendments to the Codes.]` — enacted (several carry bill numbers) but printed in the **companion
    Amendments volume**. No re-OCR, re-read, or archive scan of these seven PDFs will ever produce them. They need
    reclassification against another source, not recovery.
  - **DEFECT 1 (fixed) — three enactment paths, not one.** Acts that became law **unsigned** (ten-day lapse) or
    **over the Governor's veto** carry no `[Approved …]` bracket at all, so any detection anchored on it was
    structurally blind to two constitutionally distinct routes to law. Wording is unstable (three phrasings for the
    lapse alone). New spelled-out-date parser — the body prints *"this twenty-seventh day of February, A. D.
    eighteen hundred and sixty-six"* and **no such parser existed anywhere in the pipeline**. `test_enactment_paths.py` 27/27.
  - **DEFECT 2 (fixed) — em-dash chapter headings.** Heading punctuation varies by era: `CHAP. CXLIII.` (1866,
    space) vs `CHAP.—XCI.` (1876/78, **em dash**). **Not one pattern in the entire pipeline matched the em-dash
    form.** `_DASH` was already defined but used only in the trailing *"—An Act to…"* position. Canonical regex
    **5/9 → 9/9** on real printed forms, 0 false positives.
  - **DEFECT D (fixed) — headings that never say "An Act."** `is_confident_act` required `AN_ACT_RE`; 1876 ch.508
    (`[An amendment to the Code…]`, printed p.772) and 1870 ch.427 (`Charter of the City of Stockton…`) defeat it.
    Now accepts the enacting clause — the legally operative signal.
  - **DEFECT 3 (partial) — residual bracket ranges.** Derived from the preceding chapter's START page, so they break
    on long acts: for 1872 ch.125–128 the emitted range points at **chapter 128's own body** (true pages 221–222,
    not 224–227). Fixed the truthiness bug (a `source_page` of 0 was silently dropped), replaced undocumented ±4
    magic numbers, added implausible-span detection. **Forward-scan not implemented** — needs page text the function
    never receives. `test_residual_bracket.py` 16/16.
  - **DEFECT F — the printed volumes contradict themselves in BOTH directions.** 1874 ch.261: contents right (p.358),
    **body** running head misprinted `CHAPTER CLXI.`. 1866 ch.342: **contents** misprinted `242`, body fine.
    **Neither source is trustworthy alone; agreement between contents and body is the reliable signal** — a free
    cross-check, since both ship in every volume.
  - **The date-extraction test suite was DEAD**, and had been since the module reorg — `test_date_parser_fix.py:68`
    pointed at a path that no longer existed, so it died at import before its first assertion. **Zero live coverage
    on `parse_act_date`.** `5080/parse_born_digital.py` had been unloadable for the same reason. Nothing caught
    either: **the repo has no CI**, and `smoke_imports.py` is AST-based while the broken reference was a string path.
  - **Archives visit packet** for 2026-07-27 (`ARCHIVES_VISIT_PACKET_2026-07-27.md`): venue double-verified as the
    **Witkin State Law Library** (914 Capitol Mall, call number **L325**, copy c.2) — the State Archives at 1020 O St
    **bans cell phones and patron copying of bound volumes**. Missing-leaf count corrected from the disputed 8/9 to
    **9 fully-missing + 3 partial across 7 volumes**, all page ranges pixel-verified; 1972 Vol.1 ch.517 added (it was
    omitted from the scan request). HathiTrust's **complete 19.5M-volume inventory** was scanned: six of seven
    volumes are digitized nowhere.

## 2026-06-19

- **cc013 — session-number remodel: oracle re-keyed on canonical session id; the missing 14th session (1863) added.**
  *(Orchestrated via subagents — opus implementation, sonnet fixes — with 4 adversarial "Hans" gates.)* Replaced the
  year-based session matching (a proxy hack that caused the **1863/1864 collision** and the recurring **biennium-bucketing
  bug**) with a canonical session-number key. The oracle (`ca_chapter_counts.tsv`) gains `session_number` / `session_kind`
  / `canonical_id` columns; the matchers (`chapter_vs_oracle.py`, `find_oracle_match`, new `build_volume_canonical_map.py`)
  key on `canonical_id`, falling back to legacy `(year,type)` only when the oracle has no canonical column.
  **Added the missing 14th session — `1863 Regular Session`, 538 chapters, `S14`** — established two independent ways: the
  printed-index read (duplicate-title test, 18/20 of the 800s entries are page-number contamination) AND the ordinal-sequence
  `+1` offset (~28 anchors 1863-64→1945, twice-Hans-audited). `1863-64 Regular Session` → `S15` (476). **Denominator
  119,667 → 120,205** (216 rows, contiguous `S1..S134`). The biennium-bucketing bug class is retired (even-year extra
  sessions get their own `{year}X{n}` ids; the 6 NNchapters extra volumes that were silently dropped now bucket correctly).
  Reversible — pre-change backup at `project-archives/ca_chapter_counts_PRE_CANONICAL_2026-06-19.tsv`. Plan + full audit
  trail: `docs/30_SYSTEM_DESIGN/SESSION_NUMBER_REMODEL_PLAN.md`. Known issue carried forward: `1949-vol1-49chapters-prior`
  resolves to S59 (1949 Regular) but is the 1st Extraordinary (pre-existing, parity 0-diff).

## 2026-06-17

- **cc013 — oracle denominator corrected from printed-volume indices (3 early-era undercounts).** Re-derived
  early-era chapter counts from each volume's OWN printed index (authoritative internal source) and, after
  read-verifying the actual `An Act` index lines, **applied 3 Patrick-approved corrections to
  `ca_chapter_counts.tsv`:** 1865-66 **280→650**, 1887 **51→188**, 1883 **23→96** (oracle total
  **119,157→119,737, +580**). The clerk web index that seeded these rows undercounts them. **1865-66 was
  previously mis-filed as a "parser artifact" — disproven by reading the volume (continuous real acts ch 1→650);
  the prior Hans tier + 6-16 "confirmed correct" were the 1887 flip-flop repeating.** Held: 1863 (session-identity
  — `production-1863` index 538 vs the single oracle row `1863-64=476`; possible missing 14th-session row, not a
  wrong value). Details + remaining tiers: `docs/30_SYSTEM_DESIGN/sources/ORACLE_DISCREPANCY_EARLY_2026-06-17.md`.
- **cc013 — 1860 over-count corrected (455→385); code amendments confirmed already-counted.** A duplicate-title
  test proved the early-index **page-number contamination** failure mode: in 1860, 20/22 of the spurious "800s"
  index entries are duplicate titles of low chapters (page numbers misread as chapter numbers), so the real
  count is the dense run ~385 — **oracle 455→385** (total 119,737→119,667). Same artifact ruled the 1863 800s
  contamination (18/20 dups; 14th-session count ≈538, ADD pending a session-key disambiguation). **Code
  amendments (`-code` volumes) share the general-statutes chapter sequence** (main body roman headers run to
  673≈oracle 679; `-code` numbers fall within 1–679) — they're **already counted in the oracle**, so no
  undercount and no separate rows; "are all code changes counted?" = **yes**. Reliable early counts require a
  **dense-continuous-from-1** index run; gappy indexes need body- or hand-reading.
- **cc013 — modern era is self-indexing; no CONTENTS-page acquisition needed.** The modern body (`CHAPTER N`)
  re-derives the count and matches the oracle (1931=1220, 1945≈1527); new tool `derive_modern_from_body.py`.
  We hold every modern source PDF (chief-clerk-archive, 1861–2000); absent CONTENTS pages are an OCR-scope
  matter, not a holdings gap. No real modern oracle undercounts found. Supersedes the prior "must OCR CONTENTS
  pages" claim (`CORPUS_COMPLETENESS_STATE.md` §3h).
- **cc013 — engine-union index recall fix (analysis).** Unioning the 4 OCR engine fields recovers early-roman
  index pages the italic-garbled consensus drops (coverage ~0.6→~0.81–0.99); recovered 1855/1857/1862/1869-70/
  1875-76/1877-78 from NO_INDEX to oracle MATCH. To be folded into canonical `rederive_index_counts.py` under a
  Hans ×2 gate (deferred during the 2026-06-17 safety-classifier outage).

## 2026-06-02

- **cc002 — 1850-1875 corpus build (system of record).** OCR'd, banked, and ingested the 1850-1875 Chief Clerk session laws as **version-B multi-engine token consensus: 4262 acts** across 21 source volumes (one row each in `enactment` / `provision` / `change_event` / `designation_history`). Consensus committed via the canonical `pipeline/ingest_clean.py` (sha256-keyed `source_document`, scoped purge-then-insert, atomic per volume, dry-run + double-guard `--commit`/`PATOLEX_ALLOW_COMMIT=1`). Committed consensus method: 4057 `token_majority_3` + 205 `token_majority_2`; zero single-engine committed text.
- **Schema LIVE.** Gate D DDL applied to local PostgreSQL 16 on the 5080 (migrations `0000`-`0004`, 7 tables; `btree_gist`, GiST exclusions, `uuid_generate_v7()`, generated `fts_vector` all clean). `provision_version` and `lineage_edge` are **0 by design** (materialization sweep + 1872 recodification edges deferred).
- **Consensus is 3 engines** — Tesseract + docTR + Surya (`consensus.py`, `N_MAX_ENGINES=3`); qwen2.5vl / GOT run as disagreement-flagging vectors only. **PaddleOCR is NOT a consensus voter** (correcting earlier bake-off prose).
- **Three-tier corpus model documented** (`DATA_SOURCES_HISTORICAL.md` §1d, `BUILD_RUNBOOK.md`): (a) image-only ≤ ~1996 → OCR consensus; (b) born-digital Chief Clerk ~1997-2008 → direct text extract (no OCR, `parse_born_digital.py`); (c) leginfo PUBINFO XML 1989/1994-present → reconstruct backward. OCR campaign bounded on the modern end at ~1993-94, not 2008.
- **Forward campaign in flight** past 1875; modern-format parser (`parse_born_digital.py`, tier b) prototyped but not yet ingested.
- **BUILD_RUNBOOK created** as the operational entry point (queue + two GPU nodes, scheduled tasks, 0800-backoff-disable rule, canonical ingest chain, resume procedure).
- **Documentation rewrite (this entry's session).** Reconciled ARCHITECTURE, ROADMAP, CLAUDE.md, SCHEMA_DESIGN, and CHANGELOG against `TRUTH_BASELINE_2026-06-02.md` / `DOC_DELTA_MAP_2026-06-02.md`: removed the superseded "modern-POC-1991-first / historical = Phase 2" framing (project is historical-first), corrected the active pipeline stack (Python OCR/parse + TS/Drizzle; C#/.NET deferred), fixed the 3-engine (not 4) consensus fact throughout, corrected the recodification mechanism (`lineage_edge`, no first-class `recodification` table) and the date columns (chaptered/effective/operative, no `enacted_date`), and added the Hygiene-Cadence + Findings-in-durable-docs rules to CLAUDE.md.

## 2026-06-01

- **cc002 — risks retired.** OCR proven legal-grade (~1.5% body-CER on clean non-Google scans; **not yet human-gold certified**) with ensemble disagreement-flagging; Google Books scans identified as the sole prior blocker. Reconstruction engine **Method A** (parse session-law amendment directives, apply forward) returned **QUALIFIED-GO** on the 1883 Penal Code slice. Full-corpus inventory: completable from clean sources (unbroken session-law backbone). **Gate D schema designed** (event-sourced + CQRS, domain-neutral, lineage-edge recodification, USLM-aware). **Launch bar reframed:** completeness still required before launch; validation bar = OCR-confidence + source-image display + correction path, not expert-verified-throughout. Crowd-correction wiki + two-tier model designed. Idea recorded: emit the law as a Git repo (emitted artifact, not the merge engine).

## 2026-05-31

- **cc001:** Initial project structure established from PatoLex template (Pato repo template, 2026-04). Documentation hierarchy, CLAUDE.md, full `.claude/` tooling (Next.js / TypeScript / C# pipeline / Supabase / Codex). Telegram tag `[plx-ccNN]`. Co-author attribution `Claude Code <ClaudeCode@Kolasinski-Law.com>`. Stack decisions finalized: Next.js 15 + tRPC + Drizzle + Supabase PostgreSQL + C# pipeline. Supabase project provisioned (nqigiiyurwlmruexircz). Added `pipeline/` directory. Seven milestones defined in ROADMAP.
