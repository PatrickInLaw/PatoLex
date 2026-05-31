# Session Logs

This folder contains session summaries for all PatoLex AI agent sessions.

Session summaries are reference documents -- they record what happened, what was decided, and what was produced. They are not authoritative for architecture, schema, or design decisions. For authority, see the canonical documents under `docs/10_*` through `docs/60_*`.

---

## Structure

```
docs/80_PROJECT_HISTORY/session-logs/
  README.md                        -- this file
  SESSION-SUMMARY-RULES.md         -- numbering, naming, and format conventions
  SESSION-SUMMARY-TEMPLATE.md      -- blank template for new summaries
  claude-code/                     -- Claude Code session summaries
```

Additional agent folders (e.g., `claude/`, `codex/`, `chatgpt/`) should be created as needed when sessions are conducted in those interfaces.

---

## Session Numbering

Each agent type gets its own numbering stream:

- Claude Code: `cc001`, `cc002`, ...
- Claude Chat: `SESSION_001`, `SESSION_002`, ... (if used)
- Codex CLI: `cx001`, `cx002`, ... (if recorded)
- Other agents: own folder and stream

See `SESSION-SUMMARY-RULES.md` for the authoritative conventions.

---

## Usage

To find when a decision was made: search session summaries by keyword.

To produce a summary for the current session: use `SESSION-SUMMARY-TEMPLATE.md`.

Root `session-logs/` should contain shared infrastructure docs and agent subfolders only. Session summaries belong in the appropriate agent folder.

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial version. |
