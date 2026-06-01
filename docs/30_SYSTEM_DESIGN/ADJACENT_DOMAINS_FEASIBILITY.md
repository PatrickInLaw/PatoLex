# Adjacent Domains: Feasibility of Extending the PatoLex Model

**Status:** Strategic reference (cc002, 2026-06-01). Informs long-term scope and Gate D schema design. **Not near-term scope** — PatoLex stays focused on CA statutes (the North Star).

This note records a researched feasibility assessment of applying the PatoLex point-in-time / law-as-Git model to three adjacent domains, and what the (more mature) federal ecosystem teaches us. All findings are sourced; see the inline links.

---

## TL;DR

| Domain | Feasibility | Biggest enabler | Biggest obstacle |
|--------|-------------|-----------------|------------------|
| **CA statutes** (our scope) | Proven (cc002) | Blank-slate session-law chain; Method A validated | No pre-computed amendment mapping → must parse (this is also the moat) |
| **CA regulatory (CCR)** | Feasible via **baseline-plus-forward** (deep history hard) | Forward-only = eCFR's own model; asset accrues; drops into the same schema | Acquiring a clean current-CCR **baseline** (official text is behind Westlaw/Barclays, no bulk export) |
| **Federal statutory (US Code)** | Highly feasible (easier than CA) | OLRC **Classification Tables pre-compute** the Public-Law→section mapping; USLM XML | Positive vs. non-positive titles; pre-1994 not machine-readable |
| **Federal regulatory (CFR)** | Highly feasible (best-resourced) | **eCFR already does point-in-time** via free API; FR = XML event stream | Volume (~186k pages, 3,000+ rules/yr); pre-1994 gap |

**Strategic read:** the federal ecosystem *validates our entire thesis* (eCFR is literally "regulation as of date" run by the government; OLRC release-points mirror our chaptered-snapshot model; `nickvido/us-code` already commits US Code release-points to git). The genuinely **unfilled** niche is deep-historical **CA point-in-time statutes** — unfilled precisely because CA, unlike the feds, has no official "what did this bill change" mapping. The amendment-directive parsing we proved in the Method-A spike *is* that missing capability.

---

## CA Regulatory Law (California Code of Regulations)

