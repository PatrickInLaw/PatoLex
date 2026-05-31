# Architecture

## Working Vision

PatoLex is a two-component system: a public-facing Next.js web application and a private C# data pipeline. The pipeline crawls California's legislative source documents (current law from leginfo.legislature.ca.gov; historical law from CA State Archives, HathiTrust, and related sources), extracts and parses statute text, resolves amendment chains, and loads versioned records into a Supabase PostgreSQL database. The web application reads from that database, allowing users to navigate the California code hierarchy and retrieve the exact statutory text that was in effect at any given date.

## Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Frontend | Next.js 15 (App Router) + TypeScript 5 | ISR for static statute pages; dynamic for search/browse |
| Styling | Tailwind CSS + shadcn/ui | Professional UI suitable for legal research |
| API | tRPC (inside Next.js) | Type-safe, no OpenAPI ceremony |
| ORM | Drizzle ORM | Stays close to raw SQL; Patrick's SQL instincts transfer directly |
| Database | PostgreSQL 16 via Supabase | FTS via tsvector, point-in-time versioning, RLS |
| Search (phase 2) | Meilisearch or Typesense | Add when PG FTS UX hits its limits |
| Data pipeline | C# (.NET 8) | AngleSharp (crawl), PdfPig (PDF text), Tesseract.NET (OCR), Dapper (load) |
| Deployment | Vercel (frontend) + Supabase (DB) | Free tier for POC; pipeline runs locally on 5080 |

## Data Model (Conceptual)

```
codes                    -- e.g., Civil Code, Penal Code, Business & Professions Code
  sections               -- the atomic unit -- one row per section identity

statute_versions         -- one row per (section, effective_date) pair
  section_id
  effective_date
  expiry_date            -- NULL = currently in effect
  text                   -- full statutory text
  text_search            -- tsvector column for FTS
  chaptered_bill         -- e.g., "SB 123 (2024)"
  session_year

amendments               -- links session laws to the sections they touched
```

Point-in-time query pattern:
```sql
SELECT * FROM statute_versions
WHERE section_id = $1
  AND effective_date <= $2
  AND (expiry_date IS NULL OR expiry_date > $2)
```

## Constraints

- All data is public domain (California state government output)
- No authentication required for read access; RLS enforces read-only for anon key
- Pipeline runs as a batch process on local machines (5080), not a cloud service
- Historical documents (pre-1950) may be scanned images requiring OCR; accuracy will vary
- Supabase free tier: 500MB storage -- sufficient for POC; may need to upgrade for full historical corpus

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial architecture. Stack decided. Conceptual data model sketched. |
