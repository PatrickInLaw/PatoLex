# California Chapter Counts — Authoritative Reference (`ca_chapter_counts.tsv`)

**Purpose:** A per-session reference of how many chapters (statutes) each California
legislative session enacted in *Statutes and Amendments to the Codes*, 1850–2024.
Used to validate completeness of the OCR-parsed corpus: for any session, the
highest chapter number = the total chapters (chapters run 1..N contiguously), so the
expected enactment count for that session in the DB should equal `total_chapters`.

**File:** `ca_chapter_counts.tsv` (this directory).
Columns: `session_label | session_year | session_type | total_chapters | source_url | confidence`.

## Validated method

The total chapter count for a session = the **highest chapter number** in that
session's *Statutes and Amendments to the Codes* table of contents. Chapters are
numbered 1..N with no gaps, so the last chapter number IS the count.

**Method validated against both required anchors:**
- **Statutes of 1957, Regular Session = 2,424** ✔ (Chief Clerk page states "Chapters 1401–2424").
- **Statutes of 1996, Regular Session = 1,171** ✔ (Chief Clerk page states regular-session statute chapters run to 1171; vols 1–5).

## Verified corrections / confirmations — early annual sessions (2026-06-16)

A verification pass re-checked the suspect early entries (1850–1879) against the
PRIMARY source (CA Assembly Chief Clerk archive volume titles) plus scanned-volume
cross-checks (archive.org Google digitizations; the Chief Clerk full-volume PDFs).
Result: **one correction (1854), all other suspects confirmed unchanged.**

| Session | Old | New | Confidence | Evidence |
|---------|-----|-----|-----------|----------|
| 1854 Regular | 71 | **174** | high | Chief Clerk 1854 page lists the volume as TWO separately-numbered series: **Laws 1–71** and **Special Laws 1–103**. Confirmed against the scanned original (archive.org `statutescalifor05greggoog`, a Google digitization of the 1854 Fifth Session print volume): general laws "LAWS OF CALIFORNIA" run Ch. 1–71, then "SPECIAL ACTS" restart at Ch. 1 and run to Ch. 103. Total statutes = 71 + 103 = **174**. The old `71` captured only the general-laws series. |
| 1852 Regular | 202 | 202 (unchanged) | high | Chief Clerk page: single Statutes series **1–202** (Resolutions 1–29 separate). The parse's ~274 is a parse artifact, NOT a true higher count — the authoritative max is 202. |
| 1853 Regular | 180 | 180 (unchanged) | high | Chief Clerk page: single Statutes series **1–180** (Resolutions 1–22 separate). Parse's ~301 is a parse artifact; authoritative max is 180. |
| 1865-66 Regular | 280 | 280 (unchanged) | high | **Conflict resolved.** Chief Clerk page AND full-volume PDF (TOC at p.89) AND independent Google Books scan (`id=EPk4AQAAMAAJ`, J. Winchester 1866) all confirm the Statutes series ends at **Ch. 280**. The OCR run past 280 (283…307) is spurious. The volume has NO separate "Amendments to the Codes" numbered series (the four codes were not enacted until 1872); the only other numbered series are **Assembly Resolutions 1–35** and **Senate Resolutions 1–41** — the most likely source of the stray >280 numerals (or bleed-in from the following 1867-68 volume, which is 545). |

**1850, 1851, 1855 spot-checked and confirmed single-series** (146 / 139 / 231) — no
dual-series structure, oracle correct. No other 1850–1879 "parse > oracle" structural
discrepancies found.

### IMPORTANT structural caveat for 1854 (breaks the "max chapter = count" rule)

1854 is the ONE early year where the "highest chapter number = total count" method
does **not** apply, because the volume uses **two independent chapter sequences that
both start at 1** (general Laws 1–71 and Special Acts 1–103). Chapters 1–71 exist in
*both* series. For the corpus completeness check this means:
- The expected 1854 enactment count is the **sum** of the two series = **174**, not a
  single max.
- Any ingest of 1854 acts MUST namespace chapter numbers by series (general vs.
  special) to avoid collisions — a bare "Chapter 5, 1854" is ambiguous.
- This is the likely cause of the parse's ~117: the parser caught the 71 general laws
  plus part of the special acts but conflated/dropped some due to the restart-at-1.

(This dual-series pattern was checked for and NOT found in 1850/51/52/53/55, so 1854
appears to be an isolated case among the annual-session years.)

## Sources (in priority order)

