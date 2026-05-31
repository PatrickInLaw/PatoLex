# Roadmap

## Current Status

**Phase:** Repository setup and structure definition (cc001). No code yet.

The project goal is a public website where any attorney or researcher can look up any California statute and see the exact language in effect at any point in time, from 1849 to present. Two parallel workstreams will develop: (1) the web application (Next.js / Supabase), and (2) the data pipeline (C# / CA state archives crawl). The pipeline feeds the database; the web app reads from it.

## Milestones

| # | Milestone | Status | Description |
|---|-----------|--------|-------------|
| 1 | Repository structure | **Done (cc001)** | Docs hierarchy, CLAUDE.md, .claude/ tooling, session logs |
| 2 | Web app scaffold | Not started | Next.js 15 project init, tRPC wiring, Drizzle + Supabase connection, placeholder pages |
| 3 | Database schema | Not started | Supabase tables: statutes, statute_versions, codes, sessions, amendments. Point-in-time query design. |
| 4 | Pipeline scaffold | Not started | C# console/worker project. AngleSharp + PdfPig + Tesseract.NET + Dapper. Crawl leginfo.legislature.ca.gov for current law. |
| 5 | Search | Not started | PostgreSQL full-text search (tsvector) on statute text. Basic statute browser working. |
| 6 | Historical depth | Not started | Crawl CA State Archives / HathiTrust for pre-1970 session laws. OCR pipeline for scanned documents. |
| 7 | Public launch (POC) | Not started | Vercel deployment, public URL, minimal viable UI for attorney use case. |

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial version. Seven milestones defined. |
