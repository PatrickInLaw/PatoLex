# CLAUDE.md

**READ THIS FILE COMPLETELY BEFORE EVERY TASK. THESE RULES ARE MANDATORY.**

---

## What PatoLex Is

PatoLex is a public-facing web application that provides a complete, searchable archive of California's statutory law with full historical depth — every version of every statute from statehood (1849-1851) to the present. The target users are attorneys and legal researchers who need to know exactly what a statute said at a specific point in time. The project is also a proof-of-concept for agentic coding and design at scale. The stack is Next.js 15 + TypeScript (web frontend), Supabase PostgreSQL (database), tRPC (API), and a separate C# console/worker pipeline for crawling and parsing CA state archive documents. Deployment: Vercel (frontend) + Supabase (managed DB). The data pipeline runs on local machines.

Default bias for new dependencies: **TypeScript-native** for the web layer, **C#/.NET-native** for the pipeline. Microsoft-aligned where applicable.

---

## MANDATORY: Session Hygiene (Claude Chat only)

**Applies to Claude Chat (web UI) sessions only. Claude Code manages context differently (automatic compression) and does not count exchanges.**

| Exchange Count | Action |
|----------------|--------|
| 15-20 | Flag checkpoint, suggest pausing |
| 30 | **HARD STOP** - verify all work before continuing |
| 3+ bug fix rounds on same task | **STOP** - reassess approach, consider fresh session |

---

## MANDATORY: Documentation Hygiene

**Claude tracks documentation needs during sessions:**

1. When bugs/surprises/workarounds occur, note them for lessons files
2. At session end (or at checkpoints), proactively suggest documentation additions
3. If a task revealed any lessons or required workarounds, update `docs/80_PROJECT_HISTORY/lessons/`

**Don't rely on CC to notice documentation needs - explicitly include them in prompts.**

---

## MANDATORY: Token Conservation

**Delegate mechanical work to haiku-worker subagents. Reserve Opus context for decisions.**

