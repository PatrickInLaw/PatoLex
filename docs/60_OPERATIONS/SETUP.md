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
```
NEXT_PUBLIC_SUPABASE_URL=https://nqigiiyurwlmruexircz.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<from Supabase dashboard>
SUPABASE_SERVICE_ROLE_KEY=<from Supabase dashboard -- server-side only>
DATABASE_URL=postgresql://postgres:<password>@db.nqigiiyurwlmruexircz.supabase.co:5432/postgres
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

## Supabase

- **Project:** nqigiiyurwlmruexircz (single project for now; split dev/prod before launch)
- **Connection (direct, for pipeline):** `postgresql://postgres:<password>@db.nqigiiyurwlmruexircz.supabase.co:5432/postgres`
- **Connection (pooled, for Vercel):** `postgresql://postgres:<password>@db.nqigiiyurwlmruexircz.supabase.co:6543/postgres?pgbouncer=true`
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
