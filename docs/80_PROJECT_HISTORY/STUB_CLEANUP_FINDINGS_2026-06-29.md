# Stub Cleanup — VERIFY-then-QUARANTINE — Outcome: QUARANTINE NOTHING — 2026-06-29

**Task.** Find and quarantine abandoned near-empty scaffolding `production-*` dirs (acts ≤ 2 in
`parsed_acts_merged.json`). Each candidate had to clear ALL THREE gates before quarantine:
(1) ≤ 2 acts; (2) any acts PROVABLY DUPLICATED (same `chapter_int` + title) in the real sibling
dir; (3) NOT referenced in `pipeline/year_dir_alias.py`, `pipeline/analysis/_recall_allyears.py`,
or any pipeline config.

**Outcome: NOTHING was quarantined.** A full sweep of all 215 `production-*` dirs found 12 dirs
with acts ≤ 2. **Every one of the 12 fails at least one gate.** This contradicts the casual "junk
stub → Item 3 cleanup" characterization in `PAGE_CONTINUITY_AUDIT_2026-06-23.md`; the ingest layer
treats the "stubs" as real, registered Extra-Session volumes. Hans (verify-auditor, fresh context)
audited the refusal and returned **VERDICT: SOUND** — "quarantine nothing" is correct; no candidate
was wrongly refused, none wrongly kept.

## The 12 acts≤2 candidates and why each was REFUSED

| Dir | acts | Why NOT quarantined |
|---|---:|---|
| `production-1927-vol1-26chapters` | 0 | **Gate 3 FAIL.** = **1926 Extra Session, 46th Legislature** — `ingest_clean.py:187`, `ingest_from_ocr.py:141` (both "verified ADD"), `analysis/chapter_vs_oracle.py:215`, `verify/prose_coherence_sweep.py:70`. Registered ingest target. |
| `production-1929-vol1-28chapters` | 1 | **Gate 2 + Gate 3 FAIL.** ch.1 = 1928 *extraordinary*-session constitutional-amendment submission; the regular sibling `-29chapters` ch.1 is the Colorado River Compact — DIFFERENT act, NOT duplicated. = **1928 Extra Session, 47th** in `ingest_clean.py:191`, `ingest_from_ocr.py:144`, `sql/consolidate_manifest.py:26`, `prose_coherence_sweep.py:71`. |
| `production-1883-84` | 2 | **Gate 2 + Gate 3 FAIL.** ch.4/ch.7 = 1884 *extra*-session appropriations; the regular sibling `-regular` ch.4/ch.7 are code amendments — DIFFERENT acts, NOT duplicated. = **1884 Extra Session, 25th** in `ingest_clean.py:139`, `ingest_from_ocr.py:98`. |
| `production-1873-74-code` | 1 | **Gate 3 FAIL.** In `year_dir_alias.py:81` (1874 alias = code-amendment sibling volume); also `ingest_from_ocr.py`, `ingest_clean.py`, `parse_all.py`, `prose_coherence_sweep.py`, `check_citation_integrity.py`. Real code-amendment volume. |
| `production-1971-vol3-chapters` | 0 | **NOT scaffolding.** 392 real page renders; auditable CLEAN in the page-continuity audit. Continuation volume. Referenced in `ingest_from_ocr.py`, `append_body_entries.py`. Removing breaks audit volume resolution (same hazard as the `production-2000-vol*` dirs). |
| `production-1987-vol4-chapters` | 0 | **NOT scaffolding.** 732 page renders; auditable CLEAN. Continuation volume; in `ingest_from_ocr.py`. |
| `production-1988-vol4-chapters` | 0 | **NOT scaffolding.** Real OCR consensus + 709 page-classification entries (raw images not retained on disk); auditable CLEAN. In `ingest_from_ocr.py`. |
| `production-1992-vol4` | 0 | **NOT scaffolding.** 1515 page renders; auditable CLEAN. In `ingest_from_ocr.py`. |
| `production-1993-vol5` | 0 | **NOT scaffolding.** 1485 page renders; auditable CLEAN. In `ingest_from_ocr.py`. |
| `production-1996-vol6` | 0 | **NOT scaffolding.** 1929 page renders; auditable CLEAN. In `ingest_from_ocr.py`. |
| `production-1997-vol6` | 0 | **NOT scaffolding.** 1904 page renders; auditable CLEAN. In `ingest_from_ocr.py`. |
| `production-1998-vol6` | 0 | **NOT scaffolding.** 2157 page renders; auditable CLEAN. In `ingest_from_ocr.py`. |

## Key lesson (durable)

**A `production-*` dir with 0 acts in `parsed_acts_merged.json` is NOT evidence of abandoned
scaffolding.** Two distinct legitimate cases produce an empty `merged.json`:
1. **Real Extra-Session volumes** (`-26chapters`/`-28chapters`, the misfiled `1883-84`): the chapters
   share a chapter-number with the regular session (each session renumbers from 1), so the
   scoreboard's `chapter_int` union already covers them — but the *text* is a different, unique
   statute. The ingest layer (`ingest_clean.py` / `ingest_from_ocr.py`) maps these to named Extra
   Sessions ("verified ADD"). They hold unique content; quarantine would lose the only OCR copy.
2. **Continuation/index volumes** (`vol3`/`vol4`/`vol5`/`vol6`, `1971-vol3`): hundreds–thousands of
   real page renders, auditable CLEAN in the page-continuity audit, but their parsed acts live in
   the sibling vol or are appendix/index matter. Removing them breaks the audit's `render_dir_for`
   volume resolution (the exact hazard already documented for `production-2000-vol*`).

The reliable "is this scaffolding?" test is **gate 3 (config reference) + page-render presence +
audit status**, NOT the merged-acts count.

## Scoreboard unchanged (proof of no data loss)

Because nothing was moved, `pipeline/analysis/_recall_allyears.py` is byte-identical before/after:
**215 distinct production dirs, 108 mapped years, RESIDUAL = 17, 99.98% after.** No real data
removed (trivially — no move occurred).

## Hans verdict

`verify-auditor` (fresh context, merciless) verified every gate-3 file:line reference, the gate-2
title mismatches (1883-84 ch.4/ch.7 and 1929 ch.1), and confirmed the 12-candidate sweep was
complete. **VERDICT: SOUND.** One wording nit (1988-vol4 has OCR consensus + page entries but no
retained raw images — still a real processed volume, not scaffolding) — does not change the
decision.
