# Reparse Plan — applying the cc019 parser fixes to the corpus

**v2 · 2026-07-25 · supersedes v1 (same day)** — v1 was reviewed by Hans and self-reviewed; both found severe defects, including one that would have corrupted the corpus on first run. Every change below is traceable to a specific finding.

---

## ⛔ BLOCKING DISCOVERY — read before anything else

**The recovery chain has no path into the database. The cc015–cc018 campaign's output is DB-inert.**

Verified in code, three independent ways:

| Evidence | What it says |
|---|---|
| `ingest_clean.py:782` | `acts_path = scratch / "parsed_acts_fixed.json"` — **the only** `parsed_acts_*` file the canonical ingest ever opens |
| `recover_all.py:3` | *"Writes parsed_acts_recovered.json per volume (additive; **no DB**, no overwrite of parsed_acts_fixed)"* |
| `recover_early.py:334` | *"does NOT write parsed_acts_fixed.json"* |
| `merge_passes.py:29` | consumes `fixed.json` as an **input**, emits `merged.json` — and **nothing reads `merged.json` back** |
| `BUILD_RUNBOOK.md:69` | canonical chain is *"OCR → parse → `ingest_clean.py --commit`"* — **the recovery chain is not in it** |

The recovery passes were deliberately built **additive and non-destructive** to `fixed.json`. That was the right call for safety. But the consequence is that **`merged` / `certified` / `recovered` / `repaired` / `clauserec` / `visual` terminate in files nothing downstream consumes.**

### What this means

- **The 99.9% recall figure (95,923/96,002) describes FILES, not the database.**
- The 71 chapters recovered in cc019, and everything cc015–cc018 recovered, **would never reach Postgres** under the current pipeline.
- v1's Phase 5 ("re-run the recovery chain") was **solving the wrong problem**. Re-running it produces more files nothing reads.

### The actual missing work

**A bridge step that folds recovery output into the ingest path does not exist and has never existed.** It is a new, unbuilt component — not a re-run. Designing it is a prerequisite to this plan mattering at all, and it is a **decision for Patrick**, because there are at least three shapes it could take:

1. **Merge-into-fixed** — a step that writes recovery gains back into `parsed_acts_fixed.json`. Simplest; destroys the additive-safety property that currently protects the campaign's work.
2. **Teach `ingest_clean.py` the chain** — have it read the terminal artifact (`merged` or `certified`) instead of `fixed`. Cleaner; changes the canonical ingest contract and needs its own Hans pass.
3. **A third artifact** — an explicit `parsed_acts_ingestible.json` produced by a documented merge, leaving both `fixed` and the chain untouched.

**Until this is decided, a reparse changes only files that nothing ingests.** That does not make the reparse pointless — it makes the corpus files correct and is a prerequisite either way — but nobody should believe it moves the database.

---

## What this plan applies

Four parser defects fixed in cc019 (`f152284..5e4a423`), none yet applied to the corpus. Every artifact on disk came from the **pre-fix** parser.

| Defect | Effect | Measured exposure |
|---|---|---|
| 2 — em-dash / comma headings | recovers unmatched headings | +116 comma, +2 em-dash (4 early volumes) |
| 1 — unsigned / veto-override enactments | acts with no `[Approved …]` now parse and date | 40 modern (1982–99); early-era recall 40% → 70% |
| D — non-"An Act" headings | enacting clause accepted as act evidence | 1876 ch.508, 1870 ch.427 class |
| 3 — bracket ranges | ranges widened, implausible spans flagged | partial; forward-scan still open |

**This is PARSING, not re-OCR.** No engine runs, no GPU. Measured: **~15–30 s** for the full corpus at 16 workers.

---

## Phase −1 — Preconditions (BLOCKING)

