# Session cc001 Summary

| Field | Value |
|-------|-------|
| Session | cc001 |
| Date | 2026-05-31 |
| Agent | Claude Code |
| Context | Milestone 1 -- Repository structure setup |
| Branch | main |

---

## What Was Done

1. **Template review:** Extracted Sample_Repo.7z and read all 40 files completely before building anything. Also reviewed PatoAudio and KolaLaw-DB-2025 CLAUDE.md, settings, hooks, and lessons to understand the full conventions.

2. **Pre-session discussions:** Talked through tech stack decisions (Next.js 15 + TypeScript + tRPC + Drizzle, Supabase PostgreSQL, C# pipeline), why C# beats Python for Patrick's pipeline (he can review it), why Supabase beats local PostgreSQL (no migration tax, two projects = dev + prod for free), and PostgreSQL basics for a SQL Server/MySQL developer.

3. **Repo creation:** Created PatoLex directory from template, ran find-and-replace substitution (PROJECT_NAME=PatoLex, PROJECT_TAG=plx, date=2026-05-31).

4. **Customizations from template:**
   - CLAUDE.md: Rewrote "What PatoLex Is", removed .NET versioning section, updated Coding Conventions for Next.js + C# pipeline stack, added layer discipline section, added Supabase credential rules
   - .gitignore: Replaced audio/video/ML sections with Next.js/Node.js ignores; kept C# pipeline output; added Supabase local dev, .machine, pipeline data artifacts
   - .gitattributes: Added TypeScript/TSX/JSX/CSS/SQL line ending rules
   - settings.json: Added npm/npx/node/next permissions; added pre-bash-check hook (was only block-compound-bash in template); added WebFetch for Next.js/Supabase/tRPC/Drizzle docs
   - pre-bash-check.ps1: Removed dotnet version enforcement (no VersionInfo.cs); updated Codex reminder to cover both src/ and pipeline/; renamed references to "Hans"
   - ship.ps1: Replaced dotnet build with npm run build; updated skip-file logic for pipeline data dirs
   - ROADMAP.md: Seven real milestones filled in
   - ARCHITECTURE.md: Full stack table filled in; conceptual data model sketched
   - SETUP.md: Real requirements (Node.js, .NET 8, Supabase details, connection strings)
   - CHANGELOG.md: Real cc001 entry
   - LESSONS_OVERVIEW.md: Added PatoLex-specific lessons (Supabase ports, service_role, read-before-build, Write-requires-Read)
   - PROJECT_STRUCTURE.md: Updated for web project layout (src/app, src/server, src/lib/db, pipeline/)
   - README.md: Real project description

5. **New directory:** Added `pipeline/` directory for C# data pipeline (alongside `src/` for Next.js).

6. **Removed:** TEMPLATE-USAGE.md (per template instructions).

7. **Credentials:** Supabase DB password saved to `C:\Users\PatrickKolasinski\Documents\PatoLex-secrets.env` (outside repo). Connection string details in SETUP.md.

8. **Git + GitHub:** Initialized repo, created GitHub remote, pushed cc001.

---

## Files Changed

**New files (all):** Full repo scaffold -- 50+ files. Key customized files:
- `CLAUDE.md` -- PatoLex-specific rules and conventions
- `.gitignore` -- Next.js + C# pipeline ignores
- `.gitattributes` -- TS/TSX line ending rules added
- `.claude/settings.json` -- npm/node/next permissions + pre-bash-check hook
- `.claude/hooks/pre-bash-check.ps1` -- No dotnet enforcement; Hans reminder covers src/ and pipeline/
- `.claude/scripts/ship.ps1` -- npm build instead of dotnet build
- `docs/20_ROADMAP/ROADMAP.md` -- 7 real milestones
- `docs/30_SYSTEM_DESIGN/ARCHITECTURE.md` -- Stack table + conceptual data model
- `docs/60_OPERATIONS/SETUP.md` -- Supabase details, Node requirements
- `docs/80_PROJECT_HISTORY/CHANGELOG.md` -- cc001 entry
- `docs/80_PROJECT_HISTORY/lessons/LESSONS_OVERVIEW.md` -- Inherited + PatoLex lessons
- `pipeline/.gitkeep` -- New directory for C# pipeline

---

## Decisions Made

| Decision | Detail |
|----------|--------|
| Stack: Next.js 15 + TypeScript | Best ecosystem for content-heavy public site; ISR for statute pages; good SEO |
| Stack: tRPC | Type-safe API with no OpenAPI ceremony; frontend + backend in same TS codebase |
| Stack: Drizzle ORM | Stays close to raw SQL; Patrick's SQL Server instincts transfer directly |
| Stack: Supabase PostgreSQL | Managed, free tier, built-in FTS, RLS, dashboard, PgBouncer pooling |
| Stack: C# pipeline (not Python) | Patrick can read and review C#; same capability as Python for this task |
| No local PostgreSQL | Start with Supabase from day one; avoid migration tax |
| Pipeline dir separate from src | `pipeline/` for C#; `src/` for Next.js -- different stacks, different concerns |
| Supabase project: nqigiiyurwlmruexircz | Provisioned by Patrick; password saved to PatoLex-secrets.env |

---

## Open Items at Close

| Item | Priority |
|------|----------|
| Install Supabase agent skills (`npx skills add supabase/agent-skills`) | Medium |
| Scaffold Next.js 15 project in src/ (Milestone 2) | High |
| Get Supabase ANON_KEY and SERVICE_ROLE_KEY from dashboard | High |
| Fill in .env.local from PatoLex-secrets.env | High |

---

## Next Session Should Start With

1. Read CLAUDE.md and ROADMAP.md (standard)
2. Get ANON_KEY and SERVICE_ROLE_KEY from Supabase dashboard
3. Scaffold Next.js 15 project: `npx create-next-app@latest src --typescript --tailwind --app --src-dir --import-alias "@/*"`
4. Wire Drizzle ORM + Supabase connection
5. Consider: `npx skills add supabase/agent-skills` to add Supabase-specific Claude Code tooling

---

## Lessons Learned

- Write tool requires a Read in the same session before it will overwrite. On large scaffolds, this means batch-reading before batch-writing, or accepting an extra read per file. Added to LESSONS_OVERVIEW.
- The template's find-and-replace PowerShell one-liner from TEMPLATE-USAGE.md works correctly -- use it.
- Parallel Writes fail if the files haven't been read first; run Reads in parallel first, then Writes in the next parallel batch.
