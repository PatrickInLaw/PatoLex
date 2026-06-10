# Gate D — Schema Design (Event-Sourced, Domain-Neutral, Temporal)

**Status:** Design decision (cc002, 2026-06-01); **DDL implemented and LIVE on local PostgreSQL 16 (migrations 0000-0004, 7 tables, 4262 acts ingested for 1850-1875) — reconciled to as-built 2026-06-02.** The container the reconstructed corpus is written into.
**Depends on:** Method A (validated, QUALIFIED-GO). **Feeds:** Gate E scale-out, the web app (Gate H), and the Git emitter (`LAW_AS_GIT.md`).
**Related:** `ROADMAP.md`, `DATA_SOURCES_HISTORICAL.md`, `LAW_AS_GIT.md`, `ADJACENT_DOMAINS_FEASIBILITY.md`.

---

## The four load-bearing decisions

1. **Event-sourced, with materialized read models (CQRS).** The system of record is an **append-only log of change-events** (one legislative/regulatory action's effect on one provision) — the *write side*. We never store "the text of §187" as a mutable row; we store the sequence of acts that produced it. But **queries never replay the log**: we materialize read-optimized projections (the *read side*). Both consumers are projections of the same log — the **web UI** reads a materialized `provision_version` table; the **Git repo** *is itself* a projection (the commit history rendered from the log, with `git checkout @{date}` as its precomputed point-in-time index). This is CQRS: one write model → two read models, no history-replay at query time. (See "Read models, CQRS & query performance" below — this is the resolution of the "must we recompute on every query?" question: no.) **A property of CA drafting makes derivation nearly free anyway:** amendments restate the *entire* section, so each event carries the full new text — deriving a version is *selection* of the latest event ≤ a date, not *replay* of accumulated diffs.
2. **Domain-neutral.** Nothing in the core model says "statute." An *enactment* (chaptered act / public law / OAL rulemaking action) changes a *provision* (code section / uncodified act section / CCR section), keyed by `jurisdiction` + `unit_type`. CA statutes are the first corpus; CA regulations (baseline-plus-forward) and a possible federal v2 are **drop-in corpora on the same machinery**, not rebuilds. (See `ADJACENT_DOMAINS_FEASIBILITY.md`.)
3. **Reconciliation lives here, never in Git.** §9605 (chapter-order priority, whole-section replacement), double-jointing, and recodification lineage are computed in this schema. The Git repo is an emitted, read-only projection. (Rationale: `LAW_AS_GIT.md`.)
4. **USLM / Akoma-Ntoso-aware.** Field names and the provision/version/source split track USLM (GPO standard, Akoma-Ntoso-derived) so federal ingest/emit is a mapping, not a redesign. The provision≈*work* / version≈*expression* / source_document≈*manifestation* split mirrors Akoma-Ntoso's FRBR model.

---

## Core entities

### `source_document` — provenance
Every artifact we ingest. `id`, `type` (session_law | bill | annotated_edition | scan | regulatory_action | official_xml), `citation`, `jurisdiction`, `source_channel` (IA id / Chief Clerk URL / leginfo / OLRC), `scan_quality`, `ocr_engine`, `ocr_cer_estimate`, `trust_level`, `retrieved_at`. Clean-channel flag (per the licensing analysis — IA-non-goog / CA-gov only for served text).

**As built (live migrations 0000-0004):** the table also carries `content_sha256` (content identity — the ingest key `ingest_clean.py` resolves a volume by), `ocr_stats` (jsonb), plus corpus-positioning columns `corpus`, `edition_year`, `claimed_year`, `coverage_start_year`, `coverage_end_year`, `section_range`, `page_count`, `media_format`, `file_name`, `source_uri`, `verification_note`, `clean_channel`.

### `enactment` — the "commit"
One act with legal force. `id`, `source_document_id`, `citation` (e.g. `Stats. 1883 ch. 38`), `jurisdiction`, `session`/`legislature`, **`chapter_number`** (the §9605 ordering key), **three dates** — `chaptered_date`, `effective_date`, `operative_date` (all nullable, era-aware), `title`, `bill_number`, `kind` (statute | recodification | regulatory_action). Maps 1:1 to a Git commit.

> **As-built note:** the three date columns are `chaptered_date` / `effective_date` / `operative_date`. **There is NO `enacted_date` column** — any older prose referencing one is wrong; use the chaptered/effective/operative trio (point-in-time queries key on `operative_date`).

### `provision` — the addressable unit (domain-neutral, the lineage anchor)
The thing with identity across time. **Synthetic, surface-independent identity** that survives renumbering/recodification — this is the single most important concept in the schema (it's what makes "this is the same section even though it was renumbered in 1943" expressible).

**Key choice (decided cc002):** internal **`bigint` identity PK** (`id`) for compact joins/indexes across the millions of `change_event` / `provision_version` rows, **plus a stable external `uuid` v7** (`public_id`) as the durable forever-handle used in permalinks, cross-corpus references, and Git metadata. (A `uuid` PK would bloat and fragment every index; UUIDv7 is time-ordered for index locality when minted during ingest.) The id is **opaque** — never encode the section number into it (the number changes; identity doesn't). Other fields: `jurisdiction`, `unit_type` (code_section | act_section | reg_section), `current_designation`, `status` (active | repealed | reserved | superseded).

**Git note:** the `uuid` does **not** appear in Git file paths (that would wreck the human-browsable repo). Paths use the *current designation* (`penal-code/0187.txt`); the `uuid` rides in a per-file metadata header / `lineage.json` manifest so identity and lineage survive renames.

### `designation_history` — surface labels over time
`provision_id` → (`code`, `section_number`, `label`, `valid_range`). Because the *displayed* citation changes (renumbering) while the `provision_id` does not. Handles the §634-game-law-vs-plumbing collision the Method-A spike surfaced.

### `change_event` — the heart (append-only)
One enactment's effect on one provision. `id`, `enactment_id`, `provision_id`, **`action`** (enact | amend | repeal | add | renumber | recodify | reserve), **`new_text`** (full replacement — CA restates the *entire* section, so each event carries the whole new text, not a patch), `operative_date`, **in-act order / sequence** (global order = operative_date, then `chapter_number`, then in-act order — the tiebreak chain that resolves §9605), **resolution metadata** (`supersedes_id` / `superseded_by_id` / `double_jointed_with_id` / `chaptered_out` flag), `diff_from_prior` (jsonb; see below), `source_document_id` + `page_ref` (provenance), `trust_level`.

> **As-built capture-all-signals columns (live):** `change_event` also carries **`confident`** (bool), **`confidence`** (real), and **`ocr_provenance`** (jsonb) — the per-act OCR consensus signals. `ocr_provenance->>'consensus_method'` records the **3-engine** vote (`token_majority_3` / `token_majority_2` / `single`) from `pipeline/consensus.py` (`N_MAX_ENGINES=3`: Tesseract + docTR + Surya). PaddleOCR is **not** a consensus voter. As of the 1850-1875 build: 4057 acts `token_majority_3`, 205 `token_majority_2`, zero single-engine committed; `confident` = t on 3424 / f on 838.

### Diffs & redline (derived — canonical text is always the whole section)
We **capture word-level diffs**, but always *derived from* two stored whole-section texts — never the reverse (preserving "selection, not replay"). Two surfaces:
- **DB/UI:** `change_event.diff_from_prior` stores a precomputed **token-level structured diff** (`[{op: equal|insert|delete, tokens}]`, punctuation-aware) so the UI renders a legislative redline (struck deletions / underlined insertions) without running a diff engine per page view. Example target: a 250-word section changing only "shall"→"may" yields a diff of one delete + one insert, rest `equal`.
- **Git:** word-level delta is **intrinsic and free** — because every commit writes the whole new section file, `git diff --word-diff` / `--color-words` shows exactly the changed words. (A strong argument *for* the Git artifact.)
- **Distinguish text-delta from label-delta:** a pure `renumber` has an *empty* text diff but a designation change — it must not render as a substantive amendment. The first (`enact`) version has no prior → "all-inserted." Across a `split`, diff a child against the relevant span of its predecessor (best-effort) or label "originated by split from §X" rather than force a misleading whole-section redline.

### `lineage_edge` — recodification as a typed directed graph (1872, 1943, and the constant drizzle of small renumbers)
What Git's rename detection *cannot* infer, and the genuinely hard modeling problem in the schema. Recodification ranges from **rare-huge** (1872 codification act_sections→code_sections; 1943 Government Code / Political Code dissolution) to **medium** (1992 Family Code lifted much of the Civil Code) to **frequent-small** (single-section renumbers; decimal spinoffs like §1170 → §1170.1). **One mechanism handles all of it:** provisions are nodes; recodification creates **typed directed edges** between predecessor and successor provisions, each edge stamped with the `enactment` that caused it. A 1943 mega-event is just thousands of edges from one enactment; a §1170 spinoff is two edges from another — same table, same query path.

`lineage_edge`: `id`, `enactment_id`, `predecessor_provision_id`, `successor_provision_id`, `edge_type`, `text_disposition`, `note`.

| `edge_type` | Cardinality | provision_id (identity) behavior |
|-------------|-------------|----------------------------------|
| `renumber` | 1→1 | **Keep the same provision_id** — add a `designation_history` row only. (Most frequent-small case; near-zero ceremony.) |
| `transfer` | 1→1 cross-code | Keep the same provision_id (e.g. Civil → Family Code 1992). |
| `split` | 1→N | **Hybrid rule:** if a clear *primary successor* (retains number + bulk of text) exists, it **keeps** the provision_id and the spinoffs get new ids with `split` edges; if the split is genuinely even, mint new ids for all children and mark the predecessor `superseded`. |
| `merge` | N→1 | New id (or the dominant predecessor's), with `merge` edges from each predecessor. Rare. |
| `repeal_reenact` | 1→1 | New id + a flagged `continues` edge (the legal chain technically broke; the flag lets the UI show continuity honestly). |
| `repeal_without_successor` | 1→0 | Predecessor terminated; no successor. |

**The load-bearing principle: identity continuity is an explicit, recorded decision per edge — never inferred.** 1:1 renumber/transfer keep identity; split/merge make a recorded judgment about which (if any) successor inherits it.

**Query — "full history of this provision":** a recursive CTE walks the edge graph to collect all ancestor/descendant ids, then unions their versions. This recursive traversal is *the* reason the synthetic stable id exists. Emits as the Git `mv`+rewrite commits.

**What makes it tractable:** (1) most small ones are *parseable, not hand-built* — CA codes carry "former §X / renumbered from / added by / repealed and reenacted by" history notes that map almost directly to edges; the 1872/1943 acts have (pending confirmation — open roadmap question) disposition tables. So human judgment concentrates on splits/merges and the big acts. (2) **Validation invariants** (Gate G): every `superseded` predecessor must have ≥1 successor edge or an explicit `repeal_without_successor`; text must not vanish without a disposition; and the **1991 modern seam is the oracle** — terminal lineage nodes must reconcile with the current leginfo section numbers. (3) The irreducible hard part — deciding identity inheritance and "continues" semantics during the big events — stays a spot-audit task, but the model makes that judgment *explicit (a typed edge)* rather than buried.

---

## Read models, CQRS & query performance (not the system of record)

The event log is the write side; **end-user queries never replay it.** Two materialized read models, both regenerable from the log at any time.

> **As-built state (2026-06-02):** `provision_version` currently has **0 rows BY DESIGN** — it is a materialized projection built at build/publish time, and that sweep has not yet been run (the system of record is the `change_event` log, which holds the 1850-1875 corpus). Likewise `lineage_edge` is **0 by design** — the 1872 recodification edges are not yet materialized. Empty ≠ broken for either table.

- **`provision_version` (materialized) — the web UI's read side.** For each provision, the **fully resolved text valid over a `[valid_from, valid_to)` `daterange`**, built once (at build/publish time) by folding `change_event`s in `sequence` order and applying §9605. Served with a **GiST exclusion constraint** (no overlapping ranges per provision) + **tsvector** FTS. A point-in-time query is then a single indexed lookup, **zero replay, any date:** `SELECT text FROM provision_version WHERE provision_id = ? AND as_of <@ valid_range`.
- **Git history — the second read side.** Walk `enactment`s in `(operative_date, chapter_number)` order → one commit each, touching the files for its `change_event`s; `lineage_edge`s → file moves; trailers carry `chaptered_date`/`effective_date`/`chapter_number`/`bill`/`trust_level`/chapter-out notes. `git checkout @{date}` is Git's own precomputed point-in-time index.

**Why full version-materialization, not interval snapshots** (the decision behind "do we recompute on every query?" — no): statutes are *sparse and discrete* per section (a given section changes a handful of times in 150 years), so the number of version rows per provision is tiny and total `provision_version` rows ≈ total change-events (order a few million across all CA codes + all history — to be firmed during the build). That fits comfortably in Postgres and gives **O(log n) lookup for any arbitrary date.** Interval snapshots (store full corpus state every year, replay forward from the nearest) are the right tool only when state is *large and continuously churning* (e.g. a bank balance); for law they'd waste space re-storing a mostly-unchanged corpus *and* still require partial replay. Full materialization dominates: less storage, no replay, exact dates.

**Feature 1 ("entire statutory scheme as of date X"):** for **Git**, `checkout @{date}` does this natively; for the **DB**, it's a date-filtered scan across provisions (~hundreds of thousands of well-indexed rows — fine). **No separate snapshot mechanism is needed up front.** If scale-out profiling later reveals a hot path (e.g. repeatedly rendering a whole code as-of-date), add a targeted "code-as-of" materialized cache *then* — an optimization, not a foundational decision.

---

## Era-awareness (CA statutes)

- **Pre-1872 (blank-slate start):** `unit_type = act_section`; provisions addressed by act + section. There is no code numbering yet — it is *created* by the 1872 codification, modeled as a set of `lineage_edge`s mapping act_sections → code_sections. (The live build runs **forward from 1850** — 1850-1875 is already ingested — with the 1872 codification modeled as a recodification *event* in the chain, not an enact-from-nothing baseline; see ROADMAP sequencing note.)
- **1872–1993:** code_sections, forward via Method A `change_event`s.
- **Operative vs. effective vs. chaptered:** store all three; **point-in-time queries key on `operative_date`** (Gov. Code §9600 modern 90-day default; era-specific rules for the 1849 vs. 1879 constitutions). Effective ≠ operative is a correctness trap we model explicitly.
- **`trust_level`** per event/version: `official_xml` > `human_verified` > `derived` > `ocr_uncertain`. Drives the disagreement-flagging + spot-audit QA model (no line-by-line review).

## How other corpora drop in (future, not now)

- **CA regulations (baseline-plus-forward):** the 2026 baseline = a bulk set of `enact` events dated at the baseline; each OAL action thereafter = an `enactment` (kind=regulatory_action) with `amend`/`add`/`repeal` `change_event`s. Same schema, `unit_type=reg_section`. (See `ADJACENT_DOMAINS_FEASIBILITY.md` §CA-Reg.)
- **Federal statutes:** public law = `enactment`; the OLRC Classification Tables *populate* `change_event`s instead of our parser. `unit_type=code_section`, plus a positive/non-positive-title flag governing whether Code text or Statutes-at-Large controls.

---

## Staging vs. serving

The full event model lives in **local PostgreSQL 16** (`localhost:5432/patolex` on the 5080 — the active corpus DB as of 2026-06-09). **Supabase** (also PostgreSQL 16) is the **planned future public-serving deployment** — it will receive only the **materialized `provision_version` read model** (+ FTS indexes), published once the corpus is complete and validated. It is **not** the current data store. The **Git repo** is emitted from the event log. One Drizzle schema definition; the publish step will promote finished data local → Supabase at Gate I.

**Why Postgres for staging (not SQL Server):** this schema depends on Postgres-only features that are central to correctness — `daterange`, **GiST exclusion constraints** (the no-overlapping-versions guarantee), `tsvector` FTS, and stored generated columns. SQL Server has no equivalents that preserve these guarantees, and the whole point of the two-DB design is **one Drizzle schema, identical dialect** on both sides (staging mirrors serving exactly, no translation). The SQL Server box in the local infra (`local-infra-sql-tailscale`) is other-project infrastructure / optional JSON-or-SQL scratch space — **not** the staging DB for PatoLex. Install a local Postgres 16 (native or Docker) for staging; the C# pipeline connects to it on the direct port 5432 (per CLAUDE.md).

---

## Open items for implementation (cc003 DDL)

- Drizzle DDL for all entities + the GiST exclusion / daterange specifics (Postgres `btree_gist` extension).
- Diff: **decided to store** `diff_from_prior` as a token-level structured diff; choose the token diff algorithm (word + punctuation granularity; legislative redline rendering).
- `provision`: `bigint` identity PK + external `uuid` v7 (`public_id`); confirm UUIDv7 generation in the ingest layer.
- `lineage_edge`: recursive-CTE "full history of a provision" query; the split primary-successor identity-inheritance rule in ETL.
- `sequence` representation that's stable under late-arriving events (re-fold vs. incremental).
- Exact USLM element mapping table (defer until a federal extension is real, but keep names compatible).

---

## Revision History

| Date | Change |
|------|--------|
| 2026-06-01 | cc002: Initial Gate D schema design (event-sourced + CQRS, domain-neutral, lineage-edge recodification, USLM-aware). |
| 2026-06-02 | cc002 (doc rewrite): Reconciled to the as-built live schema. Added the as-built column inventories (`source_document.content_sha256`/`ocr_stats`/corpus-positioning; `change_event.confident`/`confidence`/`ocr_provenance`). Confirmed recodification is the **`lineage_edge`** table (no first-class `recodification` table) and the date columns are **chaptered/effective/operative (no `enacted_date`)**. Noted `provision_version` and `lineage_edge` are **0 by design**. Recorded consensus = **3 engines (Tesseract+docTR+Surya), PaddleOCR not a voter**. Corrected the era-awareness build-order note to the live 1850-forward reality. |
