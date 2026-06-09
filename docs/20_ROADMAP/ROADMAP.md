# Roadmap

## Current Status

**Gate:** Between E and F — **the historical OCR campaign is COMPLETE; the modern layer (Gate F) is largely built; the 1876–1993 ingest gap is the primary remaining build task.**

**As of 2026-06-09 (cc006 verification):**
- **Schema is LIVE on local PostgreSQL 16** (5080 box, DB `patolex`): migrations `0000`–`0004`, **7 tables**, with `btree_gist`, GiST exclusion constraints, `uuid_generate_v7()`, and the generated `fts_vector` all applied cleanly.
- **Historical OCR campaign: COMPLETE and verified.** All volumes spanning ~1850 through ~2000 have been OCR'd via 3-engine consensus (Tesseract + docTR + Surya; qwen2.5vl/PaddleOCR/GOT run as disagreement-flagging vectors only, never committed). The "01:28 5090 crash" seen in late-campaign commit messages was a monitor false alarm — the campaign ran to completion.
- **Consensus = 3 engines: Tesseract + docTR + Surya** (`consensus.py`, `N_MAX_ENGINES=3`). qwen2.5vl / GOT run as disagreement-flagging vectors only and are NEVER committed as text. *(PaddleOCR is NOT a consensus voter.)*
- **Live DB inventory (local PostgreSQL 16, DB `patolex`, as of 2026-06-09):** ~35,332 enactments spanning 1850–2024; ~84,118 provisions; ~151,763 change_events. `lineage_edge` and `provision_version` intentionally 0 (deferred materialization).
- **Two coexisting DB layers:**
  - **(a) OCR-linked acts** (`source_document_id` set): 1850–1875 dense (~3,946 acts). The 1876–1993 span is **nearly empty (~360 acts)** — OCR is done for these volumes but ingest is blocked (see blockers below).
  - **(b) Gate F modern layer:** ~22,780 acts, **1991–2024**, reconstructed from official **leginfo CAML bill-XML** (139,211 section change_events, `trust_level='official_xml'`, confidence 1.0), via `pipeline/gate_f/`. **Gate F is largely built — the old "not started" framing is obsolete.**
- **Gate F remaining gaps:** sessions 1993-94 / 2001-02 / 2003-04 absent; layer ends 2023-24. PUBINFO archives for those + 2025 (current `LAW_SECTION_TBL`) + 1989 acquired 2026-06-08; parse + ingest in progress to close gaps and reach gap-free 1989→2026.
- **THE REAL REMAINING GAP — 1876–1993 historical ingest.** OCR is complete but ingest is blocked on 4 Hans-flagged items: (1) `source_document` registration for 1877–1990 volumes, (2) `LEGISLATURE_MAP` extension past 1875-76, (3) dedup-variant resolution 1927-1965, (4) logical-key diff for re-ingest validation. Date-parser fix for the chaptered_date parser bug (51 acts have wrong date, correct text) is also required first.
- **Three-tier corpus model** (see `DATA_SOURCES_HISTORICAL.md` §1d): (a) image-only ≤ ~1996 → OCR consensus, (b) born-digital Chief Clerk ~1997–2008 → direct text extract (no OCR), (c) leginfo PUBINFO XML 1989/1994–present → reconstruct backward. **The OCR campaign is bounded on the modern end at ~1993–94, not 2008.**
- **OCR↔Gate-F overlap (~1995–2008):** same chapters appear in both layers with different citation keys; no collision. Gate F (official XML) is authoritative; the OCR for those years is the seam-validation oracle. Arbitration rule for the served corpus still to define.
- **`provision_version = 0` and `lineage_edge = 0` — both BY DESIGN.** `provision_version` is a materialized read model (deferred build/publish-time sweep, not yet run); `lineage_edge` is empty because the 1872 recodification edges are not yet materialized.
- **OCR accuracy:** ~1.5% body-CER was measured on clean sample pages, but this is **NOT yet human-gold certified** — a ~10–20 page human-gold audit is still owed before the accuracy number is treated as certified.

