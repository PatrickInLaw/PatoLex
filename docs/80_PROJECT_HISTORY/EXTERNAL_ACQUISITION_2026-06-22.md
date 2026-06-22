# External Acquisition of Missing-Leaf Statute Volumes — 2026-06-22

**Task:** Acquire external complete copies of 7 "Statutes of California" volumes whose printed leaves
are physically absent from the local Chief Clerk scans (gap-verified in
`SCAN_GAP_VERIFICATION_2026-06-22.md`), to recover 19 genuinely-absent chapters. Network/CPU only —
no GPU consensus OCR; local Tesseract 5 header-OCR used for confirmation. Additive only; no DB writes.

## Source-route findings (durable)

- **HathiTrust is auth-walled for unauthenticated agents.** Both the full-volume PDF download
  (`/cgi/imgsrv/download/pdf?id=...`) and even the single-page image endpoint
  (`/cgi/imgsrv/image?id=...;seq=N`) return **HTTP 403** without a member-institution login. The
  catalog Record/Search HTML pages also 403. **Usable HathiTrust surface = the Bibliographic API only**
  (`https://catalog.hathitrust.org/api/volumes/full/recordnumber/<rec>.json`), which is open and returns
  every item's `enumcron` (year/vol), `htid`, and `rightsCode` (`pd` = public-domain full-view).
- **Google Books CAN download a full public-domain volume** with no login:
  `https://books.google.com/books/download/<title>.pdf?id=<GBID>&output=pdf` (use a browser User-Agent).
  This is the working route for PD volumes.
- **HT htid ↔ Google Books vid are the same library barcode.** A HathiTrust `pd` item digitized by
  Google maps to a Google Books volume; resolve the actual `id=` token from the `books.google.com/books?vid=<LIB>:<barcode>`
  page, then download via the Google Books PDF endpoint.
- **The authoritative index** of what is openly digitized is the CDL "California Legislative Publications
  Collection Links to HathiTrust & Google Books" Google Sheet
  (`docs.google.com/spreadsheets/d/17KKJAqDRkptT__dk-J_qc4wDcSeVW2hMe-TrsNzrNzI`, **Statutes tab = gid 0**;
  export CSV via `/export?format=csv&gid=0`).
- **Coverage limit (the hard negative):** the digitized **bound Statutes serial** (HT catalog records
  `010587406`, `011925156`, `010063843`) covers single-/multi-vol Statutes **only through 1967, plus a
  stray 1972 v.1**. It **skips 1927 and 1929** (gap 1925→1931) and has **nothing for 1970, 1981, 1985,
  1986**. The Internet-Archive `statutescalifor##greggoog` Google-scanned series stops ~1911-1916.
  Post-1967 bound Statutes were not part of the open mass-digitization (despite CA statute *text* being
  public-domain by Legislative Counsel declaration — that PD status lives in paywalled HeinOnline/West,
  not in a freely-downloadable scan).
- **The CA Assembly Chief Clerk online archive IS the source of our defective scans — verified.** A
  research sweep surfaced direct PDF URLs at
  `clerk.assembly.ca.gov/sites/clerk.assembly.ca.gov/files/archive/Statutes/<yr>/...` for all six
  remaining volumes. These are real, login-free downloads — **but they are byte-equivalent to the local
  defective scans.** Test-downloaded 1927 v.1 (131 MB) and 1986 v.3 (101 MB): page counts **identical**
  to the local copies (1927 = 2399 pp., 1986 = 1947 pp.) and the **gap regions identical** — 1927 jumps
  printed 1625 (ch815) → 1628 (ch817) with 1626-1627 absent; 1986 jumps printed 4811 (ch1356) → 4816
  (ch1359) with 4812-4815 absent. **Re-downloading the Chief Clerk PDF re-acquires the same missing
  leaf — it cannot recover the gap.** (The two test downloads were deleted as duplicates.) This is
  exactly the brief's warning: "else the copy is the same incomplete scan."

## Per-volume result table

