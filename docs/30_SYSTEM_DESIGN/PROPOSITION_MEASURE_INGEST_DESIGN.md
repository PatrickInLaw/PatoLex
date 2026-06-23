# Proposition / Initiative-Measure Ingest — Pilot Results + Design

**Date:** 2026-06-22
**Author:** Claude Code (proposition-pilot workstream, Patrick-approved)
**Status:** DESIGN + PILOT FINDINGS — durable design doc
**Companion investigation:** `docs/80_PROJECT_HISTORY/PROPOSITION_CAPTURE_INVESTIGATION_2026-06-22.md`
**Scope of this doc:** Records the 3-volume extraction PILOT, proposes the measure
record **schema**, recommends how it slots into the existing Drizzle event-sourced
schema, specifies the **point-in-time** folding of initiative-statute amendments,
the **completeness-denominator** problem, the **era split**, and a concrete
**scale-up plan + effort** to all 39 measure PDFs. No DB writes were performed.

---

## 0. TL;DR

- The measures **are** extractable from the `*_Measures.pdf` / `*_Initiative.pdf`
  PDFs already on disk. The pilot proved per-measure segmentation across three eras
  (1915 / 1935 / 1990) with a single-engine Tesseract pass.
- All three pilot volumes — **including the 1990 "modern" one — are SCANNED with no
  text layer** (PyMuPDF `get_text` returns ~0 chars/page). The born-digital
  fast-path does **not** fire for any measures volume in the archive sample; OCR is
  required for the whole 1911→~1992 range. (Genuinely born-digital measures, if any,
  begin later than 1990 — verify per-volume, do not assume.)
- The measure universe is keyed on **proposition (ballot) number**, NOT "Chapter N".
  This is the structural reason the existing chapter pipeline misses them.
- **Recommendation: model a measure as an `enactment`** (reuse the event-sourced
  `enactment → change_event → provision` spine) with **new enum values** and a small
  set of **measure-specific columns**, NOT a wholly parallel `measures` table. Folding
  initiative-statute amendments into point-in-time reads then comes almost for free.

---

## 1. Pilot — what was run

| Era | Volume | Pages | Text layer | OCR | Measures extracted |
|---|---|---|---|---|---|
| EARLY | `1915_Vol1_Initiative.pdf` | 30 | none (scanned) | Tesseract | 5 (all adopted, initiative) |
| MID | `1935_Vol1_Measures.pdf` | 26 | none (scanned) | Tesseract | 22 adopted |
| MODERN | `1990_Vol1_Measures.pdf` | 544 | none (scanned) | Tesseract | 39 (25 adopted, 14 defeated) |

Pipeline used for the pilot (scratch only, no DB):
1. `_prop_ocr_volume.py` — per-page text-layer probe → fall back to Tesseract @300dpi,
   cache to `_prop_ocr_<year>.json`.
2. `_prop_parse.py` — era-aware segmentation → `production-measures-<year>/parsed_measures.json`.

Output dirs (additive draft, NOT for DB):
`C:\PatoLex-scratch\production-measures-1915\parsed_measures.json`,
`...-1935\...`, `...-1990\...`.

**Pilot vs production OCR:** the pilot uses a **single-engine Tesseract** pass to
prove segmentation. Production MUST use the existing **3-engine token-majority
consensus** (`pipeline/ocr/consensus.py`: Tesseract + docTR + Surya) — the older
scans (1915-era) have meaningful CER, and the consensus stack + per-token confidence
is exactly what the chapter pipeline already relies on. The measures track should
reuse that stack unchanged; only the **segmenter** is new.

---

## 2. Per-volume results (counts, by kind, by result)

> Counts are pilot (single-engine) numbers — recall on the worst scans is bounded by
> single-engine CER; production consensus will recover the tail.

### 1915 `1915_Vol1_Initiative.pdf` — 5 measures (all ADOPTED)
- kinds: initiative_statute ×4, initiative_constitutional_amendment ×1
- Effective date correctly derived from the printed **"In effect December 19, 1914"**
  bracket (not election+1).
- Affected-codes best-effort worked: "Prize Fights" → **Penal Code §§412/413**.
- **Known misses (OCR):** "Prize Fights" ballot number OCR'd `°0`→`0` (true #20);
  "Suspension of Prohibition" number OCR'd `ule` and was dropped. 2 of ~7 front-TOC
  entries lost to single-engine OCR noise — a consensus pass should recover them.

