# Sacramento Scan Packet — Consolidated Missing-Leaf + Chapter-Recovery Trip — 2026-06-29

**Purpose.** ONE carry-to-Sacramento document that merges the two existing missing-paper
sources — the page-level missing-leaf audit and the chapter-level archivist request — into a
single packet organized **by physical volume**, with every printed page listed **once**.

**Sources merged:**
- Page-level missing leaves: the deterministic page-continuity audit
  (`docs/80_PROJECT_HISTORY/PAGE_CONTINUITY_AUDIT_2026-06-23.md` section (c); canonical data
  `C:\PatoLex-scratch\_audit_all.jsonl`). 175 missing printed pages over 82 gaps across 49 volumes.
- Chapter-level archivist request: `docs/80_PROJECT_HISTORY/ARCHIVES_SCAN_REQUEST_2026-06-22.md`
  (17 chapters: 8 original missing-leaf chapters across 1927/1929/1970/1981/1985/1986 + 9 1872
  missing-leaf chapters).

**All page numbers below are PRINTED running-head page numbers in the bound volumes — NOT
PDF/sequence numbers.**

---

## HEADLINE — hard totals for the trip

| Tier | Distinct printed pages | Confidence / meaning |
|---|---:|---|
| **HIGH missing-leaf (even-parity)** | **126** | Unambiguous dropped-leaf signature (one sheet = 2 pages; rapid-scan drops lose pages in pairs). This is the actionable scan list. |
| **odd-parity INSPECT-ONLY** | **49** | Lower confidence — usually an original printing/numbering skip or torn half-leaf, not a clean dropped leaf. Inspect on site; do **not** assume missing. |
| **TOTAL distinct pages** | **175** | |

- **Distinct printed pages to scan/inspect: 175** (126 HIGH + 49 odd-inspect).
- **Distinct physical volumes affected: 49.**
- **82 detected gaps** (41 even/HIGH + 41 odd/LOW).
- **Named-chapter recovery (cross-cutting annotation): 23 of the 175 pages** carry the 17
  archivist-named chapters. **All 10 archivist page-ranges dedup exactly onto page-level audit
  gaps in the same volume+range — zero double-counting.** 22 of these 23 chapter pages are
  even-parity HIGH; **1 is odd-parity** (1970 p.1648 — see flag below).

> **Overlap reconciliation (proven):** the archivist's 17 chapters are the SAME physical pages as
> page-level gaps in the same volumes. Each archivist entry was matched to its page-level gap
> (1872's 131-134/515-516/586-587/776-777; 1927 1626-1627; 1929 1974-1975; 1970 1648; 1981
> 1562-1563; 1985 1859-1860; 1986 4812-4815). All 10 coincide. The chapter information is folded
> in as annotation on the existing gap rows, adding **zero** new pages to the 175.

---

## ⚠ Flags (read before quoting the archivist)

1. **1929 Ch. 881 — printed-page discrepancy.** The 2026-06-22 archivist doc listed Ch. 881 at
   **pp 1962-1963** (a pre-audit manual estimate). The deterministic page-continuity audit detects
   the actual dropped leaf at **printed pp 1974-1975** (even-parity, HIGH, anchored). The parse
   confirms Ch. 881 is the missing chapter (sequence runs 880 → [gap] → 882). **Use printed
   pp 1974-1975** as the leaf to scan; ask the archivist to capture pp 1962-1976 if a slightly
   wider window is cheap, to be safe against either number.
2. **1970 Ch. 906/907 — odd-parity leaf.** The named-chapter recovery at **p. 1648** is a
   **single-page (odd) break**, tagged LOWER-confidence by the audit. It is the one named-chapter
   page that is NOT an even-parity leaf. Likely a real continuity break (the chapters are absent
   from the parse) but the physical cause cannot be proven from numbering alone — inspect on site.
3. **1985** has a SECOND even-parity HIGH leaf at **pp 804-805** that the archivist doc did NOT
   list (it only named the 1859-1860 leaf). Both are included below.
4. **1927** has TWO odd-parity inspect pages (1940, 1965) beyond the named-chapter leaf at
   1626-1627. Included as INSPECT-ONLY.

---

## BY PHYSICAL VOLUME

