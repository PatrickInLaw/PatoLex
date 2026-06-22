# LESSON 2026-06-22 — Biennial-volume one-year offset + `n_for` mis-cap (1907/1909, same family as 1901/09/11)

## Symptom
Oracle 1907 (Regular, N=539) appeared "green" (residual 0) on the `_recall_allyears.py`
scoreboard, but was being measured against the FIRST 539 chapters of the 1909 volume.
Oracle 1909 (N=729) was reported UNMAPPED. `production-1906-07\parsed_acts_merged.json`
held only 60 chapters (ch 2–64) — the **1906 EXTRA session** — not the 1907 regular session.

## Root cause (two compounding facts)
1. **Biennial volumes are offset by one year vs their dir name.** The Chief-Clerk archive
   binds the odd-year REGULAR session with the preceding even-year EXTRA session:
   - `production-1906-07` = 1907 Regular (oracle 539) + 1906 Extra (oracle 64)
   - `production-1907-09` = 1909 Regular (oracle 729) + 1907 Extra/2nd-Extra
   So the "intuitive" dir (1906-07 ≈ 1907, 1907-09 ≈ 1909) is correct, but only at the
   certified level, NOT in `merged.json`.
2. **`merge_passes.n_for()` regex-grabs the LEADING year** (`production-(\d{4})` → 1906),
   and `ORACLE[1906]` is built only from the 1906 Extra row (N=64). The merge therefore
   capped at N=64, clipping certified's real 1907-regular ch 3–539 down to ch ≤ 64. The
   full 1907 data was always present in `certified/repaired/recovered/fixed/multiengine`;
   only the merge step was under-built. **Identical bug to 1901/09/11** (see
   `merge-rerun-1901-1909-1911-run.log`), which had explicitly flagged this for a human.

## Fix (REVERSIBLE, no DB writes)
1. Back up the wrong `merged.json` → `.BAK.json` (it holds real 1906-extra data; preserve).
2. Re-run the EXISTING `merge_passes.merge_dir(D, N)` with the CORRECT N (539), via a tiny
   temp driver under `C:\PatoLex-scratch` — **never hand-fabricate, never reinvent the merge.**
   Result: 60 ch → 529 ch (cap_N 539, max_ch 539; certified 489 + multiengine 40).
3. In `_recall_allyears.py`: add the offset dirs to the glob-exclusion set
   (`BUDGET_OWNED_DIRS`) so the greedy `production-1907*` glob can't sweep `production-1907-09`
   into 1907, then alias `1907→["production-1906-07"]`, `1909→["production-1907-09"]`.
   Anti-double-count assert stays green (each dir → exactly one oracle year).

## Result
1907 residual 7 (532/539); 1909 residual 5 (724/729); unmapped list emptied; corpus-wide
incl-unmapped 98.7% → 99.4%; assert PASS (215 dirs).

## Durable rule (the real takeaway)
**Any biennium-named dir (`production-EVEN-ODD`) re-merged via the `merge_passes.py` glob CLI
will re-mis-cap to the tiny even-year extra-session N.** The lasting fix is to teach
`n_for()` / the merge CLI the same alias mapping `_recall_allyears.py` uses (odd-year regular
session → its biennial dir at the odd-year oracle N). Until then, ALWAYS pass the explicit
correct N when re-merging a biennial dir, and verify `cap_N`/`max_chapter` in `_merge_meta`
match the oracle regular N — a `cap_N` of 1, 15, or 64 on a biennial dir is the tell-tale sign
of this bug.
