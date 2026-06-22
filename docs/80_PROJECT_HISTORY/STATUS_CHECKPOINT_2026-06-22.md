# PatoLex Status Checkpoint — 2026-06-22 09:04

Clean "where we are / what's left" snapshot, written for Patrick + as a resume point. Authoritative
machine state: `docs/30_SYSTEM_DESIGN/OCR_RECALL_RECOVERY.md` CURRENT STATE + `git log`.

## Headline
- **OCR-era legislative corpus: 99.5%** recovered (residual **478**), **all 108 session-years
  (1850–1999) mapped, zero unmapped holes.** Up from "94.3% of only 91 measured years" at session start.
- **Everything recovered this session is additive draft JSON in `C:\PatoLex-scratch` — NOT in the
  Postgres DB.** The DB ingest is a separate, future single-pass step (see Track 3).

## The three tracks

### Track 1 — Legislative OCR recovery (~DONE, closing out the tail)
Residual 478 decomposes into:
- **~292 visual-fallback chapters** — local OCR exhausted (single-DPI-fragile / garbled multi-act
  headers). Need a VISION-MODEL read (~one image read each). **DECISION: Patrick** (vision-token spend).
- **~19 genuine scan gaps** — verified absent from our PDF (printed-page-number discontinuity). Need a
  **better digital copy from HathiTrust / Internet Archive**, then header-confirm. (CPU/network — mine.)
- **A few remaining verification-confirmed artifacts** — cross-vol re-points (1955 ch1139, 1988 ch398)
  + any header-loss stragglers. Local header-OCR. (Mostly CPU — mine.)
- **F1 cleanup** — point `_residual_manifest.py` at the shared `pipeline/year_dir_alias.py` (it has a
  divergent partial alias copy). Pure code. (CPU — mine.)
- **Body-text OCR (separate, later):** chapters recovered by HEADER confirmation (incl. 1989's 28) have
  their NUMBER confirmed but their full statute TEXT is not yet extracted — that needs a 3-engine
  consensus OCR pass before ingest. (GPU — later.)

### Track 2 — Proposition / Initiative + Constitution (GATED, design LOCKED, NOT started)
Voter initiatives amend statutes & the constitution outside the "Chapter N" pipeline and are currently
MISSED. Design fully decided + pilot-tested (`docs/30_SYSTEM_DESIGN/PROPOSITION_MEASURE_INGEST_DESIGN.md`):
adopted-only, all measure types, separate proposition-keyed parser reusing the event-sourced spine + a
new `precedence` column, constitution in parallel via `const_article`, two-track (probe+OCR) post-1992.
**Sequencing (Patrick): runs as an EXPLICIT roadmap gate AFTER legislative closeout, BEFORE the single
ingest.** Material (38 Measures + 1 Initiative + 58 Constitution PDFs) is on disk. **Do NOT start yet.**

### Track 3 — The single mass DB ingest (FUTURE)
Per ROADMAP: one backup→clear→full-1850–2026-ingest→diff pass, run ONCE after all prerequisites
(roadmap item list, now incl. the proposition gate as item 9). This is what turns the 99.5%
reconstruction into a queryable archive. Not started.

## CPU vs GPU (for Patrick's office-work window)
- **Pure CPU / zero GPU (safe anytime):** F1 code fix; HathiTrust/IA downloads; all documentation;
  DB-ingest prep code; reviewing/auditing existing JSON. The proposition oracle scrape is also CPU —
  but gated, so not now.
- **Tesseract/CPU but runs via the surya-venv (may touch GPU on import — keep light):** the local
  header-OCR recovery (the remaining cross-vol / header-loss / genuine-gap header confirmation).
- **GPU-heavy (defer until GPU free):** full 3-engine consensus body-text OCR (Surya) — i.e. the
  Track-1 body-text step and any full re-OCR.

## Schedule (set 2026-06-22 09:04)
- **11:35am** (cron aaf3cf6f): resume legislative closeout (keep load light; GPU back at 1pm).
- **1:00pm** (cron a2455a9c): STOP — free the GPU for Patrick's office work.
- **3:00pm** (cron 3c76a747): resume if anything remains.
- Recurring 20-min nudge: DELETED (was relaunching work). Crons are session-only — if Claude is fully
  closed they die; idle is fine.

## Immediate next actions when work resumes (in order)
1. Finish 1955 ch1139 / 1988 ch398 cross-vol re-points (CPU). 2. F1 cleanup (CPU). 3. HathiTrust/IA
pulls for the ~19 genuine gaps (CPU/network). 4. PAUSE for Patrick on: vision-token spend (~292) and
whether to start the body-text consensus-OCR pass (GPU). Then Track 2 (proposition) only on his go.