1. **CA Assembly Chief Clerk historical archive** — PRIMARY for **1850–2008**.
   `https://clerk.assembly.ca.gov/historical-information/archive-list/statutes-and-amendments-codes-YEAR`
   The per-session volume titles state chapter ranges (e.g. "Regular Session Statute
   Chapters 1401–2424") directly — no PDF download needed. 2006–2008 are under
   "Statutes and Digests of Measures" node pages (`/node/371`=2008, `/node/372`=2007,
   `/node/373`=2006).
2. **CA Secretary of State "Bill Chapters" PDFs** — PRIMARY for **2009–2024** (Chief
   Clerk archive stops ~2008). Per-year "chapter-number.pdf":
   `https://admin.cdn.sos.ca.gov/bill-chapters/YEAR/chapter-number.pdf`
   These PDFs are NOT readable via WebFetch (binary content streams). They were
   extracted locally with **PyMuPDF** (`fitz`): download the PDF, dump text, regex the
   leading chapter-number column, take the max. (See `scripts/scratch/extract_chapter_max.py`,
   archived after use.) Cross-checked: 2024 max = 1017 (Chapter 1016 = SB1112 is a
   known real chapter, so max ≥ 1016 ✔); 2020 = 372 (COVID-shortened — independently
   reported as "fewest bills signed since at least 1967" ✔).

## Structural notes (important for corpus completeness checks)

- **Numbering granularity is PER CALENDAR YEAR / per session, NOT per biennium.**
  Each session's chapters restart at 1. Even within a two-year legislative session
  (modern era), each calendar year gets its own chapter sequence (so 2023 and 2024
  are separate rows each counting from 1).

- **1850–1863: annual sessions**, single-year volumes.

- **1863/64–1905/06: biennial sessions**, one combined volume per two-year session.
  Rows are keyed to the session label (e.g. `1863-64`, `1865-66`). The session that
  met Dec 1863–Apr 1864 appears in the archive under both a standalone `1863` page and
  a `1863-64` page with the **same** 476-chapter count — these are one session; the
  TSV keeps a single row (`1863-64`, 476) to avoid double-counting.

- **1880 transition:** California shifted to odd-year regular sessions; 1880 was a
  one-off. From 1881 onward regular sessions are odd years (1881, 1883, 1885 ...).

- **Some odd-year regular sessions are genuinely tiny** and are NOT OCR/parse errors:
  - **1883 = 23 chapters** (short session).
  - **1887 = 51 chapters** (short session).
  Verified directly against the Chief Clerk volume titles.

- **1946–1966: even-year "budget sessions."** In this era the legislature held a
  short constitutionally-limited **budget session in even years** (Regular Session) and
  a full general session in odd years. The even-year *Regular Sessions* therefore have
  **single/low-double-digit chapter counts** (e.g. 1948=38, 1950=6, 1952=14, 1954=10,
  1956=13, 1958=10, 1960=14, 1962=12, **1964=1**, 1966=9) — these low numbers are
  CORRECT, not missing data. The odd-year general sessions carry the bulk
  (1957=2424, 1959=2195, 1961=2232, 1963=2181, 1965=2070). California moved to
  full annual sessions starting ~1967.

- **Extraordinary / Extra Sessions** are numbered independently of the regular
  session (each starts at chapter 1) and are recorded as separate rows
  (`session_type = extra1, extra2, ...`). They are usually small (1–169 chapters).
  Note the archive often files an extra session under the FOLLOWING year's volume
  (e.g. the 1940 extra sessions appear in the 1941 volume) — the TSV `session_year`
  reflects when the session met, `source_url` points to the volume it's printed in;
  those cross-filed extras are marked `med` confidence.

- **Recodification years (FYI for the corpus build):** the major California codes were
  enacted by the 1872 session (the four original codes) and recodified across the
  1929–1953 era; the 1872 recodification should be modeled as a recodification *event*,
  not as enact-from-nothing. (Chapter counts here are raw session totals and do not
  themselves encode the recodification.)

## Coverage / confidence summary

- **Regular sessions covered: 1850–2024** (every regular session present, no `low` rows).
- **High confidence:** ~131 rows (explicit chapter range stated in the source, or
  locally PDF-extracted with external cross-check).
- **Med confidence:** ~67 rows — almost all are extraordinary/extra sessions whose
  chapter range was read from a neighboring year's combined volume (count is reliable
  but the exact session-to-volume attribution is the soft part).
- **Eras well-covered:** the entire OCR-critical span **1850–1990** is high-confidence
  for every regular session — this is exactly where the completeness check is needed.
- **Sparse:** none for regular sessions. The only soft spots are extra-session
  attributions (med) and the fact that not every minor extra session in 2009–2024 was
  enumerated (modern extras are negligible for corpus completeness).

## How to use for the completeness check

For each session row, query the DB for enactments tagged to that session/year and
compare the count to `total_chapters`. A DB count **below** `total_chapters` = missing
acts (OCR/parse gap). A DB count **above** = duplicate ingestion or mis-attribution.
For biennial-era rows, attribute DB acts to the session label, not the calendar year.