**Baseline principle (unchanged): 1850 = a blank page — the only baseline.** Session laws are applied in order (1850 → 1871 …); the **1872 codification is modeled as a recodification EVENT in the chain (via `lineage_edge`), NOT an enact-from-nothing baseline.** **Session laws (Chief Clerk series, clean CA-gov) are the PRIMARY source**; published codes (Burch/Deering/State-Printer) are SECONDARY — verification only, except the unavoidable 1872-codification enacted text not reproduced in the session-statutes volume. The earlier 726-section Penal slice was a throwaway benchmark and is not part of this corpus.

## Goal & Philosophy

PatoLex is a public website where any attorney or researcher can look up any California statute and see the exact language in effect at any point in time, **from statehood (1849) to present**. This is the full deliverable, not a stretch goal.

**Built historical-first, risk-first.** We tackle the hardest, least-certain piece — reconstructing statutes from 1849 off scanned session laws — *first*, to prove the whole thing is achievable to a trustworthy standard before investing in the easy modern era. Quality over speed. **No public launch until the full 1849-present corpus is present and validated** (revenue and demos are explicitly not near-term drivers). Secondary goal: a proof-of-concept for agentic coding at scale.

## Reconstruction Architecture (from Gate B)

Point-in-time text is **reconstructed**, never just downloaded. Two segments meet at a **~1993 seam**:

- **Historical (1849-1993) — built FIRST.** **Blank-slate principle:** CA had no law before 1850, so the complete clean **session-law chain (1849-2025) IS the law from a blank page** — codifications (1872 etc.) are themselves acts within it. Reconstruct **forward by parsing session-law amendment directives (Method A)** from **clean non-Google scans** (Google scans fail OCR); annotated editions = validation only (exist for 14/29 codes). Event-sourced (one act = one change-event) so it can emit both the temporal DB and a **Git history of the law** (see memory: law-as-git-repo). See `docs/30_SYSTEM_DESIGN/DATA_SOURCES_HISTORICAL.md`.
- **Modern (1993-present) — built SECOND ("light speed").** Backward from the current `LAW_SECTION_TBL` snapshot, applying chaptered bill XML. See `docs/30_SYSTEM_DESIGN/DATA_SOURCES.md`.
- **The seam is a correctness oracle:** the two directions must agree where they overlap, and every historical amendment must match the modern `history` strings.

## Two-Database Architecture

| Role | Where | Purpose |
|------|-------|---------|
| Build / staging | Local PostgreSQL 16 | Pipeline ETL, OCR structuring, amendment application, reconstruction, validation, ad-hoc + Claude Code analysis. Disposable, fast. |
| Serving | Supabase PostgreSQL 16 | Read-optimized published corpus the web app reads (only once data is complete + validated). |

One Drizzle schema applied to both; a publish step promotes finished data local -> Supabase.

---

## Gates