**−1.1 The harness fix must be COMMITTED before the 5090 syncs.** *(Hans #2)*
v1's harness had an `except TypeError` fallback that called the old parser with default `write=True`, writing **pre-fix output into live volume directories** — on every volume, since no pre-cc019 ref has the kwarg. **Fixed and committed in `5e4a423`.** `git pull` only moves committed history, so a sync before that commit would ship the corpus-destroying version to the box that holds the corpus.
**Gate:** `git log --oneline -1 -- pipeline/analysis/reparse_diff.py` on the 5090 shows `5e4a423` or later, **and** `python analysis/test_reparse_diff_safety.py` passes there (16/16).

**−1.2 Decide the bridge (above).** Nothing past Phase 2 is meaningful without it.

---

## Phase 0 — Establish reality (BLOCKING; no writes)

**0.1 Chain inventory.** Every script reading/writing a `parsed_acts_*.json`: inputs, outputs, order, idempotency.
**Scope must include `pipeline/5080/`** *(Hans #3)* — it holds `reparse.py` and `re_ingest_fixed.py`, which write **the same filename** into **the same directories**. `reparse.py` self-flags *"ARCHIVED / UNSAFE… will reproduce the Cluster-A year-misread bug"* yet is live and importable. Either archive it properly or document it as a live hazard.

**0.2 Idempotency.** Which passes append vs replace; whether any consumes its own prior output.

**0.3 Irreplaceable-work audit** — work that **cannot be regenerated by re-running code**:
- cc018's 12 VLM-recovered chapters (1907/1911/1953/1956)
- 1905 ch.389–397 (Google Books; `image_verified`, `textlen=0`)
- anything in `parsed_acts_visual.json` from a vision pass
- **`_vocab/chapter_corrections.tsv`** *(Hans #4)* — a **positional** overlay keyed to `in_act_order` in the **pre-fix** sequence. The fixes are expected to change act counts and ordering, so this overlay has **no defined behaviour** against a shifted sequence. It is **not** a `parsed_acts_*.json` file and would be missed by a glob-based snapshot. Decide: re-derive, or protect.
- the 71 chapters from `RESIDUAL_71_CONTENTS_RECOVERY_2026-07-24.md` — currently **only in a markdown table**

**0.4 Snapshot — scope stated honestly** *(Hans #6)*. Timestamped copy of:
- every `parsed_acts_*.json` (all volumes)
- `_vocab/chapter_corrections.tsv`
- `_parse_outputs/date-review-worklist.jsonl` (append-only; **cannot be un-appended** without this)
- `_parse_outputs/parsed_acts_*.json` aggregates (**not in git**, despite the docstring calling that dir "GIT-VERSIONED")

**Explicitly NOT covered:** the Postgres DB. A filesystem restore does nothing for it.

**0.5 Sync the 5090** (`ddce79e`, Jun 29 — 480 lines behind on `ingest_from_ocr.py`). **Only after −1.1.**

**Exit:** written chain map incl. `5080/`, irreplaceable list, verified snapshot with counts and bytes.

---

## Phase 1 — Diff, early era (no writes)

`reparse_diff.py --volumes 1865-66,1867-68,1869-70,1871-72,1873-74,1875-76,1877-78`

Where the comma and lapse fixes bite. **Check the baseline-fidelity line first** — if BEFORE does not reproduce the on-disk artifact, the on-disk file has a provenance we do not understand and every gained/lost number is measured against the wrong baseline.

**Abort on:** any chapter **LOST**, any date **REMOVED**, any date **CHANGED** *(a moved date is worse than a lost chapter — silently wrong beats visibly absent)*, or any **BASELINE-MISMATCH**.

---

## Phase 2 — Diff, full corpus (no writes)

`reparse_diff.py --all` (~15–30 s).

**Scope caveat — Phase 2 and Phase 4 cover different volume sets** *(Hans #5)*. `discover_labels()` takes every volume with OCR (216). `parse_all.collect_labels()` clamps to 1850–1999 and drops **11** `SKIP_LABELS`: `1873-74-code`, `1875-76-code`, `1877-78-code`, `1880-code`, `1965-vol1-64chapters`, `1971-vol3-chapters`, `1987-vol4-chapters`, `1988-vol4-chapters`, `smoke-1996-vol2`, `smoke-real-1997-vol1`, `smoke-real-1998-vol1`. Four are **code volumes**, not session laws. **A Phase 4 count mismatch caused by this is benign** — the plan must say so, or the operator will read a scope difference as a parser regression.

---

## Phase 3 — Review gate (Patrick)

No corpus write before an explicit decision. Present: totals, every LOST chapter, every CHANGED date, baseline mismatches, volumes with outsized deltas.

**Acceptance criteria** *(absent from v1)*:
- zero chapters lost
- zero dates removed
- every changed date individually explained
- baseline fidelity 100%, or each exception understood
- gains consistent with the corpus measurement (+116 comma, +2 em-dash, modern lapse acts appearing)

---

## Phase 4 — In-place reparse

Only after Phase 3 approval **and** a verified Phase 0.4 snapshot.

`python -m ingest.parse_all` (~15–30 s). Verify counts match Phase 2 **for the in-scope set only** (see Phase 2 caveat).

**Known side effects:** `date-review-worklist.jsonl` gains a duplicate generation (append-only); `_parse_outputs/parsed_acts_{label}.json` (197 files) is clobbered and is **not in git**. Both are in the 0.4 snapshot.

---

## Phase 5 — Bridge, then chain *(was "re-run the chain" — that was wrong)*

Re-running the chain produces files nothing ingests. The real work is **−1.2's bridge**. Order:

1. Build the chosen bridge; Hans-review it (it decides what reaches the DB).
2. Re-run the recovery chain per the 0.1 map, preserving 0.3's irreplaceable work.
3. Verify the terminal artifact actually reaches `ingest_clean.py`.

**Cost is people, not compute** *(Hans #9)*. If the fixed parser independently finds chapters cc018 recovered by VLM, reconciliation is **71 individual judgement calls** — agree / correct / conflict — with no tooling built. That is the real unknown, and it is human hours.

---

## Phase 6 — Re-measure

`chapter_vs_oracle.py` / `_recall_allyears.py` vs the 99.9% baseline. Re-measure "51 acts wrong date" — likely an undercount.

**Verify worklist integrity first** *(Hans #7)*: if any run used the unfixed harness, `date-review-worklist.jsonl` holds phantom duplicates and is unfit as a measurement input. Dedupe or restore from snapshot before trusting it.

**Unexamined assumption** *(Hans #8)*: the oracle (`ca_chapter_counts.tsv`) is treated as fixed ground truth. Previously-uncounted unsigned/veto acts may mean the **denominator itself** needs revisiting. Not necessarily wrong — currently unstated.

---

## Phase 7 — Fold in the contents recovery

Convert the 71 to a machine-readable artifact and reconcile against what the corrected parser finds independently — genuine cross-validation, since the methods are independent.

**Moved earlier in intent:** any overlap should be visible at Phase 2/3 as corroboration, not discovered after the corpus is rewritten.

---

## Out of scope — stated, not implied

- **The database.** 35,332 enactments are already ingested from the **pre-fix** parse. This plan does **not** re-ingest them; it never calls `ingest_clean.py --commit`. Per ROADMAP, that is absorbed by the separately-planned one-time backup → wipe → full re-ingest. **A reader must not conclude this plan brings the DB current — it does not.** *(Hans #8)*
- **Gate F / modern layer.** Excluded by the code's own `1850 ≤ year ≤ 1999` clamp and by Gate F volumes having no `ocr_consensus`. Stated so the boundary is explicit.
- **`source_document` registration 1877–1990** — an open ROADMAP prerequisite. Reparsed acts for that span have nowhere to attach regardless of parser correctness. This plan does not close it.
- **Re-OCR.** Not needed, not performed.

---

## Rollback — and what it cannot fix

Restore Phase 0.4's snapshot. It covers the four artifact classes listed there.

**It does NOT fix:**
- **the Postgres DB** — if anyone runs `ingest_clean.py --commit` mid-sequence, that is a scoped purge + insert per `source_document`, irreversible without a DB-level backup. *(Mitigation: writes require BOTH `--commit` AND `PATOLEX_ALLOW_COMMIT=1`.)*
- **anything not in 0.4** — hence 0.4's expanded scope.

---

## Change log

| Finding | Source | Fix |
|---|---|---|
| Recovery chain never reaches the DB | Hans #1 | New blocking section + Phase 5 rewritten around a bridge |
| Harness wrote pre-fix output into the corpus | self-review / Hans #2 | Fixed in `5e4a423`; Phase −1.1 gates the sync on it |
| `5080/` omitted from inventory | Hans #3 | Added to 0.1 with the `reparse.py` hazard |
| `chapter_corrections.tsv` positional overlay | Hans #4 | Added to 0.3; snapshot scope widened |
| Phase 2/4 scope mismatch | Hans #5 | 11 SKIP_LABELS disclosed; benign mismatch called out |
| Rollback under-scoped | Hans #6 | 0.4 widened; explicit "cannot fix" list |
| Worklist can poison Phase 6 | Hans #7 | Integrity check added |
| DB / source_document / Gate F unstated | Hans #8 | Explicit out-of-scope section |
| Phase 5 cost hand-waved | Hans #9 | Named as human reconciliation, 71 judgement calls |
| No baseline fidelity check | self-review | Built into the harness; Phase 1 gates on it |
| Changed dates not an abort condition | self-review | Added |
| No acceptance criteria | self-review | Phase 3 |
