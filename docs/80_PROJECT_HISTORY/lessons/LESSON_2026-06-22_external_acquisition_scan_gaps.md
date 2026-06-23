# LESSON 2026-06-22 — External acquisition for physical scan gaps: routes, traps, and the Chief-Clerk-is-our-source trap

## Context
19 genuinely-absent chapters across 7 "Statutes of California" volumes have **physically missing printed
leaves** in our local Chief Clerk scans (gap-verified 2026-06-22). Re-OCR cannot recover them — only a
*different* complete copy can. This lesson records what works, what is walled, and the one trap that will
silently waste a download.

## The trap (most important)
**The California Assembly Chief Clerk online archive
(`clerk.assembly.ca.gov/.../archive/Statutes/<yr>/<vol>.pdf`) IS the source of our local scans.**
A research pass will happily surface these as "freely downloadable official government PDFs" — and they
are downloadable — but they are **byte-for-byte the same defective scans we already have.** Verified by
downloading 1927 v.1 (131 MB) and 1986 v.3 (101 MB): page counts identical to local (2399 / 1947) and the
**same printed-page gaps** (1927: printed 1625→1628, 1626-1627 absent; 1986: printed 4811→4816,
4812-4815 absent). **Re-downloading the Chief Clerk PDF re-acquires the missing leaf.** Always *compare
page count + OCR the gap region* against the local copy before believing a "new" source recovers a gap.

## What works: Google Books full-volume PD download
- **`https://books.google.com/books/download/<title>.pdf?id=<GBID>&output=pdf`** (browser User-Agent)
  downloads a complete public-domain volume with **no login**. This recovered 1905 (GBID `mKlAAQAAMAAJ`,
  the CDL/UCD copy, 1303 pp.) — its printed pp.497-512 are present where the local scan dropped them
  (the local scan had *duplicated* 481-496, masking the drop). All 9 chapters (389-397) recovered.
- Resolve a HathiTrust `pd` htid (or a CDL-sheet `vid=LIB:barcode`) to the Google Books `id=` token via
  the `books.google.com/books?vid=...` page, then hit the download endpoint.

## What is walled
- **HathiTrust**: full-volume PDF download AND single-page image endpoint both **403** without a
  member-institution login; catalog `Record/`+`Search` HTML also 403. **Only the Bibliographic API is
  open**: `catalog.hathitrust.org/api/volumes/full/recordnumber/<rec>.json` → every item's `enumcron`,
  `htid`, `rightsCode` (`pd`=full-view). Use it to learn *what exists* and map to Google Books.
- **Google Books API**: needs a key (default quota 0); the `books.google.com/search?tbm=bks` HTML is not
  fetchable by the web tool. Work from the CDL Google Sheet + individual `?vid=`/`?id=` "about" pages.

## Coverage reality (the hard negative)
The open digitized **bound Statutes serial** (HT catalog records `010587406`, `011925156`, `010063843`)
covers single-/multi-vol Statutes **only through 1967, plus a stray 1972 v.1** — it **skips 1927 & 1929**
(gap 1925→1931) and has **nothing for 1970/1981/1985/1986**. The IA `statutescalifor##greggoog` series
stops ~1911-1916. So 6 of the 7 target volumes have **no freely-downloadable copy with the missing
leaves**; they need a member HathiTrust login (full-volume download) or a paid source (HeinOnline/West).
CA statute *text* is public-domain by Legislative Counsel declaration, but that PD status does **not**
put a gap-free *scan* in any free repository.

## Authoritative index
CDL "California Legislative Publications Collection Links to HathiTrust & Google Books" Google Sheet
(`docs.google.com/spreadsheets/d/17KKJAqDRkptT__dk-J_qc4wDcSeVW2hMe-TrsNzrNzI`, **Statutes tab = gid 0**;
fetch with `/export?format=csv&gid=0`). gviz `sheet=<name>` matching silently falls back to a default
tab if the name doesn't match exactly — address tabs by **gid**.

## Procedure that confirmed 1905 (confirm-only, append-safe)
Render gap pages with PyMuPDF (surya-venv python) → OCR running-head strip + full page with Tesseract 5
(`C:\Program Files\Tesseract-OCR\tesseract.exe`, set `pytesseract.pytesseract.tesseract_cmd`) → read the
printed page number and the `CHAPTER <roman>` header → map roman→int → verify contiguity against the
pre-gap and post-gap chapters already present locally → update the `not_found_needs_reocr` stubs in
`parsed_acts_visual.json` **in place** (not appended) to `status="image_verified"`,
`printed_number_confirmed=true`, `origin="external_acquired_googlebooks"`, with a note citing the source
+ identifier → re-run `_residual_manifest.py <year>`. 1905 residual 9→0.

## See also
- `docs/80_PROJECT_HISTORY/EXTERNAL_ACQUISITION_2026-06-22.md` (full per-volume table + outcome)
- `docs/80_PROJECT_HISTORY/SCAN_GAP_VERIFICATION_2026-06-22.md` (the gap inventory this acted on)
- `LESSON_2026-06-21_scan_gap_vs_header_loss_visual_recovery.md`
