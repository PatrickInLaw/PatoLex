"""cc019 DEFECT 3 regression tests -- residual-manifest bracket derivation.

The headline fixture is the REAL 1872 ch.125-128 failure, measured during the
cc019 contents-anchored recovery: the manifest emitted PDF 224-227 while the
true pages are 221-222, so the range pointed at chapter 128's own body. A
reviewer following it finds no heading and cannot tell "chapter missing" from
"range wrong". We cannot fix the corrupt input page here, but we CAN detect
that the span is physically impossible and say so.

Run:  python test_residual_bracket.py
"""
import os
import sys
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_MOD = os.path.join(_HERE, "_residual_manifest.py")
_spec = importlib.util.spec_from_file_location("_residual_manifest", _MOD)
_rm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rm)

PASS = 0
FAIL = 0


def check(label, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("  PASS  %s" % label)
    else:
        FAIL += 1
        print("  FAIL  %s\n          got=%r\n         want=%r" % (label, got, want))


print("\n=== _run_lengths ===\n")
check("single isolated chapter", _rm._run_lengths([5]), {5: 1})
check("run of 4 (the 1872 ch.125-128 shape)",
      _rm._run_lengths([125, 126, 127, 128]),
      {125: 4, 126: 4, 127: 4, 128: 4})
check("two separate runs",
      _rm._run_lengths([10, 11, 20]), {10: 2, 11: 2, 20: 1})
check("empty", _rm._run_lengths([]), {})

print("\n=== truthiness bug: source_page == 0 must NOT be dropped ===\n")
# Old code did `if lo_p and hi_p`, so a page of 0 was falsy -> rng=None and the
# chapter silently vanished from the histogram.
rng, lo, hi, lo_p, hi_p, imp = _rm.bracket_for(2, [1, 5], {1: 0, 5: 40})
check("lo_page=0 still yields a range (not None)", rng is not None, True)
check("lo_page=0 recorded, not coerced", lo_p, 0)

print("\n=== two-sided bracket gets a safety margin ===\n")
rng, *_ = _rm.bracket_for(50, [40, 60], {40: 100, 60: 140})
check("range widened by BRACKET_MARGIN both sides",
      rng, [100 - _rm.BRACKET_MARGIN, 140 + _rm.BRACKET_MARGIN])
check("lower bound never below page 1",
      _rm.bracket_for(2, [1, 5], {1: 1, 5: 9})[0][0], 1)

print("\n=== THE 1872 ch.125-128 FAILURE -- span must be flagged implausible ===\n")
# Recorded (corrupt) neighbour pages: ch.124 -> PDF 224, ch.129 -> PDF 227.
# Four chapters (125,126,127,128) cannot fit in a 3-page gap.
rng, lo, hi, lo_p, hi_p, imp = _rm.bracket_for(
    125, [124, 129], {124: 224, 129: 227}, run_len=4)
check("4 missing chapters in a 3-page gap -> span_implausible", imp, True)
check("neighbours still reported", (lo, hi), (124, 129))

# The same shape with a believable gap must NOT be flagged.
rng, _, _, _, _, imp_ok = _rm.bracket_for(
    125, [124, 129], {124: 220, 129: 240}, run_len=4)
check("4 missing chapters in a 20-page gap -> not flagged", imp_ok, False)

print("\n=== one-sided brackets scale with run length ===\n")
# A run of 10 missing chapters needs a wider window than a single one.
r_single = _rm.bracket_for(99, [98], {98: 500}, run_len=1)[0]
r_run = _rm.bracket_for(99, [98], {98: 500}, run_len=10)[0]
check("longer run -> wider one-sided window", r_run[1] > r_single[1], True)
check("one-sided lower bound clamped at 1",
      _rm.bracket_for(1, [2], {2: 3}, run_len=1)[0][0], 1)

print("\n=== no neighbour pages at all ===\n")
rng, lo, hi, lo_p, hi_p, imp = _rm.bracket_for(7, [], {})
check("no neighbours -> rng None (caller warns)", rng, None)
check("no neighbours -> not flagged implausible", imp, False)

print("\n=== paths resolve to something real ===\n")
check("ORACLE path exists", os.path.exists(_rm.ORACLE), True)

print("\n" + "=" * 60)
print("Results: %d passed, %d failed" % (PASS, FAIL))
print("=" * 60)
sys.exit(1 if FAIL else 0)
