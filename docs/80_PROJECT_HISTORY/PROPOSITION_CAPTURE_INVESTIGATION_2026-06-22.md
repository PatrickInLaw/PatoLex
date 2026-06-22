# Proposition / Initiative-Measure Capture Investigation

**Date:** 2026-06-22
**Author:** Claude Code (research agent)
**Status:** FINDING — durable design doc
**Scope:** Read-only. No data writes. Investigates whether the PatoLex corpus captures
changes to California statutes (and the Constitution) made by **ballot propositions /
initiative measures** (voter-approved, NOT legislative chapters).

---

## VERDICT

**MISSED.** Proposition / initiative-measure changes to statutes (and constitutional
amendments) are currently **NOT captured** in the PatoLex corpus.

- The **source PDFs exist** in the local archive (`*_Measures.pdf`, `*_Initiative.pdf`,
  `*_Constitution.pdf` — 38 + 1 + 58 files respectively under
  `C:\PatoLex-scratch\chief-clerk-archive\`), but
- **none of the 232 `production-*` parses ingest them.** Every production parse targets a
  `*_Chapters` / chapter-bearing volume only. There is **zero** `production-*-measures`,
  `production-*-initiative`, or `production-*-constitution` parse.
- The oracle `ca_chapter_counts.tsv` tracks **only `total_chapters` per legislative
  session** — it has no column for measures, initiatives, or constitutional amendments,
  and by design counts only regular legislative chapters.

Consequently, for any statute amended or enacted by an initiative (e.g. a 1990 initiative
statute), a point-in-time query "what did statute X say on date Y" would return a
**stale / wrong** answer for the window governed by the initiative change, because the
initiative text was never ingested.

This is a **correctness gap with corpus-completeness implications**, not merely a
coverage-breadth nicety: initiatives have **directly amended ordinary codified statutes**
(e.g. Prop-style initiative statutes), so the chaptered-acts-only corpus is missing real,
operative changes to the statutory text from 1911 forward.

---

## 1. Source-document structure (what the volumes actually contain)

From 1911 forward (the initiative process was added to the Constitution in 1911), the
"Statutes of California" volumes are split, in the chief-clerk archive, into **separate
named PDFs per volume** — confirmed by direct file listing and by rendering the actual
section title pages via PyMuPDF:

| Component | Example file | What it is |
|---|---|---|
| Chapters | `1915_Vol1_Chapters.pdf` | The numbered legislative chapters (what we ingest) |
| **Initiative measures** | `1915_Vol1_Initiative.pdf` | Initiative measures filed with the Secretary of State |
| **Measures / Propositions** | `1935_Vol1_Measures.pdf`, `1990_Vol1_Measures.pdf` | Propositions submitted to vote of electors |
| **Constitution** | `1915_Vol1_Constitution.pdf` … (58 files) | The state Constitution as amended that session |
| Index / Tables | `*_Index.pdf`, `*_Tables.pdf` | Finding aids |

### Section title pages — rendered and quoted

**1915 `1915_Vol1_Initiative.pdf` (p.1), verbatim:**
> **INITIATIVE MEASURES**
> FILED WITH
> **SECRETARY OF STATE UNDER PROVISIONS OF SECTION 1, ARTICLE IV, OF STATE CONSTITUTION**

(30 pages — a substantive section, not a stub.)

**1935 `1935_Vol1_Measures.pdf` (p.1), verbatim:**
> **PROPOSITIONS SUBMITTED TO VOTE OF ELECTORS**
> GENERAL ELECTION, NOVEMBER 6, 1934, AND SPECIAL ELECTIONS, DECEMBER 19, 1933, AND AUGUST 13, 1935.

**1990 `1990_Vol1_Measures.pdf` (p.1 / p.4), verbatim section structure:**
> **MEASURES SUBMITTED TO VOTE OF ELECTORS** — Primary Election, June 5, 1990, and General Election, November 6, 1990
>
> **MEASURES ADOPTED**
> - CONSTITUTIONAL AMENDMENT SUBMITTED BY LEGISLATURE
> - **INITIATIVE CONSTITUTIONAL AMENDMENTS**
> - **INITIATIVE CONSTITUTIONAL AMENDMENT AND STATUTE**
> - BOND ACTS SUBMITTED BY LEGISLATURE
> - **INITIATIVE STATUTE SUBMITTED BY LEGISLATURE**
>
> **MEASURES DEFEATED** (same sub-categories)

### How measures are identified (NOT by chapter number)

The 1990 table-of-contents shows each measure carries a **ballot Number** (proposition
number), e.g. 127, 132, 139, 140, 141, 142, 146. Critically:

- **Legislature-referred** measures get a *resolution-chapter* parenthetical, e.g.
  `(Statutes 1990, Resolution Chapter 57, SCA 33)` or `(Statutes 1934, chapter 34)`.
- **Pure initiative** measures get **NO chapter citation at all** — e.g.
  `140. Marine Resources` (Initiative Constitutional Amendment),
  `139. Prison Inmate Labor. Tax Credit.` (Initiative Const. Amendment AND Statute),
  `141. Toxic Chemical Discharge. Public Agencies.` (Initiative Statute).

This is the structural proof that **initiative statutes fall entirely outside the
"Chapter N" keying** our pipeline depends on. They are physically present in the volumes,
in a **separate section**, identified by **proposition number, not chapter number**.

### Location in the volume

These measures sections are bound into **Vol. 1** of each session's set (front/appendix
region, alongside the Constitution reprint), separate from the numbered Chapters PDF and
separate from the Index. They are their own discrete files in our archive.

---

## 2. Did we ingest it? (No.)

- **Production parses:** 232 `production-*` directories exist. Filtering for
  `measure|initiative|constitution|elector|proposition` returns **zero** results.
  Every parse is `*-chapters` or a chapter-bearing `volN`. The `*_Measures.pdf`,
  `*_Initiative.pdf`, and `*_Constitution.pdf` source files were **never run through OCR /
  parse / certify**.
- **Spot-check of a certified parse:** `production-1990-vol1-chapters/parsed_acts_certified.json`
  contains **177 entries**, every one keyed as `"chapter": "1"…"177"` with titles of the form
  `"An act to amend Section … of the … Code"`. Searching the JSON for `"initiative"` → 0 hits;
  `"measure submitted"` → 0 hits. (The 1 "proposition"/2 "elector" hits are inside ordinary
  chapter body text, not measure entries.) So the 1990 chapters parse is **chapters-only**,
  as expected.
- **Oracle TSV (`docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv`):** columns are
  `session_label, session_year, session_type, total_chapters, source_url, confidence,
  session_number, session_kind, canonical_id`. It is a **per-session chapter count only** —
  no measures/initiative/constitutional-amendment dimension. Confirmed: the oracle counts
  **only regular legislative chapters.**

**Conclusion:** initiative measures and voter-approved constitutional amendments are
**simply ABSENT** from the corpus. We have the raw PDFs on disk but no ingested data.

---

## 3. Magnitude (how big is the gap?)

**Authoritative source — California Secretary of State, "Initiatives: Summary of Data,
Between 1912 and July 1, 2025"** (`https://elections.cdn.sos.ca.gov/ballot-measures/pdf/summary-data.pdf`):

- 2,152 statewide **initiatives** titled & summarized for circulation; 401 qualified for the ballot; 396 placed on the ballot.
- **140 initiatives APPROVED by the voters**, broken down as:
  - **40** initiative **constitutional amendments**
  - **86** initiative **statute** revisions
  - **14** initiative **constitutional amendments AND statutes**

So roughly **100 voter-approved INITIATIVES directly touched ordinary STATUTES**
(86 statute + 14 const+statute), and **54 touched the CONSTITUTION** (40 const + 14 both)
— from the **initiative** path alone, 1912–2025.

**Broader proposition context** (initiatives + legislative referrals + referenda),
per Ballotpedia / Wikipedia "List of California ballot propositions":

- ~**1,300** statewide ballot measures decided 1910–2025.
- ~**863** legislatively referred + ~**444** citizen initiatives (qualified for ballot).

Note: legislature-referred measures usually *also* carry a resolution-chapter cite, so some
of those are partially traceable via resolution chapters — but **pure initiative statutes
have no chapter at all** and are the hard, fully-missed core (~100 statute-affecting,
voter-approved initiatives).

**Bottom line on magnitude:** the missed set most relevant to statute correctness is on
the order of **~100 voter-approved initiative measures that changed codified statutes**
(plus ~54 constitutional changes), spread 1911→present. Small in count, but each one is a
real, operative change to the statutory/constitutional text that our chapters-only corpus
does not reflect.

---

## 4. Codes-vs-session-laws nuance (why this matters for reconstruction)

- The **current/official CODES** (Business & Professions, Health & Safety, Elections,
  etc.) reflect **ALL** changes — legislative chapters **and** voter-approved initiative
  statutes — because the codes are the consolidated end-state of the law.
- The **session-law / chapter volumes** we ingest are **primarily the legislative
  product**: numbered chapters from each session. Initiative measures are printed in the
  *same physical volume set* but in a **separate, non-chaptered section**.
- Therefore a **complete point-in-time reconstruction** cannot be built from the Chapters
  PDFs alone. To know what a statute said on a given date, the timeline must also fold in:
  1. legislative chapter amendments (we have these), **and**
  2. **initiative-statute amendments** with their **effective dates** (the day after the
     election, typically — distinct from the legislative chapter effective-date rule).
  Without (2), the reconstruction silently diverges from the true law for any code
  section an initiative touched.

---

## 5. Recommended options

**Option A — Ingest the existing `*_Measures.pdf` / `*_Initiative.pdf` sections (recommended).**
We already have the source PDFs locally (38 Measures + 1 Initiative + 58 Constitution
files). Build a **separate parser track** keyed on **proposition number** (not "Chapter N"),
emitting an `enactment`-like record with `kind = 'initiative_measure'` /
`'voter_const_amendment'`, an effective date derived from the election date, and the
amended code sections. This is the highest-fidelity path and uses material already on disk.
Pre-1911 has no initiatives, so the track only needs 1911→present.

**Option B — Cross-reference against a structured proposition list** (SoS / Hastings UC Law
California Ballot Propositions Database / Ballotpedia) to (i) enumerate the ~140
voter-approved initiatives, (ii) flag which code sections each amended, and (iii) at
minimum **annotate** affected statutes as "modified by Proposition N, effective <date>"
even before full text ingest. Good interim correctness guardrail.

**Option C — Scope decision / disclosure.** If initiatives are deliberately out of scope
for an early milestone, that must be an **explicit, documented limitation** (a statute view
must warn "initiative changes not yet reflected" for affected sections), because silently
returning legislative-only text is a wrong answer to the core product question.

**Option D — Schema follow-up.** Whichever path, the schema/oracle needs a dimension for
non-chapter enactments (proposition number, measure type ICA/IS/both, election date,
effective date) so completeness can be *measured* — today the oracle literally cannot count
what is missing.

---

## Evidence index (files cited)

- Source PDFs: `C:\PatoLex-scratch\chief-clerk-archive\1915_Vol1_Initiative.pdf`,
  `1935_Vol1_Measures.pdf`, `1990_Vol1_Measures.pdf`, plus 38 `*_Measures.pdf`,
  58 `*_Constitution.pdf`.
- Rendered title pages (temp, under scratch): `C:\PatoLex-scratch\_propinv_*.png`.
- Production parse (chapters-only): `C:\PatoLex-scratch\production-1990-vol1-chapters\parsed_acts_certified.json` (177 chapter entries, 0 initiative entries).
- Oracle: `docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv` (total_chapters only).
- Magnitude: CA SoS "Initiatives: Summary of Data" (1912–2025): 140 approved (40 ICA / 86 IS / 14 both).
