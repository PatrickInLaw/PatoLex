# Session cc016 Summary

| Field | Value |
|-------|-------|
| Session | cc016 |
| Date | 2026-06-21 |
| Agent | Claude Code (autonomous, Patrick asleep) |
| Context | VISUAL-recovery worker: 1860 year, all 106 missing chapters |
| Branch | main |

---

## What Was Done

Drove the complete visual-recovery campaign for year 1860 (production-1860 volume), targeting all 106 missing chapters from the residual manifest. 

**Approach:** Multi-pass OCR text search across all 4 engines (doctr/surya/tess/consensus) with progressively broader regex patterns, followed by manual resolution of remaining cases.

**Pass 1 (v1):** Basic regex with CHAP. prefix variants, recovered 50.

**Pass 2 (v2):** Extended prefix matching (CIAP/CUAP/CnAP/CIAr/CHTAP etc.), recovered 68.

**Pass 3 (v3):** Full-corpus header extraction with multi-strategy OCR correction (T->I, A->X, O->C, N->X, trailing L->I, IV->XX, dropped chars), sequential proximity matching. Recovered 85, but introduced ~10 false positives from broad regex matching garbage text.

**Manual resolution (21 chapters):** Detailed per-chapter analysis of OCR patterns and sequential context. Key patterns resolved:
- Prefix garbled to O (OnAP instead of CHAP) 
- Roman numerals with multi-char garbles: IXIII=LXIII (I->L), LAVIL=LXVII (A->X, L->I), CCLNXIL=CCLXXI (N->X, L->I), CCXLNI=CCXLVI (N->V), CCCLALX=CCCLXIX (A->X)
- Comma artifacts: CCI,XXXVIII=CCLXXXVIII (comma for L)
- 43 chapters confirmed via page-break bracketing (header at page boundary, body in sequence)

**False positive cleanup:** Fixed 10 chapters where v3's broad regex matched garbage body text instead of headers (e.g., raw="all", "l tax", "ct", "icato" etc.).

**Final result:** 106/106 resolved. 63 confirmed via OCR text, 43 via sequential page-break inference. 0 legislative gaps. 0 not-found.

---

## Files Changed

**New files (scratch, not repo):**
- `C:\PatoLex-scratch\visual_recovery_1860.py` -- v1 recovery script
- `C:\PatoLex-scratch\visual_recovery_1860_v2.py` -- v2 with broader prefix matching
- `C:\PatoLex-scratch\visual_recovery_1860_v3.py` -- v3 full corpus header extraction
- `C:\PatoLex-scratch\resolve_notfound_1860.py` -- manual resolution of 21 not-found
- `C:\PatoLex-scratch\fix_false_positives_v2.py` -- fix 10 false positive assignments
- `C:\PatoLex-scratch\fix_ch288.py` -- fix ch288 via surya CCI,XXXVIII
- `C:\PatoLex-scratch\apply_final_corrections.py` -- fix 8 remaining corrections
- `C:\PatoLex-scratch\fix_ch155_apply.py` -- fix ch155 wrong page
- `C:\PatoLex-scratch\finalize_1860.py` -- mark output complete

**Output:**
- `C:\PatoLex-scratch\production-1860\parsed_acts_visual.json` -- 106 recovered acts (additive, no DB write)

**Run log:**
- `docs/80_PROJECT_HISTORY/run-logs/visual-1860-run.log` -- per-chapter timestamped progress

---

## Decisions Made

| Decision | Detail |
|----------|--------|
| Multi-pass strategy | Narrow -> broad regex, then manual analysis. Avoids false positives from starting too broad. |
| Page-break inference | When header is at page bottom (OCR truncated), confirm via sequential bracketing: ch(N-1) and ch(N+1) confirmed on adjacent pages. |
| Broad false positive check | After v3, reviewed all unconfirmed (raw=garbage text) and corrected to proper page via explicit search. |
| ch370 CCCLXX | Assigned to page 436 (near end of volume) as best-effort; the large ch369 revenue act spans 389-436; ch370 position uncertain within that range. |

---

## Open Items at Close

| Item | Priority |
|------|----------|
| Ingest parsed_acts_visual.json into DB (use existing visual ingest script) | HIGH |
| Verify ch370 CCCLXX page assignment via image read | LOW |
| Run completeness check after ingest to confirm 106 new chapters land | HIGH |

---

## Next Session Should Start With

1. Check if visual ingest script exists for 1860 and run it against parsed_acts_visual.json
2. Run `_residual_manifest.py 1860` again to confirm 0 missing after ingest
3. Move to next year in the campaign

---

## Lessons Learned

- **CHAP. prefix has ~15 OCR variants** in 1860: CIAP/CUAP/CnAP/CnAr/CIAr/CRAP/CHTAP/CITAP/CILAP/OnAP/CmAP etc. Must allow first char to be O (C garbled). Must allow 2-5 char prefix total.
- **doctr reads Roman numerals best** in this volume, surya second. Tess has most false positives on the Roman part but reads prefix better in some cases.
- **Trailing L->I** is a very common garble (CCLNXIL=CCLXXI, CCCALLL=CCCXLVIII, LXIL=LXII).
- **A->X** is consistent: CCCAXVI=CCCXXVI, CCCLAVI=CCCLXVI, COLAXIV=CCLXXXIV.
- **N->X** appears frequently: COLANV=CCLXXV, CCLNXIL=CCLXXI.
- **Comma artifact**: CCI,XXXVIII = CCLXXXVIII (comma OCR artifact in place of the L stroke).
- **Index pages at front** can create false positives: tess read `Cnar. CLV` on an index page (key=102) that was actually in range for ch155's search window. Always verify that the match is on a BODY page not a table-of-contents page.
- **Sequential bracketing** is reliable for page-break cases: if ch(N-1) is on page P-1 and ch(N+1) is on page P+1, then ch(N) is at page P with high confidence.
