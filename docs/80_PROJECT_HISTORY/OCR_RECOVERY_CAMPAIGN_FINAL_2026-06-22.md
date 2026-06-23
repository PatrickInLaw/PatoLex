# OCR-Era Chapter-Recovery Campaign — Final Report — 2026-06-22

**Scope:** the OCR era of the PatoLex corpus, session-years **1850–1999**.
**Goal (Patrick, GATE):** full per-year chapter coverage before the project moves forward —
"any omissions will break the entire project."
**Guardrail honored throughout:** CPU/doc work + local models only; **zero Claude vision
tokens**; nothing written to Postgres or to any existing `parsed_acts_*.json` — every recovery
is additive draft JSON under `C:\PatoLex-scratch`, fully reversible.

---

## Headline result

| | Value |
|---|---|
| **Start** | 94.3% of only **91 mapped** session-years |
| **End** | **99.9%** across **all 108** session-years (1850–1999), zero unmapped holes |
| **Chapters recovered to** | **95,911 / 96,002** (effective N, minus 12 confirmed legislative gaps) |
| **Residual** | **~91 chapters** |
| **Claude vision tokens spent** | **0** |

Confirm at any time with the scoreboard:
`python C:/GitHub/PatoLex/pipeline/analysis/_recall_allyears.py`
(it counts only verified recoveries and is anti-double-count guarded: 215 distinct production
dirs, none counted under two oracle years).

---

## What the campaign did (the recovery layers, in order)

All layers are **additive** — each emits its own draft JSON that the scoreboard/merge reads;
none mutates a prior pass.

1. **Status normalization + scoreboard discipline.** A single effN-aware scoreboard
   (`_recall_allyears.py`) that counts only verified chapters under a 3-tier confidence scheme
   (image-verified / ocr-text-or-sequence-located / confirmed legislative gap), plus
   `_residual_manifest.py` to enumerate each year's still-missing chapters with page brackets.
2. **Biennial / budget session-year remap.** Many session-years are stored under biennial or
   budget-named production dirs (e.g. 1866 → `production-1865-66`, the 1952–1964 budget aliases).
   A single source-of-truth alias map (`pipeline/year_dir_alias.py`) maps oracle years to dirs;
   the scoreboard and manifest both consume it (F1 fix removed a divergent partial copy in the
   manifest). This alone lifted "91 mapped years" to the full 108.
3. **Merge re-runs for the transition years** (1901 / 1907 / 1909 / 1911) and the
   best-of-merge + OCR-header same-act dedup (`pipeline/ingest/merge_passes.py`,
   Hans-hardened over multiple rounds).
4. **1854 dual-series content fix** — the contents-anchored 174/174 parse
   (`parsed_acts_dualseries_v2.json`), resolving the dual-numbering-series split.
5. **Header-independent clause-sequence recovery** (`pipeline/ingest/recover_clause_seq.py`) —
   LIS-anchor backbone + enactment-clause boundaries (modern) and roman-header-direct recovery
   with canonical + sequence validation (early era). Emits `parsed_acts_clauserec.json`.
6. **Local Tesseract header-OCR (~620 chapters).** Targeted top-strip OCR of the printed
   running head, CONFIRM-ONLY (a chapter is written only when its exact oracle number reads as
   a clean header in range — a miss costs coverage, never a wrong claim). Emits per-volume
   `parsed_acts_visual.json`. Root cause it exploits: full-page OCR systematically drops the
   page-top `CHAPTER N` running head while keeping the act body.
   (`lessons/LESSON_2026-06-21_local_header_ocr_recovery.md`.)
7. **Surya DL-OCR** — deep-learning OCR pass for headers Tesseract's psm passes missed.
8. **Local Qwen2.5-VL-7B vision-language model (~116 chapters).** The stubborn multi-act-page
   headers that Tesseract + Surya both drop, read directly by a local VLM on the 5090
   (`C:\PatoLex-scratch\_vlm_header_recover.py`, append-safe, `--confirm`-gated, no DB writes).
   ~100% read-lift on chapters actually printed on the page; the residual misses are
   manifest-anchor artifacts, not model misses.
   (`lessons/LESSON_2026-06-22_vlm_header_recovery_pilot.md`.)

**The unifying root cause** across all layers: the OCR pipeline drops the page-top
`CHAPTER N` running header (it lives in a zone the OCR skips) while capturing the act body.
That one fact explains the "missing" chapters, the phantom duplicates, and why visual /
header-targeted recovery was the right tool — not re-OCR of whole pages.

---

## Residual breakdown (~91 chapters)

| Bucket | ~Count | Page present in our scan? | Resolution path | Tracked in |
|---|---|---|---|---|
| **(a) Human-review biennial** | **~71** (this report counts 71 exactly, years 1866–1878) | **Yes** | A human reads the printed number/title off our existing PDF image — **no re-scan** | `HUMAN_REVIEW_LIST_2026-06-22.md` |
| **(b) Truly-missing leaves** | **9** | **No** (leaf physically absent from every digital copy) | External / archivist high-res scan of the specific printed pages | `ARCHIVES_SCAN_REQUEST_2026-06-22.md` |
| **(c) Misc** | **~7** | mixed | 1911-era leftovers + a few cross-vol/header-loss stragglers; CPU/local-header-OCR | run logs / `_residual_manifest.py` |

