# SESSION cc019 — Archives Visit Prep + Residual Root-Cause

**Date:** 2026-07-24 · **Model:** Opus 5 (1M) · **Repo state at start:** clean, HEAD `7917708` (2026-06-23, cc018) — idle ~1 month

---

## Why this session happened

Patrick visits a Sacramento archive **Monday 2026-07-27** — a single, non-repeatable trip — and needed a clean, verified list of what to capture. Secondary ask: stop PatoAudio Python sidecars holding RAM.

---

## 1. Environment (done)

Stopped on `PKS_2025_ALIEN`: `diarizer_service.py` (pid 37484, port 8766) and `translation_service.py` (pid 22672, port 8767). Ports confirmed released. Free RAM 3.7 → 4.0 GB — both were idle with models unloaded, so the reclaim was small; real pressure is ServiceShell (758 MB), Dell TechHub agents (~700 MB), OneDrive (~700 MB). Postgres 16 (pid 7712) untouched, still listening on 5432. `ollama serve` (25 MB, idle) left running — not requested.

---

## 2. The scan list was not safe to use

`ARCHIVES_SCAN_REQUEST_2026-06-22.md` had three problems: it was a **mail-order quote request**, not an in-person pull list; it disagreed with cc018 on the count (**9 vs 8**, with the arithmetic implying 7); and it **omitted a volume**.

Resolved from page-level PDF evidence rather than the residual scoreboard:

**The count is 9 fully-missing + 3 partial = 12 chapters across 7 volumes / 15 printed pages.**

- **cc018's "9 → 8" is wrong.** It credited 1927 ch.816 and 1986 ch.1359 as recovered; both are still `textlen=0` placeholders (`status=legislative_gap` / `not_found_needs_reocr`). Same artifact `EXTERNAL_ACQUISITION.md` already flagged for 1970 ch.906/907 — `parsed_acts_visual.json` stubs with `status=image_verified` make the residual manifest count a chapter present when no text exists. **The residual scoreboard is not trustworthy for this question.**
- **1972 Vol.1 ch.517** (printed 896–897) was missing from the scan request — it *is* in `SCAN_GAP_VERIFICATION_2026-06-22.md:22,45`, so not a new discovery, but it would have missed the trip.
- **1985 ch.507 is present** (3-line repealer starting printed 1861, which survived). `SCAN_GAP_VERIFICATION.md` wrongly listed it.

**Deliverable:** `docs/80_PROJECT_HISTORY/ARCHIVES_VISIT_PACKET_2026-07-27.md` — supersedes the scan request.

---

## 3. Hans pass on the packet

**All seven page ranges independently re-derived pixel-level (rendered and read, not OCR-trusted) — all seven CORRECT.** No wasted-trip risk from a wrong page number. Also confirmed: the ch.507 call, the 9-not-8 correction, and no repeat of the known `Code.pdf` filename trap (`1927_Vol1_Chapters.pdf` 131.9 MB real vs `1927_Vol1_26Chapters.pdf` 120 KB fragment).

Four doc errors found and fixed:

1. **CRITICAL — "title-leaf-only" was wrong** for ch.817 / ch.1359 / ch.517. Operative **body text** is missing too. The first surviving page after each gap opens mid-clause, lowercase (1972 p898 *"unincorporated territory and the corporate area…"* → SEC. 1 and the start of SEC. 2 gone). **Risk averted:** the post-trip ingest would have transcribed a heading and discarded recovered statutory text existing nowhere else.
2. Dropped a false "NEW — on no prior list" tag on ch.517.
3. **Undercount:** 3 of 7 volumes also recover an adjacent chapter *tail* — ch.815 (1927), ch.377 (1981), ch.504 (1985) each end mid-sentence on the last surviving page. **The corpus currently holds these three chapters truncated without knowing it.**
4. Total capture pages ~24 → **~29**.

---

## 4. Venue — near-miss averted

Double-verified via CSL Alma/Primo MARC **and** Library of Congress SRU (independent paths):

**Sole holder = WITKIN STATE LAW LIBRARY**, Gillis Hall 3rd Fl, 914 Capitol Mall. Call number **`L325`** ("GOVDOC L325"), OCLC `27878031`. Complete **1850–current** run, 4 copies — **ask for c.2**. A full-title catalog sweep found **no** Gov Pubs / California History / Sutro copy. *The packet's first draft named Government Publications; that was wrong.*

**Near-miss:** the **CA State Archives (1020 O St) bans cell phones in the research room and prohibits patron copying of bound volumes** — Patrick had it as a live option. He would have arrived with an unusable phone for un-photographable books. **California History Section is closed Mondays** and has moved to 900 N St.

**Monday verified:** open **9:30 am–4:00 pm**, no appointment, no reader card, **photography expressly permitted with no form — but flash prohibited**, free scanners **require photo ID**. Phone (916) 323-9839 opens 9:00 am.

Patrick could not call before Monday (Friday 17:20, all closed), so phone-dependent prep was replaced with weekend-doable actions: book a Gillis table, send an `askus.library.ca.gov` paging request (recovers the pre-request), check HathiTrust.

**Backup:** Sacramento County Public Law Library, 609 9th St, Mon–Fri 9–5, ~6-min walk, `KFC 30 .A2`, coverage 1850–2008.

---

## 5. External availability — exhaustive, not sampled

Scanned HathiTrust's **complete inventory dump** (`hathi_full_20260701.txt.gz`, 1.22 GB, **19,573,293 volumes**).