| Gate | Name | Status | Description |
|------|------|--------|-------------|
| A | Repository Structure | **Done (cc001)** | Docs hierarchy, CLAUDE.md, .claude/ tooling. |
| B | Data Source Reconnaissance | **Done (cc002)** | Modern: bulk leginfo data confirmed, current-only, reconstruct backward from snapshot. Historical: acquisition solved (catalog of 4,034 vols w/ HathiTrust+Google links + Chief Clerk archive 1850-2008 + IA 1872 Codes w/ OCR — all verified by download). OCR mostly already exists -> harvest + correct, not an OCR farm. Three-era model; risk = section-number integrity + recodification events. See both DATA_SOURCES docs. |
| C | Historical Slice Proof — Penal Code 1872-1900 (RISK GATE) | **Done (cc002)** | **Data-first spike, no formal schema yet.** Baseline = original 1872 Penal Code (downloaded). Method: diff successive **annotated PC editions** (Desty 1881/1883/1885/1889, Deering 1903 — already OCR'd on Internet Archive) to derive per-section version timelines, using their inline `Stats. YYYY` history notes for operative dates. Scratch store = **JSON** (SQL Server available locally/Tailscale if querying helps). Steps: (1) pull editions, (2) extract sections + history notes, (3) reconstruct timelines, (4) **validate** vs *Index to the Laws 1850-1893*. **RESULT (cc002):** method validated at 85% (timeline) and OCR proven legal-grade at ~1.5% body-CER on **clean non-Google scans** (Tesseract 5 + qwen2.5vl + 99% disagreement flag-recall) — the Google Books scans were the sole blocker. Core risks retired. **Key learning for scale-out: source clean non-Google scans (IA/HathiTrust JP2), never Google Books.** See `GATE_C_SLICE_PROOF.md`. |
| D | Schema (event-sourced, domain-neutral, era-aware) | **Done — LIVE (cc002)** — Drizzle, **7 tables**, adversarially reviewed; `src/lib/db/` + `drizzle/`. **Applied to live local PostgreSQL 16** (migrations 0000-0004; `btree_gist`, GiST exclusions, `uuid_generate_v7()`, generated `fts_vector` all clean) and **holding 4262 ingested acts** (1850-1875). See `docs/40_SCHEMA/SCHEMA_DESIGN.md` | **Decided:** append-only **event log** is the system of record (point-in-time text, current text, and the Git history are all *derived*); **domain-neutral** (enactment→provision keyed by jurisdiction+unit_type, so CA regs + a federal v2 drop in); §9605/recodification reconciliation lives in the schema, never in Git; **USLM/Akoma-Ntoso-aware** field names. Core entities: `source_document`, `enactment` (the "commit", w/ `chapter_number` + the three dates `chaptered_date`/`effective_date`/`operative_date` — **there is no `enacted_date` column**), `provision` (synthetic surface-independent identity = the lineage anchor; `bigint` PK + external `uuid` `public_id`), `designation_history`, `change_event` (append-only, whole-section `new_text`, §9605 resolution metadata, plus the as-built `confident`/`confidence`/`ocr_provenance` capture columns). **Recodification is modeled via the `lineage_edge` table (typed directed edges) — there is NO first-class `recodification` table.** Read models: materialized `provision_version` (daterange + GiST + tsvector) for Supabase serving — **0 rows by design** until the materialization sweep runs; Git emission from the log. `lineage_edge` is likewise **0 by design** until the 1872 recodification edges are materialized. **Local PostgreSQL 16 (staging) + Supabase PostgreSQL 16 (serving)** — Postgres both sides (the GiST/daterange/tsvector model is Postgres-only; SQL Server can't express it). |
| E | Historical Scale-Out | **OCR COMPLETE (cc006, 2026-06-09); ingest 1876–1993 BLOCKED on 4 items** — see Current Status. 1850–1875 dense (~3,946 acts version-B consensus); 1876–1993 OCR done, ~360 acts ingested. Blockers: source_document registration 1877-1990, LEGISLATURE_MAP extension, dedup-variant 1927-1965, logical-key diff + chaptered_date parser fix. | **Build order (corrected cc002):** **THE ONLY BASELINE IS 1850 = BLANK PAGE.** Build FORWARD from nothing — session laws applied in order from 1850. The earlier Penal Code "1872 spike" used the 1872 codification *slice* only as a convenient test of the parsing mechanism — that was **NOT a baseline** and is a throwaway. The real corpus lays the **1850-1871 session laws first** (the true "from nothing" origin), then applies the **1872 codification as a RECODIFICATION event in the chain, NOT a baseline** — else every codified section's pre-1872 history is truncated and a point-in-time query for e.g. 1860 wrongly shows "no law." **Session laws are PRIMARY; published codes (Burch/Deering) are verification-only.** The 1872 codification = `lineage_edge` (recodify) from each pre-code act → its 1872 section + `repeal` of superseded acts + `enact` only for genuinely-new sections. Hard dependency: the 1872 **disposition mapping** (1850-71 act → 1872 section) from Code Commissioners' notes + *Index to the Laws 1850-1893*. **Source CLEAN non-Google scans (IA JP2 / Chief Clerk / HathiTrust 300dpi+), never Google Books.** OCR Tesseract + docTR + Surya token-majority consensus. |
| F | Modern Layer | **Largely BUILT (cc006) — NOT "not started"** — 1991–2024 reconstructed from official leginfo CAML bill-XML into the live DB (22,780 enactments / 139,211 change_events, `trust_level='official_xml'`), via `pipeline/gate_f/parse_bill_versions.py` → `ingest_gate_f.py`. **Gaps:** sessions 1993-94 / 2001-02 / 2003-04 absent, layer ends 2023-24. PUBINFO archives for those + 2025 (current `LAW_SECTION_TBL`) + 1989 acquired 2026-06-08; parse+ingest in progress to make it gap-free 1989→2026. | Reconstruct 1993-present backward from the current snapshot via chaptered bill XML. **First spike the #1 modern risk:** bill XML format + whether bill->section linkage is explicit or must be parsed. Join to the historical spine at the seam. |
| G | Full-Timeline Validation | Not started | Validate 1849-present end to end: seam agreement, history-string cross-checks, structural invariants, statistical sampling with per-era error-rate confidence intervals. Establish the defensible accuracy standard for an attorney-facing product. |
| H | Web App + Point-in-Time UI + Search | Not started | Next.js 15 + Drizzle over the service layer. Code browser, statute-as-of-date rendering, PostgreSQL FTS. Source-page image alongside OCR text; per-token confidence display; correction UI (crowd wiki tier + professional tier). "Verify against official sources / not legal advice" disclaimer. See `docs/30_SYSTEM_DESIGN/CROWDSOURCE_CORRECTION.md`. |
| I | Public Launch | Not started | Full corpus (1849-present) must be present. **Reframed launch bar (2026-06-01):** launch does NOT require every token to be expert-verified. Production-acceptable = processed text + source-page image side-by-side + correction path. Accuracy converges via crowd + expert correction post-launch. Completeness requirement is unchanged; the pre-launch validation requirement is now "OCR-confidence + source-image display standard," not "expert-verified throughout." See `docs/30_SYSTEM_DESIGN/CROWDSOURCE_CORRECTION.md`. Vercel + Supabase (Pro tier). Split dev/prod Supabase. |

Web stack note: data access is **RSC + Server Actions over a transport-agnostic service layer** (`src/server/`); **tRPC deferred**; MCP server is the likely first external interface, public API later. See ARCHITECTURE.md.

---

## Crowdsource Correction + Launch-Bar Reframe (2026-06-01)

**Full design:** `docs/30_SYSTEM_DESIGN/CROWDSOURCE_CORRECTION.md`

Summary: PatoLex launches with OCR text + source-page images + a correction path. Accuracy converges over time via an open-source wiki-style crowd-correction layer. Two tiers:

- **Public (wiki) tier** — anyone reads, searches, and corrects. Random-teleport drops reviewers onto low-confidence regions (driven by the pipeline's per-token disagreement queue). Corrections flow through a trust ladder (`ocr_consensus` → `crowd_proposed` → `crowd_confirmed` → `expert_verified`). Gamified: attribution, leaderboard, reputation, law school community appeal.
- **Professional / attorney tier** — filters to `expert_verified` + `crowd_confirmed` subsets; source image + provenance always visible; attorney-appropriate confidence labeling.

**Relationship to VERIFICATION_TOOL.md:** the WinUI3 captcha tool (in-house/outsourced reviewers) and the public correction wiki are sibling consumers of the same pipeline disagreement queue. Both write `change_event`s at the appropriate trust level. The WinUI3 tool handles bulk backlog at scale; the wiki handles the long tail and ongoing corrections.

**Citation stability:** a correction creates a new `provision_version` (OCR correction path); it never silently rewrites a version an attorney may have already cited. Full audit trail in the event log and Git commit notes.

---

## Open Questions (carried into Gate C/D)

- 1937-1953 recodification acts: do they contain complete old->new disposition tables, or rebuild from annotated codes?
- Pre-1873 repeal scope (what the 1872 codes repealed vs. left standing).
- Era-specific effective-date rules (1849 vs. 1879 constitution).
- Scope: codes only, or also uncodified session law (appropriations, special acts)?
- [Gate F] Chaptered bill XML format + bill->section linkage.
- Vision-LLM OCR hallucination control + per-volume re-OCR triage thresholds.
- Storage footprint of the full multi-version corpus + tsvector indexes (Supabase tier).

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial version. Gates A-G defined. |
| 2026-05-31 | cc002: Major revision -- split scope, Gate B recon, vertical-slice, two-DB, schema requirements, tRPC deferred. |
| 2026-05-31 | cc002: Gate B done (modern). Reconstruction = amendment-application validated against current snapshot. |
| 2026-05-31 | cc002: Data-first reorder (Patrick) -- Penal Code 1872-1900 slice proof becomes Gate C (annotated-edition diffing, JSON scratch); schema follows as Gate D. Acquisition done (1872 baseline + 653-vol manifest). |
| 2026-06-01 | cc002: OCR risk RETIRED (clean scans -> ~1.5% body-CER, 99% flag-recall; Google scans were the blocker). Full-corpus inventory: completable from clean sources, blank-slate principle confirmed, production method = forward-from-session-laws (Method A). Open risk: session-law amendment parsing at scale. Idea: emit law as a Git repo. |
| 2026-06-01 | cc002: Method A re-spike QUALIFIED-GO (engine validated). Law-as-git boundary fixed (git = emitted artifact, not the merge engine). Adjacent-domain feasibility documented (federal easier; CA regs via baseline-plus-forward; design USLM-aware). **Gate D schema designed** (event-sourced, domain-neutral, era-aware). Build order decided: start at 1872 baseline, pre-code 1850-71 as a later pass. |
| 2026-06-01 | cc002: **Launch-bar reframed** (Patrick). Completeness requirement unchanged (full 1849-present before launch); validation requirement now "OCR confidence + source image + correction path," not "expert-verified throughout." Crowd correction wiki + two-tier model designed. See `docs/30_SYSTEM_DESIGN/CROWDSOURCE_CORRECTION.md`. |
| 2026-05-31 | cc002: **Reversed to historical-first / risk-first** (Patrick's call). Full 1849-present is the deliverable; no launch until complete + validated. Gate B-Historical done (acquisition solved via Internet Archive, three-era model, two-pass OCR). Gates re-sequenced: schema -> historical one-code slice proof (risk gate) -> historical scale-out -> modern layer -> full validation -> web -> launch. |
| 2026-06-02 | cc002 (doc rewrite): Reconciled Current Status + gate states to TRUTH_BASELINE. Removed the false "no corpus ingested yet / schema not applied to a live DB" claims. State: **schema LIVE (7 tables, migrations 0000-0004), 1850-1875 = 4262 version-B acts ingested, OCR campaign in flight, three data tiers (OCR ceiling ~1993-94).** Advanced Gate C → Done, Gate D → Done/LIVE, Gate E → In progress. Corrected consensus to **3 engines (Tesseract+docTR+Surya), PaddleOCR not a voter**; noted `provision_version`/`lineage_edge` = 0 by design; corrected the recodification mechanism to `lineage_edge` (no first-class `recodification` table) and the date columns to chaptered/effective/operative (no `enacted_date`). |
| 2026-06-09 | cc006: Major status update. **Historical OCR campaign COMPLETE and verified** (~1850–2000, "01:28 crash" was a monitor false alarm). **Gate F largely built** — 22,780 acts 1991–2024 from leginfo CAML bill-XML already in DB ("Gate F not started" framing is obsolete). **Live DB: 35,332 enactments / 84,118 provisions / 151,763 change_events spanning 1850–2024.** Real remaining gap = **1876–1993 ingest**, blocked on 4 Hans-flagged items + chaptered_date parser fix. Gate F remaining gaps (1993-94, 2001-02, 2003-04, 2025) in progress. Updated Current Status section and Gate E/F table rows accordingly. |