- **Model transfers:** the **California Regulatory Notice Register ("Z Register")**, published weekly by OAL, is the event stream — each adopt/amend/repeal action with an effective date maps to a commit, exactly like statutes.
- **Public domain:** CCR text is effectively public domain (*County of Santa Clara v. Superior Court*, CPRA; government-edict doctrine; Public.Resource.Org published the full CCR in 2012 unchallenged — [law.resource.org/pub/us/code/ccr](https://law.resource.org/pub/us/code/ccr/)).
- **Why it's harder than statutes:**
  - Official CCR is published via **Barclays / Thomson Reuters (Westlaw)**; **no official state bulk export** ([oal.ca.gov/publications/ccr](https://oal.ca.gov/publications/ccr/)).
  - The Notice Register (the amendment event stream) is **PDF-only — no structured XML** (unlike our statute data or the federal FR).
  - **OAL deleted all pre-2018 Notice Register issues** from its site in 2019 (accessibility compliance); 2002–2017 survive only via web archives, pre-2002 only on microfiche/print at law libraries ([UCLA Law Library](https://libguides.law.ucla.edu/caladminlaw/history)).
  - No free point-in-time historical CCR exists anywhere online.
- **Volume:** ~600+ regulatory actions/yr from 200+ agencies — similar order to statutes.
- **Verdict:** full *historical* reconstruction requires OCR of Notice Register PDFs and the record is fragmented — but a **baseline-plus-forward** approach sidesteps all of that (see next).

### CA Regulatory via baseline-plus-forward (the recommended shape)

Rather than reconstruct deep CCR history, take a **clean snapshot of the current CCR as a dated baseline and track forward** from it. This is the correct shape for CA regs, not a compromise:

- **It avoids every hard part.** The difficulty was *historical* (PDF-only Notice Register, OAL's deleted pre-2018 issues, microfiche). Forward-only never touches it. You're left with two clean problems: (1) acquire one complete baseline snapshot; (2) apply the forward event stream (OAL-approved actions, weekly, each with adopted text + effective date). Forward documents are modern/born-digital — text extraction, not OCR of old scans. Volume (~600 actions/yr) is trivial.
- **It's exactly what eCFR does.** The federal government's own point-in-time CFR only reaches back to 2017 — a baseline + forward. We'd be doing for CA precisely what the feds chose for the CFR. Strong validation that the model is sufficient.
- **The asset accrues.** Year one = "current CCR + change tracking" (already useful — commercial players don't expose free point-in-time). Each year forward silently becomes the free historical CCR archive nobody else offers. Deep history can be backfilled *behind* the baseline later (steward, via microfiche OCR) without ever blocking.
- **Maps cleanly to law-as-git + the Gate D schema:** the baseline = a bulk set of `enact` events dated at the baseline; each OAL action = an `enactment` with `amend`/`add`/`repeal` `change_event`s. `unit_type = reg_section`. No new machinery (see `SCHEMA_DESIGN.md`).

**The one load-bearing unknown — the baseline itself.** A point-in-time archive is only as trustworthy as its baseline, and the official current CCR lives behind **Westlaw/Barclays with no bulk export**. The *text* is public domain, but **channel terms bind regardless of copyright** (the HathiTrust lesson). Malamud's 2012 full-CCR publication proves it's *legally* publishable but it's stale. Before committing to CA regs, **verify a clean, complete, defensibly-sourced current-CCR baseline is obtainable through a non-Westlaw channel.** Smaller caveats: **Title 24 (building standards)** is published separately (special-case or scope out); no structured feed (build a small OAL/Notice-Register PDF parser).

- **Verdict:** **feasible and recommended via baseline-plus-forward**, gated on confirming clean baseline acquisition. Still a **later** extension — parked behind CA statutes. The only thing that matters *now* is keeping the Gate D schema domain-neutral so CCR drops in (done — see `SCHEMA_DESIGN.md`).

## Federal Statutory Law (US Code)

- **Federal "session laws" = Statutes at Large / Public Laws:** free, USLM XML from 2003, scanned to 1789 ([govinfo.gov/help/statute](https://www.govinfo.gov/help/statute)).
- **The decisive advantage — OLRC Classification Tables:** the government **pre-computes the Public-Law → US-Code-section mapping** ([uscode.house.gov/classification/tables.shtml](https://uscode.house.gov/classification/tables.shtml)). The hardest thing PatoLex must do for CA (parse amendment directives to find what changed) is *already done* federally.
- **Point-in-time:** official USLM XML release-points back to 2013; annual editions to 1994 ([uscode.house.gov/download](https://uscode.house.gov/download/download.shtml)). Pre-1994 not machine-readable.
- **Wrinkle — positive vs. non-positive law titles:** ~24 non-positive titles are only "prima facie" evidence; the **Statutes at Large controls**, so accurate reconstruction there must source session laws, not the Code text ([OLRC](https://uscode.house.gov/codification/term_positive_law.htm)). CA has no equivalent — all CA codes are authoritative compilations of chaptered law.
- **Prior art:** `nickvido/us-code` ([github.com/nickvido/us-code](https://github.com/nickvido/us-code)) commits each OLRC release-point as a git commit (~13 commits 2013–2025; roadmap lists bills-as-PRs); `publicdocs/uscode` similar but abandoned at 2016; `@unitedstates/congress` scrapers actively maintained. **No one has shipped full historical reconstruction + bills-as-branches at production quality** — the pieces exist, the synthesis doesn't.
- **Caveat on release-points:** they snapshot the Code *after a batch* of Public Laws, so they don't give bill-granularity blame. PatoLex's per-act event model is finer-grained than the federal git efforts.

## Federal Regulatory Law (CFR / Federal Register)

- **eCFR already implements our Feature 1:** a free, documented government API with **point-in-time queries back to 2017** (`/versioner/v1/full/{date}/title-{n}.xml`, `/versions/{title}`, `/ancestry/{date}/...`) — [ecfr.gov/developers](https://www.ecfr.gov/developers/documentation/api/v1), [changes-through-time](https://www.ecfr.gov/reader-aids/using-ecfr/ecfr-changes-through-time).
- **Federal Register = the event stream:** final rules carry **amendatory instructions** ("In §1.23, revise paragraph (b)…") in XML for all documents since 1994 ([federalregister.gov/developers](https://www.federalregister.gov/developers/documentation/api/v1)). CFR annual editions in bulk XML from 1996 ([govinfo.gov/help/cfr](https://www.govinfo.gov/help/cfr)).
- **Public domain:** 17 U.S.C. §105 — no copyright on federal works, no channel chokepoint.
- **Prior art:** `AlextheYounga/ecfr` reconstructed eCFR history to 2002 in git (~2,368 commits).
- **Obstacle:** volume — Federal Register hit 106k pages in 2024; CFR ~186k pages; an incremental pipeline (not full rebuilds) is mandatory. Pre-1994 is scanned-PDF only.

---

## What PatoLex should take from this (actionable now)

1. **Design the Gate D schema USLM / Akoma-Ntoso-aware.** USLM is GPO's standard (Akoma-Ntoso-derived; [github.com/usgpo/uslm](https://github.com/usgpo/uslm)) used for US Code, bills, and Statutes at Large. If PatoLex ever extends to federal, a USLM-compatible event/emit model makes it a **parser swap, not a redesign**. Cheap insurance.
2. **Build live bill tracking (Feature 2) on primary government sources only.** ProPublica's Congress API died (2024), GovTrack's bulk API died (2016), Sunlight folded — but Congress.gov and CA leginfo persist. Confirms the leginfo-direct approach; never depend on an intermediary.
3. **Our hard problem is our moat.** CA has no Classification-Tables equivalent; the Method-A amendment-directive parser we validated is exactly the capability that makes deep-historical CA statutes possible where others stopped. Lean into it.
4. **Sequencing recommendation:** stay focused on CA statutes. File **federal statutory** as the most natural "v2" (easiest data + existing prior art to extend) and **CA regulatory** as a harder later extension. Both are growth paths a future academic steward could take on (see memory `patolex-perpetuity-gift`).

---

## Key external references

- US Code / OLRC: [download](https://uscode.house.gov/download/download.shtml), [release points](https://uscode.house.gov/download/priorreleasepoints.htm), [classification tables](https://uscode.house.gov/classification/tables.shtml), [positive law](https://uscode.house.gov/codification/term_positive_law.htm)
- Statutes at Large: [govinfo.gov/help/statute](https://www.govinfo.gov/help/statute); USLM schema: [github.com/usgpo/uslm](https://github.com/usgpo/uslm)
- Federal bill data: [Congress.gov API](https://api.congress.gov/), [unitedstates/congress](https://github.com/unitedstates/congress)
- Law-as-git prior art: [nickvido/us-code](https://github.com/nickvido/us-code), [AlextheYounga/ecfr](https://github.com/AlextheYounga/ecfr)
- eCFR: [API docs](https://www.ecfr.gov/developers/documentation/api/v1), [changes through time](https://www.ecfr.gov/reader-aids/using-ecfr/ecfr-changes-through-time)
- Federal Register: [API](https://www.federalregister.gov/developers/documentation/api/v1); CFR bulk: [govinfo.gov/help/cfr](https://www.govinfo.gov/help/cfr)
- CCR: [OAL](https://oal.ca.gov/publications/ccr/), [Notice Register history / UCLA](https://libguides.law.ucla.edu/caladminlaw/history), [Public.Resource.Org CCR](https://law.resource.org/pub/us/code/ccr/)