- **1927, 1929, 1970, 1981, 1985, 1986 are not digitized anywhere** (HathiTrust / IA / LLMC-free). The physical trip is genuinely required.
- **1972 v.1 IS openly available** — `umn.31951d02287802e`, `rights=pd, access=allow`. UMN bound copy, Google-digitized = **independent scan, not the Chief Clerk microfilm**. Needs a 5-min browser check of printed p.896; if present, strike the volume.
- **Correction:** `EXTERNAL_ACQUISITION_2026-06-22.md`'s reasoning is wrong — HathiTrust's 403 is an **edge/bot block, not an institutional-login wall**. PD items are full-view in any browser.
- **HeinOnline lead:** Session Laws Library carries CA 1849–present as "exact replications of the bound session laws," chapter-indexed, **scanned from Hein's own print holdings** (independent provenance). Free onsite at CA public law libraries — including SacLaw, 6 min away. **Could clear all seven without touching a book.**

---

## 6. Track 2 (propositions) — retrieval complete, archive incomplete

97 files on disk (39 measures-type + 58 constitution-type), exactly matching the manifest — **0 zero-byte, 0 corrupt. The download never failed; the gaps are gaps in what the Chief Clerk publishes.**

**7 elections have no measures section anywhere in the series:** 1911-10-10 special *(the election that created the initiative power)*, 1912-11-05, 1916-11-07, 1918-11-05, 1920-11-02, 1922-11-07, 1924-11-04. Confirmed by OCR of back matter + indexes of the 1913/1917/1919/1921/1923/1925 volumes — ACAs/SCAs appear only as **referrals**, never as approved text.

**Unknown whether the printed volumes lack the section or the scan omitted it — resolvable only by physical inspection.** Added to the packet as Task B (6 volumes, ~10 min, highest information-per-minute of the day).

Design-doc corrections owed: measures for **1993–2008 ARE present**, embedded in monolithic `YYYY_Vol1.pdf` (1996+ **born-digital with text layers** — §7's "born-digital fast-path never fires" holds only through 1995); and the pilot **missed `1915_Vol1_Measures.pdf`** (2 pp, genuine REFERENDUM MEASURES section, never parsed).

---

## 7. ★ The residual 71 are a PARSER GRAMMAR problem, not an OCR problem

**The headline finding of the session.** See `lessons/LESSON_2026-07-24_residual_71_is_parser_grammar_not_ocr.md`.

Two independent checks:

1. **Legibility audit:** all 7 biennial PDFs are uniform **native 300 DPI, 1-bit, no text layer**, headings crisp. 300 DPI is the native ceiling. → **The 71 do NOT need re-scanning; excluded from the trip.**
2. **Blind read by Opus 5** of 4 residual targets, expected values withheld until after transcription — **3 of 3 legible-page targets correct on first pass**, with full titles and approval dates.

Three mechanical root causes, **none OCR-related**:

- **Defect 1 — no `[Approved …]` bracket on acts that became law unsigned.** 1866 ch.143 carries a Speaker/President block + *"This bill having remained with the Governor ten days… it has become a law."* Adjacent ch.144 has a normal bracket and parsed fine. **Any detection anchored on `[Approved` is structurally blind to a whole constitutional class of enactment.**
- **Defect 2 — heading punctuation varies by era.** 1866 = `CHAP. CXLIII.` (space); 1876/1878 = `CHAP.—XCI.` / `CHAP.—CLXXIII.` (**em dash, no space**). `CHAP\.\s+` misses every em-dash volume.
- **Defect 3 — bracket ranges break on long acts.** 1872 ch.125–128 is labeled "multi-act cluster, pp. 224–227"; p225–226 are **body text (SEC. 5–15) of ch.124**, a long roads act running past p227. Ranges derive from the preceding chapter's *start* page, assuming adjacency.

**Fourth, irreducible class:** 1874 ch.261 is printed `CHAPTER CLXI.` — the leading `C` is absent from the **physical typesetting**. No parser or camera fixes it; only neighbour-context inference.

**Implications:** the "machine-unreadable" label is wrong and mis-routes work to humans/archivists when the fix is in code. 95,923/96,002 = 99.9% stands, but the residual's *explanation* is wrong. **These defects have been running across the entire OCR era, not just the 71** — chapters that WERE found may carry null/wrong `chaptered_date`, likely intersecting the known open item *"Roman-numeral heading + chaptered_date parser fix (51 acts wrong date, correct text)."* **Audit scope must extend past the residual, and this must land before the single mass ingest.**

---

## Decisions (Patrick)

- Venue: both/undecided → **resolved to Witkin** by research.
- Capture: photograph in person **and** order what can't be photographed.
- **Approved: full 71-chapter vision pass (~500k tokens) AND the parser defect fixes** — run independently so parser-recovery and vision-recovery cross-validate.

## Open / next

- **IN FLIGHT:** parser defect fixes (code map being built) + 71-chapter vision pass.
- Weekend (Patrick): HeinOnline access check · 1972 HathiTrust page-896 check · HathiTrust 010063843 for 1910s–20s · book Gillis table · send askus paging request.
- **Owed:** 1905 ch.389–397 are `image_verified` but `textlen=0` — images acquired, **text never transcribed**.
- **Data bug:** 1927 ch.816 has `status=legislative_gap` while its own note says "SCAN GAP… absent from the PDF scan" — a downstream tool would conclude the chapter was never enacted.
- **Stale docs:** ROADMAP.md (revision history ends 2026-06-09), CHANGELOG.md (**cc014–cc018 entirely absent**), `OCR_RECALL_RECOVERY.md` CURRENT STATE block.

## Files

- **NEW** `docs/80_PROJECT_HISTORY/ARCHIVES_VISIT_PACKET_2026-07-27.md`
- **NEW** `docs/80_PROJECT_HISTORY/lessons/LESSON_2026-07-24_residual_71_is_parser_grammar_not_ocr.md`
- **NEW** `docs/80_PROJECT_HISTORY/run-logs/archives-visit-prep-run.log`
- **NEW** this session log
