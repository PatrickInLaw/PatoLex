# Cold-Start Documentation Audit — 2026-06-02

**Auditor:** Claude (read-only audit subagent). **Scope:** Could a brand-new session, with no conversation history and no compaction artifact, resume PatoLex effectively from the durable repo + memory files alone?

**Method:** Read all session logs (cc001, cc002), the cc002→cc003 handoff, the 2026-06-02 MORNING_REPORT, both DATA_SOURCES docs + the source manifests, the acquisition + modern-parser run-logs, CHANGELOG, ROADMAP, ARCHITECTURE, OCR_ACCURACY_VALIDATION, and the full cross-session memory layer (13 memory files).

---

## VERDICT

**Score: 8 / 10 — a cold session could resume effectively, with two costly exceptions.**

The durable trail is unusually strong. The *why* of every major decision (event-sourcing/CQRS, domain-neutral schema, lineage DAG, Method A, blank-slate 1850 baseline, clean-channel licensing, VLM-as-flagging-only) is captured redundantly across SCHEMA_DESIGN, the two DATA_SOURCES docs, the handoff, the cc002 session log, and the memory layer. A new session would correctly understand the goal, the schema, the reconstruction strategy, and the operational rules.

**The two things that would force costly re-discovery:**
1. **No deterministic RUNBOOK / single orchestration entry point** for the multi-day OCR→ingest build — promised ~6 times in the cc002 log, never written as a standalone durable doc. The mechanics survive only as prose scattered through one 307-line session log + `pipeline/README.md` (which describes a boot-resilience model the log later says was *dropped*).
2. **The born-digital PDF boundary (D2)** exists ONLY in a run-log (`modern-parser-run.log`), not in any design doc — and the run-logs are exactly the layer most likely to be skimmed or pruned.

---

## CHECKLIST FINDINGS

### A. Goal, scope, target users, perpetuity-gift intent — **DOCUMENTED**
- ROADMAP §"Goal & Philosophy" + handoff ¶ "Where the project is": public point-in-time CA statute archive, 1849→present, historical-first/risk-first, no launch until full corpus present + validated, POC-for-agentic-coding secondary.
- Perpetuity gift: memory `patolex-perpetuity-gift` + handoff (Git repo = durable handoff vehicle to a law school/nonprofit). Target users (attorneys/researchers) in CLAUDE.md + ROADMAP.
- Minor staleness: ARCHITECTURE.md still leads with the *superseded* "modern POC 1991-present, historical = Phase 2" framing (cc001 text, never reconciled with the historical-first reversal). A cold session reading ARCHITECTURE first could be briefly misled, but ROADMAP/handoff/memory correct it.

### B. Schema decisions + WHY — **DOCUMENTED**
- `docs/40_SCHEMA/SCHEMA_DESIGN.md` (Gate D), reinforced by handoff "What's DECIDED" (items 1-8), memory `gate-d-schema-and-build-order`, and cc002 log Phase 12.
- Event-sourced + CQRS (append-only `change_event` = system of record; `provision_version` and Git are *materialized read models*, no replay at query time); domain-neutral (`enactment`→`provision` keyed by jurisdiction+unit_type); typed lineage DAG (`lineage_edge`) for recodification; synthetic `provision_id` bigint PK + UUIDv7 `public_id`; diffs derived not stored. The rationale for each is explicit (sparse-change → materialization dominates; Git merge would fabricate non-law → reconciliation stays in schema; section renumber/recodify → synthetic identity).
- Live DB state: 7 tables + migrations 0000-0004 applied to local Postgres; capture-all-signals columns (`confident`/`confidence`/`ocr_provenance`/`ocr_stats`) wired.

### C. Pipeline architecture — **DOCUMENTED (mostly), PARTIAL on the canonical ingest path's durability**
- OCR consensus: `OCR_ACCURACY_VALIDATION.md` + memory `ocr-verification-architecture` + MORNING_REPORT. Engines = Surya + docTR + Tesseract + PaddleOCR (4 classical, token consensus = committed text); qwen2.5vl (+GOT) as **flagging vectors only, never committed** (they modernize spelling); dissent filter for VLM false-flags. Numbers: single ~13% → 4-engine consensus ~4% → +VLM flagging ~0.5-1% legal-grade.
- 5090/5080 split: memory `local-infra-sql-tailscale` + OCR_ACCURACY_VALIDATION §Throughput + cc002 Phase 20. 5090 (32GB) = Surya-batched OCR workhorse; 5080 (16GB) = docTR + ingest box + hosts Postgres; Tesseract on CPU.
- Queue/scheduled-task mechanism: `pipeline/README.md` (shared atomic-claim queue, `supervisor_5090.ps1`, `queue_worker.py`, stale-claim recovery, 8AM scale-down). **PARTIAL/STALE:** README documents an ONSTART boot-resilience model that the cc002 log (Phase 20, ~07:00) explicitly says Patrick **dropped** ("Boot-resilience NOT needed"). A cold session would trust the README and re-implement abandoned hardening.
- Canonical vs lossy ingest path: the **distinction is documented** (cc002 log Phase 21 + Hans pass 3 C1; MORNING_REPORT). `ingest_clean.py` (version-B, multi-engine consensus, UTF-8-faithful, scoped-purge-then-insert, canonical key `(source_document_id, in_act_order)`) is the system of record; the older `ingest_from_ocr.py` / single-engine version-A is superseded. **The "why" is captured only in the session log + Hans audit files**, not in any pipeline-design doc — adequate but fragile.

