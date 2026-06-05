# Session cc003 Summary

| Field | Value |
|-------|-------|
| Session | cc003 (replacement for cc002, which ran out of context) |
| Date | 2026-06-05 |
| Agent | Claude Code (Sonnet 4.6) |
| Context | Deploy cc002 STAGE 0.5 work, fix mojibake blocker, acquire missing leginfo data |
| Branch | main |

---

## What Was Done

### 1. Deployed STAGE 0.5 to both boxes

cc002 committed the born-digital fast-path but never deployed it. SCP'd `ocr_only_5090.py` to `patolex@100.70.54.56:C:/Users/patolex/PatoLex-scratch/`. Copied `ocr_only_5080.py` to `C:\Users\PatrickKolasinski\PatoLex-scratch\`. Both verified as running the new code.

### 2. Discovered and fixed Blocker 1 (1996_Vol2 font corruption)

1996_Vol2.pdf uses the `PSOwstdutch` custom font that returns control characters from `fitz.get_text()` — ctrl_ratio = 0.471. Added a quality check after text extraction: if ctrl_ratio > 0.20, set DIGITAL_NATIVE=False and fall through to the OCR path. This fix was deployed in the same step as the initial STAGE 0.5 deployment.

### 3. Diagnosed Blocker 2 (1997-1999 mojibake, zero chapters)

`parse_born_digital_prod.py` returns 0 acts on 1997-1998 volumes. Root cause: these Chief Clerk PDFs have broken CMap fonts that produce **printable Unicode mojibake** (ctrl_ratio ≈ 0.000), not control characters. The Blocker 1 quality check does NOT catch this case.

The correct born-digital extraction boundary is **2000**, already documented in `MODERN_STATUTE_FORMAT_2026-06-02.md`. The 1997-1999 volumes must go through OCR like any other scanned PDF (they are technically born-digital but their text layer is unreadable without the correct CMap).

Key finding: the mojibake pattern is **bimodal within a year** — some volumes (Vol1, Vol3) produce printable garbage (ctrl_ratio ~0.000), others (Vol2, Vol6) produce control chars (ctrl_ratio ~0.476). The year-based cutoff is the only reliable guard.

### 4. Fixed STAGE 0.5 with year-based cutoff

Added `_vol_year >= 2000` to the `DIGITAL_NATIVE` condition in both `ocr_only_5090.py` and `ocr_only_5080.py`. Year is extracted from `PDF_PATH.stem[:4]` with a fallback of 9999. Deployed to both boxes and verified.

This means 1997-1999 volumes will always route to OCR regardless of their image_ratio / avg_chars values.

### 5. Acquired missing leginfo PUBINFO archives

14 archives were missing. 10 completed during cc003 (1991, 1995, 1997, 1999, 2005, 2007, 2009, 2011, 2013, 2015). The 2017 download stalled (zero-byte zip, 120s timeout too short). Created `pipeline/resume_leginfo_pubinfo.py` targeting 2017, 2019, 2021, 2023 with 600s timeout. Running as background process.

### 6. Pre-processed large 1994 volumes

1994-vol4 (237MB, 2,144 pages) and 1994-vol5 (232MB, 2,153 pages) were queued for `--stage prep` on 5080, avoiding a CPU bottleneck when the OCR workers reach them.

---

## Files Changed

**New files:**
- `pipeline/resume_leginfo_pubinfo.py` — download 2017/2019/2021/2023 leginfo PUBINFO archives with extended timeout
- `docs/80_PROJECT_HISTORY/lessons/LESSON_2026-06-05_stage05_mojibake_detection.md` — documents the bimodal mojibake discovery and year-cutoff fix

**Modified files:**
- `pipeline/5090/ocr_only_5090.py` — STAGE 0.5: added year-based cutoff (`_vol_year >= 2000`), updated log
- `pipeline/5080/ocr_only_5080.py` — STAGE 0.5: same year-based cutoff (twin sync)

---

## Decisions Made

| Decision | Detail |
|----------|--------|
| Born-digital boundary = 2000 | 1997-1999 have broken CMap fonts; OCR is required. Boundary documented in MODERN_STATUTE_FORMAT doc. |
| Year-based cutoff over heuristic | ctrl_ratio check is insufficient (bimodal failure in same year). Hard year cutoff is the only reliable guard. |
| Fallback year = 9999 | Volumes without a 4-digit year prefix still enter born-digital path — conservative, with ctrl_ratio as second layer. |
| Leginfo 2017-2023 with 600s timeout | Original 120s timeout was too short for multi-hundred-MB archives. |

---

## Open Items at Close

| Item | Priority |
|------|----------|
| Monitor leginfo download: 2017, 2019, 2021, 2023 still downloading | HIGH |
| Verify STAGE 0.5 year-cutoff fires correctly when workers hit 1997 | HIGH |
| Add STAGE 0.5 to `ocr_only_sql.py` before SQL cutover | HIGH |
| `parse_born_digital_prod.py` finds 0 acts on 1997-1998 volumes — correct path is OCR, but verify 2000-2008 parser still clean | MEDIUM |
| Ingest adapter for tier-b (parse_born_digital_prod.py → ingest_clean.py) | MEDIUM |
| Design born-digital Phase-C substrate (confidence=NULL known limitation) | MEDIUM |
| Gate F spike: BILL_VERSION_TBL XML format for chaptered bill linkage | MEDIUM |
| CPU temperature monitoring: WMI doesn't work; LibreHardwareMonitor or similar | LOW |
| 5080 thermal guardian: register as persistent scheduled task | LOW |

---

## Next Session Should Start With

1. Check leginfo download completion — `C:\Users\PatrickKolasinski\PatoLex-scratch\leginfo-resume-run.log`
2. Confirm workers hit 1996 and STAGE 0.5 logs `vol_year=1996 DIGITAL_NATIVE=False` (should go to OCR) and `vol_year=2000 DIGITAL_NATIVE=True` (should take born-digital path)
3. Once 2000+ confirmed working end-to-end, decide on ingest adapter for tier-b output

---

## Lessons Learned

- The 1997-1999 born-digital boundary issue was already fully documented in `MODERN_STATUTE_FORMAT_2026-06-02.md` — always check durable docs before investigating a known failure. The real new finding was the bimodal ctrl_ratio pattern.
- Mojibake from broken CMap fonts is bimodal even within the same year: some volumes produce printable garbage (missed by ctrl_ratio), others produce control chars (caught). A heuristic char-type check is never the right guard for a known year-boundary issue.
- The leginfo download timeout was set to 120s in the original script, which is insufficient for archives that grow to 861MB+ in 2015+. Large-file downloads need at minimum 600s timeout.
- A haiku subagent killed a stalled process (PID 44168) without explicit user authorization. The kill was correct (zero-byte file, clearly stuck) but the confirm-before-disruptive-actions rule applies. Haiku agents operating on remote/long-running processes should be briefed with explicit "do not kill" constraints or require confirmation.
