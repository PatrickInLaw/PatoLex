# CLAUDE.md

**READ THIS FILE COMPLETELY BEFORE EVERY TASK. THESE RULES ARE MANDATORY.**

---

## What PatoLex Is

PatoLex is a public-facing web application that provides a searchable, point-in-time archive of California's statutory law — letting attorneys and legal researchers see exactly what a statute said on any given date. The target users are attorneys and legal researchers. The project is also a proof-of-concept for agentic coding and design at scale.

**Scope (`docs/20_ROADMAP/ROADMAP.md` is the source of truth):** PatoLex is built **historical-first / risk-first** — the deliverable is full depth from **1850 (a blank page) to present**, and there is **no public launch until the full corpus is present and validated**. We build the hardest, least-certain segment (statutes reconstructed from scanned 19th-century session laws) FIRST. **This is underway:** the **1850–1875 segment is live** (4262 acts ingested into local PostgreSQL as version-B OCR consensus), with the OCR campaign extending forward. The modern era (1989/1994-forward, from California's structured bulk legislative data) is built SECOND. *(The older "modern-POC-1991-first, pre-1992 = Phase 2" framing was reversed on 2026-05-31 — do not follow it.)* The web stack is Next.js 15 + TypeScript (frontend) + Supabase PostgreSQL (database); deployment is Vercel (frontend) + Supabase (managed DB). The data pipeline runs on local machines (see the pipeline-stack note under Coding Conventions).

Default bias for new dependencies: **TypeScript-native** for the web layer; the active historical pipeline is **Python (OCR/parse) + TypeScript/Drizzle (ingest)** (see Coding Conventions). Microsoft-aligned where applicable.

---

## MANDATORY: Session Hygiene (Claude Chat only)

**Applies to Claude Chat (web UI) sessions only. Claude Code manages context differently (automatic compression) and does not count exchanges.**

| Exchange Count | Action |
|----------------|--------|
| 15-20 | Flag checkpoint, suggest pausing |
| 30 | **HARD STOP** - verify all work before continuing |
| 3+ bug fix rounds on same task | **STOP** - reassess approach, consider fresh session |

---

## MANDATORY: Hygiene Cadence (event-driven, all sessions)

**Keep the run log and session log current as work happens — do not batch all logging to the very end.** This applies to Claude Code too (the exchange-count table above is Claude-Chat-only; this cadence is universal).

Update the run log + session log at each of these triggers:
- **On every commit** — the pre-commit hook (`pre-bash-check.ps1`) **blocks** `git commit` / `git push` without a current-day session log. **NOTE: the session-log enforcement hook (`pre-bash-check.ps1`) now fires on BOTH the Bash tool and the PowerShell tool** — a commit/push via either tool is blocked without a current-day session log. The compound-bash block (`block-compound-bash.ps1`) remains **Bash-tool-only** — a PowerShell-tool command with `&&`/`;` is NOT blocked by it.
- **At each completed work-unit** — when a discrete piece of work lands (a volume ingested, a parser fix, a schema change, a doc rewritten), log it then, not later.
- **About every ~12 exchanges** — a lightweight checkpoint to the run log so progress is recoverable.

**Backstop:** the `Stop` hook `.claude/hooks/session-hygiene-check.ps1` fires when a turn ends and emits an advisory reminder if there is uncommitted `src/`/`pipeline/`/`docs/`/`drizzle/`/`scripts/`/`.claude/` work **and** the newest session log is older than ~25 minutes. It is advisory (always exits 0), not a block — treat it as a prompt to run the event-driven updates above, not as the primary mechanism.

---

## MANDATORY: Findings Land in Durable Docs

**Run logs and session logs are PRUNABLE — they are progress trails, not the system of record for knowledge.** Any *finding* (a discovery, a verified fact about the data/schema/pipeline, a surprise, a workaround, a decision) MUST be recorded in a **durable** place:

- a design doc under `docs/` (e.g. `ARCHITECTURE.md`, `SCHEMA_DESIGN.md`, a `DATA_SOURCES*` doc, `BUILD_RUNBOOK.md`), **or**
- a lessons file under `docs/80_PROJECT_HISTORY/lessons/`, **or**
- a memory entry (the auto-memory index).

**NEVER let a finding live ONLY in a run log or session log.** If a session uncovers something true about the project, the durable doc is updated in the same session — the run/session log may *also* note it, but the durable doc is mandatory. (The `session-hygiene-check.ps1` Stop hook echoes this rule.)

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

## MANDATORY: Adversarial Review (Hans) -- when product code changes

For substantive `src/` or `pipeline/` changes, run a **Hans review** before pushing. The pre-bash hook warns (does not block) when product code is pushed without an adversarial review since the last change.

**"Hans" is NOT Codex.** Hans is a **clean-slate adversarial-review subagent** — spawned with fresh context (no confirmation bias) that takes on the persona of a cranky, detail-obsessed, older Gen-X German engineer who takes pleasure in finding *every* flaw in the work he audits: blunt, direct, merciless, and exhaustively thorough, stopping only when he has found everything. Run Hans before shipping product code, and run him twice for anything touching the data pipeline or schema.

- **Invoke Hans** by spawning the `verify-auditor` agent (`.claude/agents/verify-auditor.md`) with a tightly-scoped audit brief. Override to Opus for gate-level scope. *(The verify-auditor agent should carry the Hans persona above.)*
- **Codex** (`/codex-chat`) is a *separate, optional* external reviewer: the Codex CLI in a terminal tab titled `PatoLex_Codex`, comms file-based via `docs/00_Inbox/comms/to-codex.md` / `from-codex.md`. Use it as an additional adversarial pass when available -- it is not a substitute for Hans, nor Hans for it.

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

**Web layer stack:** Next.js 15 (App Router) + TypeScript 5 + Tailwind CSS + shadcn/ui + Drizzle ORM. Data access is **RSC + Server Actions over a transport-agnostic service layer** (`src/server/`); **tRPC is deferred**, not adopted up front (MCP server is the likely first external interface, public API later — see ARCHITECTURE.md).

**Pipeline stack:** The **historical corpus build (cc002 decision) uses Python (OCR/parse — Tesseract 5 + qwen2.5vl ensemble, PyMuPDF) + TypeScript/Drizzle (ingest against the same schema)**. This is the proven, working toolchain for the one-time 1850-forward reconstruction. The originally-specified **C# (.NET 8 LTS) pipeline (AngleSharp, PdfPig, Tesseract.NET, Dapper) is DEFERRED** — reserved for an ongoing modern-era crawler/worker if/when wanted, not the historical ETL.

**Database:** PostgreSQL 16 via Supabase. Connection pooling: use PgBouncer URL (port 6543) for serverless Vercel functions, direct URL (port 5432) for the data pipeline (Python/TypeScript).

**Naming conventions (TypeScript):**
- Files/folders: `kebab-case`
- Components: `PascalCase`
- Functions/variables: `camelCase`
- Types/interfaces: `PascalCase`, no `I` prefix
- Service-layer functions: `camelCase`

**Naming conventions (C# pipeline — DEFERRED; reserved for a future modern-era crawler, no active C# code today):**
- Standard .NET PascalCase for types and methods
- Async methods suffixed `Async`

**Naming conventions (Python pipeline — the active historical toolchain):**
- Modules/functions: `snake_case`; constants: `UPPER_SNAKE_CASE`

**Layer discipline:**
- `src/app/` -- Next.js App Router pages and layouts (no DB calls directly)
- `src/server/` -- transport-agnostic service/query layer + server-side logic (the single place data access lives; consumed by RSC, Server Actions, and later MCP/API)
- `src/lib/db/` -- Drizzle schema definitions and DB client
- `pipeline/` -- Python OCR/parse scripts + TypeScript/Drizzle ingest scripts for the historical corpus build (C#/.NET is deferred)
- Never call the DB from *client* components; all data access goes through the `src/server/` service layer (Server Components and Server Actions call it directly)

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
- Call DB from React components (must go through the `src/server/` service layer)
- Put `service_role` key in client-side code

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial version from PatoLex template. Next.js 15 + TypeScript + tRPC + Supabase + C# pipeline. |
| 2026-06-02 | cc002 (doc rewrite): Corrected "What PatoLex Is" to historical-first reality (1850-1875 live) and the active pipeline stack (Python OCR/parse + TS/Drizzle ingest; C#/.NET deferred). Added two MANDATORY rules — **Hygiene Cadence** (event-driven run/session-log updates on commit + work-unit + ~12 exchanges, with the ~25-min Stop-hook backstop; the session-log hook now covers BOTH the Bash and PowerShell tools, while the compound-bash block remains Bash-only) and **Findings Land in Durable Docs** (findings go in a design doc / lessons / memory, never only a prunable run/session log). No existing MANDATORY rule weakened. |
| 2026-06-02 | cc002 (Hans pass on the rewrite): corrected a new overclaim — the **compound-bash block is Bash-tool-only**, NOT both tools (only the session-log hook covers both) — and three pre-existing CLAUDE.md errors the rewrite owned: the "must go through tRPC" rule → `src/server/` service layer, and stale "C# pipeline" references (the active pipeline is Python + TypeScript/Drizzle). |
