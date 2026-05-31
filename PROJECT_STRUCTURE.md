# Project Structure

Quick reference for repository organization.

```
/
+-- CLAUDE.md                    # Claude Code instructions (start here)
+-- README.md                    # Project overview
+-- PROJECT_STRUCTURE.md         # This file
+-- STRUCTURE-DESIGN.md          # Structure design rationale (reference)
|
+-- docs/                        # Documentation (see docs/README.md)
|   +-- README.md                # Docs-folder orientation
|   +-- 00_Inbox/                # Temporary staging
|   |   +-- comms/               # Codex CLI <-> Claude Code message exchange
|   +-- 10_AUTHORITY_AND_RULES/  # Authority boundaries, source-of-truth map
|   +-- 20_ROADMAP/              # Milestones, current status
|   +-- 30_SYSTEM_DESIGN/        # Architecture, system design
|   +-- 40_SCHEMA/               # Supabase table definitions, data models
|   +-- 60_OPERATIONS/           # Setup, dependencies, runtime config
|   +-- 80_PROJECT_HISTORY/      # Changelog, lessons, session logs, audits
|   |   +-- CHANGELOG.md
|   |   +-- lessons/
|   |   +-- session-logs/
|   |   |   +-- claude-code/
|   |   +-- run-logs/
|   |   +-- audits/
|   +-- 99_ARCHIVE/              # Deprecated/superseded artifacts
|
+-- src/                         # Next.js 15 web application
|   +-- app/                     # App Router pages and layouts
|   +-- server/                  # tRPC routers and server-side logic
|   +-- lib/                     # Shared utilities
|   |   +-- db/                  # Drizzle ORM schema + Supabase client
|   +-- components/              # React components (shadcn/ui + custom)
|
+-- pipeline/                    # C# data pipeline
|                                # Crawls CA state archives, extracts text,
|                                # OCRs scanned documents, loads to Supabase
|   +-- (C# project TBD)
|
+-- tests/                       # Test suite
+-- tools/                       # Supporting scripts/utilities
|
+-- .claude/                     # Claude Code configuration
|   +-- settings.json            # Shared permissions/hooks (committed)
|   +-- settings.local.json      # Per-machine overrides (committed)
|   +-- commands/                # /ship, /bump, /deliver, /ucp, /verify, /codex-chat, /telegram-chat
|   +-- agents/                  # verify-auditor, telegram-monitor, submit-and-wait
|   +-- hooks/                   # pre-bash-check, block-compound-bash, haiku-delegation-nudge
|   +-- scripts/                 # PowerShell + AHK supporting scripts
|   +-- skills/                  # archive-repo, verify
|
+-- project-archives/            # Compressed snapshots (gitignored)
```

## Key Documents

| Document | Purpose | When to Read |
|----------|---------|--------------|
| CLAUDE.md | Project instructions, conventions | Always (loaded automatically) |
| docs/20_ROADMAP/ROADMAP.md | Milestones, current status | Before starting work |
| docs/30_SYSTEM_DESIGN/ARCHITECTURE.md | System architecture | Before design/code changes |
| docs/40_SCHEMA/ | Supabase table definitions | When touching the database |
| docs/60_OPERATIONS/SETUP.md | Environment setup | When setting up or adding deps |
| docs/80_PROJECT_HISTORY/CHANGELOG.md | Project history | When understanding past decisions |
| docs/80_PROJECT_HISTORY/lessons/LESSONS_OVERVIEW.md | What failed, what not to do | Before "improving" anything |

## Which Document Answers Which Question?

| If you're asking... | Look in... |
|---------------------|------------|
| "Where does this file go?" | PROJECT_STRUCTURE.md |
| "What's the current status?" | docs/20_ROADMAP/ROADMAP.md |
| "Why is it built this way?" | docs/30_SYSTEM_DESIGN/ARCHITECTURE.md |
| "How do I set up the environment?" | docs/60_OPERATIONS/SETUP.md |
| "What's the data schema?" | docs/40_SCHEMA/ |
| "What mistakes should I avoid?" | docs/80_PROJECT_HISTORY/lessons/LESSONS_OVERVIEW.md |
| "What changed and why?" | docs/80_PROJECT_HISTORY/CHANGELOG.md |
| "How do I work in this repo?" (for Claude/CC) | CLAUDE.md |

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial version. Next.js + C# pipeline layout. |
