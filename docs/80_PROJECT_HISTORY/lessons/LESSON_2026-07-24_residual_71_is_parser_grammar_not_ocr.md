# LESSON 2026-07-24 — The "71 machine-unreadable chapters" are a PARSER GRAMMAR problem, not an OCR problem

**Session:** cc019 · **Status:** verified by direct visual inspection · **Supersedes framing in:** `HUMAN_REVIEW_LIST_2026-06-22.md`, `OCR_RECOVERY_CAMPAIGN_FINAL_2026-06-22.md`

---

## Summary

The 71 residual biennial-era chapters (1866, 1868, 1870, 1872, 1874, 1876, 1878) were characterized as *"chapters the OCR-recovery campaign could not resolve by machine (Tesseract + Surya + Qwen2.5-VL all miss them — almost always tiny multi-act entries with no cleanly-printed running head)."*

**That characterization is wrong.** The pages are clean, native 300 DPI, and trivially legible. Three separate mechanical defects — none of them OCR-related — account for the misses. **None is fixable by better OCR, a better VLM, or a re-scan; all three are likely fixable deterministically for zero model tokens.**

## Evidence

Two independent checks, same session:

1. **Resolution/legibility audit.** All seven biennial PDFs are uniform **native 300 DPI, 1-bit DeviceGray, no text layer**. Headings are crisp; 600 DPI upsampling holds serifs, italics, and Roman numerals. 300 DPI *is* the native ceiling — re-rendering higher gains nothing.
2. **Blind read by Opus 5** of 4 residual targets from 200 DPI renders, with expected values withheld until after transcription. **3 of 3 legible-page targets read correctly on first pass**, including full act title and approval date:

| Target | Read | Correct |
|---|---|---|
| 1866 ch. 143 | `CHAP. CXLIII.` — *An Act for the relief of J. B. Cook, County Treasurer of Lake County* | ✅ |
| 1876 ch. 91 | `CHAP.—XCI.` — *An Act to provide for the funding of the levee indebtedness of the City of Marysville* · [Approved February 18, 1876] | ✅ |
| 1878 ch. 173 | `CHAP.—CLXXIII.` — *An Act to provide for the building of a school house in the Fresno City School District…* · [Approved March 9, 1878] | ✅ |
| 1872 ch. 125–128 | (no heading on page — see defect 3) | list defect, not a read failure |

---

> **UPDATE 2026-07-24 (same session, after the full contents-anchored recovery of all 71):** defect 1 is broader than first written — there are **three** enactment paths, not two, and the wording is unstable. Two further structural classes were found (D and E below). All 71 residual chapters were recovered; see `RESIDUAL_71_CONTENTS_RECOVERY_2026-07-24.md`. Defects 1 and 2 are **fixed and tested**; defect 3 is **partially** fixed (detection + widening; the forward-scan remains open).

## Defect 1 — Acts that became law WITHOUT the Governor's signature carry no `[Approved …]` bracket

**1866 ch. 143** has **no approval bracket at all.** In its place the printer set:

> JOHN YULE, *Speaker of the Assembly.* / S. P. WRIGHT, *President of the Senate pro tem.*
> "This bill having remained with the Governor ten days, (Sundays excepted,) and the Senate and Assembly being in session, **it has become a law** this twenty-seventh day of February, A. D. eighteen hundred and sixty-six."

The immediately following act, ch. 144, carries a normal `[Approved February 28, 1866.]` and parsed without trouble.

**Any act-detection or date-extraction anchored on `[Approved` is structurally blind to unsigned-enactment acts, regardless of scan quality.** This is a whole *class* of California enactment — a constitutionally distinct path to law — that the grammar does not model.

**Fix:** add an alternate enactment-date anchor matching the ten-day-lapse block (`became a law` / `having remained with the Governor`), and record the enactment path as a field. Do **not** treat a missing `[Approved …]` as a parse failure.

