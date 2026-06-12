# Pipeline Cleanup — Execution Plan & Live Progress

**This is the working reference for the full `pipeline/` cleanup.** Companion to `PIPELINE_REFACTOR_PLAN.md`
(why + inventory) and `PIPELINE_CLEANUP_RUNBOOK.md` (env/account facts). The non-negotiable gate at every
structural step: the deterministic cascade must still reproduce `pipeline/tests/golden_master_cascade.json`
(`check_golden_master.py` → `GOLDEN-MASTER OK`). A moved number = a regression, not progress.

## Environment facts (don't re-learn)
- Repo + interactive session = `patrickkolasinski` (Azure-AD admin). Cascade Python deps + corpus data =
  `patolex` (SSH-only local account): `ssh -i C:\Users\PatrickKolasinski\.ssh\patolex_5090 patolex@100.70.54.56`,
  Python `C:\Users\patolex\AppData\Local\Programs\Python\Python312\python.exe`, data `C:\Users\patolex\PatoLex-scratch`.
- **Golden-master gate runs on patolex over SSH** (env fidelity — dictionary is version-sensitive; pinned in
  `pipeline/requirements-correction.txt`). Deploy refactored code into scratch (run sandbox), run from-reunify
  with `CASCADE_APPLY_SYMSPELL` unset, scp report back, `check_golden_master.py`.
- Launch detached: `Invoke-CimMethod Win32_Process Create`. SSH gotchas: no `$_`, no `-ExecutionPolicy Bypass`.
  Commit msgs via `git commit -F` file (the `;`-in-message hook). Co-author: `Claude Opus 4.8 (1M context)`.
- **ARCHIVE, never delete** (Patrick): `git mv` to `project-archives/`, or box-side `_archive/` for scratch.

