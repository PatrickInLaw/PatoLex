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

## Related

- Confirms and generalizes `[[early-era-headers-consensus-bug]]` — the heading token is the corpus's most variable element across eras.
- Consistent with `[[dictionary-membership-too-blunt]]`: the true defect rate is dominated by systematic grammar gaps, not random character error.
- The 1874 ch. 261 case (printed `CHAPTER CLXI.`, leading `C` absent from the physical typesetting) is a **fourth**, genuinely irreducible class: a defect in the paper itself. See `ARCHIVES_VISIT_PACKET_2026-07-27.md` §4. No parser or camera fixes that one — only neighbour-context inference.
