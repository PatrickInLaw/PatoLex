"""Run every runnable test in the pipeline and report honestly.

WHY THIS EXISTS
---------------
`pipeline/test_date_parser_fix.py` was DEAD for roughly a month and nobody
noticed: a module reorg moved `ingest_from_ocr.py` from `pipeline/5080/` to
`pipeline/ingest/`, the test's loader still pointed at the old path, and it died
at import BEFORE its first assertion. Net effect: ZERO live regression coverage
on `parse_act_date` -- the exact function cc019 then had to change.

Nothing caught it. The repo has no CI, no pytest.ini, no conftest.py, no
workflow; every test is hand-invoked. `smoke_imports.py` could not catch it
either -- it is AST-based and the broken reference was a STRING PATH, not an
import. The same rot hit `pipeline/5080/parse_born_digital.py`, which was
unloadable for the same reason.

This runner is the cheapest possible guard: one command that runs everything and
FAILS LOUDLY if a suite cannot even start. A suite that errors at import is
reported as BROKEN, distinct from a suite that runs and fails -- because those
are different problems and the first one is the one that hides.

Usage:
    python run_all_tests.py            # everything runnable
    python run_all_tests.py --list     # show what would run, and what is skipped
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# Tests that run standalone -- no corpus, no DB, no GPU.
# Keep this list current. A new test that is not here is a test nobody runs.
STANDALONE = [
    "test_enactment_paths.py",
    "test_date_parser_fix.py",
    "test_chapter_parser.py",
    "test_detect_body_start.py",
    "analysis/test_residual_bracket.py",
    "analysis/test_reparse_diff_safety.py",
    "analysis/_test_chap_guards.py",
    "analysis/test_recover_early_dedup.py",
    "ocr/test_consensus.py",
    "analysis/test_recover_guards.py",
    "tests/smoke_imports.py",
]

# Known to require the corpus / a specific machine. Reported, never silently
# ignored -- an unrunnable test is still a fact about the repo.
NEEDS_CORPUS = {
    "tests/check_golden_master.py":
        "hardcodes the pre-2026-06-19 scratch root C:\\Users\\patolex\\PatoLex-scratch",
    "tests/test_local_fixes.py":
        "not audited; may need corpus",
    "../.scratch-certify/test_spillover.py":
        "scratch probe; hardcodes the stale scratch root",
}

# Pre-existing failures NOT introduced by current work. Listed so a red result
# is not mistaken for a new regression -- but they still RUN and still report.
#
# EMPTY, and it should stay that way. cc019 cleared the three that were here --
# all the same rot class (`import config` unresolvable without pipeline/ on
# sys.path, plus one FALSE POSITIVE in smoke_imports itself):
#   ocr/test_consensus.py            8/9 -> 9/9   (added pipeline/ to sys.path)
#   analysis/test_recover_guards.py  DEAD -> PASS (same)
#   tests/smoke_imports.py           2 violations -> 0; the checker did not model
#                                    files that add their own sys.path roots, so
#                                    it was wrong about analysis/_diag_early5.py
#                                    and _diag_fp.py -- the imports resolve fine
#                                    at runtime.
#
# A standing "known failure" is how a real failure hides. If something lands
# here, fix it or write down why it cannot be fixed.
KNOWN_FAILING = {}


def run_one(rel):
    path = _HERE / rel
    if not path.exists():
        return {"test": rel, "state": "MISSING", "seconds": 0.0, "tail": "file not found"}
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(_HERE), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=600,
    )
    dt = time.time() - t0
    out = (proc.stdout or "") + (proc.stderr or "")

    # A suite that dies at import never reaches its assertions. That is the
    # failure mode this runner exists to surface, so name it distinctly.
    broken = ("Traceback (most recent call last)" in out
              and ("ModuleNotFoundError" in out
                   or "FileNotFoundError" in out
                   or "ImportError" in out)
              and "passed" not in out.lower())
    if broken:
        state = "BROKEN"
    elif proc.returncode == 0:
        state = "PASS"
    else:
        state = "FAIL"

    tail = "\n".join([ln for ln in out.strip().splitlines() if ln.strip()][-3:])
    return {"test": rel, "state": state, "seconds": round(dt, 2), "tail": tail}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        print("STANDALONE (run by default):")
        for t in STANDALONE:
            note = KNOWN_FAILING.get(t)
            print("  %-42s%s" % (t, ("   [known: %s]" % note) if note else ""))
        print("\nNOT RUN (needs corpus / stale path):")
        for t, why in NEEDS_CORPUS.items():
            print("  %-42s   %s" % (t, why))
        return 0

    print("=" * 78)
    print("PatoLex pipeline test sweep")
    print("=" * 78)

    results = [run_one(t) for t in STANDALONE]
    for r in results:
        mark = {"PASS": "ok  ", "FAIL": "FAIL", "BROKEN": "DEAD", "MISSING": "MISS"}[r["state"]]
        known = " (known)" if r["test"] in KNOWN_FAILING and r["state"] != "PASS" else ""
        print("[%s] %-42s %5.2fs%s" % (mark, r["test"], r["seconds"], known))
        if r["state"] in ("FAIL", "BROKEN", "MISSING"):
            for ln in r["tail"].splitlines():
                print("        | %s" % ln)

    n_pass = sum(1 for r in results if r["state"] == "PASS")
    n_fail = [r for r in results if r["state"] == "FAIL"]
    n_dead = [r for r in results if r["state"] in ("BROKEN", "MISSING")]

    print("-" * 78)
    print("pass=%d  fail=%d  DEAD/MISSING=%d  of %d" %
          (n_pass, len(n_fail), len(n_dead), len(results)))

    new_dead = [r for r in n_dead if r["test"] not in KNOWN_FAILING]
    new_fail = [r for r in n_fail if r["test"] not in KNOWN_FAILING]

    if n_dead:
        print("\n★ DEAD SUITES -- these never reached an assertion:")
        for r in n_dead:
            print("    %s%s" % (r["test"], "  (known)" if r["test"] in KNOWN_FAILING else "  <-- NEW"))
        print("  A dead suite is worse than a failing one: it reports nothing and")
        print("  looks like absence of a problem. This is exactly how")
        print("  test_date_parser_fix.py hid for a month.")

    if not new_dead and not new_fail:
        print("\nNo NEW failures or dead suites.")
        return 0
    print("\nNEW problems: %d failing, %d dead." % (len(new_fail), len(new_dead)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
