# Code-Amendment Parse — Design (Method A: change_event targeting codified provisions)

**Date:** 2026-06-02
**Author:** cc (parser-validate session)
**Status:** DESIGN ONLY — not implemented. No DB writes, no schema changes made.
**Source studied:** Real banked OCR of `production-1875-76-code/ocr_consensus/page_ocr_results.json`
(120 pages present, page indices 2–134; "Amendments to the Codes," 21st Legislature, 1875–76).
`production-1873-74-code` was **not present locally** at study time (still OCRing) — skipped.

---

## 1. What a "Amendments to the Codes" volume actually is

This volume is **not** new free-standing law. It is a session-law volume whose every chapter
is an act that **edits the existing four Codes** (Civil, Penal, Political, Code of Civil
Procedure) enacted at the 1872 recodification. Each chapter is a directive: "amend Section X
of the Y Code so as to read as follows: «new text»." Point-in-time CODIFIED law is therefore
built by **applying these directives as change_events against the 1872 code-section baseline** —
NOT by inserting each chapter as a stand-alone `act_section` provision (which is what the
existing general-statutes parser does, and which is wrong for this corpus).

### 1.1 Unit structure (verified against page 34, agreement 0.680)

A complete amendment act, exactly as OCR'd (em-dash garble `—`/`Cuap`/`Cuar` is OCR noise
for `Chap.`):

```
Cuap. XVI.—An Act to amend sections seven hundred and fifty-
one and seven hundred and Aty-sie of the Political Code, in
reyard to deputies for the Clerk of the Supreme Court.
                              [Approved January 20, 1876.3
The People of the State of California, represented in Senate and
Assembly, do enact as follows :

Secrron 1. Section seven hundred and fifty-one of the
Political Code of this State is hereby amended so as to read
as follows:

751. He may appoint two deputies.

Sec. 2. Section seven hundred and fifty-six of the Polit-
ical Code of this State is hereby amended so as to read as
follows:

756. The annual salary of the Deputy Clerks is eighteen
hundred dollars each. The salary of one of said deputies
shall be paid by the City and County of San Francisco.

Sze, 8. This Act shall take effect immediately.
```

The anatomy of every act:

| Element | Pattern (idealized) | OCR reality |
|---|---|---|
| **Chapter header** | `Chap. <Roman>.—An Act to amend section(s) <spelled-number[s]> of the <Code> Code[, relating to ...]` | `Cuap./Cuarv./Guar.` garbles; em-dash garbled; section numbers **spelled in words** |
| **Approval line** | `[Approved <Month> <Day>, <Year>.]` | bracket close OCR'd as `.3`, `.)`, `.]` |
| **Enacting clause** | `The People of the State of California ... do enact as follows:` | reliable anchor (`ENACT_MARKER_RE` already matches) |
| **Per-section directive** | `SECTION N. Section <spelled-number> of the <Code> Code [of this State] is [hereby] amended so as to read as follows:` | `Secrron`/`Sec.`/`Bic.`/`Sze.` garbles; **or** anaphoric `of said Code` |
| **New section text** | begins with the **section number as a printed numeral** then the replacement body, e.g. `751. He may appoint two deputies.` | margin shoulder-notes ("Deputies.") leak inline |
| **Operative clause** | `Sec. N. This Act shall take effect immediately.` / `... from and after its passage.` | standard |

### 1.2 Multiple sections per act — and the "said Code" anaphora

One act amends **one or many** sections. The **target code is named in the act title** and then
each internal directive either re-names it explicitly (`of the Political Code`) or refers back
anaphorically (`of said Code`). Verified counts across the 120 present pages:

- `of said Code`: **59**   (anaphoric — resolves to the code named in the enclosing act title)
- `of the Political Code`: **76**
- `Code of Civil Procedure`: **57**
- `of the Penal Code`: **17**
- `of the Civil Code`: **11**
- chapter headers (`Cuap/Chap`): **89**

A multi-section act with `said Code` back-reference, verified on pages 21→24 (one act spanning
≥4 pages, amending Political Code §§335, 3651, 3694, 3696):

