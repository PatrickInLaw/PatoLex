# LESSON 2026-06-22 -- dup-audit H5 "cohort" offsets are OCR digit misreads, NOT a sequence bug

## TL;DR
The merge dup-audit flagged 1913 and 1917 as standout "cohort" volumes whose body
act-headings ("CHAPTER N") disagree with the filed `chapter_int` by recurring
**+/-5 and +/-50** offsets, smelling like a systematic per-volume sequence cascade.
**It is not.** Ground-truthing every high/med candidate with the local header-OCR
proved the filed `chapter_int` is correct in **100%** of cases. The offsets are
ordinary single-digit OCR substitutions on the heading line -- overwhelmingly
**5<->0** and **3<->8**. A "+/-50" is just a 5->0 misread in the tens column; "+/-5"
is the same in the units column. **No data fix is warranted; the defect is in the
audit heuristic.**

## How to tell a digit-misread from a real sequence shift (the decisive checks)
1. **Sequence integrity of the filed spine.** A real "+50 cascade" must create a
   block of duplicate / colliding `chapter_int`. In both volumes the filed
   `chapter_int` is **monotonic, dup-free, 1..N with only sparse genuine gaps**
   (1913: 636 acts 1..699, 0 dups; 1917: 773 acts 1..803, 0 dups, 0 page
   inversions). Clean spine == no cascade. This one check is usually conclusive.
2. **Single-digit decomposition.** Right-align filed vs audit-heading and diff
   digit-by-digit. 22/24 differed by exactly ONE digit; the confusion histogram
   was 5->0 (x8), 3->8 (x6), 8->3 (x2), 5->9 (x2), tail of 5->3/4->3/3->2/7->1.
   These are textbook Tesseract digit confusions, not arithmetic offsets.
3. **Neighbor confirmation via local header-OCR.** Confirm filed N sits between
   confirmed N-1 and N+1 on adjacent pages (full-page multi-psm scan, dedup all
   "CHAPTER N" headers). Every residual resolved filed-correct this way.

## Gotcha: the page-TOP running head is NOT the chapter in these volumes
In 1913/1917 the page-top running head is the **printed page number** +
"FORTIETH SESSION." / "STATUTES OF CALIFORNIA." -- *not* "CHAPTER N". "CHAPTER N"
only appears as the body act-heading, and pages carry 2-3 acts. So the naive
"top-strip running head is the arbiter" rule does **not** apply here; use the
full-page header scan + neighbor-sequence confirmation instead. (Contrast the
early roman volumes where the top strip does carry the chapter head.)

## Why the audit produced the illusion
H5 compared the consensus-resolved `chapter_int` against a **fresh, un-consensused
re-read** of the heading line. The fresh read came from a different (often worse)
engine pass; on a 5/0 or 3/8 heading digit it disagrees. Per-engine inspection
showed the engines disagree among *themselves* on these digits (e.g. 1913 p275:
tess+consensus read "183", doctr+surya read "133") -- pure OCR noise.

## Action items (proposal -- not yet applied)
- **Corpus: no change.** Do not "shift" any 1913/1917 chapters. 0 chapters to fix.
- **Audit heuristic H5:** suppress the flag when (a) the filed `chapter_int` is in
  clean monotonic order between confirmed page-neighbors AND (b) the disagreement
  is a single-digit substitution on a known OCR-confusable pair (5/0, 3/8, 8/3,
  5/9, 7/1, or a dropped digit). This clears all 24+12 as false positives and will
  de-noise the same signature in 1907/1919/1921/1923 (visible in dup-audit-run.log).

## Scope note
The genuine sequence GAPS (1913: 63, 1917: 30 missing chapters within 1..max) are a
SEPARATE lostheader / missing-chapter problem, not an H5 mis-number, and were not
addressed here.

## Files
- Investigation log: `docs/80_PROJECT_HISTORY/run-logs/content-1913-1917-run.log`
- Audit input: `C:\PatoLex-scratch\_dup_audit_candidates.json`
- Tooling: `C:\PatoLex-scratch\_header_ocr.py` (+ `_scan_headers.py`); throwaway
  analysis scripts `_inv_*.py` under `C:\PatoLex-scratch` (temp).
