# Session cc002 Summary

| Field | Value |
|-------|-------|
| Session | cc002 |
| Date | 2026-05-31 |
| Agent | Claude Code / Opus 4.8 |
| Context | First real dev session: roadmap sanity-check, scope revision, Gate B data reconnaissance |
| Branch | main |

---

## What Was Done

cc001 was repository structure setup. cc002 was the first substantive session: review cc001's deliverables, sanity-check the scope and tech decisions (made by a prior Sonnet session), revise the plan, then execute Gate B (data source reconnaissance).

### 1. Scope split (North Star vs. POC)
The 1849-to-present vision is a moonshot, not a POC: pre-1992 law has no clean digital source (requires OCR of bound *Statutes of California* volumes + historical amendment-chain reconstruction) — a multi-year research program. Even Westlaw/Lexis/HeinOnline have only partial depth there. Split, with Patrick's approval:
- **POC (Phase 1):** modern point-in-time archive, 1991-92 session to present, from California's official bulk legislative data.
- **North Star (Phase 2):** full historical depth to 1849, only after the modern POC is solid.

### 2. Two-database architecture
Reversed cc001's "no local Postgres" decision for the pipeline:
- **Local PostgreSQL 16** — pipeline build/staging (ETL, amendment diffing, experimentation, ad-hoc + Claude Code analysis). Disposable, fast.
- **Supabase PostgreSQL 16** — public serving layer. One Drizzle schema applied to both; a publish step promotes finished data local -> Supabase.

### 3. Roadmap / gate re-sequencing
Rewrote ROADMAP around recon-before-scaffolding and vertical-slice-first: Gate B (data recon, no code) -> C (schema) -> D (pipeline, one-code slice) -> E (web + point-in-time read) -> F (search) -> G (scale-out + correctness validation + launch). Phase 2 = Gates H (historical OCR) and I (public API/citator).

### 4. tRPC deferred
Data access = RSC + Server Actions over a transport-agnostic service layer (`src/server/`). tRPC is private/TS-only, so it does not serve the MCP-then-API path; deferred. Likely external-interface order: RSC/Server Actions -> MCP server -> public REST API.

### 5. Gate B reconnaissance (completed this session)
Dispatched two sonnet subagents (data inventory + reconstruction methodology) plus a haiku subagent (this session log). Findings synthesized into `docs/30_SYSTEM_DESIGN/DATA_SOURCES.md`. Headline results:
- **Source confirmed:** `https://downloads.leginfo.legislature.ca.gov/` — biennial `pubinfo_YYYY.zip` (1989-2025), MySQL `capublic` schema, tab-delimited `.dat` + `.lob` text. 162,169 current code sections, 30 codes + Constitution, ~215 MB text/snapshot, public domain.
- **Critical finding:** `LAW_SECTION_TBL` is a **current-only snapshot** (all rows `active_flg='Y'`; loader truncates/replaces). Older archives (1989-2003) lack the law tables entirely. So point-in-time text cannot be downloaded — it must be **reconstructed** by parsing chaptered bill text (`BILL_VERSION_TBL`, back to 1993-94) and applying amendments in operative order, validated against the current snapshot.
- **POC floor:** Jan 1, 1994. Pre-1993 -> Phase 2 OCR.
- **Legal-correctness rules confirmed necessary** (not gold-plating): operative-vs-effective dates (Gov. Code §9600), double-jointing / chaptering-out resolution (§9605, ~140-221 bills/session), synthetic `section_id` + number-history for renumbering/recodification, provenance per version.
- **#1 risk to spike in Gate D:** chaptered bill XML format + whether bill->code-section linkage is explicit or must be parsed from "Section X of the Y Code is amended to read:".

---

## Files Changed

**Modified:**
- `docs/20_ROADMAP/ROADMAP.md` — full rewrite; later updated to mark Gate B done, Gate C next.
- `docs/30_SYSTEM_DESIGN/ARCHITECTURE.md` — scope, two-DB, data model (operative date, provenance, GiST exclusion), API/data-access strategy.
- `README.md`, `CLAUDE.md` — North Star vs. POC scope; tRPC deferral; layer-discipline fix (client components never touch DB; service layer is the single data-access point).

**New:**
- `docs/30_SYSTEM_DESIGN/DATA_SOURCES.md` — Gate B report (authoritative data-source + reconstruction-strategy record).
- `docs/80_PROJECT_HISTORY/run-logs/cc002-planning-run.log` — run log.
- Memory: `orchestrator-only-model.md`, `both-logs-every-session.md` (+ MEMORY.md index).

---

## Decisions Made

1. North Star vs. POC split — POC = modern era (1991-present) from bulk data.
2. Two-database architecture — local Postgres (build) + Supabase (serve).
3. Gate B (data recon) mandatory before any pipeline code — now complete.
4. Vertical-slice-first — one code end-to-end before scaling.
5. Schema: synthetic section IDs, operative-date ranges, provenance, daterange GiST exclusion, double-jointed-loser audit table.
6. Reconstruction = amendment-application validated against current snapshot (not snapshot-diff — historical snapshots don't exist).
7. tRPC deferred — RSC + Server Actions over a transport-agnostic service layer.
8. Working model: Opus orchestrates; reading/code/download delegated to haiku/sonnet/local.

---

## Open Items at Close

- Gate C (schema design) — HIGH, next.
- Gate D spike: chaptered bill XML format + bill->section linkage — HIGH (resolve early in Gate D).
- Local Postgres + Supabase Pro tier setup — MEDIUM.
- Commit cc002 docs — pending Patrick's go-ahead.

---

## Next Session Should Start With

1. Design the schema (Gate C) from `DATA_SOURCES.md`: `codes -> sections (synthetic id) -> statute_versions (operative_range, provenance, GiST exclusion)`, `section_number_history`, `bill`/`amendment`, chaptered-out audit table. Drizzle, applied to local + Supabase.
2. Stand up local Postgres 16 for staging.
3. Plan the Gate D bill-XML spike before writing pipeline code.

---

## Lessons Learned

- **Dual logging is mandatory:** every session needs both a run log (real-time) and a session log (summary).
- **Recon-as-a-gate prevents rework:** Gate B overturned a core assumption (no historical snapshots exist) before any pipeline code was written.
- **The `block-compound-bash` hook scans the raw command for `; `, `&&`, `||`, `cd ` — including inside quoted strings and PowerShell hashtables.** Telegram/JSON sends must avoid `; ` entirely: put `chat_id` in the URL, scrub semicolons from message text, and use `| Out-Null` rather than `; 'done'`.
- **Delegated doc writes can come back mangled:** the haiku session-log draft rendered literal "backtick"/"C hash"/`�` artifacts; rewritten cleanly by the orchestrator. When a delegated doc is malformed, fix in place rather than re-delegating.

---

## Commits

None yet this session (awaiting go-ahead).
