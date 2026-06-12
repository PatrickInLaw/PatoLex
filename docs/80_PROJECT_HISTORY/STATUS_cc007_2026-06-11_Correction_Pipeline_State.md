# PatoLex — State of the Project

| | |
|---|---|
| **Date** | 2026-06-11 (PT) |
| **Session** | cc007 (Claude Code, Opus orchestrator) |
| **Phase** | Text-correction pipeline (evolved from ingest-prep) |
| **Author** | Claude Code, reviewed against committed artifacts |
| **Companion docs** | `session-logs/claude-code/SESSION_cc007_SUMMARY_2026-06-09_Parallel_Ingest_Prep.md`, `docs/30_SYSTEM_DESIGN/CORRECTION_AND_DISPLAY_LAYER.md` |

> Numbers below are real and traceable to committed artifacts. The DB figures were last
> directly verified 2026-06-09 and are unchanged since (no ingest has run). Quality figures are
> measured on the OCR corpus as noted; where a number is an upper bound or estimate, it says so.

---

## What we're building and why
A point-in-time archive of California statutory law from **1850 to present** — so an attorney can
see exactly what a statute said on any given date. We build it **hardest-part-first**: the
19th-century statutes reconstructed from scanned session laws, where the data is least certain.
No public launch until the full corpus is present and validated.

---

## Where the corpus stands (real numbers)
The data lives in **local PostgreSQL on the 5080** (`localhost:5432/patolex`). Last directly
verified 2026-06-09; unchanged since (no ingest has run):

- **35,332 enactments**, ~84,118 provisions, ~151,763 change-events
  - 4,262 — OCR consensus, **1850–1875**
  - 22,780 — structured modern data, **1991–2024**
  - 8,290 — born-digital PDF, **2000–2008**
- **OCR campaign: complete.** Source scans (full volumes **1850–2008**) intact in the master
  archive (`chief-clerk-archive`), verified present on both machines.
- **Parse stage:** 76,691 acts across 197 volumes.

---

## What this session did
Started as ingest prep; became a deep pass on **text quality** — the thing that determines whether
this is trustworthy for lawyers. Two tracks:

### 1. Chapter numbers — DONE, 215 / 215
Roman/Arabic chapter numbers were badly garbled by OCR (~**1,206** of them). Most were fixed
deterministically by exploiting that chapter numbers run in sequence. The **215 hardest** cases
were finished by rendering the original page from the archive PDF and reading the scan:
deterministic re-OCR for modern numerals, AI-vision-plus-sequence-cross-check for old Roman ones,
~35 read by hand. All 215 resolved, as a reversible overlay (`chapter_corrections_GRAND.tsv`).

### 2. Text quality — characterized and attacked
- **Headline:** after the existing cleanup passes, **~0.56% of words are still flagged as suspect**
  (737,115 of ~132 million word-occurrences). Baseline before cleanup was **1.14%**.
- **Critical caveat:** 0.56% is an **upper bound, not the error rate** — it counts flags from a
  heuristic, and was measured on text *before* applying the corrections we've since computed.
- **Honest, measured decomposition of that residual:**
  - **~17% genuine garbage** (illegible OCR salad — the real floor)
  - **~63% cleanly recoverable** — 36% single-character typos, 25% two-character typos, ~2% words run together
  - **~19% harder typos** (recoverable with more effort)
  - genuine rare-real-words: a tiny sliver
- **Tools built / rebuilt:**
  - **Word-rejoiner** (fixes words OCR split apart): rebuilt to handle same-line splits, cross-page
    splits, and multi-fragment words → **11,156 → 15,434** rejoins.
  - **Dictionary integration:** the spell-checker now knows the corpus's own vocabulary —
    **5,926 validated additions** (5,425 census/GeoNames-verified names + **501 AI-validated legal
    terms**), lifting the dictionary from 328,139 to 333,565 words.
  - **Singleton autocorrect** (Patrick's idea): corpus-weighted spell-correction cleanly fixes
    ~23% of the one-off errors the earlier passes had skipped.
  - **Sonnet text-adjudication overlay:** 1,704 high-frequency fixes (58,700 occurrences).

---

## Challenges we hit, and how we got past them
The recurring challenge was **asserting things instead of measuring them** — caught every time:
- "The scans are missing" → they weren't; OCR keeps text only, source PDFs are in the archive.
- "That file is missing" → it wasn't; the code grabbed a 15-page stub instead of the real
  448-page file named `_Code.pdf`.
- "60% of the tail is garbage" → it's ~17%; a bucket was labeled by what one test couldn't do.
- "A name dictionary is the big lever" → worth ~1–2%; the residual is mostly errors, not names.
- "Use the corpus's frequent words as the dictionary" → frequency ≠ validity, because OCR errors
  are *systematic* and frequent (`secrion`→section appears thousands of times).

**How we overcame them:** measure the contents, not the label; sweep both machines before
declaring anything missing; and — the big one — **heuristics cannot curate vocabulary; it takes
real ground truth (name databases) or an AI validation pass.** The AI validation worked cleanly:
it split 1,266 ambiguous candidates into **565 real terms** and **701 fragments/errors.** Two
adversarial ("Hans") reviews caught a real bug that would have corrupted multi-fragment words.

---

## What remains before us
**Text-correction track (near-term):**
1. Build the **word-splitter** pass (for run-together words).
2. Build the production **autocorrect** pass (corpus + English weighted, edit-1/2/3, guarded).
3. **Apply all the reversible overlays** (chapters, rejoins, AI fixes, autocorrect, dictionary),
   then **re-measure** — that produces the first *real* error rate. Everything quoted so far is a
   pre-correction upper bound.
4. Finish dictionary validation across all frequency tiers.

**Ingest track (the big remaining build):**
5. The single **1850–2026 mass ingest**: back up the DB → clear it → ingest everything with all
   overlays applied → diff to verify. Not yet run.
6. Backfill 22,780 modern rows missing a source-document link; ingest 2025–2026 (DB stops at 2024).

---

## Honest bottom line
We do **not** yet have a defensible final error rate — but we now know the residual is
**overwhelmingly recoverable errors (~83%), not noise (~17%)**, and we've built or scoped every
pass needed to bring it down. The path from "0.56% flagged, pre-correction" to a real, measured,
low error number is clear and mechanical from here. That — plus the single mass ingest — is what
stands between us and a validated, launch-ready corpus.

---

## Key figures at a glance
| Metric | Value |
|---|---|
| Enactments in DB | 35,332 (4,262 + 22,780 + 8,290) |
| Provisions / change-events | ~84,118 / ~151,763 |
| Parsed acts (OCR corpus) | 76,691 across 197 volumes |
| Garbled chapter numbers resolved | 215 / 215 hardest (of ~1,206 total) |
| Text garble flag-rate (pre-overlay) | 1.14% → **0.56%** (737,115 / ~132M) — upper bound |
| Singleton tail composition | ~17% garbage / ~63% recoverable / ~19% harder |
| Word-rejoin corrections | 15,434 |
| Dictionary size / validated additions | 333,565 / 5,926 (5,425 names + 501 legal) |
| AI vocab validation | 1,266 → 565 real / 701 error+fragment |
| Sonnet text fixes (overlay) | 1,704 types / 58,700 occurrences |
