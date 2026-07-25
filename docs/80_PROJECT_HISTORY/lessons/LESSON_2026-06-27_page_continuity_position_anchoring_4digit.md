# LESSON 2026-06-27 — Page-continuity audit: position-anchoring + 4-digit pagination recovers the modern multi-volume "Cohort B"

**Area:** deterministic page-continuity / missing-leaf audit (`C:\PatoLex-scratch\page_continuity_audit.py`)
**Deliverable:** `docs/80_PROJECT_HISTORY/PAGE_CONTINUITY_AUDIT_2026-06-23.md`
**Status:** Hans-reviewed **SOUND** (B1 + W1/W3/W4 fixed).

## The problem (Cohort B)
~46 modern multi-volume statute books (1957, 1971–1999, mostly `vol3`/`vol4`/`vol5`) were marked NOT AUDITABLE (`low_support` / `partial_numbering`) **despite reading ~100% of page numbers** (read≈1.0). Root cause: these volumes use **CONTINUOUS 4-DIGIT pagination across the year's volumes** — vol3 of 1990 runs printed pp ~3500–5700, a 6-volume year reaches the 8000s. So:
1. The old plausible-page cap `NUM_MAX=3000` **silently TRUNCATED the real 4-digit page-number stream**, leaving only the running-head YEAR and the per-page CHAPTER number as survivors → no consistent offset → `low_support`.
2. The true offset for a vol3/vol4/vol5 is **the cumulative page count of the prior volumes (thousands)**, not a small front-matter offset — the "offset ≈ tens of pages" intuition only holds for vol1. (The per-year offsets are beautifully monotonic: 1996 vol2=1457, vol3=3333, vol4=5227, vol5=7357 — confirming the model.)
3. 4-digit corner numbers garble far more easily than 3-digit ones (one misread digit on `4615` → `4915`/`9615`/… → a wildly wrong implied offset), inflating the offset-vote histogram and threatening the monotone fit.

## The fix (Patrick's position-anchoring method)
**Trust POSITION, not every read.** `implied_offset(page) = printed_read − pdf_seq_position`; the true offset is piecewise-constant, monotone non-decreasing, and **locally stable**.
- **Raise the cap** to `NUM_MAX=9999` so real 4-digit page numbers survive (5+ digit garbles still excluded by the `\d{1,4}` extractor + `MIN_OFFSET_VOTES`).
- **`_apply_anchor_filter` / `_anchor_offsets` (a pre-fit NOISE FILTER):** certify "trusted offsets" from **runs of ≥3 consecutive +1 page-number reads** (a garble almost never lands on three correct successors by chance), then **discard any candidate read whose implied offset is not in the trusted set**. This cheaply removes garbled 4-digit reads before the DP votes. The filter only ever **deletes** reads, **never invents** one. NO-OPs only when too few anchors exist (truly sparse numbering).
- Each emitted gap carries an **EVEN/ODD confidence tag** (Patrick's even-skip prior): rapid-scan stuck-page drops lose pages in PAIRS (a leaf = 1 sheet = 2 printed pages), so an **EVEN-count jump = HIGH** confidence real leaf drop; an **ODD jump = LOW** (likely an original printing/numbering skip or an OCR leading-digit-drop artifact, not a clean dropped leaf).

## Results
- **46 volumes recovered** not-auditable → auditable. Auditable **157 → 203**, not-auditable **68 → 22**, missing pages **133 → 175**. **Zero regressions.**
- Gap confidence split: **even/HIGH = 41 gaps / 126 pages**, **odd/LOW = 41 gaps / 49 pages**.
- Residual not-auditable (22) is honest: 10 `no_page_images`, 2 `too_few_pages`, and 10 early-1850s/1883-84 `low_support` (faint corner numbers at read 0.8–0.95 — Cohort A, deliberately untouched).
- Regression gate: **1872 still reports EXACTLY its 4 known leaves** (pp 131-134, 515-516, 586-587, 776-777, all even/HIGH).
- New big gaps spot-verified against raw reads: **1990-vol2 3295→3313 (18pp)**, **1989-vol2 2831→2836 (4pp)**, **1991-vol1 1243→1252 (8pp)** — all REAL sequence breaks.

## Durable gotchas (carry these forward)
1. **A doc claim that the filter "NO-OPs on the legacy / 3-digit corpus" is FALSE.** The filter **applies broadly — ~134/225 volumes, INCLUDING 1872 (`anchor_filter=true`, 5 anchor offsets)**. Hans flagged this as a BLOCKER: it is a *delete-only noise filter*, and the legacy corpus is safe because **(a) it never invents a number and (b) the monotone DP is robust to deleted reads** — NOT because it no-ops. State the mechanism truthfully; "it no-ops so it's safe" is the wrong reasoning even when the *outcome* (no regression) is right.
2. **The per-gap "distinct ranges, not merged" localization guarantee is conditional.** When two real drops are adjacent with only unreadable/filter-removed pages between them, the DP **MERGES** them into one range. The **total missing COUNT stays correct**; only the split is lost. Don't overstate localization.
3. **Odd single-page gaps are frequently OCR leading-digit-drop artifacts**, not missing leaves (e.g. 1971-vol2 4148: page reads "148" not "4148"; 1951-vol2 4195: two consecutive unreadable scan pages). The even/odd tag handles this honestly — odd = "inspect, do not assume missing."
4. **Name twin constants distinctly.** `ANCHOR_RUN_LEN` (consecutive-run LENGTH to certify an anchor) vs `MIN_ANCHOR_RUN` (a body page-count floor) were near-identical and a maintenance trap (Hans W3) — renamed.
5. **Background heavy sweeps hit the 600 s task cap.** The 225-volume run (~65 min) was killed mid-flight; the **crash-safe `--jsonl` + `--resume`** flags let it finish in one resume call (198 done → 27 remaining). Always run the corpus sweep with `--jsonl` so a kill loses nothing.

## Reproduce
```
C:/PatoLex-scratch/ocr-engines/qwenvl-venv/Scripts/python.exe \
  C:/PatoLex-scratch/page_continuity_audit.py all --workers 16 \
  --jsonl C:/PatoLex-scratch/_audit_all.jsonl --resume \
  --json-out C:/PatoLex-scratch/_audit_all.json
# then: python _make_report.py  (regenerates the deliverable from the jsonl)
```

Extends the missing-leaf method first validated on 1872; complements
[LESSON_2026-06-21_scan_gap_vs_header_loss_visual_recovery](LESSON_2026-06-21_scan_gap_vs_header_loss_visual_recovery.md)
(a scan gap is a printed-page-number jump, invisible at the filename level) and
[LESSON_2026-06-22_H5_digit_misread_not_sequence_bug](LESSON_2026-06-22_H5_digit_misread_not_sequence_bug.md)
(single-digit OCR substitutions, not sequence cascades).