### D. CORPUS STRUCTURE / ACQUISITION DISCOVERY — **DOCUMENTED (this is a strength)**
This is well captured and would NOT be lost:
- `docs/30_SYSTEM_DESIGN/sources/chief_clerk_statutes_manifest.csv` — the **653-PDF Chief Clerk backbone, 1850-2008**, with per-volume `session_year`, `volume_label` (Statutes / Index / Chapters / Vol1.../Constitution / Summary / Treasury / AR / SRE / Rec_Exp), exact `pdf_url`, and verified sizes. Multi-volume vs single-volume is visible directly (e.g. 1850 = Statutes+Index; later years = Vol1_Chapters/Vol2/etc).
- `DATA_SOURCES_HISTORICAL.md` §1, §1b (era→best-clean-source table), §1c (full-corpus inventory + blank-slate reframe) — coverage, biennial-from-1863 note, the "Statutes/Chapters/Amendments to the Codes" naming, page counts.
- `CA_Legislative_Publications_Catalog.csv/.xlsx` — 4,034 vols with HathiTrust+Google links.
- The acquisition run-logs (`acquire-chiefclerk-full`, `acquire-chiefclerk-fix`) record real page counts per volume and the byte-verification lesson (64 truncated files silently passed as "success"). 652/653 valid; the lone gap is `1855_Index.pdf` (genuine server 404).

### D2. FORMAT / ACCESSIBILITY BOUNDARIES — **(i) born-digital boundary = PARTIAL/AT-RISK; (ii) modern structured channel = DOCUMENTED**

**(i) Image-only vs born-digital boundary in the Chief Clerk PDFs — RECOVERED, but lives ONLY in a run-log (at risk of loss).**
The exact finding is in `docs/80_PROJECT_HISTORY/run-logs/modern-parser-run.log`:

> `[2026-06-02 00:10 PT] CHARACTERIZE | 2008_Vol1 (1652pp): chaptered statutes start p522; 209 CHAPTER-header pages; per-chapter = CHAPTER N / An act.../ [Approved by Governor <date>. Filed with Secretary of State <date>.] / do enact. Bill markers ([Senate Bill No]) CONFIRMED ABSENT in chaptered section (2008+2001).`
> `[2026-06-02 00:25 PT] PROTOTYPE | parse_born_digital.py on 2008_Vol1: 227 chapters, ALL confident, continuous 1..227, 0 missing iso_date, titles+dates correct (2008-02-28, 2008-03-14).`

Interpretation: by **2008 (and verified back to 2001), the Chief Clerk volumes are born-digital with a clean text layer** — `parse_born_digital.py` extracts 100% confident chapters with zero OCR. The early volumes (1850s-1870s) are **image-only PDFs, no text layer** (confirmed repeatedly: `acquire-ocr-1850-run.log` "480 pages, image-only (no text layer), PixEdit scan"; `resource-1872-pure-run.log` "image-only, no text layer"). `DATA_SOURCES_HISTORICAL.md` labels the whole Chief Clerk range "Image-only PDF (no text layer)" — which is **now wrong for the modern tail** and contains no born-digital crossover note.
**The precise crossover year between image-only and born-digital is NOT pinned** in any doc; the durable evidence is "image-only at least through the 1870s, born-digital by 2001." A design doc capturing this boundary does **not exist** — it would be re-discovered only by re-characterizing the PDFs.

