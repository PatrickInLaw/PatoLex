# Roadmap

## Current Status

**Gate:** C (Historical Slice Proof — Penal Code 1872-1900) **in progress (cc002)**, data-first. Gate B done. No product code yet.

## Goal & Philosophy

PatoLex is a public website where any attorney or researcher can look up any California statute and see the exact language in effect at any point in time, **from statehood (1849) to present**. This is the full deliverable, not a stretch goal.

**Built historical-first, risk-first.** We tackle the hardest, least-certain piece — reconstructing statutes from 1849 off scanned session laws — *first*, to prove the whole thing is achievable to a trustworthy standard before investing in the easy modern era. Quality over speed. **No public launch until the full 1849-present corpus is present and validated** (revenue and demos are explicitly not near-term drivers). Secondary goal: a proof-of-concept for agentic coding at scale.

## Reconstruction Architecture (from Gate B)

Point-in-time text is **reconstructed**, never just downloaded. Two segments meet at a **~1993 seam**:

- **Historical (1849-1993) — built FIRST.** Forward from the 1872 code baseline, applying each session's amendments (text harvested from existing Google/HathiTrust OCR, corrected as needed — not OCR'd from scratch). Pre-1872 is an act-based, separable sub-project. See `docs/30_SYSTEM_DESIGN/DATA_SOURCES_HISTORICAL.md`.
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
| C | Historical Slice Proof — Penal Code 1872-1900 (RISK GATE) | **In progress (cc002)** | **Data-first spike, no formal schema yet.** Baseline = original 1872 Penal Code (downloaded). Method: diff successive **annotated PC editions** (Desty 1881/1883/1885/1889, Deering 1903 — already OCR'd on Internet Archive) to derive per-section version timelines, using their inline `Stats. YYYY` history notes for operative dates. Scratch store = **JSON** (SQL Server available locally/Tailscale if querying helps). Steps: (1) pull editions, (2) extract sections + history notes, (3) reconstruct timelines, (4) **validate** vs *Index to the Laws 1850-1893* + internal history-note consistency, measuring section-number integrity + text accuracy. Proves trustworthiness before any schema or scale-out. Stops at 1900 (closes the "simple" 19th century, before the 1937-53 recodification mess). |
| D | Schema (era-aware) | Not started | Designed **from** the slice-proof learnings (data follows reality). Synthetic `section_id` lineage surviving renumbering; `section_number_history`; operative-date ranges with `daterange` + GiST exclusion; recodification events as first-class entities (esp. 1943 Government Code); provenance + trust-level per version; era-aware effective-date rules. Local Postgres/SQL Server (staging) + Supabase (serving). |
| E | Historical Scale-Out | Not started | Acquire via the supplied catalog (4,034 vols, HathiTrust+Google links; HTID = canonical ID) + Chief Clerk archive for the post-1966 Statutes gap; harvest existing OCR + correct. Extend reconstruction across all codes, 1873-1993. Model the recodification events (esp. 1943 Government Code). Decide pre-1872 act-era scope. |
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
| 2026-05-31 | cc002: **Reversed to historical-first / risk-first** (Patrick's call). Full 1849-present is the deliverable; no launch until complete + validated. Gate B-Historical done (acquisition solved via Internet Archive, three-era model, two-pass OCR). Gates re-sequenced: schema -> historical one-code slice proof (risk gate) -> historical scale-out -> modern layer -> full validation -> web -> launch. |