| # | Volume | Need printed pp. | Chapters | Source tried (best) | Identifier / URL | OBTAINED | Pages verified present | Chapters recovered | Still missing |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1905 Statutes (single vol) | 497-512 | 389-397 (9) | Google Books (CDL/UCD copy) | `books.google.com/books?vid=UCD:31175019185118` → GBID **mKlAAQAAMAAJ** (PD, 1303 pp.) | **YES** | 497-512 (THIRTY-SIXTH SESSION running heads idx 555-570) | **389-397 (all 9)** | none |
| 2 | 1927 Statutes Vol 1 (47th) | 1626-1627 | 816 (+817 title) | IA, Google Books, HathiTrust bib API, CDL sheet, **Chief Clerk archive (downloaded+compared)** | clerk `27vol1_Chapters.pdf` = **same defective scan** (2399 pp., 1626-1627 absent) | **NO** | — | none | ch816; ch817 title-only |
| 3 | 1929 Statutes Vol 1 (48th) | 1962-1963 | 881 | IA, Google Books, HathiTrust bib API, CDL sheet, Chief Clerk archive | clerk `29Vol1_29Chapters.pdf` = our local source (serial skips 1925→1931 elsewhere) | **NO** | — | none | ch881 |
| 4 | 1970 Statutes Vol 1 | leaf 1648 | 906, 907 | IA, Google Books, HathiTrust bib API, CDL sheet, Chief Clerk archive | clerk `70vol1_Chapters.pdf` = our local source (open serial stops 1967) | **NO** | — | none | ch906, ch907 |
| 5 | 1981 Statutes Vol 2 | 1562-1563 | 378 | IA, Google Books, HathiTrust bib API, CDL sheet, Chief Clerk archive | clerk `81Vol2.PDF` = our local source (no open scan post-1972) | **NO** | — | none | ch378 |
| 6 | 1985 Statutes Vol 1 | 1859-1860 | 505, 506, 507 | IA, Google Books, HathiTrust bib API, CDL sheet, Chief Clerk archive | clerk `85Vol1_Chapters.pdf` = our local source | **NO** | — | none | ch505, ch506 (ch507 already present in local parse — see note) |
| 7 | 1986 Statutes Vol 3 | 4812-4815 | 1357, 1358 (+1359 title) | IA, Google Books, HathiTrust bib API, CDL sheet, **Chief Clerk archive (downloaded+compared)** | clerk `86Vol3.PDF` = **same defective scan** (1947 pp., 4812-4815 absent) | **NO** | — | none | ch1357, ch1358; ch1359 title-only |

### Notes
- **1905 (OBTAINED):** Google Books copy contains the exact leaf (printed 497-512) physically absent
  from the local Chief Clerk scan (which duplicated 481-496, masking the dropped 497-512). Header OCR
  (Tesseract 5) confirmed each Roman-numeral CHAPTER on its printed page; the chapter→page→title map was
  written append-safe to `production-1905/parsed_acts_visual.json` (the prior `not_found_needs_reocr`
  stubs were converted in place to `status="image_verified"`, `printed_number_confirmed=true`,
  `origin="external_acquired_googlebooks"`). Contiguity double-checked: ch388 (CCCLXXXVIII, p496) →
  ch389…ch397 (p498-511) → ch398 (CCCXCVIII, p~519) — exactly matching the local scan's pre-/post-gap
  boundary. **Residual 1905: 9 → 0.**
- **1985 ch507:** the gap-verification listed 507 as also-missing, but at the parse level **ch507 is
  already present** in `production-1985-vol1-chapters/parsed_acts_merged.json` (real text, printed p1857).
  Only ch505 & ch506 are `not_found` stubs. So the residual-relevant 1985 loss is 2 chapters, not 3.
- **1970 ch906/907:** present in the visual JSON as `not_found_needs_reocr` stubs (page 1648, empty text),
  so the residual manifest already counts them as "present"; they remain genuinely unrecovered.

## Outcome

- **OBTAINED 1/7:** 1905 (9 chapters recovered, residual 9→0).
- **UNOBTAINED 6/7:** 1927, 1929, 1970, 1981, 1985, 1986 — no complete freely-downloadable copy with the
  needed leaves exists in the open repositories (Internet Archive / Google Books / CDL-HathiTrust). The
  bound-Statutes open digitization does not cover these years. NOT faked — left as genuine gaps.
- **Remaining genuinely-absent (residual-affecting):** 1927 ch816 · 1929 ch881 · 1970 ch906, ch907 ·
  1981 ch378 · 1985 ch505, ch506 · 1986 ch1357, ch1358 = **9 chapters** still missing.
- **Remaining title-only items (body present, OCR-recoverable locally; not external-acquisition gaps):**
  1927 ch817 · 1986 ch1359 (and 1972 ch517, out of this task's 7-volume scope).

These 6 volumes require either a member-institution HathiTrust login (full-volume download) or a
paid source (HeinOnline / West) — outside this network-only task's reach.
