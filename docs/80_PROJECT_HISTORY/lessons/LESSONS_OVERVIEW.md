# Lessons Overview

Index of lessons learned during the PatoLex project.

## Inherited Lessons (from Pato template, 2026-04-27)

These lessons came from the template's own setup history and apply to any new repo using this template:

- **Don't hardcode model versions in tooling.** Co-author attribution should be `Claude Code <ClaudeCode@Kolasinski-Law.com>` -- survives model upgrades without churn.
- **`block-compound-bash.ps1` is non-negotiable.** Compound bash (`&&`, `||`, `;`, `cd ...`) causes endless permission prompts. Hook included by default in this template; do not disable.
- **Verbose session-log naming wins.** `SESSION_ccNNN_SUMMARY_YYYY-MM-DD_Title.md` browses much better in Explorer than `ccNNN-summary.md`.
- **Bump enforcement must tolerate missing VersionInfo.cs.** Pre-scaffold mode is built into `bump.ps1` and the pre-bash hook; do not remove the file-existence checks.
- **Parallelize template-porting and other mechanical work.** Repo setup is mostly content adaptation of known files. Batch by directory and dispatch parallel Sonnet/Haiku subagents -- don't sequence Opus through it. Estimated savings: ~3/4 wall-clock time, ~1/2 tokens.
- **Codex window title should be project-specific.** This repo uses `PatoLex_Codex`.
- **Hooks: omit `"shell": "powershell"` in settings.json.** Setting this causes `$CLAUDE_PROJECT_DIR` to be evaluated as a PowerShell variable (empty), breaking the path. Let Claude Code do the substitution by leaving the field out.

## PatoLex-Specific Lessons (cc001)

- **Supabase: use port 6543 (PgBouncer) for Vercel, port 5432 (direct) for the C# pipeline.** Serverless functions exhaust the 60-connection limit on the direct URL. The pipeline is a long-running batch process and benefits from a persistent direct connection.
- **`service_role` key must never appear in client-side code.** Use `anon` key for browser-facing calls; `service_role` only in Next.js Server Components / Route Handlers / tRPC procedures running server-side.
- **Read the template FIRST, then build.** On cc001, the agent started building before fully reviewing the sample repo and had to stop and restart. Cost: extra time and context. Rule: always extract and read the full template before touching the new repo.
- **Write tool requires Read first.** Claude Code's Write tool will refuse to overwrite a file it hasn't read this session. On large repo setups, batch-read target files before batch-writing, or accept the read-then-write sequence for each file.

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial version with inherited template lessons + PatoLex-specific lessons. |
