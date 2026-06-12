# cc007 RECOVERY MEMO — read this first after compaction (2026-06-12)

This memo is your memory. The session hit 95% context and was compacted. Everything below is what you
(Claude/Opus) need to continue PatoLex work without re-deriving or repeating mistakes. Read it fully before
acting. Cross-refs: `docs/30_SYSTEM_DESIGN/PIPELINE_CLEANUP_EXECUTION.md` (the live plan),
`docs/80_PROJECT_HISTORY/run-logs/pipeline-cleanup-run.log` (live run log), session log Continuation 58 in
`SESSION_cc007_SUMMARY_2026-06-09_Parallel_Ingest_Prep.md`, and `docs/30_SYSTEM_DESIGN/CORRECTION_AND_DISPLAY_LAYER.md`.

---
## 0. IMMEDIATE ORIENTATION
- You are Claude Code (Opus 4.8) working with **Patrick** (CA attorney; rigorous, honest, hardware/cost-aware,
  Microsoft-aligned). His repo: `C:\Users\PatrickKolasinski\Documents\GitHub\patolex` (branch `main`).
- **Project phase:** the big PIPELINE CLEANUP / REORG is essentially DONE + validated (this session). The
  ACTUAL unfinished work is the **TEXT CLEANUP (OCR correction)** — see §7. Ingest / mass-ingest / Step D
  re-parse come MUCH LATER (Patrick: "ingest comes much later, text cleanup isn't finished").
