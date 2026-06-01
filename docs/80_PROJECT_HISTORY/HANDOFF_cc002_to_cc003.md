# Handoff: cc002 → cc003

**From:** cc002 (Opus, orchestrator) · **Date:** 2026-06-01
**Your likely first job:** implement the **Gate D DDL** (the database tables for the schema cc002 designed), then begin the historical build at the 1872 baseline.

Read this, then read (in order): `CLAUDE.md`, `docs/20_ROADMAP/ROADMAP.md`, `docs/40_SCHEMA/SCHEMA_DESIGN.md`, the memory index. This handoff is the orientation; those are the authority.

---

## Where the project is

PatoLex = a public, point-in-time archive of California statutory law (what any statute said on any date), **1850–present**, built **historical-first / risk-first**, distributed **free** (likely handed to a law school/nonprofit to steward forever — the Git repo is the durable gift). It's also a proof-of-concept for agentic coding at scale.

**All the hard risks are retired (cc002):**
- **OCR** → legal-grade (~1.5% body-CER) on *clean non-Google* scans + ensemble disagreement-flagging (99% flag-recall). Google Books scans were the sole blocker.
- **Reconstruction engine** → **Method A** (parse session-law amendment directives, apply forward) validated **QUALIFIED-GO**: parser hit 100% precision/recall on the 1883 Penal Code slice; the lone validation mismatch was a Google-scan OCR error, not a method failure.
- **Sourcing** → corpus completable from clean sources; unbroken session-law backbone 1849–2025 (blank-slate principle).

**So the engine works. What's missing is the container (the schema) and then the build itself.**

---

## What's DECIDED (do not relitigate without cause)

1. **Schema is event-sourced + CQRS.** Append-only `change_event` log = system of record (write side). Queries hit **materialized read models** — `provision_version` (daterange + GiST + tsvector) for the web UI, and the **Git repo** for the other "eye." **No history-replay at query time.** Full version-materialization, *not* interval snapshots (statutes change sparsely; materialization dominates).
2. **Domain-neutral.** `enactment` → `provision` keyed by `jurisdiction` + `unit_type`. CA statutes are first; CA regs (baseline-plus-forward) and a federal v2 are drop-in corpora. Design neutral, **build/test only the CA-statute path now** (YAGNI on the rest).
3. **Reconciliation (§9605, recodification) lives in the schema, NEVER in Git.** Git is an emitted read-only artifact. Git's text-merge/rename-detection would fabricate non-law. (Full rationale: `LAW_AS_GIT.md`.)
4. **Synthetic provision identity** = `bigint` PK + external `uuid` v7 (`public_id`). Opaque (never encode the section number). UUID not in Git paths (paths use current designation; uuid in file metadata).
5. **Diffs are captured but derived** from stored whole-section texts (never the reverse). `change_event.diff_from_prior` = token-level structured diff for the UI redline; at the Git level, word-diff is free via `git diff --word-diff`.
6. **Recodification = a typed lineage DAG** (`lineage_edge`): renumber/transfer keep identity (1:1); split (hybrid primary-successor rule) / merge / repeal_reenact / repeal_without_successor. One mechanism for both the rare-huge (1872, 1943) and the frequent-small (decimal spinoffs, renumbers). "Full history of a provision" = recursive CTE over the edge graph.
7. **Build order:** start at the **proven 1872 codified baseline**, run Method A **forward to the ~1991 seam** (Penal Code first), THEN do **1850–1871 pre-code** as a later distinct pass (uncodified `act_section`s feeding the 1872 codification edges). **Do NOT start cold at 1850** — the pre-code act-era is a different, still-unproven modeling problem.
8. **Two databases:** local Postgres/SQL Server (build/staging) + Supabase (serving). One Drizzle schema; publish step promotes finished data. Stack: Next.js 15 + TS + Drizzle; **tRPC deferred** (RSC + Server Actions over `src/server/`).

---

## Your concrete first steps (Gate D DDL → first build vertical)

1. **Implement the Gate D DDL** per `docs/40_SCHEMA/SCHEMA_DESIGN.md`: `source_document`, `enactment`, `provision`, `designation_history`, `change_event`, `lineage_edge`, and the materialized `provision_version` read model. Postgres needs the `btree_gist` extension for the daterange GiST exclusion constraint. Use Drizzle. Target the **local** staging DB first (SQL Server/Postgres creds obtainable from the `patoaudio`/`kolalawdb` repos — Patrick authorized agents to retrieve them).
2. **Seed the 1872 Penal Code baseline** as `enact` events (clean text already in scratch — see below).
3. **Run Method A 1872→~1900 for the Penal Code** into the schema, including the bounded OCR task: the **1873–80 "Amendments to the Codes" text lives in the image-only Chief Clerk PDFs** (Tesseract pass; clean scans → ~1.5% CER). This is the first production vertical and the template for all codes.
4. **Materialize + validate + emit:** build `provision_version`, validate against the annotated editions + *Index to the Laws 1850–1893*, and emit the first Git-history slice as an end-to-end proof.

