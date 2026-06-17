# Changelog

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
