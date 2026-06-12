# Pipeline Cleanup Runbook (execute in a fresh session)

**Goal:** turn the scattered correction-engine scripts into a clean, de-duplicated, injectable, tested
core — WITHOUT changing any validated number. Companion to `PIPELINE_REFACTOR_PLAN.md` (read it first for
rationale + the target `ocrcorrect/` layout + the full inventory). This file is the step-by-step.

**Prime directive:** the refactor changes STRUCTURE, never behavior. The golden master
(`pipeline/tests/golden_master_cascade.json`) is the non-negotiable gate. If any deterministic number
moves, you introduced a bug — STOP and revert, do not "re-bless" it.

---

## 0. Facts you need (verify, don't trust blindly)

**Repo:** `C:\Users\PatrickKolasinski\Documents\GitHub\patolex` (pipeline code under `pipeline\`).
**5090 GPU box** (back online as of 2026-06-12 15:27 UTC): `ssh -i C:\Users\PatrickKolasinski\.ssh\patolex_5090 patolex@100.70.54.56`
- Python: `C:\Users\patolex\AppData\Local\Programs\Python\Python312\python.exe` (has wordfreq/nltk/pyspellchecker).
- Scratch (where the cascade actually RUNS — it runs copies here, NOT from the repo): `C:\Users\patolex\PatoLex-scratch`
- Cascade dir: `...\PatoLex-scratch\_cascade\` with `out_reunify\ out_split\ out_autocorrect\ audit\ counts\`, `cascade_report.json`, `corpus_freq.json`, `name_gazetteer.txt`, run log `cascade-run.log`.
**5080 (this/local box):** Python 3.12 on PATH but NO pipeline deps — use it only for injected-core unit tests.

**Environment gotchas (will bite you):**
- Compound-bash hook blocks ` && `, ` || `, ` ; `, leading `cd`. Run commands separately, absolute paths.
- Over SSH, `$_` gets mangled to "extglob" — avoid `$_`; use `Select-Object -ExpandProperty`.
- `-ExecutionPolicy Bypass` is auto-denied — invoke python directly (`& 'python.exe' script.py`), don't `-File foo.ps1 -ExecutionPolicy Bypass`.
- Commit messages: write to a file, `git commit -F`. Co-author line: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Long 5090 jobs: launch DETACHED via `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd /c <batch>'}` (plain `Start-Process` gets reaped when SSH returns). Monitor via the `_cascade\cascade-run.log` 15s heartbeat.

---

## 0b. ENV REALITY: two accounts on this box; the golden master is env-sensitive (read first)

The repo + interactive (Azure-AD) session run as **`patrickkolasinski`** (a system admin). The cascade's Python
deps (wordfreq/nltk/pyspellchecker) and the corpus data (`_cascade\`, `corpus_freq.json`, `name_gazetteer.txt`
under `C:\Users\patolex\`) live under **`patolex`** — a LOCAL, SSH-ONLY account (created to drive the box over
Tailscale; not interactively loginable). The 5090 has the full repo synced.

- **Code work + injected-core UNIT TESTS: run locally as `patrickkolasinski`.** No deps/data needed; the repo is
  the single source of truth. The loose `C:\Users\patolex\PatoLex-scratch\*.py` are stale legacy scp'd copies —
  never edit them as source.
- **`patrickkolasinski` (admin) CAN run the cascade locally** — access is not a hard blocker: it just needs
  (1) the deps in its own Python (`pip install wordfreq nltk pyspellchecker` + `nltk.download('words')`) and
  (2) access to patolex's data (run elevated, or `icacls C:\Users\patolex\PatoLex-scratch /grant patrickkolasinski:(OI)(CI)F /T`).
- **BUT the GOLDEN-MASTER GATE is environment-sensitive.** The locked numbers were minted in patolex's exact
  env, and `build_dictionary` (pyspellchecker + nltk `words` + wordfreq) is VERSION-sensitive — a different dep
  version shifts the dictionary and the flagged counts, producing a FALSE regression. So run the gate in an env
  that reproduces the baseline:
  - **(a) Easiest/safest:** run the gate as `patolex` over SSH (`ssh -i C:\Users\PatrickKolasinski\.ssh\patolex_5090 patolex@100.70.54.56`).
    scp the COMPLETE refactored `pipeline\*.py` set (incl. new `dictionary.py`+`edits.py`) into patolex
    `PatoLex-scratch\` (flat — all of them, or imports break), run `correction_cascade.py` (`CASCADE_FROM=reunify`,
    `CASCADE_APPLY_SYMSPELL` unset), then `check_golden_master.py`. Run-sandbox fed from the repo, NOT editing scratch as source.
  - **(b) Fully local (one-box, no SSH ever again):** pin your Python's deps to patolex's EXACT versions
    (`pip show` them over SSH first), then re-run the CURRENT (pre-refactor) cascade locally and confirm it
    reproduces the golden master. Once your env reproduces the baseline, trust local gate runs.
- **STALE-STATE WARNING:** the scratch `_cascade\cascade_report.json` and `out_autocorrect\` currently hold the
  SymSpell EXPERIMENT output (es1/es2 applied), NOT the deterministic baseline. Do NOT check the golden master
  against the EXISTING report — re-run FROM REUNIFY (`CASCADE_APPLY_SYMSPELL` unset) to regenerate deterministic
  `out_*`/report first, then check.
- SSH gotchas (if using (a)): avoid `$_` (mangles to "extglob"); no `-ExecutionPolicy Bypass` (auto-denied) —
  invoke `& 'C:\Users\patolex\AppData\Local\Programs\Python\Python312\python.exe' script.py`.

---

## 1. Establish the baseline gate (do this FIRST, before touching anything)

1. Read `PIPELINE_REFACTOR_PLAN.md` and this file fully.
2. Confirm the golden-master checker passes against the existing committed report:
   `python pipeline\tests\check_golden_master.py docs\80_PROJECT_HISTORY\run-logs\cascade_report.json`
   Expect: `GOLDEN-MASTER OK`. If not, STOP — the baseline is wrong, investigate before refactoring.
3. Confirm the local unit tests pass: `python pipeline\tests\..\test_local_fixes.py` (i.e. `pipeline\test_local_fixes.py`). Expect `ALL PASS` (13/13).

These two green checks are your "before" state. Every later step must keep them green.

---

## 2. Extract the shared core (kills the duplication — the #1 win)

`build_dictionary` is duplicated in 5 files; `known/zipf/_edits1/_affix/_is_prefix_frag/_is_suffix_frag/
damerau` in ~8. Collapse into two new modules. Do this with PURE functions so they unit-test locally
(no 5090, no corpus) exactly like `test_local_fixes.py` already does.

1. **`pipeline/dictionary.py`** — lift the canonical `build_dictionary` from `correction_passes.py`
   verbatim (it loads pyspellchecker + nltk + wordfreq + `LEGAL_SUPPLEMENT` + `ca_gazetteer.CA_NAME_TOKENS`
   + `dict_additions.txt`). Expose a small `Dictionary` object or plain helpers: `known(t)`, `strong_known(t)`,
   `zipf(t)`. Keep the EXACT same dict composition — any change to membership changes the numbers.
2. **`pipeline/edits.py`** — lift `_edits1`, `_deletes`, `_dl_within` (damerau), `_affix_of_common`,
   `_is_prefix_frag`, `_is_suffix_frag`. Pure functions taking a `known`/`zipf` callable where needed.
3. **Unit-test both locally** with synthetic dicts (extend `test_local_fixes.py` or add `test_core.py`).
   Run on the 5080 Python — must pass before wiring anything to them.
4. **Re-point importers** (do NOT change their logic, only the import source):
   - `correction_cascade.py`, `symspell_e2.py`, `mojibake_fix.py`, `context_resolve.py`,
     `cascade_summary.py`, `build_corpus_freq.py` — import dict/edit helpers from the new modules,
     delete their local copies.
   - `correction_passes.py` keeps only its Pass A/B/C body if you retain it for reference; its
     `build_dictionary` becomes a thin re-export from `dictionary.py` (so nothing else breaks).
   - `vocab_diff.py`, `triage_residual.py` (analysis tier) — re-point to `dictionary.py` too, OR leave
     and note them as analysis-only. Prefer re-pointing for full de-dup.

**After each re-point: run the local unit tests.** They won't exercise the full corpus but catch import/signature breaks.

---

## 3. Delete the verified-dead files (VERIFY each before `git rm`)

For EACH candidate below: grep the whole repo for `import <stem>` and `from <stem>` and references to its
public functions. Only delete if there are ZERO live references (test files / its own runner excepted).
If anything references it, resolve that first or leave the file and note why.

Candidates (rationale in the plan):
- `correction_passes_v2.py` (REPO ROOT — stray), `pipeline/correction_passes_v3.py` — old versions.
- `pipeline/word_splitter.py` — superseded by cascade `stage_split`.
- `pipeline/autocorrect_pass.py` — superseded by cascade `stage_autocorrect` + `symspell_e2`.
- `pipeline/line_split_reunify.py` — superseded by cascade `stage_reunify` (incl. A4).
- `pipeline/garbage_filter.py` — superseded by cascade `classify_residual`.
- `pipeline/line_split_finder.py` — measure-only, served its purpose.

Also sweep `pipeline\*.bat` and the 5090 scratch for orphaned `run_*.bat` / `test_*.py` launchers that no
longer point at live scripts; remove the dead ones. **If unsure whether something is truly dead, leave it
and ask Patrick — do not guess-delete.**

---

## 4. VALIDATE against the golden master (the gate — needs the 5090)

The cascade runs from the 5090 scratch, not the repo, so:
1. `scp` every changed/new pipeline module (`dictionary.py`, `edits.py`, `correction_cascade.py`,
   `symspell_e2.py`, `cascade_summary.py`, etc.) to `C:\Users\patolex\PatoLex-scratch\`.
2. Re-run the cascade FROM REUNIFY, deterministic (leave `CASCADE_APPLY_SYMSPELL` unset/0):
   launch `correction_cascade.py` with `CASCADE_FROM=reunify` detached via `Win32_Process.Create`;
   watch `_cascade\cascade-run.log` (15s heartbeat; ~450s wall, 205 vols).
3. `scp` the fresh `_cascade\cascade_report.json` back and run:
   `python pipeline\tests\check_golden_master.py <fresh report>`
   **It MUST print `GOLDEN-MASTER OK`.** If any number differs, the refactor broke behavior — find the
   diff (the checker prints each one), fix or revert. Do NOT edit the golden master to make it pass.

Only when the golden master is green is the refactor proven safe.

---

## 5. (Optional, same gate) move to the `ocrcorrect/` package layout

If you want the full open-source structure now (per the plan's layout): create the `ocrcorrect/` package,
move the pure cores in, keep thin runners, and put PatoLex-only bits (`ca_gazetteer`, dict-additions inputs,
hard-coded scratch paths) under `patolex_specific/`. Re-validate against the golden master after the move.
This is structural only — same numbers.

---

## 6. Close out

- Commit in logical chunks (extract-core / re-point / delete-dead / validate), each with the co-author line,
  `git commit -F`. Push.
- Update the session log (`docs/80_PROJECT_HISTORY/session-logs/claude-code/`) and note the golden-master
  result. Record any file you chose NOT to delete and why.
- Update `PIPELINE_REFACTOR_PLAN.md` to mark what's done.
- If you touched the dictionary composition or any pass logic (you shouldn't have), that's a SEPARATE
  decision — flag it to Patrick, don't fold it into "cleanup."

## DO NOT
- Do not change any pass's logic, the dictionary composition, or thresholds during cleanup — structure only.
- Do not delete a file you haven't grepped for references.
- Do not "re-bless" the golden master to make a failing check pass — a moved number is a regression.
- Do not run the cascade with `CASCADE_APPLY_SYMSPELL=1` for the golden-master check (that path is the
  experiment, not the deterministic baseline).
