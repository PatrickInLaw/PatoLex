# Architecture

## Working Vision

PatoLex is a two-component system: a public-facing Next.js web application and a private C# data pipeline. The pipeline ingests California's official legislative data, reconstructs the point-in-time text of each code section, and loads versioned records into PostgreSQL. The web application reads that data, allowing users to navigate the California code hierarchy and retrieve the exact statutory text in effect on any given date.

**Scope (see ROADMAP):** The POC targets the **modern point-in-time archive (1991-1992 session to present)**, built from California's structured bulk legislative data. Full historical depth back to 1849 -- which requires OCR of pre-1992 *Statutes of California* session-law volumes -- is a Phase 2 research program, not part of the POC.

**Primary data source:** California Legislative Information **Downloadable Files** (`leginfo.legislature.ca.gov/faces/downloadList.xhtml`) -- structured, database-ready bulk data covering the 1991-1992 session forward. This is the source of truth for the modern era. HTML scraping (AngleSharp) is a fallback only. Point-in-time section text is *computed* from chaptered amendments -- the source does not hand you "section X as of date Y" directly; reconstructing it is the pipeline's core job (exact method determined in Gate B).

## Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Frontend | Next.js 15 (App Router) + TypeScript 5 | ISR for static statute pages; dynamic for search/browse |
| Styling | Tailwind CSS + shadcn/ui | Professional UI suitable for legal research |
| Data access | RSC + Server Actions over a transport-agnostic service layer | Server Components read via Drizzle directly; Server Actions / Route Handlers for interactive bits. **tRPC deferred** (private-by-design, TS-only); add only if client interactivity warrants it |
| ORM | Drizzle ORM | Stays close to raw SQL; Patrick's SQL instincts transfer directly |
| Database | PostgreSQL 16 via Supabase | FTS via tsvector, point-in-time versioning, RLS |
| Search (later) | Meilisearch or Typesense | Add when PG FTS UX hits its limits |
| Data pipeline | C# (.NET 8) | Bulk-data ingest + Dapper (load). AngleSharp (HTML fallback), PdfPig / OCR reserved for Phase 2 historical |
| Build/staging DB | Local PostgreSQL 16 | Pipeline ETL, diffing, re-runs, ad-hoc + Claude Code analysis. Disposable. |
| Serving DB | PostgreSQL 16 via Supabase | Public read layer. **Budget for Pro tier (~$25/mo)** -- free 500MB is insufficient for the corpus + tsvector indexes |
| Deployment | Vercel (frontend) + Supabase (serving DB) | Pipeline runs locally; publishes finished data to Supabase |

### API / Data Access Strategy

All data access lives in **one transport-agnostic service layer** (`src/server/`). Every consumer — React Server Components, Server Actions, a future **MCP server**, and an eventual public **REST API** — is a thin transport over those same functions. This keeps every door open without committing to a public API shape now.

Likely order of external interfaces: **(1)** internal RSC/Server Actions (POC) → **(2)** MCP server (lets attorneys/researchers query via AI assistants) → **(3)** public REST API only if demand warrants. tRPC is intentionally *not* in this path: it is private and TS-only, so it does not serve the MCP/API goals; it would only ever be an internal convenience and is deferred.

## Data Model (Conceptual)

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
- Pipeline runs as a local batch process, staging into local Postgres, then publishing to Supabase
- Reconstructed point-in-time text MUST be validated against a known-good source before public launch (Gate G); a "verify against official sources / not legal advice" disclaimer ships with launch
- Supabase free tier (500MB) is insufficient even for the modern corpus + indexes -- plan for Pro
- Phase 2 only: pre-1992 documents are scanned images; prefer existing OCR text layers (HathiTrust/Internet Archive) over re-OCRing

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial architecture. Stack decided. Conceptual data model sketched. |
| 2026-05-31 | cc002: Scope split (modern POC vs 1849 north star). Bulk data as primary source (not scraping). Two-DB architecture (local staging + Supabase serving). Data model gains operative-date ranges, provenance, GiST overlap exclusion. Added correctness validation + Supabase sizing constraints. |