Legend — **Tier**: `HIGH` = even-parity dropped-leaf (scan); `INSPECT` = odd-parity (inspect, do
not assume missing). **Chapters** column populated only where the archivist named the chapter.

### 1872 Regular Session — *Statutes of California 1871-72*, Vol. 1  *(`production-1871-72`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 131–134 | 4 | HIGH | dropped leaves (2 sheets) | Ch. 125, 126, 127, 128 |
| 515–516 | 2 | HIGH | dropped leaf | Ch. 363, 364 |
| 586–587 | 2 | HIGH | dropped leaf | Ch. 417, 418 |
| 776–777 | 2 | HIGH | dropped leaf | Ch. 538 |

### 1915 Regular Session — Vol. 1 Chapters  *(`production-1915-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 1548–1549 | 2 | HIGH | dropped leaf | — |
| 1870–1871 | 2 | HIGH | dropped leaf | — |

### 1927 Regular Session — Vol. 1 Chapters  *(`production-1927-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 1626–1627 | 2 | HIGH | dropped leaf | **Ch. 816 (full), Ch. 817 title page** |
| 1940 | 1 | INSPECT | odd break — inspect | — |
| 1965 | 1 | INSPECT | odd break — inspect | — |

### 1929 Regular Session — Vol. 1 (29-chapter ed.)  *(`production-1929-vol1-29chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 1584 | 1 | INSPECT | odd break — inspect | — |
| 1974–1975 | 2 | HIGH | dropped leaf | **Ch. 881** *(archivist pre-audit estimate was 1962-1963 — see flag 1)* |

### 1931 Regular Session — Vol. 1 Chapters  *(`production-1931-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 2601 | 1 | INSPECT | odd break (verified by eye: 2600→2603, leaf unreadable) | — |

### 1933 Regular Session — Vol. 1 Chapters  *(`production-1933-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 2724–2725 | 2 | HIGH | dropped leaf | — |

### 1937 Regular Session — Vol. 1 Chapters  *(`production-1937-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 2568–2569 | 2 | HIGH | dropped leaf | — |

### 1938 Regular Session — Vol. 1 Chapters  *(`production-1938-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 118–119 | 2 | HIGH | dropped leaf | — |

### 1941 Regular Session — Vol. 1 (41-chapter ed.)  *(`production-1941-vol1-41chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 3233 | 1 | INSPECT | odd break — inspect | — |

### 1943 Regular Session — Vol. 1 (42-chapter ed.)  *(`production-1943-vol1-42chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 34 | 1 | INSPECT | odd break — inspect | — |

### 1943 Regular Session — Vol. 1 Chapters  *(`production-1943-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 3083 | 1 | INSPECT | odd break — inspect | — |
| 3373–3374 | 2 | HIGH | dropped leaf | — |

### 1945 Regular Session — Vol. 1 Chapters  *(`production-1945-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 2865 | 1 | INSPECT | odd break — inspect | — |

### 1947 Regular Session — Vol. 1 (46-chapter ed.)  *(`production-1947-vol1-46chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 201 | 1 | INSPECT | odd break — inspect | — |
| 339 | 1 | INSPECT | odd break — inspect | — |

### 1947 Regular Session — Vol. 1 Chapters  *(`production-1947-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 3241 | 1 | INSPECT | odd break — inspect | — |

### 1948 (1st Extra) — Vol. 1 Chapters  *(`production-1948-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 153 | 1 | INSPECT | odd break — inspect | — |

### 1949 Regular Session — Vol. 1 (49-chapter prior ed.)  *(`production-1949-vol1-49chapters-prior`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 31 | 1 | INSPECT | odd break — inspect | — |

### 1949 Regular Session — Vol. 1 Chapters  *(`production-1949-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 2849 | 1 | INSPECT | odd break — inspect | — |

### 1950 (1st Extra) — Vol. 1 Chapters  *(`production-1950-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 421–422 | 2 | HIGH | dropped leaf | — |
| 555–556 | 2 | HIGH | dropped leaf | — |

### 1951 Regular Session — Vol. 1 (50-chapter ed.)  *(`production-1951-vol1-50chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 77 | 1 | INSPECT | odd break — inspect | — |

