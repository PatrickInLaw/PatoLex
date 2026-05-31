<!-- ROUTING
Purpose: Orientation for the docs folder (not the repo).
Use when: Finding the right document quickly; understanding doc authority and lifecycle.
Do not use for: Project overview (see repo root README.md).
-->

# Documentation Library (docs/)

The repository root `README.md` explains what PatoLex is. This file explains how this documentation library is organized and where to look first.

## Quick Navigation

| If you need... | Go to... |
|----------------|----------|
| What is authoritative | `10_AUTHORITY_AND_RULES/AUTHORITY.md` |
| Current status / next work | `20_ROADMAP/ROADMAP.md` |
| System architecture | `30_SYSTEM_DESIGN/` |
| Data models / schema / metadata | `40_SCHEMA/` |
| Setup / operations | `60_OPERATIONS/` |
| History, changelogs, lessons | `80_PROJECT_HISTORY/` |
| Codex CLI <-> Claude Code comms | `00_Inbox/comms/` |
| Historical/deprecated artifacts | `99_ARCHIVE/` (non-authoritative) |

## Folder Guide

- **`00_Inbox/`** -- Temporary staging space. `comms/` subfolder holds active Codex-CC message exchange.
- **`10_AUTHORITY_AND_RULES/`** -- Source-of-truth map.
- **`20_ROADMAP/`** -- Milestones and current project status.
- **`30_SYSTEM_DESIGN/`** -- Architecture, processing pipeline, design concepts.
- **`40_SCHEMA/`** -- Data models, tables, metadata formats.
- **`60_OPERATIONS/`** -- Setup, configuration, runtime ops.
- **`80_PROJECT_HISTORY/`** -- Curated history. Useful context but not authoritative.
- **`99_ARCHIVE/`** -- Deprecated docs.

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial version. |