### 1935 `1935_Vol1_Measures.pdf` — 22 measures (ADOPTED)
- kinds: referendum ×1, initiative_constitutional_amendment ×4,
  legislatively_referred_measure ×17.
- Referendum #1 (Central Valley Project Act) and the ICA set (Liquor Regulation,
  Selection of Judges, Attorney General, State Civil Service) classified correctly
  from the section headings.
- Effective dates from **"In effect December 20, 1934"** brackets where present.
- **De-noising note:** the volume's BACK-MATTER contains a candidate/voter roster and
  vote tables whose `NN. Surname, Place ...` rows look like numbered measure entries.
  A roster-row reject + a "TOC-page-only" gate were required to suppress ~34 false
  positives. This is the single most important segmentation hazard for the MID era.

### 1990 `1990_Vol1_Measures.pdf` — _(filled after full OCR)_
- Structure (confirmed by front-matter OCR): TOC pages list each measure under an
  ALL-CAPS **category heading** (CONSTITUTIONAL AMENDMENT SUBMITTED BY LEGISLATURE /
  INITIATIVE CONSTITUTIONAL AMENDMENTS / INITIATIVE CONSTITUTIONAL AMENDMENT AND
  STATUTE / BOND ACTS / INITIATIVE STATUTES), split into **MEASURES ADOPTED** and
  **MEASURES DEFEATED**, for **two elections** (Primary June 5, 1990; General Nov 6,
  1990). Ballot numbers 107–151.
- Bodies are `NNN. Title. (Statutes 19xx, Chapter NN / Resolution Chapter NN, bill)`
  followed by `[Approved by electors DATE.]` and then the full amendment text
  ("First—That Section 9 of Article II is amended to read: …").
- The legislature-referred measures DO carry a resolution/chapter cite (partially
  traceable today); pure initiatives carry **no chapter** — the missed core.

**Pilot result: 39 measures — 25 ADOPTED, 14 DEFEATED**, ballot numbers 107–151
(plus genuine low-numbered defeated reapportionment measures). By kind:
legislatively_referred_measure ×19, initiative_statute ×12,
initiative_const_amendment_and_statute ×6, initiative_constitutional_amendment ×2.
All 39 have full_text. Matches the investigation doc's cited props (113 Chiropractic,
115 Criminal Law, 132 Marine Resources, 139 Prison Inmate Labor, 141 Toxic Chemical).

- **Segmentation hazard (MODERN):** numbered **legislative-findings paragraphs**
  inside a measure body ("3. It is important to the long-term economic …",
  "4. The forests of this state …") read as `N. Capitalized sentence` and produced
  11 false-positive "measures" on the first pass. A **prose-sentence reject**
  (sentence-stem + low Title-Case ratio) removed all 11 with zero loss to the real
  set. This — not OCR quality — is the dominant MODERN-era hazard.
