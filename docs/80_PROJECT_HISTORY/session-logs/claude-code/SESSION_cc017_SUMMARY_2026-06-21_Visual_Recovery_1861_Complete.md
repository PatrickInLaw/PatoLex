# Session cc017 Summary

| Field | Value |
|-------|-------|
| Session | cc017 |
| Date | 2026-06-21 |
| Agent | Claude Code (autonomous, continued from context-exhausted cc016 fork) |
| Context | VISUAL-recovery worker: 1861 year, completing 54 remaining gap chapters |
| Branch | main |

---

## What Was Done

Completed the 1861 visual recovery campaign, resolving the final 54 gap chapters (of the original 161 total targeted). The prior session (same day) had already confirmed 107 chapters (Chs 4–399); this session picked up from Ch 404 forward.

**Approach:** Systematic image reads of page PNGs + OCR text scans per bracket range. For each cluster of gap chapters, identified the surrounding anchors from `parsed_acts_merged.json`, read the page images in the bracket range, confirmed chapter headers visually, recorded OCR key and source_page.

**Key chapters confirmed this session:**
- Chs 404–537 (all 54 remaining gaps), batch-confirmed via direct image reads
- Ch 428 + Ch 429 both found on page cluster 532–534 (Albion River bridge and Santa Clara court-house bonds)
- Ch 436 + Ch 437 both start on OCR key 542 (troops pay act + immediate effect act, same page)
- Ch 433+434, 442+443, 451+452, 470+471, 481+482, 483+484, 486+487+488, 516+517: multi-chapter pages

**Two legislative gaps confirmed:**
- **Ch 140 (CXL)**: pages 169–177 fully occupied by Ch 139 (long El Dorado act) and Ch 141; no room; confirmed in prior session
- **Ch 493 (CDXCIII)**: number skipped between Ch 492 (massive SF Consolidation Act, OCR keys 587–595, 9 pages) and Ch 494. Full-book OCR search for "XCIII" found nothing. Page images confirm direct transition from Ch 492 end to Ch 494 on page_0596 with no intervening act.

**OCR-miss patterns discovered:**
- Ch 407 header printed as CCCCVII but OCR read as CCCXCVII (leading C garbled/dropped)
- Ch 478 header CCCCLXXVIII misread as CCCCLX (LVII portion completely dropped)
- Ch 532 (Railroad Incorporation Act, 20 pages, keys 651–670): zero chapter headers in OCR across entire span — one of the worst OCR-miss cases in the 1861 volume

**Final manifest result:** N=538, present=536, missing=2 (Ch 140 + Ch 493)

---

## Files Changed

**Scratch files updated:**
- `C:\PatoLex-scratch\visual_recovery_write.py` — crash-safe writer, updated with all 161 CONFIRMED entries

**Output:**
- `C:\PatoLex-scratch\production-1861\parsed_acts_visual.json` — 161 recovered acts: verified=159, legislative_gap=2, not_found=0, draft=false

**Run log:**
- `docs/80_PROJECT_HISTORY/run-logs/visual-1861-run.log` — final completion entries appended

---

## Decisions Made

| Decision | Detail |
|----------|--------|
| Ch 493 = legislative_gap | Full-book OCR search + 4 image reads of the page_0596 transition confirm no Ch 493 in the 1861 volume. Marked as skipped/omitted by the Legislature. |
| Ch 464 vs Ch 465 clarification | Prior context had the Sacramento Roads act misidentified as Ch 464. Corrected: Ch 464 = brief Plumas Co. bond sureties (1 page, key 559); Ch 465 = Sacramento Roads act (5 pages, key 560). |
| source_page anomalies | Many chapters in the 420–460 range have out-of-order source_pages in merged_acts. Bracket searches used only monotonically non-decreasing pages from known-good anchors. |

---

## Open Items at Close

| Item | Priority |
|------|----------|
| Ingest parsed_acts_visual.json (1861) into Postgres via visual ingest script | HIGH |
| Run `_residual_manifest.py 1861` post-ingest to confirm 536 present | HIGH |
| Continue visual recovery for other years (1860 ingest also pending) | NEXT |

---

## Next Session Should Start With

1. Check if visual ingest script exists; if not, create one matching the 1860 ingest pattern
2. Run visual ingest for 1861 against `C:\PatoLex-scratch\production-1861\parsed_acts_visual.json`
3. Run manifest post-ingest; verify present=536, missing=2
4. Repeat for 1860 if not yet ingested

---

## Lessons Learned

- **Ch 407 trap**: In dense chapter clusters, a dropped leading Roman character (CCCC→CCC) can make a chapter look like it belongs to a completely different, much-earlier range. Always cross-check chapter numbers against surrounding book page numbers.
- **Ch 493 legislative gap pattern**: The SF Consolidation Act (Ch 492) is the largest act in the 1861 session laws (~9 pages). Chapter numbers were sometimes skipped around large city charter acts — the Legislature enrolled Ch 492 and Ch 494 with no Ch 493.
- **Multi-chapter pages are common in the 480s–540s range**: Very short appropriation/claims acts (2–5 sections) fit 2–3 per page. Expect multi-chapter pages especially for acts that say "the sum of X dollars is hereby appropriated."
- **20-page OCR blackout**: The Railroad Incorporation Act (Ch 532) has zero detectable chapter headers across 20 pages in any OCR engine. Visual inspection is required for any act of this length. The header appears on OCR key 650 and the act ends at key 670 — flag any 15+ page stretch with no headers as requiring explicit image check at the boundary.
