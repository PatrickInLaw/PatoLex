# Early-Era Printed Table-of-Acts Denominator Sweep (1850–1899) — cc015, 2026-06-20

**READ-ONLY validation. The oracle (`ca_chapter_counts.tsv`) was NOT modified — the 2 FLAGs below are Patrick's call.**

## What this is

The definitive index-anchored validation of the **early OCR-era** chapter-count denominators. For each 1850–1899 regular session, the chapter count was independently re-derived from the **volume's own printed front-matter Table of Acts** ("CONTENTS — Statutes of California": *No. of Chapter | Title | Date | Page*, chapter-ordered) — the strongest primary source — and compared to the oracle's `total_chapters`. This is an INDEPENDENT check of the prior body-self-index / engine-union derivation (which is where the early-era oracle had been least certain).

**Why early-era only:** the printed `*_Index.pdf` files are page-keyed SUBJECT indexes, not chapter tables, and modern chapters volumes have no front-matter table of acts. The Table of Acts as a chapter-count source exists for the early (pre-1900) volumes; the modern denominator is already double-sourced (Chief Clerk stated ranges + body self-index). See `SESSION_cc015` for the scoping detail.

**Method/sources:** 1850–1860 from `production-<year>/pages_raw` scans; 1861–1899 from `chief-clerk-archive/*_Statutes.pdf` front matter (1883 from `1883-84_Code.pdf`). Run as a 6-batch fan-out (sonnet) + orchestrator finish/verify of the scan tail and both FLAGs. Each row: locate the Table of Acts, confirm it starts at Chapter 1, read the LAST entry = printed_max, compare to oracle_N.

## Result: 31 / 33 regular sessions CONFIRMED exactly; 2 FLAGGED (oracle > printed Table of Acts)

**CONFIRMED (printed Table-of-Acts max == oracle_N), 31 rows:** 1850=146, 1851=139, 1852=202, 1853=180, **1854=174** (dual-series, done separately), 1855=231, 1856=152, 1857=277, 1858=358, 1859=330, 1861=538, 1862=455, 1863-64=476, **1865-66=650**, 1867-68=545, 1869-70=583, 1871-72=637, 1873-74=679, 1875-76=613, 1877-78=673, 1880=126, 1881=77, **1883=96**, 1885=169, **1887=188**, 1889=290, 1891=280, 1893=244, 1895=223, 1897=278, 1899=253.

> **Independent re-confirmation of prior oracle corrections.** The sweep confirms — from the printed Table of Acts — the major early-era corrections made earlier this campaign: **1865-66 (280→650), 1883 (23→96), 1887 (51→188)** all match their volume's own contents exactly, as do 1861=538, 1862=455, 1889=290. The earlier correction work was right.

### THE 2 FLAGS — printed Table of Acts is LOWER than the oracle (likely oracle over-counts)

| canonical_id | session | oracle_N | printed Table-of-Acts max | Δ | evidence (verified by orchestrator) |
|---|---|---:|---:|---:|---|
| **S11** | **1860 Regular** | **385** | **371** | **−14** | `production-1860` front matter, page xviii: last act "**371** — An Act Appropriating Money to pay the Claim of J. S. Love; approved April 30, 1860 → p.406" immediately followed by "JOINT AND CONCURRENT RESOLUTIONS." Single series; table complete; no private-acts supplement. |
| **S14** | **1863 Regular** | **538** | **536** | **−2** | `1863_Statutes.pdf` p.xxxii: table runs … 532 (Oakland, p.xxxi) → 533 (Humboldt) → 534 (Solano) → 535 (Heros) → **536** (Oakland suppl.), then "CONCURRENT AND JOINT RESOLUTIONS." Chapters 537–538 absent from the volume's own Contents. |

**Assessment (for Patrick's decision — oracle edits are yours):**
- Both flagged oracle values were set by *body-OCR / engine-union re-derivation*, not the printed Table of Acts: **1860** was corrected 455→**385**; **1863 (S14, the reserved 14th session)** was re-derived to **538** ("duplicate-title test 18/20", 2026-06-19). In both cases the volume's own printed Table of Acts — the authoritative primary list — is *lower* (371, 536). The most likely reading is that the engine-union derivations **over-counted** (phantom/duplicate high chapters from OCR garble) and the oracle should come **down to 371 (1860) and 536 (1863)**.
- Caveat before any edit: a Table of Acts can in rare cases under-list (a chapter present in the body but omitted from the printed contents). Recommended confirmation before editing: check each volume's *body* last chapter (does it reach 371/536 or 385/538?) and, for 1860, the Chief Clerk archive page (the oracle's cited source) — if it also states a range ending at 385, that conflict needs resolving. **Resolution (2026-06-20, per Patrick's delegation):** both checks done and edits applied. **1863 → 536** (volume Contents end Ch.536; the 538 index-re-derivation over-counted by 2 — clean). **1860 → 371** (volume Contents end Ch.371; volume is COMPLETE at 453 pp, single-series, no special-acts section in OCR). ⚠️ **1860 carries an UNRESOLVED conflict:** the Chief Clerk archive page — the oracle's *original* source (the 455→385 history came from there) — lists **1–455**, which does NOT fit our 453-pp / 371-chapter volume (a 455-ch volume would run ~510+ pp). Most likely a catalog error or 1862 (=455) cross-contamination, but the 1860 row is flagged `toa-verified-CLERK-CONFLICT` so Patrick can override if a 455-chapter 1860 edition is known to exist. **Net oracle change: −16 chapters (120,205 → 120,189).**

> **1860 CONFLICT RESOLVED (2026-06-20):** the OFFICIAL Chief Clerk `1860_Statutes.pdf` (453pp, synced by the 5080) ALSO ends at **Ch.371** (last act = J. S. Love claim, identical to our scan) — so **371 is confirmed by TWO independent primary sources**, and the clerk archive-LIST page's "Statutes 1–455" is a **catalog-metadata error** (contradicted by the clerk's own PDF), not a real session count. The 1860 row is now `official-pdf-verified`; **no 1860 statutes are missing from our corpus.** (1863→536 still rests on our scan's Table of Acts alone; clerk-cross-check pending if desired.)

## Bottom line

The early-era (1850–1899) regular-session denominator is now **printed-Table-of-Acts-anchored: 31/33 confirmed exact against the volume's own primary contents, 0 contradicting low, 2 over-counts surfaced for review.** This upgrades the early-era basis from body-OCR-derived to primary-source-confirmed — exactly where the oracle was least certain.

*Artifacts: rendered table pages under `C:/Users/PatrickKolasinski/_sweepB*` and `_v1863`; render helper `pipeline/analysis/_render_pdf.py`. Oracle untouched.*