**Downstream risk:** `chaptered_date` for these acts is not merely missing — it must come from the lapse notice, which is spelled out in words (*"this twenty-seventh day of February, A. D. eighteen hundred and sixty-six"*), not the bracket's numeric form. This likely intersects the known open item *"Roman-numeral heading + `chaptered_date` parser fix (51 acts wrong date, correct text)."*

## Defect 2 — Chapter-heading punctuation varies by era

| Era observed | Printed form |
|---|---|
| 1866 | `CHAP. CXLIII.` — period + **space** |
| 1876 | `CHAP.—XCI.` — period + **em dash**, no space |
| 1878 | `CHAP.—CLXXIII.` — period + **em dash**, no space |

A pattern anchored on `CHAP\.\s+[IVXLCDM]+` matches the 1866 form and **misses every em-dash volume.** Note this compounds with the known 1861–66 italic-`CHAP.` consensus bug already recorded in memory — the heading token is proving to be the single most variable element in the corpus.

**Fix:** normalize the separator class to `[\s—–\-]*` (space, em dash, en dash, hyphen, or nothing) between `CHAP.`/`CHAPTER` and the numeral, and add a regression fixture per era.

## Defect 3 — `HUMAN_REVIEW_LIST` bracket ranges break on long acts

`HUMAN_REVIEW_LIST_2026-06-22.md` lists **1872 ch. 125–128** as a *"multi-act cluster"* at candidate PDF pages **224–227**.

Inspection: p225 and p226 (printed 135–136) are **body text — SEC. 5 through SEC. 15 — of ch. 124**, a long roads act that runs well past p227. Chapter 125 does not begin anywhere in the stated window.

The candidate ranges are derived from the OCR'd `source_page` of neighbouring *present* chapters, which silently assumes chapters occupy adjacent pages. **That assumption fails whenever the bracketing chapter is a long act.** The label "multi-act cluster" is also actively misleading — it describes the opposite of what is on the page.

**Consequence for the human-review plan:** a reviewer opens the range, finds no heading, and cannot distinguish *"this chapter is missing"* from *"this range is wrong."* Wide/unreliable flags do not cover this case — 1872 ch. 125–128 is **not** flagged.

**Fix:** derive brackets from the *end* of the preceding act (scan forward for the next heading token) rather than from the preceding act's start page; or simply widen forward until the next detected heading.

---

## What this changes

1. **Re-order the work.** Fix the three defects and re-run the recall pass **before** spending any model or human time on the 71. The cost is a parser change, not tokens. Expect the residual to drop materially — defects 1 and 2 are systematic and will recover chapters in bulk across all seven volumes and likely beyond.
2. **Retire the "machine-unreadable" label.** It is factually wrong and it mis-routes the work to human transcription (or to an archive scan) when the actual fix is in code. `HUMAN_REVIEW_LIST_2026-06-22.md` and `OCR_RECOVERY_CAMPAIGN_FINAL_2026-06-22.md` should be corrected.
3. **The 99.9% figure is sound but its residual is mis-attributed.** 95,923/96,002 stands. What is wrong is the *explanation* of the remaining 79 — most of the 71 are recoverable in code, not lost to bad paper.
4. **These defects are almost certainly not confined to the residual.** A parser blind to unsigned enactments and to em-dash headings has been running across the entire OCR era. Chapters it *did* find may still carry a wrong or null `chaptered_date`, and acts may have been mis-attributed. **Audit scope should extend past the 71.**

---

## Defect 1, corrected and widened — THREE enactment paths

