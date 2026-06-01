# Roadmap

## Current Status

**Gate:** B (Data Source Reconnaissance) -- Done (cc002). Next: Gate C (schema). No code yet.

**Gate B headline:** California bulk data is confirmed and clean, but the law tables are a **current-only snapshot** -- there are no historical text versions to download. Point-in-time text must be **reconstructed** by parsing chaptered bill text (`BILL_VERSION_TBL`, back to the 1993-94 session) and applying amendments in operative order, validated against the current snapshot. POC floor = **Jan 1, 1994**. Full findings: `docs/30_SYSTEM_DESIGN/DATA_SOURCES.md`.

## North Star vs. POC Scope

**North Star (the vision):** a public website where any attorney or researcher can look up any California statute and see the exact language in effect at any point in time, from statehood (1849) to the present.

**POC Scope (what we actually build first):** the **modern point-in-time archive** -- every version of every California code section from the **1991-1992 legislative session to present**, reconstructed from California's official bulk legislative data, fully searchable and deployed publicly.

This split is deliberate. The modern era is tractable for a solo developer + agents because California's Legislative Counsel publishes **structured, database-ready bulk data** (`leginfo` Downloadable Files) going back to the 1991-1992 session. The pre-1992 era has **no clean digital source** -- it requires OCR of bound *Statutes of California* session-law volumes plus historical amendment-chain reconstruction from original codification. That is a multi-year research program, not a POC gate, and even Westlaw/Lexis/HeinOnline have only partial depth there. Full historical depth is **Phase 2** (Gates H+), pursued only after the modern POC is solid and trustworthy.

## Sequencing Principle

**Recon before scaffolding. Vertical slice before going wide.** We do not write pipeline code until we know exactly what the source data contains and how point-in-time text is reconstructed from it (Gate B). We then drive **one code, modern era, end-to-end to a deployed page** before broadening to all codes. This de-risks every layer at once and produces a real demo early -- which also serves the secondary goal of being a proof-of-concept for agentic coding at scale.

## Two-Database Architecture

| Role | Where | Purpose |
|------|-------|---------|
| **Build / staging** | Local PostgreSQL 16 | Pipeline ETL, amendment diffing, re-runs, schema experimentation, ad-hoc analysis (incl. direct Claude Code queries). Disposable and fast. |
| **Serving** | Supabase PostgreSQL 16 | Read-optimized published corpus the web app reads. RLS, connection pooling, public. |

Same schema (one Drizzle definition) applied to both via migrations -> dev/prod parity, no translation tax. A **publish step** promotes finished data local -> Supabase (`pg_dump`/`COPY` or batched upserts).

---

## Gates (POC)

| Gate | Name | Status | Description |
|------|------|--------|-------------|
| A | Repository Structure | **Done (cc001)** | Docs hierarchy, CLAUDE.md, .claude/ tooling, session logs. |
| B | **Data Source Reconnaissance** | **Done (cc002)** | Confirmed `leginfo` PUBINFO bulk data (biennial `pubinfo_YYYY.zip`, 1989-2025, MySQL `capublic` schema). Found law tables are **current-only snapshots** (no historical versions; old archives lack law tables entirely). Strategy: **amendment-application** from chaptered bill XML, validated against the current snapshot. POC floor Jan 1 1994. Operative-date, double-jointing (§9605), and section-identity rules documented. See `docs/30_SYSTEM_DESIGN/DATA_SOURCES.md`. |
| C | Database Schema | **Next** | Design the schema from Gate B reality. `codes -> sections -> statute_versions`, with synthetic `section_id` + `section_number_history` (renumbering/repeal/re-add), **operative date** ranges, **provenance** (chaptered bill + source URL), and a **`daterange` + GiST exclusion constraint** preventing overlapping versions. Also a `bill`/`amendment` model and an audit table for chaptered-out (losing double-jointed) versions. Drizzle migrations applied to both local and Supabase. |
| D | Pipeline (Vertical Slice) | Not started | C# (.NET 8) pipeline targeting **one code, modern era**. **First spike the #1 risk:** chaptered bill XML format + whether bill->code-section linkage is explicit or must be parsed from "Section X of the Y Code is amended to read:". Then ingest bulk data (not HTML scraping), reconstruct point-in-time versions via amendment-application, load into **local staging Postgres**, and validate the reconstructed present-day state against the current `LAW_SECTION_TBL` snapshot. |
| E | Web App + Point-in-Time Read | Not started | Next.js 15 + Drizzle wired to the (Supabase) schema. One statute page rendering the correct version for a given date. Publish step promotes the one-code slice local -> Supabase. End-to-end vertical slice deployed. |
| F | Search | Not started | PostgreSQL full-text search (tsvector) over real statute text. Code browser (navigate code -> division -> section) working. |
| G | Scale Out + Correctness Validation + Public Launch | Not started | Run the pipeline across **all codes, full modern era**. **Validate** reconstructed point-in-time text against a known-good source (historical Westlaw/Lexis pull or official published volume) for a sample of sections. Add "verify against official sources / not legal advice" disclaimer. Vercel deploy, public URL. |

## Phase 2 (Beyond POC -- the North Star)

| Gate | Name | Status | Description |
|------|------|--------|-------------|
| H | Historical Depth (pre-1992) | Not started | The hard part. Source *Statutes of California* session-law volumes from HathiTrust / Internet Archive. **Prefer existing OCR text layers** over re-OCRing images; OCR only what has no usable layer. Reconstruct amendment chains back toward original codification. Treated as an ongoing research program, not a single gate. |
| I | Public API / Citator | Not started | If demand warrants -- a stable public API for programmatic access (legal researchers value this). Note: weigh against tRPC's private-by-design model chosen for the web app. |

---

## Open Questions (carried into Gate C/D)

- **[Gate D spike, highest risk]** Chaptered bill XML format: is the bill->code-section linkage explicit, or parsed from "Section X of the Y Code is amended to read:"? Is text clean "as-enacted" or tracked-changes?
- Bill-text coverage/quality for 1993-1998 (may raise the practical floor toward ~1999).
- Operative-clause parser false-negative rate on double-jointed/contingent bills.
- Full list of CLRC mass-recodification events (model as bulk renames).
- Storage footprint of the reconstructed multi-version corpus + tsvector indexes (drives Supabase tier -- free 500MB insufficient; budget Pro ~$25/mo).
- Cleanest path for direct Claude Code / analytical queries against the staging DB (local `psql` helper in `tools/` vs. MCP).

**Resolved in Gate B:** bulk source confirmed; reconstruction is amendment-application (not snapshot-diff); operative/double-jointing/section-identity handling documented in DATA_SOURCES.md.

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial version. Gates A-G defined. Pipeline before schema before web app. |
| 2026-05-31 | cc002: Major revision. Split North Star (1849+) from POC scope (1991-present, bulk-data-driven). Added Gate B data reconnaissance before any pipeline code. Reordered to vertical-slice-first (one code end-to-end before scaling out). Adopted two-database architecture (local staging + Supabase serving). Added schema requirements (operative date, provenance, daterange exclusion). Added correctness-validation gate before launch. Moved full historical depth to Phase 2. |
| 2026-05-31 | cc002: Gate B done. Bulk source confirmed; law tables are current-only -> reconstruction is amendment-application validated against current snapshot; POC floor Jan 1 1994. Gate C (schema) is next. Findings in DATA_SOURCES.md. |
