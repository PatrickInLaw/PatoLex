# Roadmap

## Current Status

**Gate:** C (Penal Code slice proof) — **core risks RETIRED (cc002)**. Reconstruction method validated (85% vs Index) AND OCR demonstrated legal-grade on a clean sample (~1.5% body-CER on 2 verified pages of one clean edition; broader human-gold audit still pending). Full-corpus inventory done: corpus is **completable from clean sources** (unbroken session-law backbone 1849-2025); **production method = forward-from-session-laws (Method A)**. **Method A re-spike returned QUALIFIED-GO (2026-06-01):** end-to-end pipeline works, directive parser 100% precision/recall on the 1883 Penal Code slice (12 directives), validation 3/5 exact + 1 near vs the annotated edition; the one mismatch was a Google-scan OCR digit error, not a method failure. The production engine is validated, and the **Gate D schema is implemented + live on local Postgres**. **THE BASELINE IS 1850 = A BLANK PAGE — the only baseline.** The corpus is built FORWARD from nothing: session laws applied in order (1850 → 1871 …), with the **1872 codification as an EVENT in that chain (a recodification act), NOT a baseline**, then 1873-onward changes on top. **Session laws are the PRIMARY source** (Chief Clerk series, clean CA-gov); **published codes (Burch/Deering/State-Printer) are SECONDARY — verification only**, never primary except the unavoidable 1872-codification enacted text (not reproduced in the session-statutes volume). **Current goal: full coverage 1850–1875.** **Right now: an OCR engine bake-off (Tesseract vs Surya/PaddleOCR/GOT-OCR2/olmOCR/Falcon vs big VLMs), gated on human-certified gold (Patrick reviews tomorrow) — no mass OCR or ingest until an engine is verified legal-grade against gold (properly-done-or-stop).** No corpus data ingested yet (the earlier 726-section Penal slice was a throwaway benchmark, to be purged).

## Goal & Philosophy

PatoLex is a public website where any attorney or researcher can look up any California statute and see the exact language in effect at any point in time, **from statehood (1849) to present**. This is the full deliverable, not a stretch goal.

**Built historical-first, risk-first.** We tackle the hardest, least-certain piece — reconstructing statutes from 1849 off scanned session laws — *first*, to prove the whole thing is achievable to a trustworthy standard before investing in the easy modern era. Quality over speed. **No public launch until the full 1849-present corpus is present and validated** (revenue and demos are explicitly not near-term drivers). Secondary goal: a proof-of-concept for agentic coding at scale.

## Reconstruction Architecture (from Gate B)

Point-in-time text is **reconstructed**, never just downloaded. Two segments meet at a **~1993 seam**:

- **Historical (1849-1993) — built FIRST.** **Blank-slate principle:** CA had no law before 1850, so the complete clean **session-law chain (1849-2025) IS the law from a blank page** — codifications (1872 etc.) are themselves acts within it. Reconstruct **forward by parsing session-law amendment directives (Method A)** from **clean non-Google scans** (Google scans fail OCR); annotated editions = validation only (exist for 14/29 codes). Event-sourced (one act = one change-event) so it can emit both the temporal DB and a **Git history of the law** (see memory: law-as-git-repo). See `docs/30_SYSTEM_DESIGN/DATA_SOURCES_HISTORICAL.md`.
- **Modern (1993-present) — built SECOND ("light speed").** Backward from the current `LAW_SECTION_TBL` snapshot, applying chaptered bill XML. See `docs/30_SYSTEM_DESIGN/DATA_SOURCES.md`.
- **The seam is a correctness oracle:** the two directions must agree where they overlap, and every historical amendment must match the modern `history` strings.

## Two-Database Architecture

| Role | Where | Purpose |
|------|-------|---------|
| Build / staging | Local PostgreSQL 16 | Pipeline ETL, OCR structuring, amendment application, reconstruction, validation, ad-hoc + Claude Code analysis. Disposable, fast. |
| Serving | Supabase PostgreSQL 16 | Read-optimized published corpus the web app reads (only once data is complete + validated). |

One Drizzle schema applied to both; a publish step promotes finished data local -> Supabase.