### 1951 Regular Session — Vol. 1 Chapters  *(`production-1951-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 1831 | 1 | INSPECT | odd break — inspect | — |

### 1951 Regular Session — Vol. 2 Chapters  *(`production-1951-vol2-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 4195 | 1 | INSPECT | odd break (verified: 2 unreadable scan pages span 1 skipped number) | — |

### 1953 Regular Session — Vol. 1 (52-chapter ed. = 1952 budget)  *(`production-1953-vol1-52chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 138–139 | 2 | HIGH | dropped leaf | — |
| 299–300 | 2 | HIGH | dropped leaf | — |
| 400–401 | 2 | HIGH | dropped leaf | — |
| 434–436 | 3 | INSPECT | odd (3-page) break — inspect | — |
| 514–515 | 2 | HIGH | dropped leaf | — |

### 1953 Regular Session — Vol. 2 Chapters  *(`production-1953-vol2-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 3693 | 1 | INSPECT | odd break — inspect | — |

### 1955 Regular Session — Vol. 1 (54-chapter ed. = 1954 budget)  *(`production-1955-vol1-54chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 117 | 1 | INSPECT | odd break — inspect | — |
| 233 | 1 | INSPECT | odd break — inspect | — |
| 371 | 1 | INSPECT | odd break — inspect | — |

### 1955 Regular Session — Vol. 2 Chapters  *(`production-1955-vol2-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 3609 | 1 | INSPECT | odd break — inspect | — |

### 1957 Regular Session — Vol. 1 (56-chapter ed. = 1956 budget)  *(`production-1957-vol1-56chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 142–143 | 2 | HIGH | dropped leaf | — |
| 271–272 | 2 | HIGH | dropped leaf | — |
| 463 | 1 | INSPECT | odd break — inspect | — |

### 1957 Regular Session — Vol. 2 (57-chapter ed.)  *(`production-1957-vol2-57chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 4183 | 1 | INSPECT | odd break — inspect | — |

### 1959 Regular Session — Vol. 1 (58-chapter ed. = 1958 budget)  *(`production-1959-vol1-58chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 175 | 1 | INSPECT | odd break — inspect | — |
| 364–365 | 2 | HIGH | dropped leaf | — |
| 460–462 | 3 | INSPECT | odd (3-page) break — inspect | — |

### 1959 Regular Session — Vol. 2 Chapters  *(`production-1959-vol2-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 5317 | 1 | INSPECT | odd break — inspect | — |

### 1961 Regular Session — Vol. 1 (60-chapter ed. = 1960 budget)  *(`production-1961-vol1-60chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 138 | 1 | INSPECT | odd break — inspect | — |
| 288 | 1 | INSPECT | odd break — inspect | — |
| 475 | 1 | INSPECT | odd break — inspect | — |

### 1961 Regular Session — Vol. 2 Chapters  *(`production-1961-vol2-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 4593 | 1 | INSPECT | odd break — inspect | — |

### 1963 Regular Session — Vol. 1 (62-chapter ed. = 1962 budget)  *(`production-1963-vol1-62chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 22 | 1 | INSPECT | odd break — inspect | — |
| 142–144 | 3 | INSPECT | odd (3-page) break — inspect | — |
| 383 | 1 | INSPECT | odd break — inspect | — |
| 420–422 | 3 | INSPECT | odd (3-page) break — inspect | — |
| 554–557 | 4 | HIGH | dropped leaves (2 sheets) | — |
| 571 | 1 | INSPECT | odd break — inspect | — |

### 1963 Regular Session — Vol. 2 Chapters  *(`production-1963-vol2-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 4569 | 1 | INSPECT | odd break — inspect | — |

### 1967 Regular Session — Vol. 3 Chapters  *(`production-1967-vol3-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 4304–4305 | 2 | HIGH | dropped leaf | — |

### 1970 Regular Session — Vol. 1 Chapters  *(`production-1970-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 1648 | 1 | INSPECT | odd break (named-chapter recovery — see flag 2) | **Ch. 906, Ch. 907** |

### 1971 Regular Session — Vol. 2  *(`production-1971-vol2`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 4148 | 1 | INSPECT | odd break — inspect | — |

### 1972 Regular Session — Vol. 1 Chapters  *(`production-1972-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 896–897 | 2 | HIGH | dropped leaf | — |

