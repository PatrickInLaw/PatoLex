# Gate F: Leginfo Modern Layer — Design Spike Findings

**Date:** 2026-06-05  
**Session:** cc003  
**Status:** Spike complete — implementation design ready

---

## What This Document Covers

Gate F is the modern-era layer: reconstructing California statutory law from leginfo PUBINFO XML bulk data. The critical pre-implementation question was: **does BILL_VERSION_TBL explicitly contain (code, section) pairs for each chaptered bill, or must we parse bill text to find amended sections?**

This document records the spike findings, confirms the implementation approach, and flags remaining unknowns.

---

## Data Format Confirmed

PUBINFO archives are tab-delimited `.dat` files with parallel `.lob` text blobs:
- `BILL_VERSION_TBL.dat` — bill metadata rows (one row per version)
- `BILL_VERSION_TBL_N.lob` — one CAML XML blob per bill version (bill text, action lines)
- `LAW_SECTION_TBL.dat` — current-law snapshot (section metadata)
- `LAW_SECTION_TBL_N.lob` — section text XML per row
- Schema: `capublic.sql` in each archive (`gate-b/pubinfo_load/capublic.sql`)

Archives available: 1989–2023. Archives for 1991, 1995, 1997, 1999, 2005, 2007, 2009, 2011, 2013, 2015, 2017 (downloading), 2019 (downloading), 2021 (downloading), 2023 (downloading).

---

## Key Finding: Bill→Section Linkage IS Explicit

Each chaptered bill XML contains `<caml:ActionLine>` elements with **explicit structured links** to the code sections they affect:

```xml
<caml:ActionLine action="IS_AMENDED" 
  xlink:href="urn:caml:codes:EDC:caml#xpointer(…/caml:LawSection[caml:Num='8265.'])"
  xlink:label="fractionType: LAW_SECTION">
  Section 8265 of the Education Code is amended to read:
</caml:ActionLine>
```

**What the ActionLine provides:**
- `action` attribute: `IS_AMENDED`, `IS_ADDED`, or `IS_REPEALED`
- `xlink:href`: structured URI with XPointer containing `(code_id, section_num)` — e.g., `EDC` = Education Code, `8265.` = section number
- The `<caml:Fragment>/<caml:LawSection>/<caml:Content>` sibling contains the final enacted text

**No text parsing required** to extract (code, section_num, action_type, new_text). These are structurally explicit in every chaptered bill XML.

Chapter metadata is also structured:
```xml
<caml:ChapterYear>2005</caml:ChapterYear>
<caml:ChapterType>SB</caml:ChapterType>
<caml:ChapterNum>1750</caml:ChapterNum>
```

---

## What Requires Bill Text Parsing

Two things are NOT in the XML structure and require heuristic text parsing:

### 1. Operative Date

Bills become operative either:
- **Immediately**: urgency statutes (`<caml:Urgency>YES</caml:Urgency>`) → effective on chaptering date
- **Standard**: January 1 of the following year

The urgency flag IS in the XML (`<caml:Urgency>`). No text parsing needed for standard/urgency distinction.

However, some bills contain **operative date clauses** in the text that delay effect beyond Jan 1 (e.g., "this act shall become operative July 1, 2006"). These require text parsing of the `<caml:Content>` block. Frequency: low but non-zero.

**Recommended approach:** Use urgency flag as primary signal; heuristic text scan for explicit operative-date clauses as secondary; flag ambiguous cases for Phase-C review.

### 2. Double-Jointing

When two bills both amend the same section in the same session, the later-chaptered bill typically amends the text AS AMENDED by the earlier bill. The XML contains no explicit `<caml:DoubleJointing>` element. Resolution requires:
- Detecting competing amendments to `(code, section_num)` in the same session
- Applying in chapter-number order (Gov. Code §9605)
- Flagging for human review when the text diff doesn't cleanly compose

**Recommended approach:** Detect conflicts programmatically; apply in order; flag conflicting cases for Phase-C QA. Do not attempt auto-resolution of double-jointed bills in Phase 1.

---

## Implementation Path

### Phase 1: Structural extraction (no text parsing)

For each chaptered bill in BILL_VERSION_TBL:
1. Load `.lob` XML blob
2. Extract chapter metadata: `ChapterYear`, `ChapterType`, `ChapterNum`, `ChapteringDate`
3. Extract `Urgency` flag → operative_date = chaptering_date or Jan 1 next year
4. For each `BillSection`:
   - Parse `ActionLine/@xlink:href` → `(code_id, section_num)`
   - Parse `ActionLine/@action` → `action_type`
   - Extract `Fragment/LawSection/Content` → `new_text`
5. Store: `(chapter_year, chapter_num, code_id, section_num, action_type, new_text, operative_date)`

### Phase 2: Apply amendments to construct point-in-time snapshots