**(ii) Additional modern structured-data channel beyond born-digital PDFs — DOCUMENTED (well).**
`DATA_SOURCES.md` §1 fully documents the **leginfo PUBINFO bulk data** channel:
> Host `https://downloads.leginfo.legislature.ca.gov/`; biennial `pubinfo_YYYY.zip` archives **1989→2025**; a MySQL `capublic` DB dumped as tab-delimited `.dat` + per-row `.lob` text files + `pubinfo_load.zip` schema DDL; public domain (Gov. Code §10248.5). Key tables `LAW_SECTION_TBL` (current code text as `<caml:Content>` XML), `LAW_TOC_*`, `CODES_TBL` (30 codes + Constitution), `BILL_VERSION_TBL` (**every version of every bill incl. chaptered text as XML**, back to the 1993-94 session).
> CRITICAL FINDING (§2): the LAW tables are a **current-only snapshot** (no historical versions; loader TRUNCATEs+replaces); older archives (1989-2003) contain bill data only, no law tables → modern point-in-time text must be **reconstructed** from chaptered bill XML and validated against the current snapshot (the end-state oracle). POC floor ≈ Jan 1, 1994.
`DATA_SOURCES_HISTORICAL.md` cross-references this as "Modern structured | leginfo PUBINFO | 1989-2025 | Born-digital CAML XML + .dat".
So the modern-era data map is durable: **born-digital CAML XML / `.dat` bulk dumps via the leginfo downloads subdomain, 1989-2025, reconstruct-backward-from-current-snapshot.** The adjacent-domain doc also notes federal/eCFR structured channels (out of near-term scope).

### E. "Acts → Chapters" statute-format evolution + parser implications — **DOCUMENTED**
- `DATA_SOURCES_HISTORICAL.md` §3 (three-era model: pre-code acts 1850-1872 / 1872 codification / 1873+ codified sections) + era-aware effective-date engine (1849 vs 1879 constitution rules).
- Parser-era specifics are captured in MORNING_REPORT + cc002 log Phase 19-20: 1850/51 `Passed Month Day, Year` (no comma) vs 1852+ `APPROVED, Month Day, Year` (comma); chapter-header format shift `CHAPTER <roman>.` (1850-57) vs garbled inline `Cuap. <roman>.—An Act` (1858-60); the latent `AN_ACT_RE` IGNORECASE bug; modern born-digital `Approved by Governor / Filed with Secretary of State`. The `(?:18|19|20)\d\d` date-cliff fix and `APPROVED_MODERN_RE` are in `modern-parser-run.log`.

### F. Current build state — **DOCUMENTED**
- MORNING_REPORT_2026-06-02 + memory `patolex-production-ocr-state` + cc002 log Phase 21: **1850-1875 OCR'd, banked, and ingested as version-B (multi-engine consensus) = the system of record** (4262 enactments = 4262 change_events; zero single-engine committed text; UTF-8 faithful; all signals captured; `trust_level='ocr_uncertain'`/`ocr_consensus`). provision_version=0 BY DESIGN (materialization is a deferred sweep).
- Note a slight inconsistency in the durable layer: the memory file `patolex-production-ocr-state` describes the *intermediate* state (1850-1860 banked, 1861-1875 resumable, GPU leak) and is **stale** relative to the cc002 log + MORNING_REPORT, which show 1850-1875 fully built and version-B canonical. A cold session reading the memory first would underestimate progress.
- Next steps captured: A/B-2 + Phase C (VLM-flagging on persisted low-confidence tokens + crowd correction), materialize provision_version when the serving layer is built, re-verify lineage_edge purge at the 1872 recodification, then extend the campaign past 1875.

### G. Operational must-knows — **DOCUMENTED**
- Bash hygiene/hooks, session-log requirement, Hans review, secrets location: CLAUDE.md + handoff "Working constraints" + memory `hans-is-not-codex`. Secrets at `C:\Users\PatrickKolasinski\Documents\PatoLex-secrets.env`.
- SSH/Tailscale to GPU boxes: memory `ssh-over-tailscale-recipe` (firewall-not-ListenAddress, Azure-AD-needs-local-account, 5090 = `100.70.54.56`, key `~/.ssh/patolex_5090`) + `local-infra-sql-tailscale`.
- Local Postgres: handoff step 1 + memory + cc002 log Phase 15 (`postgres`/`postgres`@5432, `patolex` DB, psql at `C:\Program Files\PostgreSQL\16\bin\psql.exe`).

---

## TOP GAPS (ordered by re-discovery pain)

1. **No deterministic build RUNBOOK / single orchestration entry point.**
   *Pain: HIGH — a fresh session resuming the multi-day 176-year build would have to reverse-engineer the orchestration from a 307-line session log and box-specific scratch scripts, risking "wandering off the reservation" (the exact failure Patrick called out).*
   **Doc to hold it:** a new `docs/60_OPERATIONS/BUILD_RUNBOOK.md` — one documented command sequence per stage (OCR queue launch → ingest → consensus → re-ingest → verify), determinism config (engine pinning F3/F4), and the resume procedure past 1875.

2. **The born-digital vs image-only boundary (D2-i) is not in any design doc — only a run-log.**
   *Pain: HIGH — determines whether the modern tail of the Chief Clerk corpus needs the OCR pipeline at all or a cheap text-extract path; re-discovery means re-characterizing PDFs.*
   **Doc to hold it:** `DATA_SOURCES_HISTORICAL.md` (fix the "Image-only PDF" cell) + `DATA_SOURCES.md` — add: "Chief Clerk PDFs are image-only through at least the 1870s and **born-digital with a clean text layer by 2001-2008** (verified); use `parse_born_digital.py` text-extract for born-digital years, OCR only for image-only years. Exact crossover year TBD."

