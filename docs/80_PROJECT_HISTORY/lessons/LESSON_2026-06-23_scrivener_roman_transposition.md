# LESSON 2026-06-23 — Source-side scrivener Roman-numeral typos mis-number chapters (and mask gaps)

## One-line
The *printed* session-law volumes occasionally contain a scrivener typo in a chapter's Roman
numeral (an adjacent-letter swap, e.g. `CXLIII`=143 mis-set as `CLXIII`=163); when OCR reads the typo
faithfully, the act is filed under the WRONG chapter number — which both hides the real chapter (false
"missing") and falsely satisfies the typo'd number's slot (masking a genuine gap).

## The instance (verified)
**1869-70 Statutes, ch.143.** Patrick spotted it by eye during human review of the residual-71. The
printed heading is `CLXIII` (163), but by sequence/position (right after ch.142 @ pdf p209, before
ch.144 @ p212) it is unmistakably **ch.143** (`CXLIII`). OCR read `CLXIII` → the act
("An Act to provide and pay for services rendered for the City…", pdf p210) is stored as **ch.163**.
Consequences, both confirmed in `production-1869-70`:
- **ch.143 falsely "missing"** — it exists at p210, mislabeled 163. (That's why it was in the 71.)
- **real ch.163 falsely "present"** — the genuine ch.163 sits unparsed in the p291–292 gap (between
  ch.162 @ p291 and ch.164 @ p292), but the scoreboard counts the mislabeled p210 act as 163, so the
  real gap was never flagged. Residual *count* is right by luck; the *identity* is wrong.

## Detection (cheap, read-only) — and why most cases are invisible to it
`C:\PatoLex-scratch\_scrivener_scan2.py`: for each volume, find a present chapter N that is out of
page-order AND whose Roman numeral is a single **adjacent-letter swap** of a **missing** chapter E
occupying N's page slot. Corpus-wide result: **exactly 1** (this 1870 case). So the class where OCR
*successfully reads a transposed numeral* is RARE.
- A looser sequence-anomaly scan (`_scrivener_scan.py`, LIS-based) returns ~878 hits, but those are
  dominated by OCR misreads and index/TOC-page artifacts — too noisy to act on directly.
- There are **62 within-volume duplicate chapter numbers** corpus-wide — a separate integrity triage
  (some may be typo-induced collisions; most are likely known OCR-garble dups handled by merge).
- **Key:** the more common failure mode is a source typo that makes OCR fail *entirely* → the chapter
  appears in the "missing" residual, NOT as a wrong number. Those are **invisible to the automated
  scan** and surface only under **human review of the residual** (exactly how this one was found).
  So the human-review pass over the residual-71 IS the right net for this class — flag any chapter
  whose printed Roman is wrong, and correct the citation.

## Action / rule
- **Correction to apply (in the corrections layer / citation re-derivation prereq, NOT a silent edit):**
  in `production-1869-70`, relabel the p210 act **163 → 143**, and add the **real ch.163** (p291–292)
  to the missing/review set. Recorded here so it isn't lost; do it when the text-quality / citation
  re-derivation prerequisite runs (ROADMAP §25 items 5 & 8).
- **Rule:** when human review of a residual chapter finds the printed Roman numeral is a typo, record
  BOTH the relabel AND the now-exposed real chapter (the typo usually masks a genuine gap elsewhere).
  Do not trust the residual *count* to reflect the residual *identity* in a volume with a known typo.
- This is a SOURCE error, distinct from OCR error — a corrections-layer/provenance concern, not an
  OCR-retry target. Relates to [LESSON_2026-06-21_early_era_roman_cccc_additive.md] (additive-form
  Romans) and the merge dedup ([LESSON_2026-06-20_ocr_header_garble_dedup.md]).
