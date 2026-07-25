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

---

## 8. Parser fixes — DEFECT 2 landed, test suite resurrected

**Canonical parse path confirmed** (this decides what gets edited): driver `pipeline/ingest/parse_all.py`; implementation `pipeline/ingest/ingest_from_ocr.py` STAGE 5 (lines 390–707), entry `parse_volume()` @709. **Nuance vs. project memory:** `ingest_from_ocr.py` is superseded only on its *ingest* half (replaced by `ingest_clean.py`) — **its parser half is live.** `ingest_clean.py` does no heading/date extraction, only consumes `iso_date`.

### Defect 2 — em-dash blindness was TOTAL

Verified empirically by executing **every live heading pattern in the pipeline** against the real printed forms: **not one matched `CHAP.—XCI.`** The canonical `HEADER_RE` scored **5/9**; every miss was an em-dash or en-dash variant.

**Root cause is almost comic:** `_DASH` was already defined and used in `HEADER_RE` — but only in the *trailing* `—An Act to…` position. The 1876/78 typesetters put the dash *before* the numeral, where `\.?\s*` could never reach it.

**Fix:** shared `_HDR_SEP` separator class, applied to `ingest_from_ocr.py:393` (canonical) and `chapter/chapter_reconstruct.py:29` (live verbatim copy).

**Measured: 5/9 → 9/9** on real printed forms, **0 false positives** against body text, running heads, enacting clauses, and `[Approved]` lines. Recovered tokens resolve correctly: `XCI`→91, `CLXXIII`→173, `CXLIII`→143.

**Hazard documented inline:** `parse_chapter_number("XCIAN")` returns **91**, not an error — it silently strips non-Roman characters. An over-capturing numeral group does not fail loudly; it returns a *plausible wrong number*. The numeral class must stay letter-free.

### The date test suite was DEAD

`pipeline/test_date_parser_fix.py:68` pointed at `pipeline/5080/ingest_from_ocr.py`; the module moved to `pipeline/ingest/` in the reorg. It died at import, **before its first assertion**, and had since. **Net effect: zero live regression coverage on `parse_act_date`** — including the `_TEXT_NO_DATE` case and the ±3-year clamp.

Nothing caught it: **the repo has no CI at all** (no `pytest.ini`, `pyproject.toml`, `conftest.py`, or workflows — every test is hand-invoked), and `smoke_imports.py` is AST-based while the broken reference is a *string path*.

Also fixed `pipeline/5080/parse_born_digital.py:35`, which used `Path(__file__).with_name(...)` and has therefore been **unloadable since the same reorg**.

**Post-fix: 33 passed / 0 failed** — and it passes clean, so no regressions were hiding behind the broken import.

| Suite | Result |
|---|---|
| `test_date_parser_fix.py` | **33 passed / 0 failed** (was dead) |
| `test_chapter_parser.py` | ALL PASS |
| `analysis/_test_chap_guards.py` | 0 failures |
| `analysis/test_recover_early_dedup.py` | ALL PASS |
| `test_detect_body_start.py` | 9 passed |
| `ocr/test_consensus.py` | 8/9 — **pre-existing** |
| `analysis/test_recover_guards.py` | error — **pre-existing** |

Both failures are the same `ModuleNotFoundError: No module named 'config'` sys.path issue in files this session never touched.

**Why defects 1–3 survived so long:** existing heading fixtures are **Arabic and space-separated only** (`"CHAPTER 88."`, `"CHAP. 17"`). They *cannot* fail on the em-dash or Roman gaps. Roman numerals have value-layer coverage only — **no test feeds a Roman numeral through any heading regex.**

### More stale-path rot found (pre-existing, not fixed here)

`analysis/_audit_repair.py:19`, `_eyeball_repairs.py:7`, `_verify_brackets.py:42` hardcode `C:\github\PatoLex\…` — a root that does not exist on this box. Joins `pipeline/tests/check_golden_master.py:18` and `.scratch-certify/test_spillover.py` in needing `PATOLEX_LOCATION_ROOT`.

### Contents-anchored vision pass (in flight)

All 7 biennial volumes **do** carry a chapter-ordered printed CONTENTS in front matter from PDF p3. Columns: `Chap. | TITLE OF ACT | No. of bill | Page`. **Contents numbers are Arabic** — Roman appears only in body running heads. 270 pages rendered at 200 DPI. No alphabetical back-index exists in any of the seven. Expect legitimate `[See volume of Amendments to the Codes.]` entries in 1874/76/78 — real chapters whose text lives in the companion volume, not an artifact.

