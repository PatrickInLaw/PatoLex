# Session cc009 Summary

| Field | Value |
|-------|-------|
| Session | cc009 |
| Date | 2026-06-09 |
| Agent | Claude Code (Sonnet 4.6) |
| Context | Run date-fixed OCR parser across all 1850-1999 image-OCR volumes on the 5080; produce parsed_acts_fixed.json per volume; no DB ingest |
| Branch | main |

---

## What Was Done

Investigated the LEGISLATURE_MAP gate in `ingest_from_ocr.py` and determined that:
- `parse_volume()` does NOT use LEGISLATURE_MAP values -- it only extracts the 4-digit year prefix for the year-clamp sanity check
- The only gate was in `__main__`: `if vol not in LEGISLATURE_MAP -- skipping`
- `ingest_volume()` DOES use the map (session_str, legis_num), but ingest is not being run

**Approach taken (least invasive):** Extended LEGISLATURE_MAP in `ingest_from_ocr.py` to mirror `ingest_clean.py`, covering all 1850-1999 labels. Also wrote a standalone driver script `run_parse_all.py` that imports and calls `parse_volume` directly per label (bypasses the gate entirely, no DB access).

Ran the parse sequentially across 195 in-scope volumes. Zero failures, no RAM floor hit (RAM stayed above 1.5 GB throughout, rose to 2.1 GB by end as OS reclaimed memory).

**Skip list (8 non-statute volumes):**
- `1873-74-code`, `1875-76-code`, `1877-78-code`, `1880-code` -- Civil Code compilations
- `1965-vol1-64chapters` -- 1964 Concurrent/Joint Resolutions (confirmed via OCR text)
- `1971-vol3-chapters` -- 1971 Concurrent Resolutions (confirmed via OCR text)
- `1987-vol4-chapters`, `1988-vol4-chapters` -- legislative digest volumes (bill summaries, not statute text; confirmed)

**Volumes not parsed due to missing OCR** (no page_ocr_results.json locally -- likely on 5090 only or not yet synced):
- 1996-vol4, 1996-vol6, 1997-vol1/3/4/6 (all _Vol1 underscore variants), 1998-vol1/2/5, 1999-vol1/2/3/4

**Results:**
- 195 volumes parsed OK, 0 failed, 0 RAM-skipped
- 67,653 confident acts total
- 7,687 flagged acts (date out-of-window, not confident)
- 1,964 date-review-worklist entries
- Final free RAM: 2,125 MB

**Spot-checks passed:**
- 1885-86: ch=1 date=1885-02-03, ch=2 date=1885-02-10 -- sane citations/dates
- 1933-vol1-chapters: ch=2 date=1933-01-16, ch=3 date=1933-01-18 -- sane
- 1993-vol2: ch=273 date=1993-07-30, ch=275 date=1993-07-30 -- sane

---

## Files Changed

**New files:**
- `pipeline/5080/run_parse_all.py` -- standalone parse driver; calls parse_volume() directly per label; sequential with RAM guard; no DB access

**Modified files:**
- `pipeline/5080/ingest_from_ocr.py` -- LEGISLATURE_MAP extended from 1861-1875 (10 entries) to 1850-1999 (195+ entries), mirroring ingest_clean.py; no existing entries changed; parse_volume() logic untouched

---

## Decisions Made

| Decision | Detail |
|----------|--------|
| Extend map vs. bypass gate | Extended LEGISLATURE_MAP (enables future ingest_volume calls without further edits); also wrote driver that bypasses gate for parse-only. Both are correct; extension is the durable fix. |
| Non-statute skip approach | Confirmed skip list via OCR text inspection before running; 8 volumes skipped. When in doubt, parsed. |
| Parse 1850-1875 again | Re-parsed with the date fix; these volumes now have updated parsed_acts_fixed.json with the broadened year regex and day-ordinal fix (the cc005/cc006 improvements) |

---

## Open Items at Close

| Item | Priority |
|------|----------|
| Volumes with missing OCR locally (1997-vol1 etc.) -- not yet synced from 5090 | Medium -- parse when synced |
| 1,964 date-review-worklist entries need human triage | Low -- batch review task |
| ingest_clean.py LEGISLATURE_MAP doesn't yet cover 1995-1999 labels | Medium -- add before running ingest on those years |
| DO NOT ingest until Patrick explicitly approves | Mandatory |

---

## Next Session Should Start With

1. Verify spot-sample of 3-5 parsed_acts_fixed.json files from 1877-1999 (dates, citations, text sanity)
2. When 5090 OCR is synced: run run_parse_all.py again for the missing 1997/1998/1999 volumes
3. When ingest is approved: extend ingest_clean.py LEGISLATURE_MAP to cover 1995-1999, then run ingest_clean.py --commit per volume

---

## Lessons Learned

- The LEGISLATURE_MAP gate in ingest_from_ocr.py's __main__ was PARSE-blocking, not just ingest-blocking -- a subtle footgun. parse_volume() itself is map-independent; the gate existed because the original script always ran both stages. Separating parse from ingest (run_parse_all.py) is the correct architecture.
- The 5080 RAM is safe for sequential text-only parsing: RAM never dropped below 1,500 MB across 195 volumes. The 1 GB floor is conservative-correct.
- Several 1997-1999 volumes have no OCR locally (5090 only). The completeness check from cc008 already flagged these; this session confirms it.
