# Handoff: cc002 → cc003

> **2026-06-02 UPDATE APPENDED BELOW.** The body of this handoff (dated 2026-06-01) is preserved for history but its "first steps" are now DONE. **Read the `2026-06-02 update` section at the bottom first** — it reflects the completed 1850-1875 build, the three-tier corpus model, and the in-flight forward campaign.

**From:** cc002 (Opus, orchestrator) · **Date:** 2026-06-01
**Status update:** cc002 went further than planned and **already implemented + adversarially reviewed the Gate D DDL** (Drizzle, 7 tables, in `src/lib/db/` + `drizzle/`; `db:generate` + `typecheck` pass; NOT yet applied to a live DB). **Your likely first job:** stand up local PostgreSQL 16, apply the migration, then begin the historical build at the 1872 baseline.

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
8. **Two databases — Postgres BOTH sides:** local **PostgreSQL 16** (`localhost:5432/patolex` on the 5080 — the **active build DB, where the corpus lives now**) + Supabase PostgreSQL 16 (planned future serving DB — **not yet active**; provisioned at Gate I when corpus is complete). One Drizzle schema; publish step will promote finished data. The schema is Postgres-only by necessity (GiST exclusion / daterange / tsvector / generated columns) — **SQL Server is NOT the staging DB** (it's other-project infra). Stack: Next.js 15 + TS + Drizzle; **tRPC deferred** (RSC + Server Actions over `src/server/`).

---

## Your concrete first steps (apply DDL → first build vertical)

1. **Stand up local PostgreSQL 16 and apply the existing migration.** The DDL is already written (`drizzle/0000_breezy_randall_flagg.sql`, schema in `src/lib/db/schema/`). Install Postgres 16 (native or Docker — NOT SQL Server; the schema is Postgres-only), set `DATABASE_URL` (direct, port 5432) in `.env.local`, run `npm install` then `npm run db:migrate`. Confirm `btree_gist`, both GiST exclusion constraints, the `uuid_generate_v7()` function, and the generated `fts_vector` all apply cleanly. (This is the step cc002 deliberately did NOT do — needs a live DB + Patrick's go on the install.)
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

---

## 2026-06-02 update — current state (READ THIS FIRST)

The 2026-06-01 body above is historical. The "concrete first steps" (stand up Postgres, apply DDL, seed 1872) are **all done.** Here is where the project actually is.

### What is BUILT — the system of record
- **DDL applied** to local PostgreSQL 16 on the 5080 (`postgres`/`postgres`@5432, DB `patolex`; migrations 0000-0004; 7 tables; `btree_gist`, GiST exclusions, `uuid_generate_v7()`, generated `fts_vector` all clean).
- **1850-1875 OCR'd, banked, and ingested as version-B (multi-engine token consensus) — 4262 acts = the system of record.** Verified this session via the `ocr_provenance` / `consensus_method` columns. UTF-8 faithful; zero single-engine committed text. `provision_version` = 0 **by design** (materialization is a deferred sweep, not a failure).
- **In flight:** 1877-1910 OCRing now. Modern-format parser fixes (`parse_born_digital.py`) are **in flight and NOT yet ingested.**

### The THREE-TIER corpus model (key correction — was previously thought all-OCR)
The Chief Clerk backbone is **653 PDFs, 1850-2008** (258 body vols, 413,987 body pages; counts in `PatoLex-scratch\corpus_page_counts.csv`). It is NOT uniformly image-only:
- **(a) 1850 – ~1996** = image-only scans → **OCR** (the consensus pipeline).
- **(b) ~1997 – 2008** = born-digital Chief Clerk PDFs with a clean text layer → **direct text extract, NO OCR** (`pipeline/5080/parse_born_digital.py`; verified on 2001 & 2008; 1995 still image-only; **crossover ~1997, exact volume TBD**).
- **(c) 1989/1994 – present** = **leginfo PUBINFO** bulk data (born-digital CAML XML + `.dat`) → bulk import + **reconstruct point-in-time backward** from chaptered bill XML, validated against the current snapshot (POC floor ≈ Jan 1, 1994). Authoritative doc: `DATA_SOURCES.md`.

**Consequence: the OCR campaign is bounded on the modern end at ~1993-94, NOT 2008.** Do not OCR the born-digital tail. Full model: `DATA_SOURCES_HISTORICAL.md` §1d.

### Canonical vs. lossy ingest (do not run the wrong one)
- **`pipeline/ingest_clean.py` = CANONICAL / system of record** — version-B consensus, sha256-keyed `source_document`, scoped purge-then-insert, atomic per volume, dry-run by default. Commit with `--commit` AND `PATOLEX_ALLOW_COMMIT=1` AND `PATOLEX_PG_DSN`.
- **`pipeline/5080/ingest_from_ocr.py` = SUPERSEDED / LOSSY** — single-engine; its DB rows are replaced by `ingest_clean.py`. **Hazard: no `__main__` guard → importing it triggers a DB ingest.** `PatoLex_Ingest_5080` stays DISABLED.

### Operational entry point (NEW — fills the missing runbook)
- **`docs/60_OPERATIONS/BUILD_RUNBOOK.md`** — the deterministic build/orchestration doc: OCR queue + two GPU nodes (5090 strong / 5080 also valid, shared `production_queue_state.json`), scheduled tasks, **the 0800 backoff tasks that MUST stay disabled for open-ended runs**, the canonical ingest chain, format eras, and the resume procedure past 1875.

### Real next steps (supersede the 2026-06-01 "first steps")
1. Continue the OCR campaign past 1875 → ~1993 (stop at the born-digital crossover); ingest each finished volume via `ingest_clean.py --commit`.
2. Switch ~1997-2008 to `parse_born_digital.py` (tier b); the modern era to the leginfo XML channel (tier c).
3. Deferred: materialize `provision_version` when the serving layer is built; re-verify `lineage_edge` purge at the 1872 recodification; Phase C (VLM-flagging on persisted low-confidence tokens + crowd correction).
4. Still owed: ~10-20 page **human-gold OCR audit** to certify the accuracy number (OpusGold is a frontier-model reference, not certified truth).

### Doc map for a cold start (2026-06-02)
`BUILD_RUNBOOK.md` (how to run it) · `DATA_SOURCES_HISTORICAL.md` §1d (three-tier corpus) · `DATA_SOURCES.md` (modern leginfo channel) · `MODERN_STATUTE_FORMAT_2026-06-02.md` (modern parser) · `pipeline/README.md` (canonical-vs-lossy ingest) · `COLD_START_DOC_AUDIT_2026-06-02.md` (the gap audit this update closes).
