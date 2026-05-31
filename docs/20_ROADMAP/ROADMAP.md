# Roadmap

## Current Status

**Gate:** A (Repository Setup) -- Done (cc001). No code yet.

The project goal is a public website where any attorney or researcher can look up any California statute and see the exact language in effect at any point in time, from 1849 to present. Two parallel workstreams will develop: (1) the data pipeline (C# / CA state archives crawl) and (2) the web application (Next.js / Supabase). The pipeline comes first -- the schema is designed around what the pipeline actually produces, and the web app is built against the real schema.

## Gates

| Gate | Name | Status | Description |
|------|------|--------|-------------|
| A | Repository Structure | **Done (cc001)** | Docs hierarchy, CLAUDE.md, .claude/ tooling, session logs |
| B | Pipeline Scaffold | Not started | C# console/worker project. AngleSharp + PdfPig + Tesseract.NET + Dapper. Crawl leginfo.legislature.ca.gov for current law. Discover actual data shape. |
| C | Database Schema | Not started | Design Supabase tables based on what the pipeline actually produces. Statutes, versions, codes, amendments, point-in-time query pattern. B and C will overlap -- schema emerges from data reality, not guesswork. |
| D | Web App Scaffold | Not started | Next.js 15 project init, tRPC wiring, Drizzle ORM wired to real schema. Placeholder pages. Built against actual tables, not imagined ones. |
| E | Search | Not started | PostgreSQL full-text search (tsvector) on real statute text. Basic statute browser working end-to-end. |
| F | Historical Depth | Not started | Crawl CA State Archives / HathiTrust for pre-1970 session laws. OCR pipeline for scanned documents. The hard part -- saved until the easy path (leginfo) is solid. |
| G | Public Launch (POC) | Not started | Vercel deployment, public URL, minimal viable UI for attorney use case. |

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial version. Gates A-G defined. Corrected gate naming to letters. Reordered: pipeline (B) before schema (C) before web app (D) -- data shape drives schema design. |