```
Sec. 3. Section three hundred and thirty-five of said Code is amended to read as follows:
335. The reports must be delivered by the Superintendent of State Printing as follows: ...
Sec. 5. Section three thousand six hundred and ninety-four of said Code is amended so as to read as follows:
3694. If the County Auditor fails to forward to the State Board of Equalization ...
Sec. 6. Section three thousand six hundred and ninety-six of said Code is amended so as to read as follows:
3696. Between the first and third Mondays in September ...
```

There are also **repeal** directives, not just amend — verified on page 22:

```
Cuar. DLXXVII—An Act to amend and also to repeal certain sections of the Political Code,
relating to the State Board of Equalization.
                              [Approved April 1, 1876.]
```

So `action` is not always `amend`: the corpus contains `amend`, `repeal`, `amend-and-repeal`,
and (occasionally) `add a new section`.

---

## 2. What the EXISTING STAGE5 parser does with this volume (run as-is)

Ran `parse_volume` logic (via throwaway import of `pipeline/5080/ingest_from_ocr.py`,
post the ordinal-`d` fix) over `production-1875-76-code`:

- **confident = 68, flagged = 4** (94% confident), pages = 120.
- It correctly detects each `Cuap. <Roman>` header as an act, parses the Roman chapter number
  (e.g. ch 571, 577), parses the `[Approved ...]` date, and grabs the title line.
- Sample confident parse: `ch=571 date=1876-04-03 title='Cuar. DLXXI.—An Act to amend an Act
  entitled an Act to...'`; `ch=577 date=1876-04-01 title='Cuarv. DLXXVII—An Act to amend and
  also to repeal certain...'`.
- Flagged are OCR garbles (e.g. `Cuarp. DXXTX.` → bad Roman `DXXTX`; section numbers spelled
  out so no date confusion). 

**Verdict:** the chaptered-act parser **partially works** — it correctly segments acts and dates.
But it is **semantically wrong** for this corpus: it would ingest each chapter as a brand-new
`provision (unit_type='act_section')` + an `enact` `change_event`, exactly as it does for
uncodified session law. That treats an *amendment to Civil Code §X* as if it were a new
free-standing statute. For point-in-time CODIFIED law we need the amendment to **mutate the
existing code-section provision**, not create a parallel act_section. **A distinct parse path
is required** — the act-segmentation front half can be reused; the per-section emission must be
replaced.

---

## 3. Proposed design — Method A (directive → change_event on an existing provision)

### 3.1 Reuse the act segmentation, add a code-amendment sub-parser

1. **Segment acts** with the existing `header_starts_act` / `flush_act` machinery (already proven
   here). For each act capture: chapter number, approval date (operative date), enacting marker,
   and the **target code named in the title** (`CODE_IN_TITLE_RE`: `of the (Civil|Penal|Political)
   Code | Code of Civil Procedure`).
2. **Within each act**, split on internal directive headers
   (`Sec(?:tion|rron)?\.?\s*\d+\.` tolerant of OCR garbles) into per-section *directives*.
3. For each directive, parse:
   - **action**: `amended so as to read` → `amend` (replace text); `repealed` → `repeal`;
     `is amended by adding` → `add`.
   - **target code**: explicit (`of the <X> Code`) else **resolve `said Code` to the act-title
     code** (the anaphora carrier).
   - **target section number**: the spelled-out number in the directive
     (`section seven hundred and fifty-one` → 751) — must be converted from English cardinal
     words to an integer. Cross-check against the **printed numeral** that opens the new text
     (`751.`), which is the higher-confidence signal; flag on mismatch.
   - **new text**: everything from the printed numeral up to the next `Sec. N.` directive or the
     operative clause, with margin shoulder-notes stripped.

### 3.2 Mapping to the event-sourced / point-in-time schema

Each directive becomes **one `change_event` targeting the existing code-section provision**:

