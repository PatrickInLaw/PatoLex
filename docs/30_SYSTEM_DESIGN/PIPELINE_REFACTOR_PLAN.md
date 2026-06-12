# OCR Correction Pipeline — Refactor & Open-Source Extraction Plan

**Status:** PLAN (2026-06-12, cc007). No code moves yet. Execute the refactor as ONE deliberate pass
*after* the pipeline is tuned (mojibake + context + Sonnet adjudication settled) AND the 5090 is back
to validate against the golden master. See [[opensource-ocr-engine-plan]] memory.

## Why
1. **Open-source extract.** The correction engine (deterministic high-recall candidate generation + LLM
   context adjudication) is general-purpose and worth its own repo. A clean, injectable, tested library
   is what we share — not the current scatter.
2. **Regression safety.** Doing the refactor while we still have the validated numbers lets us prove we
   didn't break anything (golden-master test below).
3. **Cleanup.** Iterative exploration scattered scratch/scripts/versions across two machines. This is the
   moment to consolidate.

## The core problem: duplication, not just sprawl
Nearly every script reimplements the same primitives. This is the #1 thing the refactor fixes.
- **`build_dictionary` is defined in 5 places:** `correction_passes.py` (canonical, v8), `correction_passes_v3.py`,
  `correction_passes_v2.py` (repo ROOT — stray), `vocab_diff.py` (own union), `triage_residual.py` (own union).
- **`known()` / `zipf()` / `_edits1()` / `_affix_of_common` / `_is_prefix_frag` / damerau** are copy-pasted into
  `correction_cascade.py`, `symspell_e2.py`, `word_splitter.py`, `autocorrect_pass.py`, `line_split_reunify.py`,
  `mojibake_fix.py`, `context_resolve.py`, `triage_residual.py`.
- Result: a fix to the dictionary or the edit model has to be made in ~8 files. That's the mess.

## Inventory (correction engine only — OCR-acquisition / modern-ingest / chapter / DB-ingest are separate)

### CANONICAL — the live engine (keep, refactor into the package)
| file | role |
|---|---|
| `correction_cascade.py` | orchestrator: reunify -> split -> autocorrect(e1) -> garbage-classify; per-stage persist/resume/audit |
| `correction_passes.py` | **only `build_dictionary` is canonical** (the layered dict). Its v8 Pass A/B/C body is superseded BY the cascade |
| `symspell_e2.py` | corpus-aware SymSpell edit-2 (`SymSpellE2`, `build_corpus_freq`) — already injectable |
| `build_corpus_freq.py` | corpus-native freq precompute (runner) |
| `mojibake_fix.py` | constrained-position mojibake corrector — already injectable core |
| `context_resolve.py` | collocation disambiguation — prototype; core already injectable |
| `cascade_summary.py` | per-volume report consolidation |
| `build_dict_additions.py` | builds `dict_additions.txt` (dict-prep runner) |
| `ca_gazetteer.py` | CA proper-name supplement (dict input; PatoLex-specific) |

### SUPERSEDED — proposed for removal (VERIFY each is truly dead + golden-master passes BEFORE deleting)
| file | superseded by | note |
|---|---|---|
| `correction_passes_v2.py` (repo ROOT) | `correction_passes.py` | stray v2 in the wrong dir |
| `correction_passes_v3.py` | `correction_passes.py` | v3, "TIGHTENED-PassB" |
| `word_splitter.py` | cascade `stage_split` | standalone split candidate-gen |
| `autocorrect_pass.py` | cascade `stage_autocorrect` + `symspell_e2` | Patrick: "stop the autocorrect, it's pointless" |
| `line_split_reunify.py` | cascade `stage_reunify` (incl. A4) | v2 reunify |
| `garbage_filter.py` | cascade `classify_residual` (folded in) | standalone duplicate |
| `line_split_finder.py` | cascade per-stage instrumentation | measure-only, served its purpose |

### ANALYSIS / MEASUREMENT (keep, but OUT of the engine core — a `tools/` or `analysis/` area)
`recoverable_compose.py`, `triage_residual.py`, `garbage_page_cluster.py`, `substitution_sample.py`, `vocab_diff.py`