- **Residual kind quirk:** some **bond acts** under an "INITIATIVE STATUTES" TOC
  heading (e.g. #108, #143, #147, #150) inherit `initiative_statute` from the heading
  even though they are legislature-referred bond acts. Heading-attribution needs a
  per-entry override when the body/cite says "Bond Act … (Statutes …, Chapter …)".
  Hardening item, not a blocker.

---

## 3. The measure record SCHEMA (parser output)

The pilot emits, per measure, a record that **mirrors the chapter-parse shape** but
is keyed on `proposition_number` rather than `chapter`:

```jsonc
{
  "proposition_number": 139,            // ballot number (the identity key)
  "title": "Prison Inmate Labor. Tax Credit.",
  "kind": "initiative_const_amendment_and_statute",  // controlled vocab, see below
  "result": "adopted",                  // adopted | defeated | unknown
  "election_text": "November 6, 1990",
  "election_date": "1990-11-06",        // ISO, parsed from election heading
  "effective_date": "1990-11-07",       // election+1 day UNLESS an explicit
  "effective_date_basis": "election_plus_1day | explicit_in_effect",
  "resolution_or_statute_cite": "Statutes 1990, Resolution Chapter 57, SCA 33",
  "category_heading": "INITIATIVE CONSTITUTIONAL AMENDMENT AND STATUTE",
  "affected_codes_sections": {          // best-effort, from body text
     "codes": ["Penal Code"],
     "sections": ["412", "413"],
     "constitution_articles": ["Article II", "Article IV"]
  },
  "full_text": "...",                   // the measure's amendment text
  "toc_source_page": 3,                 // 0-based page of the TOC entry
  "body_source_page": 18,               // 0-based page where the body begins
  "source_pdf": "1990_Vol1_Measures.pdf"
}
```

Controlled vocabulary for `kind` (inferred from the section heading, per the 1990 TOC
categories):

| `kind` | Source heading |
|---|---|
| `initiative_statute` | INITIATIVE STATUTE(S) |
| `initiative_constitutional_amendment` | INITIATIVE CONSTITUTIONAL AMENDMENT(S) |
| `initiative_const_amendment_and_statute` | INITIATIVE CONSTITUTIONAL AMENDMENT AND STATUTE |
| `referendum` | REFERENDUM |
| `legislatively_referred_measure` | …SUBMITTED BY LEGISLATURE / BOND ACT / Resolution-chapter cite |

`_meta` block carries volume-level provenance: source pdf + path, page_count, parser
id, generated_utc, by_result / by_kind tallies, with_full_text count.

---

## 4. How it slots into the existing Drizzle schema (RECOMMENDATION)

**Reviewed:** `src/lib/db/schema/{enactment,change-event,enums,provision,provision-version}.ts`
and `docs/40_SCHEMA/SCHEMA_DESIGN.md`.

The existing model is event-sourced: **`enactment`** (the "commit") →
**`change_event`** (one act's effect on one provision, append-only) → folded into
**`provision_version`** for point-in-time reads. An initiative measure that amends a
code section is, legally, exactly the same shape of object as a legislative chapter
that amends a code section. **It should be an `enactment`, not a parallel table.**

### Recommended (Option A — reuse the spine, additive columns + enum values)

1. **Extend `enactmentKindEnum`** (`enums.ts`) from
   `[statute, recodification, regulatory_action]` to add:
   `initiative_statute`, `initiative_constitutional_amendment`,
   `initiative_const_amendment_and_statute`, `referendum`,
   `legislatively_referred_measure`.
   (Postgres enum value ADD is online/non-breaking.)

2. **Add nullable columns to `enactment`** (all NULL for ordinary chapters):
   - `proposition_number integer` — the ballot number (identity for measures).
   - `election_date date` — date of the election that adopted/rejected it.
   - `measure_result text` — `adopted` | `defeated` (only adopted ones change law;
     defeated rows are kept for the completeness denominator + audit).
   - (reuse existing `effective_date` / `operative_date` for the election-derived
     dates; reuse `citation` for the resolution-chapter cite when present.)

3. **`change_event` rows** are produced exactly as for chapters: one per amended
   code section / constitution article, `action ∈ {amend, add, repeal, enact}`,
   `new_text` = the restated section, `operative_date` = the measure's
   election-derived operative date, `trust_level = ocr_uncertain` (→ upgrade on
   human verify). The **constitution** is reachable too: model amended articles via a
   `provision` whose `unit_type` is extended with `const_article` (see §5).

4. **§9605 ordering caveat (IMPORTANT):** the canonical ordering tuple is
   `(operative_date, enactment.chapter_number, in_act_order)`. Initiatives have **no
   `chapter_number`**. Two resolutions:
   - (a) Treat a NULL `chapter_number` as **highest precedence within its operative
     date** (initiatives adopted by the electorate generally control), made explicit
     with a `COALESCE(chapter_number, <sentinel-high>)` in the fold, OR
   - (b) add a dedicated `precedence` integer to `enactment` that the fold uses
     instead of overloading `chapter_number`.
   **Open decision for Patrick (see §8).**

### Rejected (Option B — parallel `measures` table)
A standalone `measures` table would duplicate the enactment/change_event/provision
machinery and, worse, would NOT participate in the point-in-time fold — so a statute
view would still miss initiative amendments unless a second, parallel fold were
built. Reuse is strictly better. Keep measure-specific metadata as columns on
`enactment`, not a new table.

---

## 5. Point-in-time query — folding initiative amendments

The product question is "what did statute X say on date Y". Today the fold selects
the latest `change_event ≤ Y` per provision, ordered by the §9605 tuple. To include
initiatives:

1. **Same fold, more events.** Because an adopted initiative statute becomes
   `change_event` rows on the affected `provision`s with an
   **election-derived operative date**, the *existing* "latest event ≤ date" selection
   already folds them in — **no second query path**. This is the payoff of Option A.
2. **Effective-date rule differs from chapters.** A proposition takes effect **the day
   after the election** *unless the measure states otherwise* (Cal. Const. art. II
   §10(a); many older volumes print an explicit "In effect <date>" — the pilot already
   prefers that when present). The ingest must set `operative_date` from
   `effective_date_basis`: explicit-in-effect > election+1day. Do NOT apply the
   Gov. Code §9600 "90 days after chaptering" legislative default to initiatives.
3. **Constitution.** Voter-approved constitutional amendments need an addressable
   provision. Extend `unitTypeEnum` with `const_article` (or `const_section`) so an
   amended `Article XX §22` is a first-class `provision` and the same fold serves a
   future "Constitution as of date Y" view.
4. **Precedence vs same-day chapters.** When an initiative and a chapter touch the
   same section in the same period, §9605 last-chaptered-wins does not directly apply
   (no chapter number). Use the §4(b) precedence resolution above; surface a
   conflict flag rather than silently picking one.

---

## 6. Completeness denominator (the oracle gap)

**We have no oracle for measures today.** `ca_chapter_counts.tsv` counts only
`total_chapters`. To *measure* measure-completeness we need an independent universe:

- **CA Secretary of State "Initiatives: Summary of Data, 1912–<present>"**
  (the PDF cited in the investigation): authoritative count of qualified + approved
  **initiatives** (140 approved: 40 ICA / 86 IS / 14 both). Good for the
  initiative slice.
- **CA SoS complete ballot-measure list** / **UC Law SF (Hastings) California Ballot
  Propositions Database** / Ballotpedia: the full ~1,300 statewide measures
  (initiatives + legislative referrals + referenda), by election, with ballot number,
  type, and pass/fail. This is the natural **denominator table** — one row per
  (election, proposition_number) with expected type + result.
- **Build a `measure_oracle.tsv`** mirroring `ca_chapter_counts.tsv`: columns
  `election_date, proposition_number, expected_kind, expected_result, title, source_url, confidence`.
  Completeness = parsed (election, number) set vs oracle set, per volume. Adopted-only
  is the correctness-critical subset; defeated rows still count toward "did we read the
  whole volume".

**Open decision (see §8):** which denominator source is canonical, and whether to
seed it by scraping the SoS/Hastings list or by hand for the ~80 sessions.

---

## 7. Era split

| Era | Volumes | Text layer | Segmentation hazards |
|---|---|---|---|
| **EARLY 1911–~1934** | `1915_Vol1_Initiative.pdf`, early `*_Measures` | scanned, **noisy** | bodies keyed by **Title header, not number**; numbers garbled by OCR; needs consensus OCR |
| **MID ~1935–~1978** | bulk of the 38 `*_Measures.pdf` | scanned | back-matter **roster/vote tables** masquerade as numbered entries (roster-reject + TOC-page gate required) |
| **MODERN ~1979–1992+** | `1979`…`1992_Vol1_Measures.pdf` | **scanned** in our sample (1990 had NO text layer) — verify per volume | clean category headings + `[Approved by electors DATE]`; resolution-chapter cites present; easiest to segment once OCR'd |

**Key correction to the assumed era split:** "born-digital after ~1980" did NOT hold
for the 1990 volume in our archive — it is a scan. Treat the born-digital fast-path as
**opportunistic per-volume** (probe `get_text`), not era-assumed. Some later volumes
(post-1992, not in this pilot's 38+1) may be born-digital; verify when reached.

---

## 8. Scale-up plan + effort (3-volume pilot → all 39 measure PDFs)

**Universe:** 38 `*_Measures.pdf` + 1 `*_Initiative.pdf` (+ 58 `*_Constitution.pdf` —
a *separate* track, not in this estimate). Spans ~1911→1992 in the archive.

**Phased plan:**
1. **OCR all 39** with the production 3-engine consensus stack (reuse
   `pipeline/ocr/consensus.py`; the measures volumes are small — most ≤ 50pp except a
   few like 1990's 544pp). Cache per-volume consensus text. *Effort: ~1 GPU-day batch
   on the 5090, mostly unattended (1990 is the long pole at 544pp).*
2. **Generalize the segmenter** (`_prop_parse.py`) into a `pipeline/measures/`
   module with the three era handlers, the roster-reject, the TOC-page gate, and the
   title-header body fallback. Add per-volume `election_default` + `kind` config.
   *Effort: ~1–2 engineer-days to harden + add unit tests on the 3 pilot volumes as
   fixtures.*
3. **Build `measure_oracle.tsv`** from the SoS/Hastings list; wire a completeness
   check (parsed vs oracle per election). *Effort: ~1 day to seed + script; +0.5 day
   if scraped vs hand-entered.*
4. **Certify pass** mirroring the chapter `parsed_acts_certified.json` split into
   confident / flagged by consensus agreement; human-review the flagged tail (the
   adopted-measure tail is small — ~140 initiatives + referrals over the whole range).
   *Effort: review is bounded by the small adopted set; ~2–3 days of human verify for
   the corpus-wide adopted measures.*
5. **Schema migration** (enum ADD + nullable columns + `const_article` unit type) and
   a **TS/Drizzle ingest** script analogous to the chapter ingest, emitting
   `enactment` + `change_event` rows. *Effort: ~2–3 engineer-days incl. the fold
   precedence change + tests.*
6. **Hans review** (twice — schema + pipeline) before any DB write.

**Total rough effort:** ~2 engineer-weeks to a validated, ingested measures corpus
for the 1911→1992 archive (excludes the 58-file Constitution track and any post-1992
born-digital measures). The OCR is cheap/unattended; the cost is segmenter hardening,
the oracle, and human-verifying the (small) adopted tail.

---

## 9. Decisions — RESOLVED (Patrick, 2026-06-22)

1. **Precedence/ordering → ADD an explicit `precedence` column to `enactment`** (NOT a
   COALESCE sentinel on `chapter_number`). Every enactment fills it: chapter number for
   chapters; election-date-derived value for initiatives (initiatives sort by their
   post-election effective date, which correctly supersedes earlier same-year chapters on
   the same provision per the §9605 spirit). Small one-time migration; keeps
   `chapter_number` semantically honest. [§4(b), §5(4)]
2. **Completeness oracle → the FULL Hastings/SoS ballot-measure list, ALL adopted measure
   types** (initiatives + referenda + legislature-referred + constitutional), filtered to
   ADOPTED. SCRAPE it into `measure_oracle.tsv` (few hundred rows, re-runnable), not
   hand-seed. (Rationale: we ingest all adopted measures incl. constitution, so the
   denominator must span all adopted types.) [§6]
3. **Defeated measures → DO NOT INGEST. Adopted-only.** (Same as we don't ingest defeated
   bills.) A future "GitHub-model" process that treats propositions/bills as BRANCHES
   (incl. defeated/proposed) is an entire separate project, far down the line — explicitly
   out of scope here. [§3, §4(2)]
4. **Constitution track → YES, build it in parallel** (like the legislative changes), via
   the `const_article` provision modeling. The 58 `*_Constitution.pdf` are in scope for the
   proposition gate. [§5(3)]
5. **Bond / legislature-referred measures → LINK, don't double-count.** These are TWO
   events: the legislative referral (already a chapter) and the voter approval. The measure
   record LINKS to the referral chapter, but the **measure copy is AUTHORITATIVE for the
   operative voter-approval event** (carries the real post-election effective date that
   drives the fold). Ingest-time reconciliation rule, not a blocker. [§4]
6. **Born-digital → PROBE post-1992 volumes for a text layer, but OCR REGARDLESS**
   (two-track, exactly as the statutes pipeline). The 1990 vol had no text layer; do not
   assume any later one does. [§7]

### Sequencing decision (Patrick, 2026-06-22) — REVERSES the earlier "do A now"
Propositions become an **EXPLICIT ROADMAP GATE**: **finish legislative work FIRST → then the
proposition+constitution gate → THEN ingestion.** The proposition track is well-designed and
pilot-tested but deliberately NOT started yet; we pivot back to closing out legislative work
now. This gate is recorded in `docs/20_ROADMAP/ROADMAP.md`.

---

## Evidence index
- Parser + OCR (scratch): `C:\PatoLex-scratch\_prop_ocr_volume.py`, `_prop_parse.py`.
- Pilot outputs (additive draft, NOT DB):
  `C:\PatoLex-scratch\production-measures-{1915,1935,1990}\parsed_measures.json`.
- Cached OCR: `C:\PatoLex-scratch\_prop_ocr_{1915,1935,1990}.json`.
- Run log: `docs/80_PROJECT_HISTORY/run-logs/proposition-pilot-run.log`.
- Schema reviewed: `src/lib/db/schema/{enactment,change-event,enums}.ts`,
  `docs/40_SCHEMA/SCHEMA_DESIGN.md`.
- Companion: `docs/80_PROJECT_HISTORY/PROPOSITION_CAPTURE_INVESTIGATION_2026-06-22.md`.
```