- **Resolve target provision**: look up the `provision` whose `designation_history` row matches
  `(code = '<Civil|Penal|Political|CCP>', section_number = <N>)` valid at the act's operative
  date. This is the 1872-baseline provision (or a later amendment's successor).
- **`change_event`**: `action = 'amend' | 'repeal' | 'add'`, `provision_id = <resolved>`,
  `new_text = <replacement section text>` (literal OCR, `amend`/`add`); `operative_date =
  <approved date>`; `source_document_id = <this code volume>`; `enactment_id = <the chapter act>`;
  `page_ref`, `in_act_order`, `trust_level='ocr_uncertain'`.
- **`enactment`**: ONE row per chapter (the amending act), `kind='statute'`, chapter_number =
  Roman→int, citation `Stats. 1875-76 ch. <N>`. The enactment is the *vehicle*; the change_events
  are the *edits*.
- **`provision` / `designation_history`**: **do NOT create** new `act_section` provisions for
  these chapters. The provisions already exist from the 1872 baseline; the amendment only adds a
  new `provision_version` (the new text, `valid_range` opening at the operative date) and a
  `change_event`. If `add`, a new code-section provision IS created (new section number).
- **`provision_version`**: insert the new section text with `valid_range = [operative_date, )`
  and close the prior version's range at `operative_date` (point-in-time supersession).

This is **Method A** as specified: parse the directive "amend Section X of the Y Code" → apply
new text to that existing provision as of the operative date, rather than minting a standalone
`act_section`.

---

## 4. Open questions (must resolve before implementing)

1. **1872 baseline dependency (hard blocker).** Method A requires the four 1872 Codes to already
   be loaded as `provision` + `designation_history` rows keyed by `(code, section_number)`. Until
   the 1872 recodification baseline is ingested (per the Gate-D build order: lay 1850–71 pre-code,
   then 1872 as a recodification event), there is **no target provision to resolve**. The 1875–76
   amendments cannot be correctly ingested before 1872 exists.
2. **Section identity / lineage & target resolution.** How do we resolve `section_number → provision_id`
   when a section may itself have been amended in an earlier 1873–74 volume? The lookup must be
   **point-in-time** (the provision version valid just before this act's operative date), and must
   tolerate the fact that section numbers are stable across amendments but text is not.
3. **Spelled-out section numbers.** Targets are English cardinal words
   ("three thousand six hundred and ninety-four" → 3694). Need a robust words→int converter; the
   printed numeral opening the new text (`3694.`) is the cross-check. What to do on mismatch
   (OCR garble in either) — flag, don't guess.
4. **`said Code` anaphora reliability.** Resolution depends on correctly parsing the code named in
   the act title. If the title OCR is garbled (e.g. missing "Political"), the whole act's
   directives lose their code anchor. Need a confidence gate + flag path.
5. **Repeal / add / "amend and repeal" actions.** Not all directives are `amend`. Page 22 shows an
   "amend and also to repeal certain sections" act. The sub-parser must classify action per
   directive, and `repeal` produces a `change_event` with no `new_text` and a closed
   `provision_version` range.
6. **Multi-section act boundaries vs. page splits.** Acts span many pages (the §335/§3651/§3694/§3696
   act ran pages 21–24). Directive splitting must survive page-boundary line breaks and embedded
   tables (page 23 contains a mangled assessment-book table). Tables will OCR poorly — flag those
   sections rather than committing garbage as authoritative code text.
7. **Mid-volume "Amendments to the Codes" vs. ordinary statutes.** Some 1870s volumes mix code
   amendments with ordinary session law. Need a per-act classifier (does the title say "amend
   section(s) ... of the <X> Code"?) to route each act to the code-amendment path vs. the existing
   uncodified-statute path.

---

## 5. Recommendation

Do **not** ingest the code volumes through the current STAGE5/STAGE6 path — it would create
spurious `act_section` provisions. Build the code-amendment path **after** the 1872 baseline is in
the DB, reusing the (now-validated) act segmentation but replacing per-section emission with the
directive→change_event mapping above. The 1875–76 OCR studied here is clean enough (94% confident
act segmentation, dates parsing) that the limiting factor is the **1872 baseline + target-resolution
logic**, not the OCR.