### 1981 Regular Session — Vol. 2  *(`production-1981-vol2`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 1562–1563 | 2 | HIGH | dropped leaf | **Ch. 378** |

### 1982 Regular Session — Vol. 1 Chapters  *(`production-1982-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 1256–1257 | 2 | HIGH | dropped leaf | — |
| 1264–1265 | 2 | HIGH | dropped leaf | — |
| 1282–1283 | 2 | HIGH | dropped leaf | — |
| 1298–1299 | 2 | HIGH | dropped leaf | — |

### 1982 Regular Session — Vol. 2  *(`production-1982-vol2`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 2234–2245 | 12 | HIGH | dropped gathering (6 leaves) | — |

### 1983 Regular Session — Vol. 1 Chapters  *(`production-1983-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 945–950 | 6 | HIGH | dropped leaves (3 sheets) | — |

### 1985 Regular Session — Vol. 1 Chapters  *(`production-1985-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 804–805 | 2 | HIGH | dropped leaf (not in archivist doc — see flag 3) | — |
| 1859–1860 | 2 | HIGH | dropped leaf | **Ch. 505, Ch. 506** |

### 1986 Regular Session — Vol. 3  *(`production-1986-vol3`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 4812–4815 | 4 | HIGH | dropped leaves (2 sheets) | **Ch. 1357, Ch. 1358, Ch. 1359 title page** |

### 1987 Regular Session — Vol. 2  *(`production-1987-vol2`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 2030–2031 | 2 | HIGH | dropped leaf | — |

### 1989 Regular Session — Vol. 1 Chapters  *(`production-1989-vol1-chapters`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 1146–1147 | 2 | HIGH | dropped leaf | — |

### 1989 Regular Session — Vol. 2  *(`production-1989-vol2`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 2128–2129 | 2 | HIGH | dropped leaf | — |
| 2832–2835 | 4 | HIGH | dropped leaves (2 sheets) | — |

### 1990 Regular Session — Vol. 2  *(`production-1990-vol2`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 3295–3312 | 18 | HIGH | dropped gathering (9 leaves) | — |

### 1990 Regular Session — Vol. 4  *(`production-1990-vol4`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 6848 | 1 | INSPECT | odd break — inspect | — |

### 1991 Regular Session — Vol. 1  *(`production-1991-vol1`)*

| Printed pages | Pages | Tier | Expected content | Chapters |
|---|---:|---|---|---|
| 1244–1251 | 8 | HIGH | dropped leaves (4 sheets) | — |
| 1258–1259 | 2 | HIGH | dropped leaf | — |

---

## Per-volume tier counts (for ordering a quote)