---

## Gates

| Gate | Name | Status | Description |
|------|------|--------|-------------|
| A | Repository Structure | **Done (cc001)** | Docs hierarchy, CLAUDE.md, .claude/ tooling. |
| B | Data Source Reconnaissance | **Done (cc002)** | Modern: bulk leginfo data confirmed, current-only, reconstruct backward from snapshot. Historical: acquisition solved (catalog of 4,034 vols w/ HathiTrust+Google links + Chief Clerk archive 1850-2008 + IA 1872 Codes w/ OCR — all verified by download). OCR mostly already exists -> harvest + correct, not an OCR farm. Three-era model; risk = section-number integrity + recodification events. See both DATA_SOURCES docs. |
| C | Historical Slice Proof — Penal Code 1872-1900 (RISK GATE) | **In progress (cc002)** | **Data-first spike, no formal schema yet.** Baseline = original 1872 Penal Code (downloaded). Method: diff successive **annotated PC editions** (Desty 1881/1883/1885/1889, Deering 1903 — already OCR'd on Internet Archive) to derive per-section version timelines, using their inline `Stats. YYYY` history notes for operative dates. Scratch store = **JSON** (SQL Server available locally/Tailscale if querying helps). Steps: (1) pull editions, (2) extract sections + history notes, (3) reconstruct timelines, (4) **validate** vs *Index to the Laws 1850-1893*. **RESULT (cc002):** method validated at 85% (timeline) and OCR proven legal-grade at ~1.5% body-CER on **clean non-Google scans** (Tesseract 5 + qwen2.5vl + 99% disagreement flag-recall) — the Google Books scans were the sole blocker. Core risks retired. **Key learning for scale-out: source clean non-Google scans (IA/HathiTrust JP2), never Google Books.** See `GATE_C_SLICE_PROOF.md`. |
| D | Schema (event-sourced, domain-neutral, era-aware) | **DDL implemented (cc002)** — Drizzle, 7 tables, adversarially reviewed; `src/lib/db/` + `drizzle/`. Not yet applied to a live DB. See `docs/40_SCHEMA/SCHEMA_DESIGN.md` | **Decided:** append-only **event log** is the system of record (point-in-time text, current text, and the Git history are all *derived*); **domain-neutral** (enactment→provision keyed by jurisdiction+unit_type, so CA regs + a federal v2 drop in); §9605/recodification reconciliation lives in the schema, never in Git; **USLM/Akoma-Ntoso-aware** field names. Core entities: `source_document`, `enactment` (the "commit", w/ chapter_number + 3 dates), `provision` (synthetic surface-independent `provision_id` = the lineage anchor), `designation_history`, `change_event` (append-only, whole-section `new_text`, §9605 resolution metadata), `recodification` (first-class, 1872/1943). Read models: materialized `provision_version` (daterange + GiST + tsvector) for Supabase serving; Git emission from the log. **Local PostgreSQL 16 (staging) + Supabase PostgreSQL 16 (serving)** — Postgres both sides (the GiST/daterange/tsvector model is Postgres-only; SQL Server can't express it). |
| E | Historical Scale-Out | Not started | **Build order (corrected cc002):** **THE ONLY BASELINE IS 1850 = BLANK PAGE.** Build FORWARD from nothing — session laws applied in order from 1850. The earlier Penal Code "1872 spike" used the 1872 codification *slice* only as a convenient test of the parsing mechanism — that was **NOT a baseline** and is a throwaway. The real corpus lays the **1850-1871 session laws first** (the true "from nothing" origin), then applies the **1872 codification as a RECODIFICATION event in the chain, NOT a baseline** — else every codified section's pre-1872 history is truncated and a point-in-time query for e.g. 1860 wrongly shows "no law." **Session laws are PRIMARY; published codes (Burch/Deering) are verification-only.** The 1872 codification = `lineage_edge` (recodify) from each pre-code act → its 1872 section + `repeal` of superseded acts + `enact` only for genuinely-new sections. (Event-sourcing nuance: ingestion *order* is flexible since materialize is a date-ordered fold, but the *model* must treat 1872 as recodification.) Hard dependency: the 1872 **disposition mapping** (1850-71 act → 1872 section) from Code Commissioners' notes + *Index to the Laws 1850-1893* — same class as the 1943 Government Code recodification. **Source CLEAN non-Google scans (IA JP2 / Chief Clerk / HathiTrust 300dpi+), never Google Books** (the OCR blocker). OCR Tesseract 5 + qwen2.5vl ensemble + disagreement-flagging + spot-audit. Immediate bounded task: OCR the 1873-80 Chief Clerk volumes to fill the "Amendments to the Codes" gap. Model recodification events (esp. 1943 Government Code). |
| F | Modern Layer | Not started | Reconstruct 1993-present backward from the current snapshot via chaptered bill XML. **First spike the #1 modern risk:** bill XML format + whether bill->section linkage is explicit or must be parsed. Join to the historical spine at the seam. |
| G | Full-Timeline Validation | Not started | Validate 1849-present end to end: seam agreement, history-string cross-checks, structural invariants, statistical sampling with per-era error-rate confidence intervals. Establish the defensible accuracy standard for an attorney-facing product. |
| H | Web App + Point-in-Time UI + Search | Not started | Next.js 15 + Drizzle over the service layer. Code browser, statute-as-of-date rendering, PostgreSQL FTS. "Verify against official sources / not legal advice" disclaimer. |
| I | Public Launch | Not started | Only when the full corpus is present and validated. Vercel + Supabase (Pro tier — free 500MB is insufficient). Split dev/prod Supabase. |

Web stack note: data access is **RSC + Server Actions over a transport-agnostic service layer** (`src/server/`); **tRPC deferred**; MCP server is the likely first external interface, public API later. See ARCHITECTURE.md.

---

## Open Questions (carried into Gate C/D)

- 1937-1953 recodification acts: do they contain complete old->new disposition tables, or rebuild from annotated codes?
- Pre-1873 repeal scope (what the 1872 codes repealed vs. left standing).
- Era-specific effective-date rules (1849 vs. 1879 constitution).
- Scope: codes only, or also uncodified session law (appropriations, special acts)?
- [Gate F] Chaptered bill XML format + bill->section linkage.
- Vision-LLM OCR hallucination control + per-volume re-OCR triage thresholds.
- Storage footprint of the full multi-version corpus + tsvector indexes (Supabase tier).

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial version. Gates A-G defined. |
| 2026-05-31 | cc002: Major revision -- split scope, Gate B recon, vertical-slice, two-DB, schema requirements, tRPC deferred. |
| 2026-05-31 | cc002: Gate B done (modern). Reconstruction = amendment-application validated against current snapshot. |
| 2026-05-31 | cc002: Data-first reorder (Patrick) -- Penal Code 1872-1900 slice proof becomes Gate C (annotated-edition diffing, JSON scratch); schema follows as Gate D. Acquisition done (1872 baseline + 653-vol manifest). |
| 2026-06-01 | cc002: OCR risk RETIRED (clean scans -> ~1.5% body-CER, 99% flag-recall; Google scans were the blocker). Full-corpus inventory: completable from clean sources, blank-slate principle confirmed, production method = forward-from-session-laws (Method A). Open risk: session-law amendment parsing at scale. Idea: emit law as a Git repo. |
| 2026-06-01 | cc002: Method A re-spike QUALIFIED-GO (engine validated). Law-as-git boundary fixed (git = emitted artifact, not the merge engine). Adjacent-domain feasibility documented (federal easier; CA regs via baseline-plus-forward; design USLM-aware). **Gate D schema designed** (event-sourced, domain-neutral, era-aware). Build order decided: start at 1872 baseline, pre-code 1850-71 as a later pass. |
| 2026-05-31 | cc002: **Reversed to historical-first / risk-first** (Patrick's call). Full 1849-present is the deliverable; no launch until complete + validated. Gate B-Historical done (acquisition solved via Internet Archive, three-era model, two-pass OCR). Gates re-sequenced: schema -> historical one-code slice proof (risk gate) -> historical scale-out -> modern layer -> full validation -> web -> launch. |
