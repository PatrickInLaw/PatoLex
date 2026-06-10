# Environment Setup

## Baseline Requirements

- **OS:** Windows (the .ps1/.ahk tooling assumes Windows)
- **PowerShell 7+** -- required by `.claude/scripts/`
- **7-Zip** (`winget install 7zip.7zip`) -- required by `archive-repo` skill
- **AutoHotkey v2** -- required by `send_to_codex.ahk` for Codex CLI nudge
- **Codex CLI** (`npx @openai/codex`) -- for Hans (adversarial) review
- **Node.js 20 LTS** -- required for Next.js web app (`winget install OpenJS.NodeJS.LTS`)
- **npm 10+** -- comes with Node.js
- **.NET 8 SDK** -- required for C# pipeline (`winget install Microsoft.DotNet.SDK.8`)

## Web Application Setup

Once the Next.js project is scaffolded (Milestone 2):

```powershell
npm install
```

Required environment variables (`.env.local` -- gitignored):

> **CURRENT STATE (2026-06-09):** The active corpus database is **local PostgreSQL 16** on the 5080 (`localhost:5432/patolex`). `DATABASE_URL` points there. The Supabase project (nqigiiyurwlmruexircz) is a **planned future public-serving deployment** — it is not the current data store. The `NEXT_PUBLIC_SUPABASE_*` / `SUPABASE_SERVICE_ROLE_KEY` vars are listed here for when the web app is wired up to Supabase at launch time, but are not active today.

```
# Active pipeline / build DB (current):
DATABASE_URL=postgresql://postgres:<password>@localhost:5432/patolex

# Future public-serving Supabase deployment (not yet active):
NEXT_PUBLIC_SUPABASE_URL=https://nqigiiyurwlmruexircz.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<from Supabase dashboard>
SUPABASE_SERVICE_ROLE_KEY=<from Supabase dashboard -- server-side only>
DATABASE_URL_POOLED=postgresql://postgres:<password>@db.nqigiiyurwlmruexircz.supabase.co:6543/postgres?pgbouncer=true
```

Credentials file: `C:\Users\PatrickKolasinski\Documents\PatoLex-secrets.env`

```powershell
# Run development server
npm run dev

# Build for production
npm run build
```

## Pipeline Setup (C# -- Milestone 4)

Once the C# pipeline project is scaffolded:

```powershell
dotnet restore pipeline\PatoLex.Pipeline\PatoLex.Pipeline.csproj
dotnet build pipeline\PatoLex.Pipeline\PatoLex.Pipeline.csproj
```

The pipeline uses `appsettings.Local.json` (gitignored) for connection strings.

## Database

### Active Build DB (current)

The live corpus and all pipeline work run against **local PostgreSQL 16** on the 5080:

- **DSN:** `postgresql://postgres:<password>@localhost:5432/patolex`
- **Env var:** `DATABASE_URL` in `.env.local` (credentials in `C:\Users\PatrickKolasinski\Documents\PatoLex-secrets.env`)
- Use the **direct port 5432** for the pipeline (long-running batch process; no pooler needed).

### Supabase (planned future public-serving deployment — NOT yet active)

Supabase will become the serving DB when the corpus is complete and validated (Gate I). It is **not** where the corpus data lives today.

- **Project:** nqigiiyurwlmruexircz (single project for now; split dev/prod before launch)
- **Connection (direct):** `postgresql://postgres:<password>@db.nqigiiyurwlmruexircz.supabase.co:5432/postgres`
- **Connection (pooled, for Vercel serverless):** `postgresql://postgres:<password>@db.nqigiiyurwlmruexircz.supabase.co:6543/postgres?pgbouncer=true`
- **Dashboard:** https://supabase.com/dashboard

## Claude Code / Codex Operations

- `/ship "<message>"` -- build + commit + push (npm build gated once web project exists)
- `/ucp` -- update session log + commit + push
- `/verify <scope>` -- adversarial audit (`phase` | `subgate` | `gate`)
- `/codex-chat send <message>` -- send work to Codex CLI (Hans) for review
- `/telegram-chat send <message>` -- ping Patrick `[plx-ccNN]`

A separate terminal should run `.claude/scripts/comms-watcher.ps1` to capture Codex transcripts.

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial setup doc. Supabase project details. Node/dotnet requirements. |