| Volume | HIGH pages | INSPECT pages | Total |
|---|---:|---:|---:|
| 1871-72 | 10 | 0 | 10 |
| 1915-vol1-chapters | 4 | 0 | 4 |
| 1927-vol1-chapters | 2 | 2 | 4 |
| 1929-vol1-29chapters | 2 | 1 | 3 |
| 1931-vol1-chapters | 0 | 1 | 1 |
| 1933-vol1-chapters | 2 | 0 | 2 |
| 1937-vol1-chapters | 2 | 0 | 2 |
| 1938-vol1-chapters | 2 | 0 | 2 |
| 1941-vol1-41chapters | 0 | 1 | 1 |
| 1943-vol1-42chapters | 0 | 1 | 1 |
| 1943-vol1-chapters | 2 | 1 | 3 |
| 1945-vol1-chapters | 0 | 1 | 1 |
| 1947-vol1-46chapters | 0 | 2 | 2 |
| 1947-vol1-chapters | 0 | 1 | 1 |
| 1948-vol1-chapters | 0 | 1 | 1 |
| 1949-vol1-49chapters-prior | 0 | 1 | 1 |
| 1949-vol1-chapters | 0 | 1 | 1 |
| 1950-vol1-chapters | 4 | 0 | 4 |
| 1951-vol1-50chapters | 0 | 1 | 1 |
| 1951-vol1-chapters | 0 | 1 | 1 |
| 1951-vol2-chapters | 0 | 1 | 1 |
| 1953-vol1-52chapters | 8 | 3 | 11 |
| 1953-vol2-chapters | 0 | 1 | 1 |
| 1955-vol1-54chapters | 0 | 3 | 3 |
| 1955-vol2-chapters | 0 | 1 | 1 |
| 1957-vol1-56chapters | 4 | 1 | 5 |
| 1957-vol2-57chapters | 0 | 1 | 1 |
| 1959-vol1-58chapters | 2 | 4 | 6 |
| 1959-vol2-chapters | 0 | 1 | 1 |
| 1961-vol1-60chapters | 0 | 3 | 3 |
| 1961-vol2-chapters | 0 | 1 | 1 |
| 1963-vol1-62chapters | 4 | 9 | 13 |
| 1963-vol2-chapters | 0 | 1 | 1 |
| 1967-vol3-chapters | 2 | 0 | 2 |
| 1970-vol1-chapters | 0 | 1 | 1 |
| 1971-vol2 | 0 | 1 | 1 |
| 1972-vol1-chapters | 2 | 0 | 2 |
| 1981-vol2 | 2 | 0 | 2 |
| 1982-vol1-chapters | 8 | 0 | 8 |
| 1982-vol2 | 12 | 0 | 12 |
| 1983-vol1-chapters | 6 | 0 | 6 |
| 1985-vol1-chapters | 4 | 0 | 4 |
| 1986-vol3 | 4 | 0 | 4 |
| 1987-vol2 | 2 | 0 | 2 |
| 1989-vol1-chapters | 2 | 0 | 2 |
| 1989-vol2 | 6 | 0 | 6 |
| 1990-vol2 | 18 | 0 | 18 |
| 1990-vol4 | 0 | 1 | 1 |
| 1991-vol1 | 10 | 0 | 10 |
| **TOTAL (49 volumes)** | **126** | **49** | **175** |

---

## Archive contacts (from `ARCHIVES_SCAN_REQUEST_2026-06-22.md`)

Two California institutions hold the bound *Statutes of California* set and provide paid
copy / scanning service. **Best fit: California State Library, Government Publications Section.**

| Institution / desk | Email | Phone | Source (official) |
|---|---|---|---|
| **California State Library — Government Publications Section** (best fit) | **cslgps@library.ca.gov** | (916) 323-9845 | https://www.library.ca.gov/government-publications/ |
| California State Library — California History Section (photo-duplication / digital reproduction) | **cslcal@library.ca.gov** | (916) 654-0176 | https://www.library.ca.gov/california-history/digital-images/ |
| California State Archives — Reference Services (Secretary of State; fallback) | **Reference@sos.ca.gov** | (916) 653-2246 | https://www.sos.ca.gov/archives/services/reference-services |

Notes from the official pages:
- **State Library Government Publications:** full California state-publications depository; public
  book/microform scanning at the Stanley Mosk Library & Courts Building, 914 Capitol Mall, 3rd
  Floor, Sacramento. Email/phone above for inquiries (M–F 9–5).
- **State Library California History Section:** handles digital-image reproduction; mailing address
  California History Section, California State Library, PO Box 942837, Sacramento, CA 94237-0001;
  FAX (916) 654-8777.
- **State Archives Reference:** limited remote research; copies for a fee (staff can usually do up
  to ~50 pages); requests handled in order received, typically 3–5 business days plus copying/mail.

---

## Provenance & method

- Page-level gaps and H/L parity tiers: `PAGE_CONTINUITY_AUDIT_2026-06-23.md` section (c) +
  `C:\PatoLex-scratch\_audit_all.jsonl` (deterministic top-strip running-head OCR + monotone
  offset DP; even-parity = HIGH dropped-leaf, odd-parity = LOWER inspect-only).
- Chapter names + the original scan-request framing: `ARCHIVES_SCAN_REQUEST_2026-06-22.md`.
- Overlap dedup: all 10 archivist page-ranges verified to coincide with page-level audit gaps in
  the same volume+range (script `C:\PatoLex-scratch\_packet_compute.py`); chapter info folded in as
  annotation, adding zero pages. 175 distinct pages = 126 HIGH + 49 INSPECT; reconciles to the
  audit headline.

*Document generated 2026-06-29. This supersedes the two prior sources as the single carry-to-
Sacramento packet; the prior docs remain as provenance.*
