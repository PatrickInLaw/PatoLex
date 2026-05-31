# Session Summary Rules

This document defines the conventions for session summaries across all PatoLex project agents.

---

## Session Numbering

The repository uses separate numbering streams by agent:

- Claude Code: `cc001`, `cc002`, ...
- Claude Chat: `SESSION_001`, `SESSION_002`, ... (if used)
- Codex CLI: `cx001`, `cx002`, ... (if recorded)
- Other agents: own folder and numbering stream

Do not force streams into a fake unified numbering model.

---

## Summary File Naming

```
SESSION_ccNNN_SUMMARY_2026-05-31_Short_Title.md          (Claude Code)
SESSION_NNN_SUMMARY_2026-05-31_Short_Title.md            (Claude Chat)
SESSION_cxNNN_SUMMARY_2026-05-31_Short_Title.md          (Codex)
```

- NNN: 3-digit number with leading zeros
- Short_Title: underscores between words, descriptive (3-6 words)
- The verbose name is preferred over the terser `ccNNN-summary.md` form because it browses far better in Explorer / VS Code

---

## Agent Folders

Summaries are stored by agent:

```
docs/80_PROJECT_HISTORY/session-logs/
  claude-code/     -- Claude Code (CLI / desktop / web)
  claude/          -- Claude Chat (if used)
  codex/           -- Codex CLI (if used)
  chatgpt/         -- ChatGPT (if used)
```

Additional agent folders are created as needed. The root `session-logs/` folder is for shared infrastructure docs only.

---

## Summary Sections (Required)

Every summary must include all of the following sections, in order:

1. **Header table** -- Session number, date, agent, context (milestone/task), branch (if applicable)
2. **What Was Done** -- Narrative. What was built, designed, decided, or resolved. Use numbered sub-sections for distinct work items.
3. **Files Changed** -- New files created and existing files modified. Group logically (code, docs, config).
4. **Decisions Made** -- Table with decision and detail. Only include if decisions were actually made. If none, write "None this session."
5. **Open Items at Close** -- Table with item and priority. What's unfinished or needs follow-up.
6. **Next Session Should Start With** -- Ordered list of 1-5 priorities.
7. **Lessons Learned** -- Small surprises, failures, or patterns worth capturing. If none, write "None this session."

### Optional Sections

- **Commits** -- Table of commit hashes and descriptions (useful for multi-commit sessions)
- **Known Issues** -- Problems discovered but not fixed this session

---

## Who Produces the Summary

The AI agent that conducted the session produces its own summary. The summary is a deliverable at session close, not a cleanup task for the next session.

---

## Run Logs vs Session Logs

These serve different purposes:

| | Run Log | Session Log |
|-|---------|-------------|
| **Granularity** | Line-per-step, during work | Summary after session |
| **Audience** | Real-time progress tracking | Future sessions, audits |
| **Location** | `docs/80_PROJECT_HISTORY/run-logs/` | `docs/80_PROJECT_HISTORY/session-logs/` |
| **Format** | `[timestamp] PHASE \| Description \| OK/WARN/FAIL` | Markdown with sections |
| **When written** | As work progresses | At session close |

Both are required for substantive sessions. A session that only reads files and answers questions does not need a run log, but still needs a session summary.

---

## Run Log Format

Run logs track real-time progress during work. They replace `echo`/`printf` for status output (which cause popup approvals in local agent mode).

**Location:** `docs/80_PROJECT_HISTORY/run-logs/{task-name}-run.log`

**Entry format:**
```
[2026-05-31 HH:MM PT] PHASE | Description | OK/WARN/FAIL
```

**Example:**
```
[2026-04-27 10:30 PT] START | Project structure setup (cc001) | OK
[2026-04-27 10:35 PT] DOCS | Created docs/ skeleton | OK
[2026-04-27 11:00 PT] TOOLING | Ported .claude/ configuration | OK
[2026-04-27 11:30 PT] DONE | Structure setup complete | OK
```

**Status codes:**
- `OK` -- Completed successfully
- `WARN` -- Completed with warnings or minor issues
- `FAIL` -- Blocked, needs intervention

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial version. Verbose session-log naming. |