### LLM ADJUDICATION (the AI tier — its own `adjudicate/` subpackage)
`review_adjudicate_local.py` (gemma/Ollama), `substitution_judge_local.py` (gemma), `compare_adjudications.py`
(local-vs-Sonnet), `review_worklist.py`. NOTE: the Sonnet side was run via CC subagents, not a committed script —
the refactor should add a real `adjudicate/sonnet.py` adapter so the AI tier is reproducible.

## Target package layout (the open-source extract)
```
ocrcorrect/                  # corpus-AGNOSTIC core (the shareable library)
  dictionary.py              # build_dictionary + Dictionary(known/strong_known/zipf) + additions/gazetteer loading
  edits.py                   # edits1, deletes, damerau_within, affix/prefix/suffix-frag helpers   (THE de-duplication)
  reunify.py                 # reunify core A1-A4 (pure: tokens + Dictionary -> edits)
  split.py                   # split_token / decompose_long (pure)
  autocorrect.py             # best_correction edit-1 strict (pure)
  symspell.py                # SymSpellE2 + build_corpus_freq (already injectable)
  mojibake.py                # mojibake_candidates + choose_fix (already injectable)
  context.py                 # ctx_score + resolve + bigram model (already injectable)
  garbage.py                 # classify_residual (pure)
  cascade.py                 # orchestrator: wires stages + persistence + audit + report
  report.py                  # summary
  adjudicate/                # AI tier (pluggable): base.py, local_ollama.py, sonnet.py
runners/                     # thin CLI entry points (replace the run_*.bat launchers)
tests/
  test_units.py              # injected-dict unit tests (already started: pipeline/test_local_fixes.py)
  golden_master_cascade.json # locked validated numbers (this commit)
  check_golden_master.py     # asserts a fresh cascade_report reproduces the deterministic invariants
patolex_specific/            # NON-shareable: ca_gazetteer, dict_additions inputs, PatoLex paths
```
Principle: every pass = **pure injectable core** (takes a `Dictionary`/freq/bigram model, returns edits, no I/O)
+ a thin runner that does the file/parallel/persist plumbing. The injected core is unit-testable without
the 5090 or the corpus (proven today: `pipeline/test_local_fixes.py`, 13/13 with synthetic dicts).

## Golden-master regression strategy (set up NOW — the safety net)
`pipeline/tests/golden_master_cascade.json` locks the validated DETERMINISTIC pipeline (reunify+split+e1,
the auto-applied path; SymSpell routes to Sonnet so it's excluded). Source: the 2026-06-12 A4 run
(`cascade_report.json`). After ANY refactor, re-run the cascade and `check_golden_master.py` must pass:
the deterministic stage counts/rates and correction tallies must match EXACTLY (the passes are
deterministic — a diff = a regression). Locked invariants:
- raw 1,476,105 (1.1042%) -> reunify 1,236,821 (0.9268%) -> split 1,231,231 (0.9226%) -> e1 656,695 (0.4921%)
- corrections: reunify_break 225,418 / reunify_window 6,681 / reunify_space 623 / reunify_xpage 244 / split 5,590 / autocorrect_e1 574,536
- residual: garbage 60,404 / roman 4,906 / recoverable 591,385 (by_rule repeat4 44,967 / cons5 8,575 / repeat3 5,115 / toolong 1,697 / mojibake 50)

## Sequencing
1. **NOW (5090 down):** this plan + the golden-master fixture + unit-test scaffold (`test_local_fixes.py`). Boy-scout:
   new/touched modules already get injectable cores (`mojibake_fix`, `context_resolve` done).
2. **Finish tuning (box back):** mojibake run, context-resolve feasibility, Sonnet adjudication decision. The
   cascade SHAPE stabilizes.
3. **Execute the refactor as ONE pass:** extract `ocrcorrect/`, de-duplicate dictionary+edits, move passes to
   pure cores, delete the verified-dead files, wire runners. Validate against the golden master at every step.
4. **Open-source split:** lift `ocrcorrect/` (minus `patolex_specific/`) into its own repo with a license,
   minimal example corpus, and the unit + golden-master tests.

## Guardrails
- **Nothing deleted without verification** that it is truly unreferenced + the golden master still passes.
- The refactor changes STRUCTURE, never the validated numbers — if a number moves, it's a bug, not progress.