| # | Path | Printed forms observed | Was modeled? |
|---|---|---|---|
| 1 | Signed by the Governor | `—approved February 18, 1876` | ✅ |
| 2 | **Became law unsigned** (10-day lapse) | `became law by the operation of Constitution` · `became law by operation of the Constitution` · `became a law by constitutional provision` | ❌ |
| 3 | **Passed over the Governor's veto** | `became a law by a constitutional majority of both Houses, over the Governor's objections` | ❌ |

**The wording is not stable — three phrasings for path 2 alone.** Anchor on the stable core `bec[ao]me (a )?law` and treat the qualifier as free text.

**A vowel cost a test.** The body prints *"it has **become** a law"*; the contents prints *"**became** law"*. A first-draft regex using a bare `become` passed the body fixture and silently failed every contents row. **Fixtures must come from real printed text, not invented strings** — an invented fixture would have used one spelling and hidden the bug.

**These cluster.** 1870 ch. 428, 429, 430, 431 are four *consecutive* unsigned enactments dated April 3, 1870 — bills passed at the close of session hit the ten-day window together. That is why they concentrate in the residual rather than scattering.

**Paths 2 and 3 are constitutionally distinct and must be stored distinctly**, not collapsed into "not approved".

## Defect D — headings that never say "An Act"

`is_confident_act` required `AN_ACT_RE`. Two real counter-examples:

- **1876 ch. 508** — `[An amendment to the Code, but which also repeals the Act of March 28, 1874, in relation to solvent debts]` · S.B. 391 · **printed p. 772**. It *has* a page — the act is printed in this volume; only its heading is unconventional.
- **1870 ch. 427** — `Charter of the City of Stockton—An Act to reincorporate the City of Stockton`.

**Fix:** accept the enacting clause (*"The People of the State of California … do enact as follows"*) as an alternative to the literal "An Act". The enacting clause is the legally operative signal; the title wording is a printing convention.

## Defect E — a whole class that is not in these volumes at all

`[See volume of Amendments to the Codes.]` is a **common, legitimate contents entry**, not an artifact. On a single 1876 contents page, nine chapters carry it (488, 490, 497, 498, 499, 502, 504, 505, 506).

Five of the 71 residual chapters are in this class: **1874 ch. 587 and 679, 1876 ch. 306, 497, 498.** They were enacted (several still carry bill numbers) but their text was printed in the companion *Amendments to the Codes* volume.

**Consequence: the residual can never reach zero as currently defined.** No re-OCR, re-reading, or archive scan of the statutes volumes will ever produce them. They need reclassification against a separate source, not recovery.

## Defect F — the printed volumes contradict themselves, in BOTH directions

- **1874 ch. 261:** the contents is right (p. 358); the **body running head** is misprinted `CHAPTER CLXI.` where `CCLXI` belongs.
- **1866 ch. 342:** the **contents** is misprinted `242`; the body is fine.

**Neither the contents nor the body running heads can be trusted alone. Agreement between them is the reliable signal.** This is a durable rule for the whole corpus, not just these seven volumes, and it is the cheapest available cross-check — both sources are already in every volume.

---

## What was actually fixed (2026-07-24)

| Defect | Status | Evidence |
|---|---|---|
| 2 — em-dash headings | **FIXED** | canonical regex 5/9 → **9/9** on real printed forms, 0 false positives. `ingest_from_ocr.py:393`, `chapter_reconstruct.py:29` |
| 1 — three enactment paths | **FIXED** | new `LAPSE_SPELLED_RE` / `LAPSE_NUMERIC_RE` / `detect_enactment_path` / spelled-out-date parser. `test_enactment_paths.py` **27/27** |
| D — non-"An Act" headings | **FIXED** | `is_confident_act` accepts the enacting clause |
| 3 — bracket ranges | **PARTIAL** | truthiness bug fixed, magic numbers documented, implausible-span detection added (catches the real 1872 case). `test_residual_bracket.py` **16/16**. **Forward-scan NOT implemented** — needs page text `bracket_for` does not receive |
| E — Amendments-volume class | **IDENTIFIED, not fixed** | needs a source outside these volumes |
| F — self-contradicting volumes | **IDENTIFIED** | cross-check contents against body |

**Also repaired en route:** `test_date_parser_fix.py` had been **dead since the module reorg** (zero live coverage on `parse_act_date`), and `5080/parse_born_digital.py` had been **unloadable** for the same reason. Three more files hardcode `C:\github\PatoLex\…`, a root that does not exist; `_residual_manifest.py` had two such roots and now honours `PATOLEX_LOCATION_ROOT`.

**The repo has no CI** — no `pytest.ini`, `pyproject.toml`, `conftest.py`, or workflows. Every test is hand-invoked, which is why a dead suite went unnoticed. `smoke_imports.py` cannot catch it (AST-based; the broken reference was a string path).

---

## ★ Hans FAIL and what it corrected (2026-07-25)

An adversarial pass ran the new regexes **against the real corpus over SSH** — millions of lines of actual 19th-century statute text — rather than against a hand-written fixture set. It returned **FAIL**. Full report: `audits/2026-07-25_030205-verify-phase-report.md`.

### The methodological lesson (the important part)

**The commit claimed "0 false positives against body text." That claim was false.** It was measured against a **hand-written negative set of six lines**, not the corpus. Against real text, the separator class produced **55 confirmed false-positive header matches** on back-of-book index entries (`"crabs, 47"`, `"charges, 1192"`).

**A regex change to a corpus parser is not verified until it has been run over the corpus.** Unit fixtures prove a pattern *can* match what you intended; only the corpus shows what *else* it matches. This applies to every remaining parser change in this project.

### HANS-1 (severe) — cross-act date poisoning

On `production-1865-66` page 24 — a printed CONTENTS page, **exactly the source type the feature reads** — the numeric lapse regex captured **chapter 380's *approved* date as chapter 379's *lapse* date.** The `[^.]{0,120}?` qualifier ran past a page-number column and a second act's title.

**The ±3-year clamp cannot catch this**: the stolen date is the same year, only weeks off. Silent, plausible, and wrong — the worst possible failure for a corpus ingested exactly once.

**Fix:** the gap now forbids periods, **digits**, `An Act`, and `CHAP`, and is tightened 120 → 80 chars. The qualifier is always prose and never legitimately contains a digit, so excluding digits is principled rather than a hack — it blocks the page-number column that caused the poisoning.

### HANS-2 — the comma in `_HDR_SEP`

The comma was **speculative** — no printed form requires it. Removed. Only whitespace and dashes occur between the glyph and the numeral.

### HANS-3 — a third un-synced `HEADER_RE`

`pipeline/5080/reparse.py` carried a third live copy, still em-dash-blind. It is a dead/tombstoned module, but leaving a broken copy invites a future copy-paste. **Synced**, with a comment saying why.

### HANS-4 — smaller, real

- `spelled_ordinal_to_int` accepted **impossible days 32–39** (`"thirty-fifth"` → 35). Clamped to 21–31.
- `is_confident_act`'s new enacting-clause fallback made unanchored `ENACT_MARKER_RE` **load-bearing**. Now the clause must appear in the **first 2000 chars** (an enacting clause is printed under the title; a match deep in the body is a quotation of another act), and an explicit **`RESOLUTION_RE` guard** rejects the Concurrent/Joint Resolutions section that every one of these volumes carries after the chapters.

### Doc-claim check

Hans also challenged the headline "71/71 recovered" as potentially overclaiming, since 5 are Amendments-volume redirects and **no statutory body text was recovered for any of them**. The doc already states both limits explicitly — recovery is of **identity** (number, title, date, bill, page), and body-text OCR remains owed. Keeping the headline, with those qualifications kept prominent.

## Related

- Confirms and generalizes `[[early-era-headers-consensus-bug]]` — the heading token is the corpus's most variable element across eras.
- Consistent with `[[dictionary-membership-too-blunt]]`: the true defect rate is dominated by systematic grammar gaps, not random character error.
- The 1874 ch. 261 case (printed `CHAPTER CLXI.`, leading `C` absent from the physical typesetting) is a **fourth**, genuinely irreducible class: a defect in the paper itself. See `ARCHIVES_VISIT_PACKET_2026-07-27.md` §4. No parser or camera fixes that one — only neighbour-context inference.