(The exact human-review count by direct manifest run is **71** — 1866:10, 1868:1, 1870:9,
1872:14, 1874:4, 1876:22, 1878:11. "~75" appears in earlier checkpoints; 71 is the current,
post-recovery figure.)

---

## What is genuinely DONE vs needs human / scan

- **DONE (machine):** 99.9% of the OCR-era corpus is recovered and verified. Every one of the
  108 session-years is mapped and measured; no year sits at a broad shortfall. The recovery
  toolchain (merge, clause-seq, local header-OCR, Surya, Qwen-VL) is built, Hans-hardened, and
  in the repo / scratch.
- **NEEDS A HUMAN (no scan):** the ~71 biennial chapters in `HUMAN_REVIEW_LIST_2026-06-22.md` —
  a person reads the printed heading off our existing page image. This is the bulk of the
  residual and needs **no** external dependency.
- **NEEDS AN EXTERNAL SCAN:** the 9 truly-missing leaves in
  `ARCHIVES_SCAN_REQUEST_2026-06-22.md` — the only genuinely external dependency.
- **Contingent:** if any of the ~71 human-review pages prove illegible at our current scan
  resolution, a higher-res re-scan of those specific pages would help (noted as a fallback in
  §5 of the archives-scan-request doc).

---

## Separate KNOWN items (NOT part of this recovery campaign)

These are tracked deliberately separately — they are not "missing chapters" and are not
measured by the chapter scoreboard:

1. **Proposition / Initiative measures — MISSED workstream (GATED).** Voter-approved
   initiative statutes and constitutional amendments amend codified statutes **outside** the
   "Chapter N" pipeline and are currently **not captured** in the corpus (~100 statute-affecting
   approved initiatives + ~54 constitutional changes, 1911→present). Source PDFs are on disk
   (38 `*_Measures.pdf` + 1 `*_Initiative.pdf` + 58 `*_Constitution.pdf`). Design is locked;
   sequenced as an explicit roadmap gate **after** legislative closeout, **before** the single
   ingest. See `PROPOSITION_CAPTURE_INVESTIGATION_2026-06-22.md` and
   `docs/30_SYSTEM_DESIGN/PROPOSITION_MEASURE_INGEST_DESIGN.md`. **Not started.**
2. **DB ingest pending.** Everything this campaign recovered is **additive draft JSON in
   `C:\PatoLex-scratch` — NOT in Postgres.** Turning the 99.9% reconstruction into the queryable
   archive is the single mass DB ingest (backup → clear → full 1850→present ingest → diff),
   run ONCE after all prerequisites incl. the proposition gate. **Not started.**
3. **Body-text OCR (later, GPU).** Chapters recovered by HEADER confirmation have their
   *number* confirmed but their full statute *text* not yet extracted — that needs a 3-engine
   consensus OCR pass before ingest.

---

## Key durable docs referenced

- `docs/80_PROJECT_HISTORY/HUMAN_REVIEW_LIST_2026-06-22.md` — the 71 human-review chapters (Deliverable 1).
- `docs/80_PROJECT_HISTORY/ARCHIVES_SCAN_REQUEST_2026-06-22.md` — the 9 truly-missing leaves + scan-vs-no-scan distinction (Deliverable 2 / §5).
- `docs/80_PROJECT_HISTORY/OCR_RECALL_CAMPAIGN_FINAL_REPORT_2026-06-21.md` — prior (mid-campaign) report.
- `docs/80_PROJECT_HISTORY/STATUS_CHECKPOINT_2026-06-22.md` — three-track status snapshot.
- `docs/80_PROJECT_HISTORY/PROPOSITION_CAPTURE_INVESTIGATION_2026-06-22.md` — the MISSED proposition workstream.
- `docs/30_SYSTEM_DESIGN/OCR_RECALL_RECOVERY.md` — authoritative machine-state / current-state doc.
- Lessons: `LESSON_2026-06-21_local_header_ocr_recovery.md`,
  `LESSON_2026-06-22_surya_gpu_header_recovery.md`,
  `LESSON_2026-06-22_vlm_header_recovery_pilot.md`,
  `LESSON_2026-06-22_multiact_band_scan_header_ocr.md`,
  `LESSON_2026-06-20_ocr_header_garble_dedup.md`,
  `LESSON_2026-06-14_chapter_recovery_header_loss_and_renumber.md`.
- Pipeline: `pipeline/ingest/merge_passes.py`, `pipeline/ingest/recover_clause_seq.py`,
  `pipeline/year_dir_alias.py`, `pipeline/analysis/_recall_allyears.py`,
  `pipeline/analysis/_residual_manifest.py`.

---

*Final report generated 2026-06-22. Scoreboard at time of writing: 95,911/96,002 = 99.9%,
residual 91, all 108 mapped OCR-era session-years.*
