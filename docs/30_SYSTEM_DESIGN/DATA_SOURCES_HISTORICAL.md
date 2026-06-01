# Historical Data Sources & Reconstruction (Gate B-Historical Report)

**Status:** Gate B-Historical complete (cc002, 2026-05-31). Synthesized from three sonnet recon subagents (acquisition, reconstruction model, OCR/extraction), the acquisition catalog Patrick supplied, and confirmed by real downloads. No code written.

Covers the **historical era (1849–1993)** — built **first** under the risk-first / historical-first decision. Pairs with `DATA_SOURCES.md` (modern era, 1993–present).

> Correction note: an earlier draft of this file invented download specifics before the acquisition agent reported. This version replaces them with verified figures.

---

## Bottom line

1. **Acquisition is solved, with redundant free sources** — verified by actually downloading volumes from each. The hard "does complete legible source even exist" risk is retired.
2. **OCR mostly already exists** (Google Books / HathiTrust / Internet Archive). Per Patrick's direction, the path is **harvest existing OCR, not run an OCR farm** — with *targeted correction* where quality is weak, not wholesale re-OCR. The local 5090 becomes a correction/validation engine, not a primary OCR pipeline.
3. **The real remaining risk is structural correctness**, not data access or compute: section-number integrity (silent corruption), amendment-chain completeness, and the mid-century recodification events (esp. the 1943 Government Code / Political Code dissolution).
4. **Built-in correctness oracle:** forward reconstruction (from the 1872 baseline) and backward reconstruction (from the modern snapshot) must agree at the ~1991 seam, and every historical amendment must match the annotated-code history chains.

**The historical-first bet is viable.**

---

## 1. Acquisition — sources, state, coverage (all verified)