- **There are OPEN DECISIONS waiting on Patrick** — see §6. Do NOT make architecture decisions unilaterally
  (that's an explicit lesson this session — see the queue story §6/§8).
- Everything to this point is committed + pushed. Last commits: `ab9d004` (OCR/machine de-hardcode),
  `9cb8d92` (C3 baseline). Working tree had uncommitted queue_claim diff investigation — that work is HELD.

---
## 1. THE RULES (Patrick emphasized these — behavioral, mandatory)
1. **Run logs are LIVE, append-only, timestamped AS work happens** — NOT batched/retroactive. Append one line
   per action with a real PT timestamp (derive PT from the UTC in system-reminders: PT = UTC − 7). File:
   `docs/80_PROJECT_HISTORY/run-logs/pipeline-cleanup-run.log`.
2. **Both logs every session** — a run log AND a session log. Session log:
   `docs/80_PROJECT_HISTORY/session-logs/claude-code/SESSION_cc007_SUMMARY_2026-06-09_Parallel_Ingest_Prep.md`
   (Continuation entries; currently at 58). UCP = update session log + commit + push.
3. **ARCHIVE, never delete** — `git mv` superseded code to `project-archives/superseded-pipeline/`; box-side
   to `_archive/`. Never `Remove-Item`/`git rm` old work.
4. **ONE file, not per-machine copies** — parsers/workers must be ONE config-driven file, not 5080/5090
   hardcoded copies that drift. **Verify cross-box sameness with FILE HASHES (`Get-FileHash`), not excerpts.**
5. **Confirm before disruptive/irreversible actions** (deletes, big git commits, killing workers, scaling).
   Report + offer + wait. Diagnostic questions get answers, not auto-fixes.
6. **Do NOT decide architecture solo.** Patrick called out that I built the JSON-over-SSH queue without his
   input when SQL was the plan. Surface design forks; let him choose.
7. **Findings land in durable docs** — any discovery goes in a design doc / lessons / memory, never ONLY in a
   prunable run/session log.
8. **Token / subagent awareness:** delegate mechanical bulk to subagents. CRITICAL: **`haiku-worker` has NO
   Edit/Write tools** (Read/Grep/Glob/Bash/web only) — use it for read/analyze/summarize. For mechanical
   EDITING sweeps use a **`general-purpose` agent** (has all tools) with a precise spec + require it to
   self-verify (py_compile + the smoke net) and report. Estimate cost before any LLM fan-out; get OK.
   When Patrick is away/asleep, never trigger interactive-approval things (Workflow opt-in).
9. **Continue in-session for sensitive steps** — a fresh session flushes the context that makes risky steps
   (engine packaging, parser, golden-master) safe. Keep logs current as the compaction safety net.
10. **Corpus-agnostic engine = NICE-TO-HAVE, not required** (forkers adapt). Don't over-engineer it.
11. Commit-message hook quirk: a `;` in the message is BLOCKED → write the message to `_commitmsg.txt`
    (gitignored) and `git commit -F _commitmsg.txt`. Co-author line on every commit:
    `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---
## 2. ENVIRONMENT FACTS (so you can operate without re-learning)
- **TWO boxes.** 5080 = this interactive session, Azure-AD login `patrickkolasinski` (system admin). 5090 =
  GPU box; the corpus DATA + the Python deps live under **`patolex`**, a LOCAL **SSH-ONLY** account I created
  for Tailscale (you canNOT interactively log into it; `patrickkolasinski` cannot read its profile w/o elevation).
- **SSH to the data/deps env:** `ssh -i C:\Users\PatrickKolasinski\.ssh\patolex_5090 patolex@100.70.54.56`
  - patolex Python (has wordfreq/nltk/pyspellchecker): `C:\Users\patolex\AppData\Local\Programs\Python\Python312\python.exe`
  - patolex scratch (the DATA): `C:\Users\patolex\PatoLex-scratch` (production-*/ocr_consensus, `_cascade`,
    `_vocab`, `_parse_outputs`, `corpus_freq.json`, `name_gazetteer.txt`, the deployed `ocrcorrect/` + `ingest/` packages).
- **5080 has Python 3.12 at** `C:\Users\PatrickKolasinski\AppData\Local\Programs\Python\Python312\python.exe`
  but **NO pipeline deps** — use it only for syntax checks / the smoke net / injected-core unit tests (no corpus).
- **The DB:** local Postgres 16 `localhost:5432/patolex` on the 5080 — the live corpus (35,332 enactments). NOT Supabase.
- **GOTCHAS (these WILL bite):**
  - The compound-bash hook BLOCKS ` && `, ` || `, ` ; `, leading `cd`. Run commands separately, absolute paths.
    It fires on the Bash tool AND scans commit messages (the `;` block) — but NOT the PowerShell tool's `&&`/`;`.
  - Over SSH, `$_` gets mangled to "extglob" — avoid `$_`; use `Select-Object -ExpandProperty`.
  - `-ExecutionPolicy Bypass` is auto-DENIED by the classifier — invoke python directly (`& 'python.exe' x.py`).
  - SSH always prints a post-quantum WARNING — ignore it.
  - Launch long 5090 jobs DETACHED: `Invoke-CimMethod -ClassName Win32_Process -MethodName Create
    -Arguments @{CommandLine='cmd /c <batch>'}` (plain `Start-Process` gets REAPED when the SSH cmd returns).
  - Git LF/CRLF warnings on add are harmless.
- **Cascade run on patolex:** deploy the changed `ocrcorrect/` files into `C:\Users\patolex\PatoLex-scratch\ocrcorrect\`,
  then run via `run_cascade_reunify.bat` (sets `CASCADE_FROM=reunify`, `PYTHONPATH=scratch`, runs
  `python -m ocrcorrect.correction_cascade`). The parser runs via `run_parse_all.bat` / `run_module.bat`
  (generic: `set PYTHONPATH=scratch` + `python -m %*`). All these bats live in patolex scratch.

---
## 3. VALIDATION MACHINERY (how you prove you didn't break anything)
- **GOLDEN MASTER** (the cascade gate): `pipeline/tests/golden_master_cascade.json` locks the DETERMINISTIC
  cascade numbers (reunify+split+edit1-strict + name/garbage guards; SymSpell NOT applied). Validate by running
  the cascade deterministically on patolex (golden master is **env-version-sensitive** — pinned by
  `pipeline/requirements-correction.txt`: nltk 3.9.4 / pyspellchecker 0.9.0 / wordfreq 3.1.1), then
  `python pipeline/tests/check_golden_master.py <fresh _cascade/cascade_report.json>` → must print
  `GOLDEN-MASTER OK`. LOCKED NUMBERS: raw 1,476,105 (1.1042%) → reunify 1,236,821 (0.9268%) → split
  1,231,231 (0.9226%) → **autocorrect_e1 0.4992% (flagged 666,212; e1=565,019)**. residual: garbage 64,457 /
  roman 4,906 / recoverable 596,849. A moved number = a regression (the passes are deterministic). Do NOT
  re-bless to make it pass unless it's an intentional, flagged algorithm change.
- **SMOKE-IMPORT NET** (the reorg gate): `pipeline/tests/smoke_imports.py` — static AST checker, no code
  execution, no deps. Run after ANY file move/import change → must print `SMOKE-IMPORTS OK` (currently 94
  internal names, 0 violations). Catches broken internal imports instantly.
- **INJECTED-CORE UNIT TESTS:** `pipeline/tests/test_local_fixes.py` (13 cases, synthetic dicts, runs on the
  5080 with no deps) — covers mojibake_fix + context_resolve pure cores.

---
## 4. WHAT THIS SESSION ACCOMPLISHED (all committed + pushed + validated)
A. **OCR-correction tuning** (text cleanup — see §7 for the live state). Built corpus-aware **SymSpell edit-2**;
   measured precision (es1 ~83%, es2 ~75-80%) = BELOW legal-grade → **DECISION: route SymSpell candidates to
   Sonnet context-adjudication, NOT auto-apply** (gated behind `CASCADE_APPLY_SYMSPELL=1`, default off). Built
   `mojibake_fix` (constrained-position fix) + `context_resolve` (collocation disambiguation prototype).
B. **Golden master RE-BLESSED** (was miscalibrated — sourced pre-guard) + **pinned env** + fixed a
   stale-count-merge bug in `_process_volume`.
C. **De-dup (Step A):** extracted `ocrcorrect/edits.py` (edits1/deletes/damerau/affix) + `ocrcorrect/dictionary.py`
   (build_dictionary re-export + build_sorted_common) — primitives were copy-pasted in ~8 files. GOLDEN-MASTER OK.
D. **PARSER DIVERGENCE FIXED:** the 5080's own scratch copy of `ingest_from_ocr.py` was a STALE 6/2 half-size
   version MISSING the `volume_year` date-clamp (the chaptered_date bug); repo+5090 had the fixed 6/11 version.
   Archived the stale copy, synced (all 3 now hash 9E9DCC4B). **DATA-QUALITY FLAG:** volumes the 5080 parsed with
   the stale parser need re-parsing before any future ingest.
E. **Scratch reconciliation:** rescued 11 scratch-only original tools into the repo; archived 34 throwaway probes box-side.
F. **FULL REPO REORG (Step B)** — `pipeline/` flat dump → concern subdirs mapping to the 4 open-source repo seams:
   `ocrcorrect/` (engine), `ocr/`, `ingest/`, `chapter/`, `verify/`, `analysis/`, `adjudicate/`, `runners/`,
   `correction_support/`, `tests/` (+ still-present machine dirs `5080/ 5090/ 5090-scale/ sql/`). Every move
   smoke-net-validated, history preserved via `git mv`. The **engine → `ocrcorrect/` package** (run as
   `python -m ocrcorrect.correction_cascade`, multiprocessing-spawn workers re-import cleanly) was GOLDEN-MASTER OK.
G. **CONFIG ROUTE (Step C1):** `pipeline/config.py` — ONE `LOCATION_ROOT` + a location REGISTRY + the single
   accessor **`path_for(name, *subpath)`**. Names: data_root, cascade_dir, vocab_dir, parse_output_dir, gazetteer.
   Relative defaults join the root; an absolute value (or env `PATOLEX_<NAME>`) auto-overrides → move-everything =
   1 line (`PATOLEX_LOCATION_ROOT`), move-one-folder = 1 line. No convenience constants (Patrick: we're rewriting).
H. **PARALLEL PARSER (Step C2):** `ingest/parse_all.py` = `ProcessPoolExecutor` over volumes (parsing is
   per-volume-independent/CPU-bound), config-driven, eliminates the run_parse_5090 monkeypatch, aggregates
   per-volume parsed_acts into `parse_output_dir`. VALIDATED: re-parsed 1862 → output BYTE-IDENTICAL (sha256
   065A1F26), date-clamp active. Archived the sequential drivers.
I. **DE-HARDCODE EVERYTHING (Python):** cascade + whole `ocrcorrect` engine (GOLDEN-MASTER OK), then 32 cluster
   scripts, then 11 OCR/machine-subdir scripts — all onto `config.path_for`. Net green. Remote cross-box SSH
   paths correctly KEPT hardcoded.
J. **C3 baseline:** `ingest/snapshot_parse_baseline.py` archived the current 197 parse outputs (292MB → 79MB
   zip, on patolex, OUT of git) + committed `ingest/parse_baseline_manifest.json` (per-file + whole-archive
   sha256) to git. After a future full re-parse: re-hash → manifest diff instantly shows which volumes the stale
   5080 parser changed.

---
## 5. CURRENT REPO STRUCTURE (where things live now)
```
pipeline/
  config.py                 # the single path_for(name,*subpath) — THE cutover knob
  ocrcorrect/               # correction ENGINE (open-source target): correction_cascade, edits, dictionary,
                            #   symspell_e2, cascade_summary, build_corpus_freq, mojibake_fix, context_resolve,
                            #   correction_passes (build_dictionary), ca_gazetteer. Run: python -m ocrcorrect.correction_cascade
  ingest/                   # ingest_from_ocr (THE parser, de-hardcoded), parse_all (parallel driver),
                            #   snapshot_parse_baseline, ingest_clean, register_source_document, batch_ingest_born_digital,
                            #   acquire/resume_leginfo_pubinfo, parse_baseline_manifest.json
  ocr/                      # consensus, ab_compare, test_consensus, archive_images, benchmark_throughput
  chapter/ verify/ analysis/ adjudicate/ correction_support/ runners/   # concern clusters (all config-driven)
  tests/                    # golden_master_cascade.json, check_golden_master.py, smoke_imports.py, test_local_fixes.py
  5080/ 5090/ 5090-scale/ sql/   # machine-specific + the SQL queue (queue_worker_sql etc.) — see §6/§8
project-archives/superseded-pipeline/   # archived dead code (v2/v3, word_splitter, the stale parser, sequential drivers...)
```
Still hardcoded (by design): `.ps1`/`.bat` LAUNCHERS (shell scripts, can't import config — need the config-CLI
mechanism, §6) and legitimately-remote cross-box SSH paths.

---
## 6. OPEN DECISIONS / PENDING (waiting on Patrick — ask, don't assume)
1. **QUEUE ARCHITECTURE (the big one — Patrick flagged my unilateral JSON-over-SSH build).** The active OCR
   queue was JSON-over-SSH (`queue_claim.py` + `production_queue_state.json`, file-lock + per-op SSH) — fragile,
   ad-hoc, built without his input. A full SQL queue (`pipeline/sql/queue_worker_sql.py`, REVISION 2: one generic
   worker by `--role`, atomic claim, lease+heartbeat+fence, DSN via `PATOLEX_QUEUE_DSN`) WAS designed/built but
   **targets MSSQL (pyodbc, the 3060 plan)** and was NEVER cut over. Patrick's point: **Postgres is already
   running** (`localhost:5432/patolex`) and has the equivalent `SELECT … FOR UPDATE SKIP LOCKED`, so the SQL
   design ports cleanly to Postgres — no MSSQL/3060 needed. **THE DECISION** hinges on whether there's future
   multi-box OCR work: if YES → port the SQL queue to Postgres, retire JSON-over-SSH + the MSSQL target; if NO
   (campaign done, remaining work is single-box) → archive the WHOLE queue layer (JSON + SQL). Either way the
   JSON-over-SSH protocol shouldn't survive to open-source. **I HELD the `queue_claim` unification** (Patrick had
   said "unify using the 5090 prepped version") because polishing a layer we may retire is pointless. The two
   `queue_claim.py` differ ONLY by the config edit + the 5090's `claimable = status in ("pending","prepped")`.
   queue_worker forensics: `5090/queue_worker.py` = canonical production worker (evolved to prep/ocr two-role at
   commit 445bea1 6/3, used in 6/8 dual-box restore); `5090-scale/queue_worker.py` = frozen 6/2 single-role
   experiment (ReadOnly), superseded.
2. **LAUNCHER de-hardcode (Patrick's idea, approved, NOT done):** the `.ps1`/`.bat` can't `import config`, but
   they CAN shell out — add a CLI entry to config (`python -m config <name>` prints `path_for(name)`) and have the
   launchers query it. Wire `config.py`'s `__main__` to print `path_for(sys.argv[1], *sys.argv[2:])`, then update
   the launchers (`for /f` in .bat, `$(python -m config data_root)` in .ps1). Keeps config the single source even
   for shell. (I told Patrick "after the queue work" — but queue is now a pending decision.)
3. **3060 SMB shared source (LATER):** host the corpus on the 3060 (free SSD+HDD) so both boxes share one source.
   Now a CLEAN one-line cutover (`PATOLEX_LOCATION_ROOT`). Not now — "serve local" for now.
4. **Step D (re-parse → diff → ingest) — MUCH LATER.** Don't do ingest now (text cleanup unfinished). When done:
   run `python -m ingest.parse_all` (parallel, all 1850-1999), re-hash, diff vs `parse_baseline_manifest.json`.
5. **NEXT after the cleanup:** Patrick's stated priority is to get **back to TEXT CLEANUP** (§7) — the actual
   unfinished deliverable.

---
## 7. THE TEXT-CLEANUP STATE (the actual unfinished work — this is the priority)
Goal: a clear, DEFENSIBLE OCR-corrected error rate with all corrections applied, BEFORE any ingest. The
correction cascade (ordered, sequence IS the architecture; each stage runs on the prior stage's persisted output):
- **Deterministic, auto-applied (the golden-master floor, 0.4921%→ now 0.4992% with guards):** reunify (A1
  adjacency, A2 line-break window, A3 cross-page, A4 positional within-6-words fragment matcher — all
  golden-master-validated) → split (over-merge + long run-on decompose) → autocorrect edit-1-strict (zipf≥3.3,
  margin≥0.5, ~90-95% precision) → garbage classification (repeat4/cons5/novowel/toolong = the 0.045%
  irreducible floor). Guards in autocorrect: skip known/roman/affix-of-word/gazetteer-name/garbage-shaped.
- **Candidate-generating, NOT auto-applied (route to LLM context adjudication):** corpus-aware SymSpell edit-1/2
  (es1 ~83%, es2 ~75-80% precision — sub-legal-grade, would inject invisible errors). ~280k corrections /
  124,353 distinct token→fix types. Frequency tiers: freq≥10 = 2,897 types (39% of occ, ~217K Sonnet tokens),
  freq≥2 = 25,965 types (~1.9M tokens), all = 124,353 types (~9.3M tokens). Singleton tail = 98,388 types (35%).
- **Mojibake** (`mojibake_fix`): constrained-position fix (the `�` marks the error) → auto-applyable when
  unambiguous; ~2,300 occ. **Context heuristic** (`context_resolve`): collocation/bigram disambiguation
  prototype to procedurally trim the ambiguous slice before AI (legal text is hyper-repetitive).
- **Local-model evidence:** gemma3:27b = 62% adjudication agreement, over-discards real words, 33× substitution
  inflation → NOT the adjudicator; at most a recall-preserving tail triage.
- **The residual** (after deterministic): garbage floor 0.0453% + roman 4,906 + recoverable ~0.4431%. Recoverable
  buckets: ~84.5% HARD (edit-2 typos like cightecn→eighteen — `c`↔`e` systematic OCR), ~9% FRAGMENT, 6% SHORT,
  <1% MOJIBAKE/NAMELIKE.
- **NOT YET DONE (the unfinished cleanup):** (a) run the Sonnet context-adjudication on the SymSpell candidate
  worklist (type-level, freq-tiered; Patrick wants to know cost vs his subscription weekly limit — Sonnet runs
  on his SUBSCRIPTION not API, weekly cap resets ~Sat 2pm; spend heavier before reset); (b) the genuinely
  ambiguous needs occurrence-level context (the bigram heuristic + AI); (c) measure the DEFENSIBLE true error
  rate via a stratified GROUND-TRUTH sample vs the page image (the number we'd ship) — still owed; (d) the
  run-together class (sameand="same and") needs a better splitter. Durable detail: `CORRECTION_AND_DISPLAY_LAYER.md`.

---
## 8. KEY DOCS / WORKING REFERENCES
- `docs/30_SYSTEM_DESIGN/PIPELINE_CLEANUP_EXECUTION.md` — the live plan (Steps A done / B done / C1+C2+de-hardcode
  done / C3 done; C4=3060 later; D=re-parse later).
- `docs/30_SYSTEM_DESIGN/PIPELINE_REFACTOR_PLAN.md` — why + the 4-repo target + inventory.
- `docs/30_SYSTEM_DESIGN/PIPELINE_CLEANUP_RUNBOOK.md` — env/account facts + the gate procedure (some §0b notes
  partly superseded — trust THIS memo + EXECUTION.md).
- `docs/30_SYSTEM_DESIGN/CORRECTION_AND_DISPLAY_LAYER.md` — all the correction/text-cleanup findings (the funnel,
  gates, tail, SymSpell precision, mojibake, context heuristic, route-to-Sonnet decision).
- `docs/30_SYSTEM_DESIGN/SQL_PIPELINE_DESIGN_2026-06-03.md` — the SQL queue design (REVISION 2, MSSQL-targeted).
- Auto-memory index `MEMORY.md` — see §9.

---
## 9. AUTO-MEMORIES (the durable facts already saved — they persist; re-verify file/flag names before relying)
opensource-ocr-engine-plan (4 repos: GitLaw / OCR toolset / correction-cleanup-verification pipeline / front end;
corpus-agnostic = nice-to-have); archive-dont-delete-scripts-scratch; one-parser-not-per-machine-copies (verify
with hashes); orchestrator-only-model; both-logs-every-session; patolex-historical-first; patricks-quality-first-
philosophy; gate-d-schema-and-build-order; hans-is-not-codex; ocr-verification-architecture; patolex-production-
ocr-state; patolex-corpus-data-tiers; confirm-before-disruptive-actions; sql-pipeline-rework-plan; feedback-
orchestrator-not-engineer; single-worker-5080-ram-safe; ingest-only-after-ocr-done; active-db-is-local-postgres;
mass-ingest-backup-compare-plan; no-interactive-auth-when-away; estimate-usage-before-fanout; run-logs-need-
heartbeats; dictionary-membership-too-blunt; ocr-bundles-image-free-source-in-archive; verify-dont-scope-to-handy.

---
## 10. RIGHT NOW — what to do on resume
1. Read this memo + skim `PIPELINE_CLEANUP_EXECUTION.md` and `CORRECTION_AND_DISPLAY_LAYER.md`.
2. The cleanup/reorg is essentially DONE + validated + pushed. Two small things are queued: the **queue
   architecture DECISION** (§6.1 — ASK Patrick: Postgres-port vs archive-the-layer) and the **launcher config-CLI**
   (§6.2 — approved, mechanical). The bigger thing Patrick wants is **back to TEXT CLEANUP** (§7).
3. ASK Patrick which: (a) the queue decision, (b) launcher de-hardcode, (c) back to text cleanup (the Sonnet
   adjudication / defensible-error-rate work). Do NOT auto-pick the queue direction.
4. Keep the run log LIVE + append-only. UCP at checkpoints. Validate any cascade change against the golden master
   on patolex. Use a general-purpose agent (not haiku) for mechanical edit sweeps.
```