3. **`patolex-production-ocr-state` memory + ARCHITECTURE.md are stale.**
   *Pain: MEDIUM-HIGH — the two most likely "first reads" (a project memory and the architecture doc) both understate reality; a cold session could misjudge both progress (F) and scope (A).*
   **Docs to hold it:** update the memory to "1850-1875 version-B canonical, system of record"; add a cc002-era revision to ARCHITECTURE.md reconciling it with historical-first (or a banner pointing to ROADMAP).

4. **Canonical-vs-lossy ingest rationale lives only in session-log + Hans audits.**
   *Pain: MEDIUM — a cold session could run the wrong/older ingest script and silently re-introduce single-engine lossy text (the exact C1 "green log over an untouched lie" trap Hans caught).*
   **Doc to hold it:** `pipeline/README.md` — state plainly that `ingest_clean.py` (version-B, scoped-purge-then-insert) is canonical and `ingest_from_ocr.py` is superseded, with the purge requirement.

5. **`pipeline/README.md` documents a boot-resilience model that was abandoned.**
   *Pain: MEDIUM — a cold session would implement ONSTART/SYSTEM hardening Patrick explicitly dropped (interactive/logged-in is fine; the build is one-time).*
   **Doc to hold it:** `pipeline/README.md` — replace the "Boot resilience" section with the determinism/reproducibility goal actually wanted.

6. **No standing HANDOFF for cc003-onward beyond the (now-outdated) cc002→cc003 handoff.**
   *Pain: MEDIUM — the existing handoff predates the entire 1850-1875 production build; its "first steps" (apply DDL, seed 1872) are already done.*
   **Doc to hold it:** a fresh `HANDOFF_*_to_next.md` (or update the existing one) reflecting version-B-complete-through-1875 and the real next step (Phase C / extend past 1875).

7. **The 1872 disposition mapping (1850-71 act → 1872 section) is a known hard dependency with no acquired source yet.**
   *Pain: MEDIUM (deferred) — well flagged as a requirement (memory + ROADMAP Gate E) but the actual source (Code Commissioners' notes + Index to the Laws 1850-1893) is not yet acquired/located in a durable artifact.*
   **Doc to hold it:** `DATA_SOURCES_HISTORICAL.md` §5 — track the disposition-mapping source acquisition status.

8. **Human-gold OCR certification still pending (OpusGold is a frontier-model reference, not certified truth).**
   *Pain: LOW-MEDIUM — clearly flagged everywhere, but the production accuracy number (1.04%) rests on it; a cold session should know the audit is owed.*
   **Doc to hold it:** `OCR_ACCURACY_VALIDATION.md` — add an explicit "owed: 10+ human-gold session-law pages to certify OpusGold" status line.

---

## RECOVERED ANSWER TO D2 (the priority item)

**(i) Born-digital boundary in the Chief Clerk PDFs:** the early volumes are **image-only scans with no text layer** (verified 1850 + 1871-72); by **2001 and 2008 the chaptered-statute PDFs are born-digital with a clean text layer** — `parse_born_digital.py` pulled 227 chapters from 2008_Vol1 at 100% confidence, continuous numbering, correct dates, **zero OCR** (`modern-parser-run.log`, 2026-06-02). Modern chaptered sections also **drop the bill markers** (`[Senate Bill No]` absent) and use `Approved by Governor <date> / Filed with Secretary of State <date>`. The **exact crossover year is not pinned** in any durable doc, and `DATA_SOURCES_HISTORICAL.md` still mislabels the entire 1850-2008 Chief Clerk range as "Image-only PDF (no text layer)." **This boundary lives ONLY in a run-log → flag as AT-RISK / PARTIAL.**

**(ii) Additional modern structured-data channel:** **leginfo PUBINFO bulk data** — `https://downloads.leginfo.legislature.ca.gov/`, biennial `pubinfo_YYYY.zip`, **1989-2025**, a MySQL `capublic` dump (tab-delimited `.dat` + `.lob` text + `pubinfo_load.zip` DDL), **born-digital CAML XML**, public domain (Gov. Code §10248.5). It carries current code text (`LAW_SECTION_TBL`) and **every chaptered bill version as XML (`BILL_VERSION_TBL`, back to 1993-94)**. Caveat the docs make explicit: the LAW tables are a **current-only snapshot**, so modern point-in-time text is **reconstructed backward** from chaptered bill XML and validated against the current snapshot (oracle); pre-1993 has no machine-readable bill text → OCR territory. **This is DOCUMENTED durably** in `DATA_SOURCES.md` §1-§4 and cross-referenced in `DATA_SOURCES_HISTORICAL.md`.