**Delegate to haiku-worker:**
- File reading, summarization, and code search/grep tasks
- Test writing when the pattern is already established
- Documentation drafts, changelog entries, session log updates
- Boilerplate generation (Next.js pages, tRPC routers, C# pipeline classes)
- Code review passes (haiku reviews first, Opus reviews haiku's output)
- Counting and inventory tasks
- Diff summaries and PR description drafts

**Keep on Opus:**
- Architecture decisions and design planning
- Cross-component refactoring
- Final review and adversarial checks (Hans)
- Complex debugging where full codebase context matters
- Any task where getting it wrong costs more time than the tokens saved

**When in doubt:** If the task is "read X and tell me Y" or "write something that follows an existing pattern," it's a haiku task.

---

## MANDATORY: Bash Hygiene

**Compound bash commands cause endless permission prompts.** The `block-compound-bash.ps1` PreToolUse hook will reject:

- `cd ` at the start of a command, or after a separator
- ` && ` chaining
- ` || ` chaining
- `; ` or ` ;` separators

Use absolute paths instead of `cd`. Run commands one at a time, in parallel tool calls if independent.

---

## MANDATORY: Progress Logging

**DO NOT use bash echo or printf for status output.** These cause popup approvals.

Instead, log progress to the run-log file:
```
docs/80_PROJECT_HISTORY/run-logs/{task-name}-run.log
```

**Log entry format:**
```
[YYYY-MM-DD HH:MM PT] PHASE | Description | OK/WARN/FAIL
```

**Status codes:**
- `OK` - Completed successfully
- `WARN` - Completed with warnings or minor issues
- `FAIL` - Blocked, needs intervention

---

## MANDATORY: Session Logs

**Every substantive session gets a session log.**

- Location: `docs/80_PROJECT_HISTORY/session-logs/claude-code/`
- Format: `SESSION_ccNNN_SUMMARY_YYYY-MM-DD_Short_Title.md`
- Template: `docs/80_PROJECT_HISTORY/session-logs/SESSION-SUMMARY-TEMPLATE.md`
- Rules: `docs/80_PROJECT_HISTORY/session-logs/SESSION-SUMMARY-RULES.md`

The pre-bash hook **blocks** `git commit` and `git push` when no current-day session log is staged/updated. Override with `[skip-session-log]` in the commit message only when justified.

---

## Versioning (Web Project)

PatoLex uses `package.json` for version tracking. No `VersionInfo.cs` exists; the bump/build enforcement in the pre-bash hook is in no-op mode.

- Use `/ship "<message>"` to build + commit + push
- Use `/ucp` to update session log + commit + push (no build required)
- Use `npm version patch|minor|major` manually when releasing

The `bump.ps1` script is included for consistency but will run in pre-scaffold (no-op token-write) mode unless a VersionInfo.cs is added to the pipeline project.

---

## MANDATORY: Codex Review (Hans) -- when product code changes

For substantive `src/` or `pipeline/` changes, request Codex review via `/codex-chat` before pushing. The pre-bash hook warns (does not block) when pushing product code that Codex has not reviewed since the last outbound message.

Codex CLI runs in a separate terminal tab titled `PatoLex_Codex`; comms are file-based via `docs/00_Inbox/comms/to-codex.md` and `from-codex.md`.

**"Hans review"** = Codex adversarial review. Run it before shipping product code, and run it twice for anything touching the data pipeline or schema.

---

## MANDATORY: Before Starting Work

1. **Read this entire file**
2. **Check `docs/80_PROJECT_HISTORY/CHANGELOG.md`** to understand recent changes
3. **Check `docs/20_ROADMAP/ROADMAP.md`** for current status and priorities

---

## Key Documents

| Document | Purpose |
|----------|---------|
| `docs/20_ROADMAP/ROADMAP.md` | Current status, what's next |
| `docs/30_SYSTEM_DESIGN/ARCHITECTURE.md` | System architecture |
| `docs/40_SCHEMA/` | Data models, schema, Supabase table definitions |
| `docs/60_OPERATIONS/SETUP.md` | Environment setup, dependencies |
| `docs/80_PROJECT_HISTORY/CHANGELOG.md` | Project history |
| `docs/80_PROJECT_HISTORY/lessons/LESSONS_OVERVIEW.md` | Index of lessons learned |

---

## Forbidden Bash Patterns

**DO NOT use these - they cause popup approvals or are blocked by hook:**

- `echo` for status output (use run-log file)
- `printf` for status output (use run-log file)
- `touch` to create files (use the Write tool)
- `mkdir` to create directories (Write tool creates dirs as needed)
- `cd ` (use absolute paths)
- ` && `, ` || `, `; ` chaining (run separately)

---

## Coding Conventions

**Web layer stack:** Next.js 15 (App Router) + TypeScript 5 + Tailwind CSS + shadcn/ui + tRPC + Drizzle ORM

**Pipeline stack:** C# (.NET 8 LTS) console app or Worker Service -- AngleSharp, PdfPig, Tesseract.NET, Dapper

**Database:** PostgreSQL 16 via Supabase. Connection pooling: use PgBouncer URL (port 6543) for serverless Vercel functions, direct URL (port 5432) for the C# pipeline.

**Naming conventions (TypeScript):**
- Files/folders: `kebab-case`
- Components: `PascalCase`
- Functions/variables: `camelCase`
- Types/interfaces: `PascalCase`, no `I` prefix
- tRPC routers: `camelCase` procedure names

**Naming conventions (C# pipeline):**
- Standard .NET PascalCase for types and methods
- Async methods suffixed `Async`

**Layer discipline:**
- `src/app/` -- Next.js App Router pages and layouts (no DB calls directly)
- `src/server/` -- tRPC routers and server-side logic
- `src/lib/db/` -- Drizzle schema definitions and DB client
- `pipeline/` -- C# pipeline project(s) for crawling, OCR, parsing, and loading
- Never call DB from React components; always go through tRPC

**Environment / secrets:**
- Never commit `.env.local` (gitignored)
- Secrets file: `C:\Users\PatrickKolasinski\Documents\PatoLex-secrets.env` (outside repo)
- Supabase: use `anon` key in client-side code only; `service_role` key in server-only routes
- Connection strings: PgBouncer URL for Vercel, direct URL for pipeline

---

## Do Not

- Skip progress logging
- Skip session logs
- Skip documentation
- Create half-baked features
- Hardcode environment values (use `.env.local` / environment variables)
- Hardcode model versions in tooling/scripts
- Guess at API behavior without checking docs first
- Implement workarounds without approval
- Exceed 30 exchanges without stopping to verify (Claude Chat only)
- Use echo or printf for status output
- Use `cd` or compound bash (`&&`, `||`, `;`) -- the hook blocks these
- Call DB from React components (must go through tRPC)
- Put `service_role` key in client-side code

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial version from PatoLex template. Next.js 15 + TypeScript + tRPC + Supabase + C# pipeline. |
