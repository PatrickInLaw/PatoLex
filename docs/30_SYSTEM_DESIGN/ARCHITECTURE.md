# Architecture

## Working Vision

PatoLex is a two-component system: a public-facing Next.js web application and a data pipeline. The pipeline ingests California's session laws and structured legislative data, reconstructs the point-in-time text of each provision, and loads versioned records into PostgreSQL. The web application reads that data, allowing users to navigate the California code hierarchy and retrieve the exact statutory text in effect on any given date.

**Scope (see ROADMAP):** PatoLex is built **historical-first / risk-first** — the deliverable is full depth from **1850 (a blank page) to present**, and there is no public launch until the full corpus is present and validated. The hardest, least-certain segment (reconstructing statutes from scanned 19th-century session laws) is tackled FIRST. **This build is underway:** the **1850–1875 segment is live** as version-B multi-engine OCR consensus (4262 acts ingested into local PostgreSQL), with the OCR campaign extending forward. The modern era (reconstructed from structured bulk data) is built SECOND, not first. *(The earlier "modern-POC-1991-first, historical = Phase 2" framing was reversed on 2026-05-31 and is obsolete.)* See `docs/20_ROADMAP/ROADMAP.md` for current status, `docs/60_OPERATIONS/BUILD_RUNBOOK.md` for how the build runs, and the three-tier corpus model in `docs/30_SYSTEM_DESIGN/DATA_SOURCES_HISTORICAL.md` §1d.

**Primary data source (current build):** the Assembly Chief Clerk *Statutes and Amendments to the Codes* session-law series (clean CA-gov / Internet Archive non-Google scans), **1850 forward** — the unbroken session-law backbone that IS the law from a blank page. Point-in-time text is *reconstructed* by parsing each act's amendment directives and applying them in operative order (Method A); the source does not hand you "section X as of date Y" directly. The **modern tier** (second build) draws on California Legislative Information bulk data (leginfo PUBINFO, 1989/1994–present), reconstructed backward from the current snapshot — see `docs/30_SYSTEM_DESIGN/DATA_SOURCES.md`. The corpus spans three data tiers (image-only → OCR; born-digital Chief Clerk → direct text extract; modern structured XML), with the OCR campaign bounded on the modern end at ~1993–94.

## Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Frontend | Next.js 15 (App Router) + TypeScript 5 | ISR for static statute pages; dynamic for search/browse |
| Styling | Tailwind CSS + shadcn/ui | Professional UI suitable for legal research |
| Data access | RSC + Server Actions over a transport-agnostic service layer | Server Components read via Drizzle directly; Server Actions / Route Handlers for interactive bits. **tRPC deferred** (private-by-design, TS-only); add only if client interactivity warrants it |
| ORM | Drizzle ORM | Stays close to raw SQL; Patrick's SQL instincts transfer directly |
| Database | PostgreSQL 16 (local, `localhost:5432/patolex` on the 5080) | FTS via tsvector, point-in-time versioning, RLS. **Active build DB is local — Supabase is a planned future public-serving deployment, not yet active.** |
| Search (later) | Meilisearch or Typesense | Add when PG FTS UX hits its limits |
| Data pipeline (historical build — ACTIVE) | Python (OCR/parse) + TypeScript/Drizzle (ingest) | OCR via **3-engine token-majority consensus (Tesseract + docTR + Surya)**, PyMuPDF for page handling; qwen2.5vl/GOT run as disagreement-flagging vectors only (never committed text). Canonical ingest = `pipeline/ingest_clean.py` against the same Drizzle schema. This is the proven toolchain for the one-time 1850-forward reconstruction. |
| Data pipeline (C#/.NET) | **DEFERRED** | The originally-specified C# (.NET 8) pipeline (AngleSharp, PdfPig, Tesseract.NET, Dapper) is **not the active toolchain** — reserved for a possible ongoing modern-era crawler/worker if/when wanted, not the historical ETL. |
| Build/staging DB | Local PostgreSQL 16 | Pipeline ETL, diffing, re-runs, ad-hoc + Claude Code analysis. Disposable. |
| Serving DB | PostgreSQL 16 via Supabase *(planned/future)* | Public read layer for the eventual public web app. **Not yet active — data lives in the local build DB.** Budget for Pro tier (~$25/mo) when this becomes active; free 500MB is insufficient for the corpus + tsvector indexes. |
| Deployment | Vercel (frontend) + Supabase (serving DB) *(planned/future)* | Pipeline runs locally against the local build DB; a publish step will promote finished data to Supabase when the corpus is complete and validated. |

### API / Data Access Strategy

All data access lives in **one transport-agnostic service layer** (`src/server/`). Every consumer — React Server Components, Server Actions, a future **MCP server**, and an eventual public **REST API** — is a thin transport over those same functions. This keeps every door open without committing to a public API shape now.

Likely order of external interfaces: **(1)** internal RSC/Server Actions (POC) → **(2)** MCP server (lets attorneys/researchers query via AI assistants) → **(3)** public REST API only if demand warrants. tRPC is intentionally *not* in this path: it is private and TS-only, so it does not serve the MCP/API goals; it would only ever be an internal convenience and is deferred.

## Data Model (Conceptual — superseded by the live schema)

> **The authoritative, as-built schema is `docs/40_SCHEMA/SCHEMA_DESIGN.md` + the live Drizzle migrations `drizzle/0000`–`0004` (7 tables, live on local PostgreSQL).** The sketch below is the original Gate-B-era conceptual shape, kept for history. The real model is event-sourced (`enactment` → `provision` → append-only `change_event`, with `provision_version` as a materialized read model and `lineage_edge` for recodification), not the `statute_versions` table drawn here.

This is the *shape*; the real schema is finalized in Gate C from Gate B's data report.

```
codes                    -- e.g., Civil Code, Penal Code, Business & Professions Code
  sections               -- the atomic unit -- one row per section identity (incl. repeal/re-add, renumbering)

statute_versions         -- one row per distinct version of a section
  section_id
  operative_range        -- daterange; the period this text was OPERATIVE law
                         --   (operative date, NOT just effective date -- see below)
  text                   -- full statutory text
  text_search            -- tsvector column for FTS
  -- provenance (mandatory for trustworthiness):
  chaptered_bill         -- e.g., "SB 123, Stats. 2024, ch. 45"
  session_year
  source_url             -- official source the version was reconstructed from
  EXCLUDE USING gist (section_id WITH =, operative_range WITH &&)
                         -- no two versions of a section may overlap in time

amendments               -- links chaptered bills to the sections they touched
```

**Operative date vs. effective date (correctness-critical):** California bills typically take *effect* Jan 1 but may become *operative* later, and the legislature routinely "double-joints" -- enacting multiple versions of the same section in one session with contingent operative dates. Point-in-time correctness depends on the **operative** date. Modeling only effective dates would render wrong law. This is malpractice-adjacent for an attorney-facing tool, so it is in the model from day one.

**Provenance:** every version carries its chaptered bill + source URL so users (and we) can verify against the official source.

Point-in-time query pattern (with daterange):
```sql
SELECT * FROM statute_versions
WHERE section_id = $1
  AND operative_range @> $2::date   -- $2 falls within the operative period
```

## Constraints

- All data is public domain (California state government output)
- No authentication required for read access; RLS enforces read-only for anon key
- Pipeline runs as a local batch process against the local build DB (`localhost:5432/patolex` on the 5080); a publish step will promote finished data to Supabase (planned future serving DB) once the corpus is complete and validated
- Reconstructed point-in-time text MUST be validated against a known-good source before public launch (Gate G); a "verify against official sources / not legal advice" disclaimer ships with launch
- Supabase free tier (500MB) will be insufficient for the modern corpus + indexes when that serving DB is provisioned -- plan for Pro tier
- Pre-~1996 session-law volumes are scanned images and must be OCR'd; serve text only from clean public-domain channels (Internet Archive non-Google + CA-gov). The ~1997–2008 Chief Clerk volumes are born-digital (direct text extract, no OCR), and 1989/1994-forward is structured XML — see the three-tier model in `DATA_SOURCES_HISTORICAL.md` §1d

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial architecture. Stack decided. Conceptual data model sketched. |
| 2026-05-31 | cc002: Scope split (modern POC vs 1849 north star). Bulk data as primary source (not scraping). Two-DB architecture (local staging + Supabase serving). Data model gains operative-date ranges, provenance, GiST overlap exclusion. Added correctness validation + Supabase sizing constraints. |
| 2026-06-02 | cc002 (doc rewrite): Reconciled to TRUTH_BASELINE. Removed the superseded "modern-POC-1991-first / historical = Phase 2" framing — scope is **historical-first**, 1850–1875 already live. Corrected the pipeline stack to the active **Python (OCR/parse: 3-engine Tesseract+docTR+Surya consensus, PyMuPDF) + TypeScript/Drizzle ingest**; C#/.NET pipeline marked DEFERRED. Primary source = Chief Clerk session laws (not leginfo-first). Flagged the conceptual data model as superseded by the live SCHEMA_DESIGN + migrations. Cross-referenced BUILD_RUNBOOK + three-tier corpus model. |