Get the DDL reviewed before loading data at scale. Consider a "Hans review" (Codex adversarial) on the schema + any pipeline code — see CLAUDE.md.

---

## Working constraints (Patrick's, mandatory — see CLAUDE.md + memory)

- **You are an ORCHESTRATOR.** Delegate reading/code-search/download/OCR/boilerplate to haiku/sonnet subagents (and local GPUs over Tailscale). Reserve your own context for decisions, architecture, final review. *"If I catch you writing code directly where it is not absolutely needed, you'll be swapped out for sonnet."* (Schema/architecture *design* is legitimately your job; mechanical DDL typing can be delegated then you review.)
- **Both logs every session:** a run-log (`docs/80_PROJECT_HISTORY/run-logs/`) AND a session log (`docs/80_PROJECT_HISTORY/session-logs/claude-code/SESSION_cc003_...md`). **Session logs are NOT a haiku job** (a haiku draft came back mangled — Patrick's explicit rule).
- **No line-by-line human review** of output — accuracy via automation (consensus + disagreement-flagging); humans spot-check + audit only.
- **Bash hygiene:** the `block-compound-bash` hook rejects leading `cd`, ` && `, ` || `, `; ` — *including inside quoted strings, heredocs, and git commit messages*. Use absolute paths, run commands singly, use the Write tool (not `echo`/`cat >>`/`touch`/`mkdir`), and scrub `; ` from commit messages. Log progress to the run-log file, not `echo`.
- **`/ucp`** = update session log + commit + push. **`/ship`** = build + commit + push. Codex review (Hans) before pushing product code.
- **Quality-first:** do it right the first time, hardest problems first; don't pitch speed/revenue.

---

## Key artifacts & scratch (the next spike needs these)

- **Repo docs:** `SCHEMA_DESIGN.md` (Gate D), `LAW_AS_GIT.md`, `ADJACENT_DOMAINS_FEASIBILITY.md`, `DATA_SOURCES_HISTORICAL.md` (§1a licensing, §1b sourcing map, §1c inventory/method), `DATA_SOURCES.md` (modern), `GATE_C_SLICE_PROOF.md`, `sources/chief_clerk_statutes_manifest.csv` (653 statute PDFs 1850–2008, the session-law backbone), `sources/CA_Legislative_Publications_Catalog.*` (4,034 vols).
- **Scratch (NOT in repo)** `C:\Users\PatrickKolasinski\PatoLex-scratch\gate-b-historical\`: 1872 Penal Code baseline (`penalcodecalifo00burcgoog_djvu.txt`), `pc_extract_{1872,1881,1883,1885,1889,1903}.json` (trusted validation editions), Method-A spike outputs, OCR test sets + benchmark CSVs, `gpu_inventory.md`. The Method-A run-log: `docs/80_PROJECT_HISTORY/run-logs/method-a-respike-run.log`.
- **Channels:** serve text ONLY from clean public-domain channels — Internet Archive non-`goog` + CA-gov (Chief Clerk, leginfo). HathiTrust/Google bulk datasets prohibit re-host/search/share (binds even free/nonprofit). Content is PD; the *channel terms* still bind.
- **Infra:** SQL Server + 5080/5090 GPUs over Tailscale; creds in `patoaudio`/`kolalawdb` repos. Secrets file `C:\Users\PatrickKolasinski\Documents\PatoLex-secrets.env` (outside repo). Telegram tag `[plx-cc003]` for AFK comms.

---

## Open threads carried forward

- Parser stress-test on a *heavier* amendment session (1883 was light, 12 directives).
- ~10–20 page **human-gold OCR audit** (needs Patrick's hands) to firm the production accuracy number.
- Source a clean 1872–1905 Penal Code baseline (IA there is Google-only; HathiTrust-UC check or law-library re-scan).
- Confirm the 1937–1953 recodification acts contain old→new disposition tables.
- WSL access discrepancy (low priority; off critical path — Windows Tesseract on clean scans is already legal-grade).
- CA regs: confirm a clean non-Westlaw current-CCR baseline is obtainable (only when regs become near-term).