## Progress
- [x] Re-bless golden master to current deterministic numbers (e1 565,019 / flagged 666,212) + verify.
- [x] Pin env → `pipeline/requirements-correction.txt`.
- [x] Repo-root declutter (7 dead scripts → `project-archives/superseded-pipeline/`; gitignore scratch).
- [x] Scratch reconciliation: 11 originals rescued into `pipeline/` (flat); 34 throwaways archived box-side.
- [x] **Step A — de-dup core** — `pipeline/edits.py` (edits1/deletes/dl_within/affix, was dup'd in cascade+symspell+context) + `pipeline/dictionary.py` (build_dictionary re-export + build_sorted_common). Re-pointed cascade/symspell/context/mojibake/build_corpus_freq. Fixed the stale-count-merge double-count bug. **GOLDEN-MASTER OK** (2026-06-12). Flat for now; moves into `ocrcorrect/` in Step B.
- [ ] **Step B — folder reorg** (`pipeline/` → package + concern subdirs). GATE.
- [ ] **Step C — scratch de-gating** (data → `C:\PatoLex`, de-hardcode paths). GATE.
- [ ] Final: update structure docs, session log, push.

## Open-source target: FOUR repos (the reorg defines these seams)
The subdir boundaries below are future **repo-extraction points** — minimize cross-concern imports so each
splits cleanly (see [[opensource-ocr-engine-plan]]):
- **GitLaw** — law-as-git-repo data emitter (future component).
- **OCR toolset** — `ocr/` (acquisition + consensus + workers). MUST NOT import the correction pipeline.
- **Correction/cleanup/verification pipeline** — `ocrcorrect/` (corpus-AGNOSTIC engine) + `analysis/` + `adjudicate/` + `verify/`.
- **Front end** — `src/` (the Next.js app).
PatoLex-specific (`patolex/`: `ca_gazetteer`, `LEGAL_SUPPLEMENT`, dict-additions, chapter, DB ingest) stays
with the app. The engine takes the CA dictionary/name layers as **injectable config**, not baked in.
Gate every move with `pipeline/tests/smoke_imports.py` (static import net) + the golden master for the engine.

## Target `pipeline/` structure
```
pipeline/
  ocrcorrect/          # the open-source correction ENGINE (de-duped, injectable core)
    __init__.py  dictionary.py  edits.py
    reunify.py  split.py  autocorrect.py  symspell.py  mojibake.py  context.py  garbage.py
    cascade.py  report.py
  correction_support/  # PatoLex dict-building: ca_gazetteer, build_dict_additions, regen_additions,
                       #   regen_raw_names, build_corpus_confident, build_corpus_freq
  analysis/            # vocab_diff, recoverable_compose, triage_residual, singleton_decompose,
                       #   singleton_fragment_analysis, save_novel_candidates, garbage_page_cluster,
                       #   substitution_sample, size_candidates
  adjudicate/          # review_adjudicate_local, substitution_judge_local, compare_adjudications,
                       #   run_local_llm_validation, review_worklist
  ocr/                 # consensus, ab_compare, archive_images, benchmark_throughput  (+ 5080/ 5090/ 5090-scale/ workers)
  ingest/              # ingest_clean, ingest_from_ocr, register_source_document, batch_ingest_born_digital,
                       #   ingest_born_digital_prep, acquire_leginfo_pubinfo, resume_leginfo_pubinfo, gate_f/
  chapter/             # chapter_reconstruct, chapter_corrections, run_chapter_vision, aggregate_chvis
  verify/              # verify_volume_completeness, prose_coherence_sweep, check_citation_integrity
  runners/             # prep_runner, queue_append, queue_extend_manifest + run_*.bat + *.ps1 launchers
  tests/               # golden_master_cascade.json, check_golden_master.py, test_local_fixes.py
  sql/                 # existing (queue SQL)
```
Principle: every correction pass = pure injectable core (takes a `Dictionary`/freq/bigram, returns edits,
no I/O) + thin runner. `patolex`-specific bits (`correction_support/`, hardcoded paths) stay out of the
open-source `ocrcorrect/` core.

## Step A — De-dup core (NOT a copy-paste; an injectable refactor)
The cascade's `known`/`strong_known`/`zipf`/`_edits1`/`_edit1_known`/`_affix_of_common`/`_is_prefix_frag`/
`_is_suffix_frag` read MODULE GLOBALS (`_WS`,`_HASWF`,`_WF`,`_ZIPF`,`_SORTED`,`_SORTED_REV`) set in `_init()`.
De-dup = lift them into shared modules as functions over an explicit `Dictionary` object.
1. `ocrcorrect/dictionary.py`: path consts (SCRATCH/OUT_DIR), `LEGAL_SUPPLEMENT`, `ca_gazetteer` import,
   `build_dictionary()` (verbatim from correction_passes.py), and a `Dictionary` holding
   `ws/has_wf/wf/zipf/sorted/sorted_rev` with methods `known/strong_known/zipf/is_roman`.
2. `ocrcorrect/edits.py`: `edits1`, `deletes`, `dl_within` (damerau), `affix_of_common`, `is_prefix_frag`,
   `is_suffix_frag`, `edit1_known` — pure, take a `Dictionary`.
3. Re-point: `correction_cascade.py`, `correction_passes.py` (re-export), `symspell_e2.py`, `build_corpus_freq.py`,
   `mojibake_fix.py`, `context_resolve.py`, `recoverable_compose.py`, `cascade_summary.py`.
4. Local unit tests (synthetic dict) green → scp engine to patolex → golden-master GATE → commit.

## Step B — Folder reorg
Move the rest into the buckets above (`git mv`, history preserved). Fix imports (the moved scripts that do
`from correction_passes import build_dictionary` → `from ocrcorrect.dictionary import build_dictionary`).
Decide cascade invocation (`python -m ocrcorrect.cascade` or a thin `pipeline/run_cascade.py` shim). Update
the run sandbox + golden-master gate procedure for the package layout. GATE → commit.

## Step C — De-gating done RIGHT: shared source + de-hardcode + parallel parser + GIT-versioned outputs (Patrick 2026-06-12)
The root cause of the parser divergence was **per-machine local copies of the data that drift**. Fix it at
the source, per the original decoupling plan:
1. **Shared corpus source** — ONE source of truth for DATA (like the repo is for CODE), reachable from both
   boxes. **Host = the 3060** (copious free SSD+HDD; frees the workstations) via SMB — but that's a *later*
   relocation: first de-gate to a convenient location on the 5090, then `ssh`-move to the 3060 before Step D.
   Because everything reads ONE config/env root, swapping the location is trivial.
2. **De-hardcode ALL pipeline paths** — every script reads its root from ONE config/env (`PATOLEX_DATA_ROOT`
   etc.) instead of baked-in `C:\Users\...` strings. Eliminates the `run_parse_5090.py` monkeypatch → ONE
   byte-identical file runs on both boxes.
3. **Rebuild the parser PARALLEL** — `ingest_from_ocr` parse driver = `ProcessPoolExecutor` over volumes
   (per-volume-independent / embarrassingly parallel). One multi-threaded parser, shared source.
4. **Parse OUTPUTS become GIT-VERSIONED, not out-of-git scratch** (Patrick): write `parsed_acts*.json` to a
   repo-tracked folder so re-parses are diffable via `git diff` and provenance is versioned. (~197 text JSONs
   — git handles that fine; the OCR rasters/large binaries stay out of git on the shared source.)
GATE: golden master (engine) + smoke-import net + a parse smoke-run.

## Step D — Re-parse the corpus with the fixed+parallel parser (AFTER B+C)
1. **Snapshot the 197 current `parsed_acts_fixed.json` into git FIRST** (they are NOT in git yet — scratch is
   outside the repo; the current set is a mix of stale-5080 + fixed-5090 outputs). Commit as the diff baseline.
2. Re-parse ALL OCR'd historical volumes (1850-1999) parallel from the shared source (CPU-only, no GPU, free).
3. **`git diff` old vs new** parse outputs → confirm exactly what the date-clamp fix changed.
4. Then the single 1850-2026 mass-ingest reads a uniformly-correct parse.

## Guardrails
- STRUCTURE only — never change pass logic, dictionary composition, or thresholds during cleanup. A number
  that moves is a bug.
- Nothing deleted — archived (`git mv` / box `_archive/`).
- Validate against the golden master after EACH structural step; do not batch A+B+C without a gate between.
- Don't re-bless the golden master to make a failing check pass (unless it's an intentional, separate, flagged
  algorithm change — it isn't, during cleanup).