---

---

## 9. ★ ALL 71 RESIDUAL CHAPTERS RECOVERED

**71 of 71. Zero remaining. None require an archive visit.**

Full record: `docs/80_PROJECT_HISTORY/RESIDUAL_71_CONTENTS_RECOVERY_2026-07-24.md`.

**Method:** contents-anchored (cc015's 1854 technique). Tesseract located pages only — **every recorded value was read visually off the printed contents by Opus 5.** That distinction mattered: the OCR sweep wrongly classified **1878 ch. 418** as an Amendments-volume redirect; the printed page shows a real act at p. 620. Four chapters (1866/143, 1876/91, 1878/173, 1874/261) were independently read from *body* pages too — all four agree.

| Class | Count | Meaning |
|---|---|---|
| Ordinary acts | **62** | Recoverable — parser fix |
| `[See volume of Amendments to the Codes.]` | **5** | **In a companion volume. Not in this book.** |
| Special enactment paths | **4** | 3 unsigned + 1 veto override |

**The residual can never reach zero as defined.** 1874 ch. 587/679 and 1876 ch. 306/497/498 were enacted but printed in the *Amendments to the Codes* volume. No re-OCR or scan of these seven PDFs will find them.

**Bracket defect quantified:** for 1872 ch. 125–128 the list gives PDF 224–227; true pages are **221–222** (offset printed + 90). The stated range lands on **chapter 128's own body**.

**`HUMAN_REVIEW_LIST_2026-06-22.md` is superseded** — no human paging required; its brackets are wrong and its "multi-act cluster" labels describe the opposite of the page.

Still owed: this recovers **identity** (number, title, date, bill, page), **not statutory text**. Body-text consensus OCR is still required before ingest.

---

## 10. Parser fixes — defects 1, 2, D landed; 3 partial

| Defect | Status | Evidence |
|---|---|---|
| **2** em-dash headings | **FIXED** | 5/9 → **9/9**, 0 false positives |
| **1** three enactment paths | **FIXED** | `test_enactment_paths.py` **27/27** |
| **D** non-"An Act" headings | **FIXED** | `is_confident_act` accepts the enacting clause |
| **3** bracket ranges | **PARTIAL** | `test_residual_bracket.py` **16/16**; forward-scan NOT implemented |
| **E** Amendments-volume class | identified, needs external source | — |
| **F** self-contradicting volumes | identified | cross-check contents vs body |

**Defect 1 was broader than first written — three paths, not two:** signed, unsigned ten-day lapse, and **passed over the Governor's veto**. Wording is unstable (three phrasings for the lapse alone), so the regex anchors on `bec[ao]me (a )?law` with a free-text qualifier. New spelled-out-date parser (`"this twenty-seventh day of February, A. D. eighteen hundred and sixty-six"` → 1866-02-27) — none existed anywhere in the pipeline.

**A vowel cost a test cycle:** the body prints *"has **become** a law"*, the contents prints *"**became** law"*. A draft using bare `become` passed the body fixture and failed every contents row. **Fixtures came from real printed text**, which is the only reason it surfaced.

**Defect 3 deliberately bounded:** fixed the truthiness bug (`source_page == 0` was silently dropped), replaced undocumented `±4` magic numbers, and added implausible-span detection that catches the real 1872 case. The **forward-scan heading detection was NOT implemented** — it needs page text `bracket_for()` never receives, and writing it untested against unreachable data would be worse than flagging it. Documented in-code as an open limitation.

**Full suite:** 33 + 27 + 16 + 9 passing, plus chapter parser / chap guards / dedup. Two pre-existing failures untouched (`ocr/test_consensus.py` 8/9, `analysis/test_recover_guards.py`) — both the same `No module named 'config'` sys.path issue in files this session never edited.

**Also repaired:** `_residual_manifest.py` had **two** hardcoded roots, including `C:\GitHub\PatoLex\…` which exists nowhere; now honours `PATOLEX_LOCATION_ROOT`.

---

---

## 11. Durable-doc hygiene

- **`CHANGELOG.md`** — added the cc019 entry, and a **prominent gap banner** for cc014–cc018 (2026-06-20→23), which were entirely absent. **Deliberately NOT backfilled:** writing five sessions' history from second-hand summaries would put unverified claims into the system of record, which is the failure that file exists to prevent. Their session logs are the source; backfill from those.
- **`ROADMAP.md`** — added a status banner rather than rewriting. The scope doc is the source of truth and restructuring it is Patrick's call, not a side effect of a parser session. The banner records five corrections, two of which are new work items:
  - **A new prerequisite is implied:** the corpus **cannot be complete without the *Amendments to the Codes* volumes.** Chapters marked `[See volume of Amendments to the Codes.]` were enacted but printed there — 5 confirmed among the residual alone, **nine on a single 1876 contents page.** No existing prerequisite covers acquiring them.
  - **Prerequisite (5)'s "51 acts wrong date" is likely an undercount** — the three defects ran across the entire OCR era, not just the residual. Re-measure after a reparse.
- **`ARCHIVES_VISIT_PACKET_2026-07-27.md` §4** — closed; the 71 are recovered, nothing from them belongs on any list.

---

## 12. ★ Hans FAIL — and the methodological correction

Hans ran the new regexes **against the real corpus over SSH**, not against fixtures, and returned **FAIL**. Report: `audits/2026-07-25_030205-verify-phase-report.md`. All findings fixed; `test_enactment_paths.py` now **49/49** with a regression per finding.

**The lesson worth keeping:** the commit claimed *"0 false positives against body text."* **That claim was false.** It was measured against a hand-written six-line negative set. Against the corpus, the separator produced **55 false-positive header matches** on index entries (`"crabs, 47"`).

> **A regex change to a corpus parser is not verified until it has been run over the corpus.** Fixtures prove a pattern *can* match what you intended; only the corpus reveals what *else* it matches.

| # | Finding | Severity | Fix |
|---|---|---|---|
| 1 | **Cross-act date poisoning** — on `production-1865-66` p.24 (a CONTENTS page) the lapse regex captured **ch.380's approved date as ch.379's lapse date**. Same year, weeks off — **the ±3yr clamp is blind to it** | **severe** | gap now forbids periods, **digits**, `An Act`, `CHAP`; 120→80 chars |
| 2 | Comma in `_HDR_SEP` matched index lines | real | comma removed (it was speculative — no printed form needs it) |
| 3 | Third un-synced `HEADER_RE` in `5080/reparse.py`, still em-dash-blind | real | synced despite being a dead module — a broken copy invites copy-paste |
| 4 | `spelled_ordinal_to_int` accepted impossible days 32–39 | minor | clamped 21–31 |
| 5 | `ENACT_MARKER_RE` unanchored, now load-bearing via the new fallback | minor | clause must be in first 2000 chars + explicit `RESOLUTION_RE` guard |

**Why finding 1 mattered most:** these volumes carry a Concurrent/Joint Resolutions section and printed contents tables with multiple acts per visual block. A date-stealing regex would run unattended across the un-reviewed 1877–1994 forward campaign and write plausible wrong dates into a corpus ingested exactly once.

**Also fixed:** `pipeline/README.md` labelled `ingest_from_ocr.py` blanket "SUPERSEDED / LOSSY" while cc019 called it "(CANONICAL parser)" — a real contradiction. Resolved: its **ingest half is superseded; its parser half is live and canonical.** The README's stale `pipeline/5080/` path is the same one that left `test_date_parser_fix.py` dead for a month. Its "no `__main__` guard" hazard is stale — a guard exists at line 1273 (verified).

---

## 13. ★★ Corpus measurement — it overturned two of my own fixes

Measured on **1,732,428 real OCR lines / 27,595 pages / 19 volumes**. Full detail in the lesson file.

| Metric | R1 (original) | R2 (after Hans) | **R4 (final)** |
|---|---|---|---|
| HEADER_RE matches | 2,986 | 2,861 | **2,976** |
| Genuine headings missed vs R1 | — | **116** | **0** |
| Index-line FPs | 9 | 0 | **0** |
| Lapse matches | 12 (1 poisoned) | 16 | **58** |
| p.25 poisoning | **PRESENT** | dead | **dead** |
| Lapse recall (early era) | — | 40% | **70%** |
| Resolution guard | — | 2 rejects (1 **wrong**) | **1 (correct)** |

**Two of my "fixes" were wrong, and only the corpus revealed it:**

1. **Removing the comma cost 116 genuine headings** to block 9 index lines. Hans's "55" was itself wrong (real: 9), and I acted on it without measuring. The discriminator was in the data all along — genuine comma headings carry **Roman** numerals, index lines **Arabic**. Comma-before-Roman recovers all 116, blocks all 9, adds zero junk.

2. **My digit ban suppressed every modern lapse act in the corpus.** I asserted the qualifier "never legitimately contains a digit." The entire 20th-century form is `[Became law without Governor's signature. Filed with Secretary of State October 1, 1982.]` — period *and* digits. R2 found **0**; R4 finds **40** across 1982–1999.

3. **My em-dash claim was overstated** — "5/9 → 9/9" came from a hand-built fixture set. At corpus scale the em-dash form is a **2-instance outlier** (1875-76/1877-78 print period+space in 379 of 462 headings). Correct fix, +2 headings, not a campaign.

4. **My positional resolution guard made itself inert** — 0 rejections across 3,091 buffers, because genuine resolutions *quote* act titles. Anchored on the enacting clause instead (exclusive to acts; resolutions never carry it).

> **The rule:** a regex change to a corpus parser is not verified until it has been run over the corpus — and "fixing" it on a reviewer's count without re-measuring can be worse than the original bug.

**Accepted residual (measured):** 3/10 early-era lapse misses with visible causes (hyphenated month, parenthetical ordinal, OCR `uf`), and 62 implausible-token header FPs that are **pre-existing and separator-independent**. Performance clean: 2.8 s full scan, max page 16 ms, 0 pages >100 ms.

**Not measured:** standalone regexes only — the full parser was not run, so downstream-gate survival of the remaining FPs is unknown; the 40 modern lapse hits are per-page, not per-act.

---

## 14. Reparse ≠ re-OCR — and the before/after diff harness

**Question raised:** are we re-OCRing everything or just parsing? **Answer: just parsing.**

`parse_volume()` reads `ocr_consensus/page_ocr_results.json` and consumes the already-banked `consensus_text`. **No OCR engine runs; no GPU is touched.** Verified in code, not assumed.

| | Cost |
|---|---|
| Re-OCR | GPU-days — 3 engines over ~27k+ pages. **Not needed.** |
| Reparse | CPU reading JSON already on disk. |

The consensus text is unchanged; the cc019 fixes are entirely in how that text is *interpreted*. Now documented in the `parse_volume` docstring so nobody has to re-derive it.

**Patrick's call: before/after diff, not an in-place reparse.** Correct instinct — the corpus is ingested exactly once, and a reparse moves chapter counts, which feed the recall oracle. The delta gets reviewed *before* anything lands.

**NEW `pipeline/analysis/reparse_diff.py`** — runs two parsers over identical input:
- **BEFORE** = `git show <ref>:pipeline/ingest/ingest_from_ocr.py` (default `f152284`, pre-fix)
- **AFTER** = current working tree
- Both with `write=False` — **no volume directory is touched**

Reports per volume and corpus-wide: confident/flagged counts, the **set** of chapters (gained vs **lost**), per-chapter dates added/changed/removed, and the enactment-path distribution. **Lost chapters and removed dates are flagged loudly** — the fixes should be strictly additive, so either is a regression to investigate before running for real.

`parse_volume()` gained `out_path` / `write` params; defaults preserve existing behaviour exactly. Also documented what it does **not** touch: only `parsed_acts_fixed.json`. The merged/clauserec/visual/certified outputs are the recovery passes' work from cc015–cc018 and must not be clobbered.

---

## 15. Reparse cost measured — and the risk that actually matters

**A full corpus reparse is a sub-minute job.** Measured on the 5090.

| | |
|---|---|
| `production-*` dirs | 225 |
| Reparseable (have OCR) | **216** (9 lack it: `2000-vol1..6`, `measures-1915/1935/1990`) |
| `parse_all.py` in-scope | **208** volumes / 328,881 pages / 3.65 GB |
| Total pages | **332,608** · OCR JSON **3.44 GiB** |
| Throughput | **7,701 pages/s**, ~88 MB/s single-process |
| Single-process ETA | **~45–60 s** |
| **16 workers (5090: 24 cores)** | **~15–30 s** |
| 5090 state | 22% CPU, 32 GB free of 63.5, GPU idle, **no contention** |
| Disk | overwrites in place; net new ≈ **+6 MB**. 542 GB free |

**★ The cost is not the constraint. Downstream desync is.**

The recovery chain — `merged` → `recovered` → `repaired` → `clauserec` → `certified` — was built **from** the June-12 `parsed_acts_fixed.json`. A reparse rewrites `fixed.json` **in place** and does *not* touch those artifacts. That is **worse than clobbering them**: they'd be silently stale relative to their own input, with nothing flagging the mismatch. If `fixed.json` content changes anywhere, the entire cc015–cc018 recovery chain is built on a superseded base.

**This vindicates the diff-first decision.** Snapshot all `parsed_acts_*.json` (~298 MB × ~7 artifacts) before any in-place run.

**Two further side effects found:**
1. `_parse_outputs\date-review-worklist.jsonl` is **append-only** — a full run appends a duplicate generation rather than replacing.
2. `parse_all.py` clobbers `_parse_outputs\parsed_acts_{label}.json` (197 files). Its docstring calls that dir "GIT-VERSIONED", but it lives under `C:\PatoLex-scratch`, **outside the repo** — those copies are *not* in git.

**★ A flaw in my own harness, caught by this measurement.** `_append_date_review` fires from `flush_act` — during the parse, not at write time. So `write=False` suppressed the JSON write but **would still have appended a full duplicate generation** to the shared worklist. My "touches nothing" claim was false. Fixed with a `_SUPPRESS_DATE_REVIEW` flag scoped to dry-run parses; `parse_volume` now delegates to `_parse_volume_inner` inside a try/finally so the flag always restores.

**Timing caveat, stated plainly:** the three timed volumes (1927 3pp, 1997, 1949) came back **byte-identical** to their June backups — but they were chosen by *size*, not by defect exposure, and cc019's fixes target **early-era** phenomena. **That is not evidence a reparse is a no-op.** The diff harness over early-era volumes is what settles it.

---

## 16. ★ Self-review of the reparse plan found a corpus-destroying bug in my own harness

Patrick: *"Make a plan, have Hans review it, and consider all the ways it is wrong (your first plan always is), then fix it."* Correct instinct — the first version had a bug that would have damaged the corpus on its first run.

### The severe one (mine, found in self-review before Hans reported)

`reparse_diff.py` called `mod_before.parse_volume(label, write=False)`. **The BEFORE parser predates the `write=` kwarg**, so that raises `TypeError` — and my `except TypeError` fallback called `parse_volume(label)` with the **default `write=True`**.

```python
except TypeError:
    with tempfile.TemporaryDirectory() as td:
        saved = mod_before.SCRATCH_ROOT      # saved...
        try:
            r_before = mod_before.parse_volume(label)   # ...but NEVER reassigned
```

I saved `SCRATCH_ROOT` and **never redirected it**. So the fallback would have written `parsed_acts_fixed.json` into the **live volume directory, with PRE-FIX parser output** — silently reverting the corpus while the docstring claimed it touched nothing. It would have fired on **every volume**, since no pre-cc019 ref has the kwarg.

**Fix:** the write is removed from the BEFORE **source** before import, and the patch is **asserted** — if the expected call site isn't found (e.g. a future rename), it raises rather than importing a parser that can write. The `except TypeError` fallback is deleted entirely; there is deliberately no fallback, because a fallback is what caused this. The append-only date-review worklist is neutered in the same pass.

*(Redirecting `SCRATCH_ROOT` is not a valid alternative — the OCR input is read from the same root.)*

### Second: the diff had no baseline fidelity check

The diff is only meaningful if BEFORE **reproduces what is actually on disk**. If the on-disk `parsed_acts_fixed.json` came from some other code path or a hand edit, "BEFORE" is a fiction and every gained/lost number is measured against the wrong baseline. Now checked per volume and summarised corpus-wide, with a loud `BASELINE-MISMATCH` flag.

### Third: a changed date is more alarming than a lost chapter

My abort condition only mentioned LOST chapters. A date that **moved** means the parser reads a *different* date off the same text — silently wrong, versus visibly absent. Now flagged as loudly as a loss (`DATE-MOVED`).

### Also fixed
`_load_parser` didn't put `pipeline/` on `sys.path`, so the BEFORE module died on `import config` — the harness could not have run at all from `analysis/`.

**NEW `pipeline/analysis/test_reparse_diff_safety.py` — 16/16.** Asserts the neutering holds, that BEFORE carries the pre-cc019 signature (wrong ref fails loudly), that suppressed appends open no file, and that no `except TypeError` fallback has crept back.

### Plan gaps I identified but have NOT yet fixed (pending Hans)

- **The DB is not addressed at all** — 35,332 enactments are already ingested from the *old* parse.
- **Phase 5 has no exit criteria and no cost bound** — "most unknown cost" is not a plan.
- **Gate F overlap** — the modern lapse fix affects 1982–1999, overlapping Gate F's 1991–2024 official-XML layer.
- **No dry-run of `parse_all` itself** — the per-volume diff doesn't exercise its aggregation/worker behaviour.
- **Phase 7 (fold in the 71) is sequenced too late** to serve as cross-validation.
- **Rollback is incomplete** — a `parsed_acts_*` snapshot doesn't undo worklist appends or `_parse_outputs` clobbering (which is *not* in git).
- **No acceptance criteria** — nothing defines what "success" looks like.

---

## 17. ⛔ THE FINDING OF THE SESSION — the recovery chain never reaches the database

Hans's review of the reparse plan surfaced something bigger than the plan. **Verified independently in code before reporting it:**

| Evidence | What it says |
|---|---|
| `ingest_clean.py:782` | `acts_path = scratch / "parsed_acts_fixed.json"` — **the only** `parsed_acts_*` file the canonical ingest opens |
| `recover_all.py:3` | *"additive; **no DB**, no overwrite of parsed_acts_fixed"* |
| `recover_early.py:334` | *"does NOT write parsed_acts_fixed.json"* |
| `merge_passes.py:29` | consumes `fixed.json` as **input**, emits `merged.json` — **nothing reads it back** |
| `BUILD_RUNBOOK.md:69` | canonical chain = *"OCR → parse → ingest_clean --commit"*; **recovery chain absent** |

The recovery passes were deliberately built **additive and non-destructive** — correct for safety, but the consequence is that `merged` / `certified` / `recovered` / `repaired` / `clauserec` / `visual` **terminate in files nothing downstream consumes.**

### Consequences

- **The 99.9% recall figure (95,923/96,002) describes FILES, not the database.**
- The 71 chapters recovered this session, and everything cc015–cc018 recovered, **would never reach Postgres**.
- My plan's Phase 5 ("re-run the recovery chain") was **solving the wrong problem** — re-running it produces more files nothing reads.

### The missing component

**A bridge folding recovery output into the ingest path does not exist and never has.** It is new, unbuilt work — not a re-run. Three candidate shapes, and it is **Patrick's call**:

1. **Merge-into-fixed** — simplest; destroys the additive-safety property protecting the campaign's work.
2. **Teach `ingest_clean.py` the chain** — cleaner; changes the canonical ingest contract, needs its own Hans pass.
3. **A third artifact** (`parsed_acts_ingestible.json`) — leaves both `fixed` and the chain untouched.

Until decided, **a reparse changes only files nothing ingests.** Still worth doing — the corpus files become correct, a prerequisite either way — but nobody should believe it moves the DB.

---

## 18. Plan v2 — every v1 defect traced to a finding

`REPARSE_PLAN_2026-07-25.md` rewritten. v1 was wrong in ways worth recording:

| Finding | Source | Fix in v2 |
|---|---|---|
| **Recovery chain never reaches the DB** | Hans #1 | Blocking section; Phase 5 rewritten around a bridge |
| **Harness wrote pre-fix output into the corpus** | self-review / Hans #2 | Fixed `5e4a423`; new Phase −1.1 gates the 5090 sync on it |
| `pipeline/5080/` omitted from inventory | Hans #3 | Added — it writes **the same filename** into the same dirs, and `reparse.py` self-flags "ARCHIVED / UNSAFE" while staying live and importable |
| `_vocab/chapter_corrections.tsv` | Hans #4 | A **positional** overlay keyed to pre-fix `in_act_order`; the fixes change ordering, so it has **no defined behaviour** after. Not a `parsed_acts_*` file → a glob snapshot misses it |
| Phase 2/4 scope mismatch | Hans #5 | 11 `SKIP_LABELS` disclosed (4 are **code volumes**); a mismatch from this is **benign**, and v1 would have read it as a regression |
| Rollback under-scoped | Hans #6 | Snapshot widened to 4 artifact classes; explicit "cannot fix" list |
| Worklist poisons Phase 6 | Hans #7 | Integrity check before trusting it as a measurement input |
| DB / `source_document` / Gate F unstated | Hans #8 | Explicit out-of-scope section |
| Phase 5 cost hand-waved | Hans #9 | Named: **human reconciliation, 71 judgement calls**, no tooling built |
| No baseline fidelity check | self-review | In the harness; Phase 1 gates on it |
| Changed dates not an abort condition | self-review | Added — a moved date beats a lost chapter for danger |
| No acceptance criteria | self-review | Phase 3 |

**Hans's sharpest process catch:** Phase 0.5 said "sync the 5090 via `git pull`" — but **`git pull` only moves committed history**, and the harness fix was uncommitted when he reviewed. Syncing first would have shipped the corpus-destroying version to the box that *holds the corpus*. Now committed (`5e4a423`) and gated explicitly.

---

## 19. ✅ "What bridge?" — Patrick was right; measurement killed my invented component

I asserted a missing "bridge" component from file topology alone. Patrick pushed back immediately. **Measurement across all 225 volumes proved him right.**

**Nothing with real statutory text is un-reproducible by a corrected text parser.**

| Bucket | n | Verdict |
|---|---|---|
| Real text absent from `fixed.json` | **3,243** | **100% text-pass provenance** — zero vision, zero external. Built from the same consensus OCR, so a corrected parser can produce them. |
| Vision / external / human | **~2,033** | **Every one `textlen = 0`.** Vision read a chapter *number* off an image; it never extracted body text. A bridge carries **empty shells**. |

Both cc018's 12 VLM chapters and the 9 Google Books records (1905 ch. 389–397) are `textlen=0` identity assertions.

### ★ The real finding — not a bridge at all

> **7,744 stranded records' text is ALREADY in `parsed_acts_fixed.json` under `flagged_acts`, which `ingest_clean.py` silently discards** (`:782-788`, `confident_acts` only).

Real text, already on disk, already in the file ingest reads, dropped by one line. **The largest cheap win in the corpus, hidden behind an architecture problem that did not exist.** Live example: cc018's "1956 ch.10" (really `1957-vol1-56chapters` ch.10) sits in `flagged_acts` with 2,000 chars — dropped purely for being flagged.

### Three corrections to my own picture

1. **"25,514 chain-only chapters" was an artifact** — the chain renumbers (`chapter_int_final`, 13,492 `renumber_status=filled`) while `fixed.json` holds raw garbled `chapter_int`. Same act, different key. Content-matching: **25,514 → 3,243**.
2. **The chain is NOT a superset — it dropped 14 acts with real text** (469–4,876 chars). "Point ingest at `merged.json`" would be a **regression**.
3. **23 volumes have no `parsed_acts_fixed.json` at all** — invisible to ingest regardless; 5 hold **373 records of real text**.

### Revised work order

| # | Item | Why |
|---|---|---|
| **1** | **Stop discarding `flagged_acts`** (with triage) | 7,744 records, real text, already on disk |
| **2** | Reparse with cc019 fixes | subsumes the chain's text gains |
| **3** | 23 volumes with no base parse | 5 carry real text |
| **4** | ~2,033 identity-only records | not a bridge; optional "chapter exists, text pending" markers |

**Lesson, twice in one session: measure the problem before designing the solution.** Same error class as the comma removal — acting on a plausible diagnosis without the number. The first time cost 116 headings; this time it nearly cost an unnecessary architectural component.

---

## 20. Test suite: 8/11 with 3 rotting → **11/11 green**

A dead suite hid for a month because nothing ran everything. Fixed the mechanism *and* the rot.

**NEW `pipeline/run_all_tests.py`** — one command, runs all 11, and critically **distinguishes DEAD from FAIL**. A suite that dies at import never reaches an assertion and reports nothing — it looks like *absence of a problem*. That is exactly how `test_date_parser_fix.py` hid. `smoke_imports.py` could never have caught it: it's AST-based and the broken reference was a *string path*.

**All three "known failures" cleared — same rot class:**

| Suite | Before | After | Cause |
|---|---|---|---|
| `analysis/test_recover_guards.py` | **DEAD** | PASS | `recover_acts.py` does `import config` at module level; loading by path without `pipeline/` on `sys.path` killed it at import |
| `ocr/test_consensus.py` | 8/9 | **9/9** | same |
| `tests/smoke_imports.py` | 2 violations | **0** | **false positive in the checker itself** |

**The `smoke_imports` one is worth recording.** It flagged `analysis/_diag_early5.py` and `_diag_fp.py` as having broken imports of `recover_early`. They don't — both do `sys.path.insert(… / "ingest")` first, and `recover_early` genuinely lives at `pipeline/ingest/recover_early.py`. The checker modelled only two resolution paths (flat sibling, `pipeline/` root) and not the third: **a file that adds its own `sys.path` root**. Fixed in the checker, scoped per-file so it cannot mask a genuine sibling break. **244 internal imports now resolve.**

`KNOWN_FAILING` is now empty **and should stay that way** — a standing known failure is how a real one hides. If something lands there, fix it or write down why it can't be.

---

## 21. ⚠ BRANCH DIVERGENCE — my work was built on stale state

`git push` rejected: **the remote had 17 commits I did not have**, including a `cc018`→`cc020` line of work done on another machine. **Zero file overlap**, so the merge was mechanically clean and the suite stayed 11/11 — but the *content* overlaps badly.

**Session-number collision:** the remote already used **cc019** (2026-06-23, page-continuity audit) **and cc020** (2026-06-29). This session must renumber.

### ★ My Monday packet is materially WRONG

I built it on `ARCHIVES_SCAN_REQUEST_2026-06-22.md`, which has been **superseded twice** since — by `PAGE_CONTINUITY_AUDIT_2026-06-23.md` (deterministic corpus-wide missing-leaf audit) and `SACRAMENTO_SCAN_PACKET_2026-06-29.md`.

| | My packet | Sacramento packet (06-29) |
|---|---|---|
| Printed pages | 15 | **175** (126 high-confidence + 49 inspect) |
| Volumes | 7 | **49** |
| Archivist chapters | 12 | **17** |

Specific errors in mine:
- **1929 ch. 881 is at printed pp. 1974–1975, not 1962–1963.** The June-22 numbers were *"a pre-audit manual estimate"*; the deterministic audit located the actual dropped leaf.
- **1872 absent entirely from my packet** — 9 missing-leaf chapters across four gaps.
- **1985's second leaf (pp. 804–805)** not listed by me.
- **1927's two odd-parity inspect pages** (1940, 1965) not listed.

Conversely **1972 ch. 517 — which I verified — is NOT in their packet.** Both sets are real; reconciliation is in flight.

**Lesson:** I never checked whether the branch was current before building a non-repeatable-trip deliverable on a month-old document.

---

## 22. Reparse diff — RAN, no corpus touched, and it caught two of my own bugs

Harness safety verified end-to-end: **5 sample volumes byte-identical (size + mtime + MD5) before/between/after**, `date-review-worklist.jsonl` unchanged at 576,092 bytes, and a corpus-wide sweep confirmed **0 of 208** `parsed_acts_fixed.json` modified.

```
CORPUS DELTA   volumes ok=216 err=0   wall=105.5s
  chapters gained : 295
  chapters LOST   : 31        <-- REGRESSION
  dates changed   : 8
  enactment paths : {"approved": 70230}   <-- 100% approved. ZERO unsigned/veto.
  baseline fidelity: 208/208 reproduce their on-disk artifact
```

Gains concentrate exactly where predicted: 1858 +38, 1859 +30, 1865-66 +29, 1875-76 +28, 1863-64 +25, 1877-78 +24. Modern volumes gain nothing.

### ★ Bug 1 (mine) — `detect_enactment_path` was called by NOTHING

The distribution came back **100% `approved`, 0 unsigned, 0 veto_override across 70,230 acts**. Cause: `detect_enactment_path()` was defined at `ingest_from_ocr.py:772`, unit-tested, documented as a feature — and **called by nothing but its own tests**. `flush_act` never wrote the field onto the act record.

The date fix worked; the **legally meaningful path distinction was dropped on the floor**. Now wired in, with **record-level** tests (`flush_act` → assert the record carries `enactment_path`), not just function-level ones. **94/94.**

> **A tested function that nothing calls is not a feature.** The unit tests passed the entire time because they invoked it directly.

### Bug 2 — 31 chapters LOST (under investigation)

The fixes were meant to be strictly additive. Prime suspect is the **new resolution guard** in `is_confident_act`. Key distinction being measured: did each chapter *vanish*, or merely move `confident → flagged`? The latter is much milder.

Also suspicious: **1875-76 ch.138 date moves to 1878** — a year that cannot exist in an 1875-76 volume — and 1877-78 ch.252 moves three months. Six other date moves are 1–2 day shifts and plausibly corrections.

**Phase 4 is blocked until these are explained.**

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
