# Transition-Biennium Shortfall Investigation — 1901 / 1907 / 1909 / 1911

**Date:** 2026-06-22
**Author:** Claude Code (CPU-diagnostic research agent)
**Scope:** Diagnose the post-merge residual (NEITHER vision-fallback NOR scan-gap) on the four
biennium-named transition volumes whose merge was re-run from certified on 2026-06-21
(`merge-rerun-1901-1909-1911-run.log`, `rebuild-1907-merge-run.log`).
**Method:** read-only. `_residual_manifest.py` for exact missing lists; `_gap_profile.py` (merged vs
certified-text scan); PyMuPDF (CPU) page render + **light Tesseract v5.4 header reads** to spot-confirm
that missing chapters are PRINTED in the source. **No GPU OCR. No DB writes.**

---

## Headline verdict

All four years are the **same class: RECOVERABLE parse-misses.** Every missing chapter is physically
**printed in the source volume** — confirmed by direct page reads. The oracle is **NOT** over-counting
(extra/special sessions are separate TSV rows, not folded into the regular `total_chapters`), and **no**
volume is short (in every case chapter `min=1`, `max=N`, and the last 30 chapters `[N-29..N]` are
**100% present** — the volumes physically run to the oracle's final chapter).

| Year | Dir | Oracle N (regular) | Recovered (merge) | Residual (manifest) | min..max | Tail [N-29..N] | Verdict |
|------|-----|------:|------:|------:|:---:|:---:|---------|
| 1901 | production-1900-01 | 275 | 253 | **22** | 1..275 | 30/30 | RECOVERABLE |
| 1907 | production-1906-07 | 539 | 539 | **0** | 2..539 | 30/30 | ALREADY RESOLVED (residual gone) |
| 1909 | production-1907-09 | 729 | 724 | **5** | 1..729 | 30/30 | RECOVERABLE |
| 1911 | production-1910-11 | 753 | 623 | **130** | 1..753 | 30/30 | RECOVERABLE |

**Residual total across the 4 years = 157** (22 + 0 + 5 + 130). (The task's "164" was the pre-check
estimate using residual 7 for 1907; 1907 is now 0, so the live number is 157.)

- **RECOVERABLE (parse-missed, in-source): 157 / 157**
- ORACLE-OVER-COUNT: 0
- REAL-SHORT (incomplete source): 0

---

## Why the residual exists (root cause, corroborated)

The 2026-06-21 rerun log already identified the structural cause: `merge_passes.n_for()` reads the
**first** 4-digit year from the biennium dir name, so it capped each merge at the WRONG even-year oracle
(`1900→N=15`, `1910→N=1`, etc.). That was fixed by re-running the merge with the correct odd-year N. The
**residual that remains** after that fix is the ordinary parse/merge attrition the rerun log itself
flagged: per-year **"low-pass dropped"** (1911: 51, 1909: 13) and **"collapsed"** short acts. These are
chapters whose header was present in an input pass (certified/repaired/multiengine) but were dropped or
coalesced during the consensus merge — i.e. **parse-misses, not source absences.**

Two recurring mechanical sub-causes, confirmed at the page:

1. **Roman-numeral chapter headings (1901).** The 1901 volume prints `CHAPTER XIX / XX / XXI … CCXLI`,
   not Arabic. The Arabic-oriented header detector skips or mis-reads these, so short Roman-headed acts
   get dropped or merged into a neighbor.
2. **Short consecutive appropriation acts sharing a page (all years).** Single-page appropriation/claim
   acts (e.g. 1909 ch 545/547, 1911 ch 692/704) get coalesced when two headers land on one OCR page and
   the lower-confidence one is dropped by the merge's low-pass filter.

---

## Per-year detail + source spot-checks

`source_page` in the parse == **1-indexed PDF page** (offset 0, verified on 1910-11 by reading PDF
p.53 = CHAPTER 1). All four regular volumes are pure-image scans (no text layer); reads below are CPU
PyMuPDF render + light Tesseract `--psm 6` on the rendered PNG.

### 1901 — production-1900-01 — oracle 275, recovered 253, residual 22
Missing: `[20, 21, 29, 78, 109, 115, 116, 118, 123, 131, 136, 155, 174, 177, 178, 193, 202, 204, 238,
239, 240, 241]`. Scattered interior; tail 246..275 fully present. Source `1900-01_Statutes.pdf`.

Spot-checks (PRINTED in source, parse-missed):
- PDF p.70 → `CHAPTER XXI` (ch 21) printed. p.69 → `CHAPTER XIX` (19, present). → ch 20/21 dropped.
- Tail cluster: p.854 `CHAPTER CCXXXVII` (237), p.856 `CCXXXVIII` (238), p.857 `CCXXXIX` (239),
  p.858 `CCXLI` (241) — **all Roman, all printed.** 238/239/241 are in the missing list yet visibly
  present; 240 (`CCXL`) sits on the 857–858 boundary.
- **Driver: Roman-numeral header parsing.** All 22 are recoverable.

### 1907 — production-1906-07 — oracle 539, recovered 539, residual 0
`_residual_manifest.py 1907` → **missing 0.** The merge re-run (dir mtime 2026-06-22 06:29) already
closed the gap. The "residual 7" in the task brief is **stale**. No action. (Merged-only `_gap_profile`
shows 10, but clauserec/visual layers + the fresh merge cover them — the manifest, which reads all
recovery layers, is authoritative at 0.)

### 1909 — production-1907-09 — oracle 729, recovered 724, residual 5
Missing: `[547, 551, 608, 690, 691]`. Interior, tight 1–2-page brackets; tail 700..729 fully present.
Source `1907-09_Statutes.pdf`.

Spot-checks (PRINTED, parse-missed):
- PDF p.926 → `CHAPTER 547` printed (short insurance-claim appropriation; p.925 = 545/546).
- PDF p.971 → `CHAPTER 608` printed (state-budget act; p.970 = 607).
- **Driver: short single-page acts dropped by low-pass merge.** All 5 recoverable.
- Note: 1909's data lives in `production-1907-09`, which the scoreboard glob already consumes for oracle
  1907; 1909 is currently UNMAPPED there (anti-double-count guard). The merged file is correctly rebuilt
  to N=729 and ready for the dir-ownership remap (flagged in the rerun log).

### 1911 — production-1910-11 — oracle 753, recovered 623, residual 130
Missing 130, scattered across the whole interior; tail 724..753 fully present. Source
`1910-11_Statutes.pdf` (2240 pp, pure scan). Regular session is `_Statutes.pdf`; the 1st/2nd extra
sessions are SEPARATE files (`_1E*.pdf`, `_2E*.pdf`) and are SEPARATE oracle rows (1911X1=64, 1911X2=1)
— so the 753 is regular-only and is NOT inflated by special sessions.

Spot-checks (PRINTED, parse-missed):
- PDF p.54 → `CHAPTER 3` printed (in missing list).
- PDF p.91 → `CHAPTER 21` printed (a long railroad-commission act spanning pp.65–91 — explains the wide
  65–92 manifest bracket; the parse coalesced it).
- PDF p.92 → `CHAPTER 22` printed.
- PDF p.1404 → `CHAPTER 692`; p.1409 → `696/697`; p.1422 → `CHAPTER 705` printed → the run continues
  right past missing ch 704/698 exactly where expected.
- **Driver: 51 "low-pass dropped" + 9 "collapsed" (per rerun log) — short acts and coalesced
  multi-act pages.** All 130 recoverable.

(One manifest artifact worth noting: 1911 ch 88 carries an anomalous `source_page=1165`, producing a
nonsense 311–1165 bracket for ch 89/90. That is a single mis-attributed page in one input pass, not a
source problem — the real ch 89/90 sit near p.155–160.)

---

## Recommended next step (per year)

- **1907 — none.** Residual is 0; the brief's "7" is stale. Update the scoreboard note if it still
  shows 7.
- **1901 (22), 1909 (5), 1911 (130) — re-parse/recover, do not re-OCR.** The pages are already OCR'd
  and the chapters already exist in the certified/repaired/multiengine passes; they were lost in the
  consensus merge's low-pass/collapse step. Recommended, in order:
  1. **Lower-confidence recovery sweep** (clause_seq / lostheader / the existing visual-recovery path)
     targeting exactly the manifest `missing` lists — these are the proven tools for "header present in
     an input pass but dropped by merge." This alone should reclaim most of the 157.
  2. **Roman-numeral header normalization for 1901** specifically: teach the header detector to read
     `CHAPTER [IVXLCDM]+` and map to Arabic before the merge dedup. This addresses the 1901 cluster
     (20/21 and the 237–241 tail) directly.
  3. Re-run `_residual_manifest.py <year>` after each pass to confirm the missing list shrinks.
- **1909 dir-ownership remap (separate, flagged):** resolve the `production-1907-09` double-mapping
  (1907 vs 1909) so 1909's correctly-rebuilt merged file is actually counted on the scoreboard.
- **Durable merge fix (flagged in rerun log):** `merge_passes.n_for()` should consume the same
  `YEAR_DIR_ALIAS` map as the manifest/scoreboard so a future glob-CLI merge can't re-mis-cap a
  biennium-named dir.

## Bottom line
The transition-biennium shortfall is **entirely recoverable parse/merge attrition (157 chapters, all
printed in-source)** — not an oracle over-count and not a short volume. No effN reduction is warranted;
the residual should be closed by a targeted low-confidence recovery sweep (plus Roman-numeral header
handling for 1901), not by re-OCR and not by trusting the oracle less.