Starting from LAW_SECTION_TBL (current-law anchor), apply amendments backward (for historical) or forward (for future queries). Apply in chapter-number order within a session.

### Phase 3: Double-jointing and operative-date refinement

Detect competing amendments; flag for human review; implement heuristic operative-date clause parser.

---

## Coverage Analysis

| Year Range | BILL_VERSION_TBL | LAW_SECTION_TBL | Validated? |
|------------|-----------------|-----------------|------------|
| 1989–1993  | Available | Not in archive | No ground-truth anchor |
| 1994–2005  | Available | Not in archive | Backward reconstruction from 2023 anchor |
| 2005–2023  | Available | Available (current) | 2023 snapshot is validation anchor |

The earliest **validatable** reconstruction year is 1994 (Gate B confirmed), using the current-law snapshot as anchor and applying amendments backward. The 1989–1993 range is structurally available but lacks a contemporaneous anchor.

---

## Effective-Date Gap in LAW_SECTION_TBL

`effective_date` is NULL for ~42% of rows in LAW_SECTION_TBL. This is expected: sections enacted before the field was consistently populated (circa pre-1980) lack it. For point-in-time queries, this means the gate-F layer cannot reliably answer "what did section X say on 1978-01-01" from LAW_SECTION_TBL alone — must reconstruct from amendment chain.

---

## Remaining Unknowns (for implementation sprint)

| Unknown | Risk | How to resolve |
|---------|------|----------------|
| XPointer format consistency across all years | Medium | Sample 500 bills from 1994–2023; check for href format variation |
| Tracked-change PIs (`<?xm-insertion_mark_*?>`) always present? | Low | Sample 50 bills; check if markup is consistent |
| LAW_SECTION_TBL for years 1994–2004 | Medium | May require full backward reconstruction without anchor validation |
| Operative-clause parser accuracy on known double-jointed bills | Medium | Build test harness on ~20 known cases |
| Session/chapter resolution for urgency-with-delay clauses | Low | Text scan + Phase-C flag is sufficient for Phase 1 |

---

## What This Unlocks

Once Gate F structural extraction is implemented:
- 1994–2023 modern statutory law joins the corpus (covers ~20,000+ session chapters/year)
- Point-in-time queries become available for the modern era without OCR
- The corpus transitions from historical-OCR-only to full-coverage
- Overlapping range with Tier (a) OCR (1976–~1996) provides cross-validation opportunity

Gate F does NOT block the 1850–1996 OCR campaign currently underway. It should be implemented in parallel once the OCR workers clear 2000.

---

## Implementation Status (cc004, 2026-06-05)

### Extraction: COMPLETE
`parse_bill_versions.py` + `run_all_years.py` are working. Full extraction run on all 14 available pubinfo years produced **139,211 section actions** total:

| Year | Actions | Year | Actions |
|------|---------|------|---------|
| 1991 | 12,256 | 2011 | 11,268 |
| 1995 | 12,989 | 2013 | 9,501 |
| 1997 | 11,736 | 2015 | 9,290 |
| 1999 | 11,736 | 2017 | 9,265 |
| 2005 | 8,206 | 2019 | 7,023 |
| 2007 | 7,445 | 2021 | 11,286 |
| 2009 | 8,603 | 2023 | 8,607 |

Output location: `C:\Users\PatrickKolasinski\PatoLex-scratch\gate_f_out\gate_f_YYYY_actions.jsonl`

### Pre-2005 Format Difference (RESOLVED)
The 1991–1999 PUBINFO archives use an earlier CAML XML format where `<caml:ActionLine>` elements **do not have the `xlink:label` attribute**. The 2005+ format has `xlink:label="fractionType: LAW_SECTION"`. The parser initially filtered out all 1991–1999 sections because `label.upper()` of an empty string doesn't contain "LAW_SECTION".

**Fix** (`parse_bill_versions.py`): changed `if 'LAW_SECTION' not in label.upper()` to `if label and 'LAW_SECTION' not in label.upper()`. When `label` is absent/empty, the filter is skipped and the href parsing alone determines validity.

The href format is identical across all years — URL-encoded XPointer (`urn:caml:codes:VEH:caml#xpointer(%2F%2F...)`) — so no second code path was needed.

### Ingest: READY (DB connectivity required)
`ingest_gate_f.py` is written and ready. To ingest all extracted data:
```powershell
$env:DATABASE_URL = "<direct-url-from-secrets>"
python pipeline\gate_f\ingest_gate_f.py C:\Users\PatrickKolasinski\PatoLex-scratch\gate_f_out --commit
```
DB connectivity from the local machine currently fails due to IPv6-only DNS resolution for `db.nqigiiyurwlmruexircz.supabase.co`. Fix: update `DATABASE_URL` to use the Supabase `*.pooler.supabase.com` endpoint (which has IPv4).