| Tier | Source | Coverage | Format / state | Access |
|------|--------|----------|----------------|--------|
| **Catalog** | **Inbox spreadsheet** `CA_Legislative_Publications_Catalog.xlsx` (copied to `docs/30_SYSTEM_DESIGN/sources/`) | 4,034 volumes: Statutes 1849-1966, Assembly Bills 1911-87, Senate Bills 1903-87, Journals, Appendix, Final Calendar, Legislative Index, Constitutions | **Every row has BOTH a HathiTrust HTID link and a Google Books link.** HTID is the canonical cross-platform ID. No annotated Codes in catalog. | The acquisition manifest. CSV alongside the xlsx. |
| **Session laws (images)** | CA Assembly Chief Clerk archive | **Every statute volume 1850-2008** (fills the catalog's post-1966 Statutes gap) | Image-only PDF (no text layer) | Free direct HTTP, predictable URL pattern. 1993 = 5 vols. |
| **1872 Codes + compilations (w/ OCR)** | Internet Archive | All four 1872 Field Codes + Deering compilations + *Index to the Laws of CA 1850-1893* | Image PDF **plus existing OCR `.txt`** (~85-90% body-text word accuracy) | Free direct HTTP, public domain |
| **Modern structured** | leginfo PUBINFO | 1989-2025 (reliable baseline 1993) | Born-digital CAML XML + .dat | Free. See `DATA_SOURCES.md`. |
| **Paywalled fallback** | HeinOnline; HathiTrust full-volume bulk | 1849-present; 1853-1948 compiled codes | High-quality scans | Subscription / institutional membership / data capsule. Use only to fill gaps + validate. |

**Verified downloads** (in `C:\Users\PatrickKolasinski\PatoLex-scratch\gate-b-historical\`): 1850 Statutes (Chief Clerk, 30.67 MB, ~480 pp, image-only); 1873-74 (54.64 MB, ~1,086 pp); 1875-76 (35.73 MB); 1872 Civil Code (Internet Archive, 46.51 MB PDF + 1.79 MB OCR `.txt`); `pubinfo_1989.zip`.

**Coverage notes / gaps:**
- Catalog "Statutes" sheet is populated only ~1849-1966 (~121 of 203 rows have years) — **the Chief Clerk archive covers 1966-1993**, so the full span is obtainable by combining sources.
- California went **biennial in 1863** (odd-year sessions) — "missing" even years are not gaps, they're non-sessions.
- HathiTrust *full-volume bulk* download needs membership; but Google Books OCR + IA OCR are freely accessible per-volume via the catalog's HTIDs, so this is not blocking.
- Catalog has **no annotated Codes** (Deering's/West's) — those come from Internet Archive (open) and HeinOnline/Lexis (paywalled), needed for validation chains.

**Acquisition strategy:** use the catalog HTIDs as the *index*, but acquire production text from **commercially-clean channels** (Internet Archive + CA government direct) — see §1a. Use Chief Clerk high-res PDFs as page images for correction/validation; dedupe multi-library copies by HTID.

---

## 1a. Licensing & channel selection (CRITICAL)

The **content** is public domain (government-edicts doctrine; CA Gov. Code §10248.5 for modern data) — copyright is not the issue. The issue is the **contractual terms of the delivery channel**, which bind us regardless of the content's public-domain status **and regardless of whether PatoLex is commercial or a free/nonprofit public service.** PatoLex re-hosts text and runs a public search service — acts the bound channels restrict independent of price.

**Distribution model (cc002):** PatoLex is heading toward **free public distribution, likely under a nonprofit** (donations offset minimal maintenance). This is the right call for mission fit and liability, but it does **not** change the channel strategy below — see why.

**HathiTrust research datasets are NOT a viable production channel for PatoLex:**
- Two datasets exist: `ht_text_pd_open_access` (PD excluding Google-digitized; ~814K vols) and `ht_text_pd` (all PD incl. Google-digitized; ~6.6M vols). Access is by **request + signed researcher agreement**, framed as **non-commercial research**, via **rsync from a static IP**.
- The Google-digitized subset additionally requires an **institutional Google Distribution Agreement** (signed list: University of California, Stanford, etc. — a solo law firm/nonprofit does not qualify), and its terms forbid: **commercial use, re-hosting, supporting search services, sharing with third parties.** Going free/nonprofit cures only the *commercial* prong — **re-hosting, search-service, and third-party-sharing remain prohibited**, and each describes PatoLex exactly. So the Google dataset stays out regardless of price.
- The non-Google `ht_text_pd_open_access` is less restrictive, but is still a *research-use* agreement that does not clearly permit a public re-hosted archive — and we don't need it (see clean channels). Many catalog volumes are Google-digitized anyway.

**Use HathiTrust only** as a non-commercial *validation/bootstrap* aid if ever needed — never as the served corpus.

**Commercially-clean channels (use these for production):**
- **Internet Archive** — public-domain scans + OCR, reuse-friendly. Primary for the 1872 Codes and compilations.
- **CA Assembly Chief Clerk archive + leginfo PUBINFO** — California government works, public domain, no contractual strings. Primary for session-law page images (1850-2008) and modern XML.
- Where a needed volume exists only behind a bound channel, **OCR the public-domain page images ourselves** (5090) rather than ingest restricted text.

**Net:** the catalog's HTIDs remain useful as a cross-index, and HathiTrust's subset mechanics (build an HTID list → rsync just those volumes; pairtree layout; `htrc/ht-text-prep` strips running heads/footers) are documented for completeness — but the **served data comes from Internet Archive + CA-gov sources**, keeping PatoLex commercially clean.

---

## 2. OCR — harvest first, correct selectively (revised per Patrick)

Existing OCR already covers the digitized corpus, so we do **not** build an OCR farm. The pipeline is:

1. **Harvest** the existing OCR text (Google Books / HathiTrust / IA) for each catalog volume.
2. **Quality-gate** per volume (lexical real-word ratio, legal-boilerplate anchor checks, section-number sequence sanity). Existing OCR runs ~85-90% word accuracy on 19th-c. body text — **below a legal-trust standard**, so it cannot be served raw.
3. **Correct selectively:** route weak volumes/pages to correction — a constrained vision-LLM pass on the 5090 (with strict fidelity limits: word-count parity, bounded edit distance) and/or a second-engine (Tesseract) diff. Full re-OCR only for the worst 1850s-1870s long-s volumes.
4. The **1872 baseline must be near-perfect** and human-verified — every forward step depends on it.

**THE critical failure mode (unchanged): silent section-number corruption** — one wrong digit corrupts a section's entire point-in-time chain, and is invisible to lexical checks. QA is built around section-number integrity (sequence/monotonicity checks + cross-check against the annotated-code history chains). Secondary danger: vision-LLM **hallucination** ("over-historicization," silent rewording) — mitigated by fidelity constraints and treating LLM output as a candidate, never ground truth.

---

## 3. Reconstruction model — three eras, one timeline

| Era | Span | Shape | Strategy |
|-----|------|-------|----------|
| **Pre-code** | 1850–1872 | Chaptered **acts**, not codified sections | Flat, searchable **act archive** (by year/subject/title); point-in-time "what acts were in force" is hard (implied repeal) — **separable, lower-priority sub-project**. *Index to the Laws of CA 1850-1893* aids repeal tracking. |
| **Codification** | 1872 (op. 1/1/1873) | The four Field Codes (Civil, CCP, Penal, Political) | The **forward baseline**. NOT a clean repeal of all prior law (Civil Code §§22.2/23 conflict hierarchy; many special/local acts survived). |
| **Code-amendment** | 1873–1993 | Codified sections | **Forward from the 1873 baseline:** load the 1872 code text, apply each session's amendments (from *Statutes and Amendments to the Codes*) in **operative-date order**. The spine that connects to the modern era. |

**Code proliferation (highest structural risk).** California went from 4 codes (1872) to 29, mostly 1929-1953 via the Code Commission carving subject areas out of the **Political Code** (Probate 1931; Vehicle/Insurance/Streets&Hwys/Military 1935; Bus&Prof/Labor/Welfare&Inst/Harbors 1937; Elections/Health&Safety/Pub Resources/Rev&Tax 1939; **Government/Education/Water 1943 — the largest**; Financial/PUC 1951; Unemployment Ins 1953; later Commercial 1963, Evidence 1965, Family 1992). The **Political Code was formally repealed in 1951.** Each is a **bulk renumbering/transfer event** that must be a first-class entity: `(old_code, old_section) → (new_code, new_section)` with a date and an `is_substantively_amended` flag (the Commission's "no substantive change" claim must be *verified*, not trusted).

**Era-aware effective-date engine required.** 1849 Constitution: effective on signature / 10-day window, **no 90-day rule, no urgency mechanism**, explicit effective dates often stated in the act. 1879 Constitution (eff. 1/1/1880): the modern regime — Jan-1-after-90-days, urgency = immediate (2/3 vote), special sessions = 91st day. Applying modern Gov. Code §9600 rules to an 1860 statute would be wrong. Store `enacted_date` / `effective_date` / `operative_date` with confidence flags.

**The seam (~1991).** Forward-from-1873 marches up; backward-from-current-snapshot (modern era) marches down; they overlap ~1991. **Section-by-section text agreement at the seam is the strongest validation we have.**

---

## 4. Validation to a legal-trust standard

Layered, since there's no machine-readable ground truth before ~1991:
- **Annotation-history cross-check (primary):** Deering's / West's print "Stats. YYYY, ch. N, §M" chains after each section must match our amendment events. Mismatches flag errors both ways.
- **HeinOnline compiled-code editions (1853-1948):** contemporaneous official compilations → point-in-time text spot-checks.
- **HathiTrust / Google independent scans:** catch OCR divergence between sources.
- **Join-point reconciliation (~1991):** exhaustive, authoritative comparison against the modern snapshot.
- **Index to the Laws of CA 1850-1893** and **CLRC reports (1957+)** for the early and recodification eras.
- **Trust-level classification on every section-version:** `VERIFIED` (matches annotation + a compiled edition) / `ANNOTATION-CONFIRMED` / `RECONSTRUCTION-INFERRED` / `REQUIRES-REVIEW`. Surfaced to users — attorneys self-calibrate, and it bounds liability.

---

## 5. Remaining unknowns (resolve in schema + the slice proof)

- Do the 1937-1953 recodification acts contain complete old→new disposition tables, or must they be rebuilt (e.g., from LegisIntent / annotated codes)?
- Pre-1873 repeal scope (what the 1872 codes repealed vs. left standing).
- Whether 1989/1991 PUBINFO contain `LAW_SECTION_TBL` (modern baseline may be 1993).
- Per-volume existing-OCR quality distribution → how much correction vs. re-OCR is actually needed.
- Scope: codes only, or also uncodified session law (appropriations, special/local acts)?

---

## 6. Recommended next step — the make-or-break proof

A **single-code historical vertical slice** (candidate: **Penal Code** — a 1872 original surviving intact to today, so the modern history-string cross-check is strong, and it avoids the Political-Code recodification tangle):

1. Harvest + correct the 1872 Penal Code baseline to near-perfect (human-verified).
2. Parse to sections; apply amendments forward through several decades.
3. **Validate** against Deering's/West's history chains and (at the seam) the modern snapshot.

If this holds to a trustworthy accuracy standard, the approach is proven and we scale across codes. If it doesn't, we've found out cheaply — the entire point of going risk-first.

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc002: Gate B-Historical recon. Acquisition solved (inbox catalog of 4,034 vols w/ HathiTrust+Google links; Chief Clerk archive 1850-2008; IA 1872 Codes w/ OCR — all verified by download). OCR reframed to harvest-existing + selective correction (per Patrick). Three-era reconstruction model, forward-from-1872 meeting modern era at ~1991 seam. Risk = section-number integrity + recodification events. Next: one-code (Penal) historical slice proof. Replaces earlier draft that had unverified download specifics. |
