# Modern Chaptered-Statute Format (born-digital, 1997–2008+)

Date: 2026-06-02
Source examined: `2008_Vol1.pdf` (1652 pp), cross-checked `2001_Vol1.pdf` (1718 pp).
Both are born-digital (clean `fitz get_text()` text layer; no OCR needed).

## High-level layout of a year volume

1. **Front matter** (cover, table of contents, the California Constitution,
   adopted measures/propositions, Legislative Counsel's Digests, etc.).
   In `2008_Vol1.pdf` the chaptered statutes do not begin until **page 522**
   (0-indexed). Scan deep — do not assume chapters start near the front.
2. **Chaptered statutes**, in continuous chapter-number order, each beginning
   with a `CHAPTER N` header line. 2008_Vol1 has **209 pages** containing a
   `^CHAPTER \d+$` header (multiple chapters can share a page).
3. Chapters continue across volumes (Vol2..Vol5) with **continuous numbering**
   for the year — the multi-volume roll-up is required for full-year coverage.

## Per-chapter structure (the unit to parse)

A chapter record runs from its `CHAPTER N` header line up to (but not
including) the next `CHAPTER N+1` header. The header block is, in order:

```
CHAPTER 1
An act to add Sections 75074.5 and 75094 to the Government Code,
relating to judges’ retirement.
[Approved by Governor February 28, 2008. Filed with
Secretary of State February 28, 2008.]
The people of the State of California do enact as follows:
SECTION 1. Section 75074.5 is added to the Government Code, to
read:
...body (SECTION 1., SEC. 2., subdivisions (a)/(b)/(1)/(A) ...)...
```

### Components

| Component | Pattern | Notes |
|-----------|---------|-------|
| **Header** | `^\s*CHAPTER\s+(\d+)\s*$` on its own line | Arabic numerals (not Roman, unlike pre-1900). Continuous within a year across volumes. |
| **Title** | The `An act to …` line(s) immediately after the header, ending at the `[Approved…` bracket | Wraps over several lines; "An act" (lowercase "act") is the modern spelling vs. pre-1900 "An Act". |
| **Date block** | `[Approved by Governor <Month> <day>, <year>. Filed with Secretary of State <Month> <day>, <year>.]` | Enclosed in square brackets. **The bracket and the two dates frequently span a line break** (e.g. `Filed with\nSecretary of State`). Must match across newlines. Urgency statutes can also read `Approved by Governor … Filed with Secretary of State …` then add `An act … to take effect immediately`. |
| **Enact clause** | `The people of the State of California do enact as follows:` | Same marker family as the existing `ENACT_MARKER_RE` (`do enact as follow`). |
| **Body** | `SECTION 1.` / `SEC. 2.` … numbered sections, codified text | Ends at next `CHAPTER N+1`. |

### Real header excerpts (2008_Vol1)

**CHAPTER 1** (p.522):
```
CHAPTER 1
An act to add Sections 75074.5 and 75094 to the Government Code,
relating to judges’ retirement.
[Approved by Governor February 28, 2008. Filed with
Secretary of State February 28, 2008.]
The people of the State of California do enact as follows:
```

**CHAPTER 2** (p.523):
```
CHAPTER 2
An act to amend Section 15660 of, and to add Section 12301.8 to, the
Welfare and Institutions Code, relating to in-home supportive services.
[Approved by Governor March 14, 2008. Filed with
Secretary of State March 14, 2008.]
The people of the State of California do enact as follows:
```

**CHAPTER 3** (p.526, urgency statute):
```
CHAPTER 3
An act to add Section 5925 to the Government Code, relating to public
ﬁnance, and declaring the urgency thereof, to take effect immediately.
[Approved by Governor March 26, 2008. Filed with
Secretary of State March 26, 2008.]
The people of the State of California do enact as follows:
```

### Running header / footer noise

Pages carry a running header/footer with the volume identity, e.g.:
```
7
STATUTES OF 2008
[ Ch.     3 ]
```
The `[ Ch.  N ]` token is a **page footer/running head**, NOT the chapter
header — it must not be mistaken for the `CHAPTER N` start. The real header is
the standalone `CHAPTER N` line. (The current `HEADER_RE` for the old format
would not match `[ Ch. N ]` anyway, but the modern parser keys strictly on
`^CHAPTER \d+$`.)

### Bill markers — NOT present in this section

The task brief anticipated inline bill markers like `[ Senate Bill No. 200 ]`.
**Confirmed absent** from the chaptered-statutes section of both `2008_Vol1`
and `2001_Vol1` (0 pages matched `\[\s*(?:Senate|Assembly)\s+Bill\s+No`). Those
markers belong to bill/measure editions, not the Statutes-of chaptered volumes.
The modern parser therefore must NOT depend on a bill marker.

## Date-language variants observed

- `Approved by Governor <Month> <day>, <year>. Filed with Secretary of State <Month> <day>, <year>.`
- Same, line-wrapped after "Filed with".
- 2001 also shows a standalone `Filed with \nSecretary of State <Month> <day>, <year>.`

Day is a bare integer (no `st/nd/rd/th`). Year is 4-digit (1997–2008+).

## Confidence definition (modern)

A modern chapter is **confident** when it has all of:
1. `CHAPTER N` header with N > 0,
2. an `An act` title line,
3. a parsed Approved-by-Governor date,
4. the enact marker `do enact as follows`.

## TODO for 1915–1996 (image-only, needs OCR)

- **Multi-volume roll-up**: chapter numbers run continuously across Vol1..VolN
  of a year. The parser must concatenate volumes in order and treat the year as
  one chapter stream (dedupe page footers `[ Ch. N ]`).
- **OCR-fuzz tolerance**: for 1915–1996 the header/date/enact regexes need the
  same OCR-fuzzy treatment the pre-1900 parser uses (e.g. `CHAPTER` ↔
  `CIIAPTER`, `Approved` ↔ `Approvod`, ligature/`ﬁ`→`fi` normalization, OCR
  digit confusions in chapter numbers). Cannot be finalized until real
  1915–1996 OCR consensus text is available to characterize the actual error
  modes.
