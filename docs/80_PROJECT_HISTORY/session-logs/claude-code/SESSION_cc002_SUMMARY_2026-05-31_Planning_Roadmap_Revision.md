# Session cc002 Summary

| Field | Value |
|-------|-------|
| Session | cc002 |
| Date | 2026-05-31 |
| Agent | Claude Code / Opus 4.8 (orchestrator) |
| Context | First real session: roadmap sanity-check, scope/tech revision, Gate B (modern + historical) reconnaissance |
| Branch | main |

---

## What Was Done

cc001 was repo setup. cc002 reviewed it, sanity-checked the plan, and executed Gate B reconnaissance — twice (modern, then historical after a strategic reversal). Nearly all reading/downloading/research was delegated to sonnet/haiku subagents; Opus orchestrated and synthesized.

### Phase 1 — Plan sanity-check (early)
- **Scope** initially split into modern POC (1991-present) vs. 1849 north star.
- **Two-database architecture:** local Postgres (build/staging) + Supabase (serving); one Drizzle schema, publish step. (Reversed cc001's "no local Postgres.")
- **tRPC deferred:** data access = RSC + Server Actions over a transport-agnostic service layer (`src/server/`); MCP likely the first external interface, public API later.

### Phase 2 — Gate B (modern)
- Confirmed leginfo PUBINFO bulk data; **LAW tables are current-only** (no history) → reconstruct **backward from the current snapshot** via chaptered bill XML; POC floor ~Jan 1994. Operative-date, double-jointing (§9605), section-identity rules documented. → `DATA_SOURCES.md`.

### Phase 3 — STRATEGIC REVERSAL: historical-first / risk-first (Patrick)
- Patrick reversed to **historical-first**: solve the hardest part (1849 reconstruction off scans) FIRST to prove feasibility; **no public launch until the full 1849-present corpus is present and validated**; quality over speed/revenue.

### Phase 4 — Gate B (historical)
- Three sonnet subagents (acquisition, reconstruction model, OCR). Findings → `DATA_SOURCES_HISTORICAL.md`:
  - **Acquisition solved + verified by download.** Patrick supplied a catalog (`CA_Legislative_Publications_Catalog.xlsx`, **4,034 vols, every row has HathiTrust + Google links**) → copied to `docs/30_SYSTEM_DESIGN/sources/`. Plus CA Assembly Chief Clerk archive (all statute vols 1850-2008, image PDFs, free) and Internet Archive (1872 Codes w/ existing OCR).
  - **OCR mostly already exists** → harvest + selectively correct (5090 as correction engine), NOT an OCR farm. Existing OCR ~85-90% on 19th-c. text → below legal standard → targeted correction; #1 risk = silent section-number corruption.
  - **Three-era model:** pre-code (1850-1872, act-based, separable) / 1872 codification baseline / 1873-1993 forward-from-baseline; meets modern era at the **~1991 seam** (validation oracle). Biggest structural risk = recodification events, esp. the **1943 Government Code / Political Code dissolution**.
  - **Validation:** annotation-history chains (Deering's/West's), HeinOnline compiled editions, join-point reconciliation, trust-level classification per version.

### Phase 5 — Licensing / channel analysis (CRITICAL)
- Patrick supplied the HathiTrust datasets page. Finding: the **content is public domain**, but the **HathiTrust/Google bound datasets prohibit re-hosting, search-services, and third-party sharing** — which describe PatoLex exactly. **Going free/nonprofit cures only the "commercial" prong; the other prohibitions still bar those channels.**
- **Resolution:** serve from **commercially/contractually clean channels — Internet Archive + CA-government (Chief Clerk, leginfo)** — public domain, no strings. HathiTrust = non-commercial validation/bootstrap aid only. Catalog HTIDs remain useful as an index.
- **Distribution model:** PatoLex heading toward **free, likely nonprofit** (donations offset maintenance). Lowers liability surface.

### Phase 6 — Acquisition (PDFs found, clean channels)
- **Penal Code 1872 baseline downloaded:** Internet Archive `penalcodecalifo00burcgoog` (original Sacramento 1872 as-enacted, 697pp + OCR). § 187 OCR verified clean.
- **Session-law manifest built:** 653 statute-volume PDFs, 1850-2008, from the CA Assembly Chief Clerk archive — URLs + sizes verified (HTTP 200). Filenames irregular across 8 eras (enumerated, not patterned). Saved to `docs/30_SYSTEM_DESIGN/sources/chief_clerk_statutes_manifest.csv`. Archive ends 2008; 2009+ from PUBINFO.
- Next-step sources identified: Desty 1881 annotated PC (`penalcodecalifo03caligoog`), *Index to the Laws of CA 1850-1893* (`indextolawscali00caligoog`), other three 1872 codes.

### Phase 7 — Gate C slice proof (autonomous, through validation)
- Ran the Penal Code 1872-1903 proof end-to-end via sonnet subagents (pull editions → extract → reconstruct → validate). → `docs/30_SYSTEM_DESIGN/GATE_C_SLICE_PROOF.md`.
- **Inter-edition OCR text-diffing rejected** (median same-section similarity 0.07 — but see caveat: likely alignment/segmentation failure + bundling, not pure OCR garbling). **Annotation-driven method adopted + validated** vs *Index 1850-1893* at 85% (27-section overlap).
- **QUALIFIED-GO:** timeline method proven; point-in-time *text* layer is the remaining bounded risk → next step is a vision-LLM re-OCR spike on the 5090 + 5080.

### Phase 8 — OCR benchmark (round 1) + constraints
- Both GPU boxes reachable via Ollama (5080 local 16GB, 5090 Tailscale 32GB). Benchmarked qwen2.5vl(7B/32B), llava:34b, llama3.2-vision, minicpm-v on 20 PC pages / 5 gold.
- **Best = qwen2.5vl:7b ~55% page-CER (34-43% on law pages) — NOT legal-grade.** 5090 3× faster + only box for >7B; batching worse than sequential; ~23K pages/day combined.
- Caveats (adversarial): page-CER includes marginalia (overstates body error); cross-model diagnostic not actually run; Tesseract/Falcon-OCR/cloud untested. **Text-layer risk ACTIVE, not retired.**
- **Patrick constraints (2026-06-01):** full historical coverage is core/non-negotiable (dead without it); NO line-by-line human review — accuracy via automation (consensus + flagging), humans spot-check + audit only. Round-2 launched to settle text-layer viability.

### Phase 9 — OCR rounds 2-3: text-layer risk RETIRED
- **Round 2:** body-text-only CER ~17% (vs the inflated 55% page-level). Identified Google Books JPEG scan quality as the dominant limiter; consensus flag-recall 74-94%.
- **Round 3 (decisive):** on a **clean non-Google IA scan**, body-CER hit **1.2% / 1.9%** on §187/§211 (mean best 1.5%) — **legal-grade**. Scan-quality delta −37.5 pts. Ensemble flag-recall **99.2%**. **VERDICT: GO** — the project's core technical risk is retired. Recipe: clean scans (IA/HathiTrust JP2) + Tesseract 5 + qwen2.5vl + disagreement-flagging + spot-audit. Fine-tuning optional (<0.5% only).
- Caveats: 2-page sample (needs broader validation); WSL unreached by the subagent (Patrick says it's installed — off critical path); clean-scan SOURCING at scale is the new dependency.

### Phase 10 — validation broadening, sourcing map, full-corpus inventory, method decision
- **Val-50:** inter-engine disagreement proxy confirmed as a triage signal (1906 holds ~1.5%, a 1902 edition worse ~5-8% and correctly flagged). True CER still rests on 2 human-verified pages — a ~10-20 page **human-gold audit** is needed to firm the production number (fits "audit," not line-by-line).
- **Clean-scan sourcing map (§1b):** ~60-65% of catalog has a clean non-Google source (IA non-goog + Chief Clerk PDFs, both clean-licensed; HathiTrust library scans as fallback pending terms). Google-only ~35-40% is mostly the Phase-2 Bills corpus.
- **Full-corpus inventory (§1c) + BLANK-SLATE PRINCIPLE (Patrick):** CA had no law before 1850, so the unbroken clean **session-law chain 1849-2025 IS the complete law** — codifications are themselves acts within it. **Corpus completable from clean sources, no Phase-1 blocking gap.**
- **METHOD DECISION:** production = **forward-from-session-laws (Method A)**. Annotated editions exist for only 14/29 codes → Method B (annotation-driven, which the spike used) does NOT scale → demoted to validation layer.
- **Candid status:** OCR retired (GO) + reconstruction proven *in principle* (Method B), but the **production method (A: parsing raw session-law amendment directives at scale) is NOT yet proven** — the next risk to retire.
- **Idea recorded (memory `law-as-git-repo-idea`):** emit CA law as a Git repo (bills=branches, chaptering=merge, double-jointing=merge-conflict, `git blame`=legislative history). DB = system of record, git = generated open-source artifact. Method A is inherently event-sourced, so it emits both from one model.

### Phase 11 — Method-A re-spike (engine validated), law-as-git design, adjacent-domain feasibility
- **Method-A re-spike → QUALIFIED-GO.** Ran the production engine end-to-end (1872 baseline → parse session-law directives → apply forward → validate vs annotated edition) on the 1883 Penal Code slice. **Directive parser: 100% precision/recall** on 12 hand-checked directives. Validation: 3/5 exact MATCH, 1 NEAR (marginal-note OCR noise ~0.08 CER), 1 MISMATCH — and the mismatch was a **Google-scan OCR digit error** (§634→"834"), not a method failure. **The production engine is validated.** Remaining = a bounded sourcing/OCR task: 1873–80 code amendments live in a separate "Amendments to the Codes" volume whose clean text is in image-only Chief Clerk PDFs (Tesseract pass needed). **Section-number collisions** across numbering schemes (§634 = game law vs. plumbing) reinforce the synthetic `section_id` lineage requirement for Gate D.
- **`LAW_AS_GIT.md` written.** Serious review of Patrick's law-as-Git idea. **Adopt** the data-model and the distribution-artifact framings; **reject** Git's engine for reconciliation (correctness boundary: whole-section replacement + §9605 chapter-order priority + recodification lineage would make Git's three-way merge fabricate statute text that was never enacted). Two flagship features specced: (1) point-in-time full-corpus clone, (2) live bill tracking (modern+forward). Gate D schema implications enumerated (trailer fields the emitter needs).
- **Perpetuity intent recorded (Patrick):** build once, hand to a law school/nonprofit to steward forever. The **git repo is the durable handoff vehicle** (survives even if the serving stack goes dark) — reframes it from export to gift. Memory `patolex-perpetuity-gift`.
- **Adjacent-domain feasibility researched** (2 sonnet agents, fully sourced) → `ADJACENT_DOMAINS_FEASIBILITY.md`: **CA regulatory** feasible but operationally hard (Notice Register is the event stream but PDF-only; OAL deleted pre-2018 issues; no state bulk export). **Federal statutory** *easier* than CA — OLRC **Classification Tables pre-compute** the Public-Law→section mapping (the hard thing we parse, the feds publish), USLM XML standard, `nickvido/us-code` already commits release-points to git. **Federal regulatory** best-resourced — **eCFR already does point-in-time** via free API since 2017. Strategic read: the federal ecosystem validates our thesis; deep-historical **CA point-in-time statutes is the genuinely unfilled niche**, unfilled because CA has no pre-computed amendment map — and our Method-A parser *is* that capability (the moat). Actionable: design Gate D schema **USLM/Akoma-Ntoso-aware** so a federal v2 is a parser swap; build Feature 2 on primary gov sources only (ProPublica/GovTrack/Sunlight APIs all died; Congress.gov + leginfo persist).

---

## Files Changed

**New:** `docs/30_SYSTEM_DESIGN/DATA_SOURCES.md` (modern), `docs/30_SYSTEM_DESIGN/DATA_SOURCES_HISTORICAL.md` (historical + licensing), `docs/30_SYSTEM_DESIGN/sources/CA_Legislative_Publications_Catalog.xlsx` + `.csv`, `docs/30_SYSTEM_DESIGN/GATE_C_SLICE_PROOF.md`, `docs/30_SYSTEM_DESIGN/LAW_AS_GIT.md`, `docs/30_SYSTEM_DESIGN/ADJACENT_DOMAINS_FEASIBILITY.md`, `docs/30_SYSTEM_DESIGN/sources/chief_clerk_statutes_manifest.csv`, run-log, this session log. Memory: orchestrator-only, both-logs, historical-first, quality-first philosophy, local-infra, law-as-git-repo-idea, patolex-perpetuity-gift.

**Modified:** `docs/20_ROADMAP/ROADMAP.md` (historical-first re-sequence), `docs/30_SYSTEM_DESIGN/ARCHITECTURE.md`, `README.md`, `CLAUDE.md`.

---

## Decisions Made

1. Historical-first / risk-first; full 1849-present is the deliverable; no launch until complete + validated.
2. Distribution: free, likely nonprofit (not commercial).
3. Reconstruction: forward-from-1872 (historical) + backward-from-current-snapshot (modern), meeting at the ~1991 seam.
4. Data channels: Internet Archive + CA-gov only (public domain, no contractual strings); HathiTrust/Google bound datasets excluded for re-host/search/share reasons.
5. OCR: harvest existing + selective correction (5090), not an OCR farm.
6. Schema must be era-aware: synthetic section lineage, recodification events, operative-date ranges, provenance, trust-level.
7. Two-DB architecture; tRPC deferred.
8. Working model: Opus orchestrates; reading/code/download → cheaper models. Session logs NOT a haiku job.

---

## Open Items at Close

- **Gate D: event-sourced schema** — now the immediate next gate (Method A validated).
- Bounded engineering task: OCR the 1873–80 Chief Clerk statute volumes (clean scans) to fill the "Amendments to the Codes" gap and extend the Method-A proof across that window.
- ~10–20 page human-gold OCR audit (firm the production accuracy number); source a clean 1872–1905 Penal Code baseline.
- Confirm 1989/1991 PUBINFO contain LAW_SECTION_TBL; per-volume existing-OCR quality distribution.
- 1937-1953 recodification disposition tables; pre-1873 repeal scope.
- Resolve the WSL access discrepancy (low priority; off critical path).

---

## Next Session Should Start With

Current state (end of cc002 work-in-progress): scope set (historical-first, full 1849-present, free/nonprofit); sources mapped + proven completable (blank-slate); OCR risk retired (clean scans); **reconstruction engine validated — Method A QUALIFIED-GO**; law-as-git boundary fixed (git = emitted artifact, never the merge engine); perpetuity/handoff intent recorded; adjacent-domain feasibility documented.

**Next (cc002 continues or cc003):**
1. **Gate D — event-sourced schema (now the lead task).** Per-change events: author / 3 dates (chaptered-effective-operative) / bill / chapter # / diff / §9605 resolution metadata / synthetic `section_id` lineage / provenance + trust-level. Must emit BOTH the temporal DB (system of record) AND the Git history. **Design USLM/Akoma-Ntoso-aware** so a future federal v2 is a parser swap. Local SQL Server / Postgres staging.
2. **Extend the Method-A proof:** OCR the 1873–80 Chief Clerk volumes (Tesseract on clean scans) and run a heavier amendment session to stress the parser beyond the light 1883 slice.
3. **Parallel threads:** human-gold OCR audit; clean 1872–1905 Penal Code baseline sourcing.

---

## Lessons Learned

- **Recon before report.** Wrote the historical report before the acquisition agent returned and it contained invented specifics; corrected against verified data. Rule: never synthesize a report ahead of the subagent results it summarizes.
- **Public-domain content ≠ unrestricted channel.** The binding constraint can be the delivery channel's contract (HathiTrust/Google), not copyright — and free/nonprofit status doesn't lift re-host/search/share terms. Choose clean channels.
- **`block-compound-bash` scans raw command text for `; ` etc.** — including inside quoted strings, PowerShell hashtables, and `cat <<EOF` heredocs. Use `Invoke-RestMethod` with `chat_id` in the URL and no semicolons for Telegram; use the Write tool instead of `cat >>` for logs.
- Session logs are not a haiku job (haiku draft came back mangled).

---

## Commits

- `6cc71dd` — cc002 part 1 (modern Gate B + scope/two-DB/tRPC).
- `70c0720` — cc002 part 2 (historical-first reversal, Gate B-Historical, catalog, licensing).
- `dbfe8d1` — part 3 (acquisition: Chief Clerk manifest + Penal Code 1872 baseline).
- `e52889a` — part 4 (data-first reorder).
- `a0ed5fb` — part 5 (Gate C slice proof: annotation-driven method validated).
- `b3512e2` / `0d0bf44` / `b63b692` — parts 6-8 (OCR rounds 1-3; round 3 = GO, legal-grade on clean scans).
- `54b99d3` — part 9 (clean-scan sourcing map + broadened OCR validation).
- `88e5c91` — part 10 (full-corpus inventory, blank-slate, Method A decision, git-repo idea).
- `91dbc1e` — part 11 (session-log brought current pre-compaction).
- (this /ucp) — part 12 (Method A re-spike QUALIFIED-GO, LAW_AS_GIT.md, ADJACENT_DOMAINS_FEASIBILITY.md, perpetuity memory, ROADMAP status).
