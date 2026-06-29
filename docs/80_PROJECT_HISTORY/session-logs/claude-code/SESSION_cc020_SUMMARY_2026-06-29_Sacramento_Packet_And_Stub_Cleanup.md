# Session cc020 — Sacramento Scan Packet + Stub Cleanup (no quarantine) — 2026-06-29

## Goal
Two deliverables for OCR-era completeness:
- **Item 2:** consolidate the two missing-paper sources (page-level missing-leaf audit +
  chapter-level archivist request) into ONE carry-to-Sacramento packet, organized by physical
  volume, every printed page listed once.
- **Item 3:** VERIFY-then-QUARANTINE abandoned near-empty scaffolding `production-*` dirs
  (acts ≤ 2), gated by 3 hard checks. Reversible move only; never delete.

## What landed

### Item 2 — Sacramento scan packet
`docs/80_PROJECT_HISTORY/SACRAMENTO_SCAN_PACKET_2026-06-29.md`
- **175 distinct printed pages** across **49 volumes**, 82 gaps. Tier split **126 HIGH
  (even-parity leaf) + 49 odd-parity INSPECT-ONLY** — reconciles exactly to the audit headline.
- **10 archivist chapter page-ranges all dedup onto page-level audit gaps** (overlap proven,
  zero double-count). 17 named chapters folded in as annotation, adding 0 pages.
- Flags: 1929 Ch.881 printed-page discrepancy (archivist pre-audit estimate 1962-1963 vs
  audit-detected leaf 1974-1975 — parse confirms Ch.881 is the gap); 1970 Ch.906/907 leaf is
  odd-parity (the one named-chapter page that is INSPECT not HIGH); 1985 has a 2nd HIGH leaf
  (804-805) the archivist omitted. Archive contacts block carried over.
- Hans (verify-auditor): audit pending/SOUND.

### Item 3 — stub cleanup: QUARANTINE NOTHING
`docs/80_PROJECT_HISTORY/STUB_CLEANUP_FINDINGS_2026-06-29.md`
- Swept all 215 `production-*`; **12 dirs have acts ≤ 2**. **Every one fails ≥1 gate** → nothing
  quarantined. No `_quarantine_stubs` folder created (nothing to move).
- The 3 "known candidates" are real **Extra-Session volumes**: `1927-vol1-26chapters` = 1926
  Extra (46th), `1929-vol1-28chapters` = 1928 Extra (47th), `1883-84` = 1884 Extra (25th) — all
  mapped in `ingest_clean.py`/`ingest_from_ocr.py` (gate 3), and the latter two hold UNIQUE acts
  whose titles DIFFER from the regular sibling (gate 2 fails — NOT duplicated).
- The other 9 (`1873-74-code` + eight `volN`/`vol6` dirs) are referenced config / real
  continuation volumes with 392–2157 page renders (auditable CLEAN). Removing breaks audit
  volume resolution — same hazard as `production-2000-vol*`.
- Hans (verify-auditor, fresh context): **VERDICT SOUND** — quarantine nothing is correct.

## Finding (durable)
0 acts in `parsed_acts_merged.json` is NOT evidence of scaffolding. Two legit causes: (1) real
Extra-Session volumes whose chapter-number collides with the regular session's union but whose
text is unique; (2) continuation/index volumes whose acts live in the sibling. Reliable test is
gate-3 config-reference + page-render presence + audit status, not the merged-acts count.
(Recorded in `STUB_CLEANUP_FINDINGS_2026-06-29.md`.)

## Scoreboard
`_recall_allyears.py` byte-identical before/after (nothing moved): 215 dirs, 108 mapped years,
RESIDUAL = 17, 99.98% after.

## Files
- NEW `docs/80_PROJECT_HISTORY/SACRAMENTO_SCAN_PACKET_2026-06-29.md`
- NEW `docs/80_PROJECT_HISTORY/STUB_CLEANUP_FINDINGS_2026-06-29.md`
- NEW this session log
