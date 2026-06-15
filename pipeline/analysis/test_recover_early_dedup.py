"""test_recover_early_dedup.py -- regression for the recover_early MAJOR-1 dedup fix.

Hans MAJOR-1: the second-pass MIN_GAP dedup in detect_starts silently dropped a
BASELINE (B) start when two B-starts were <MIN_GAP lines apart -- a regression vs
production (violates the AFTER>=BEFORE invariant: a production-found act must never
be dropped). FIX: baseline (B) starts ALWAYS pass the dedup; only joined-form (A)
starts may be suppressed by MIN_GAP.

These tests drive detect_starts directly by stubbing the two source detectors
(_baseline_starts / _joined_starts) so the dedup logic is exercised in isolation
-- no OCR data, no DB, no file writes.

Run:  python -m analysis.test_recover_early_dedup
"""
import importlib.util
from pathlib import Path

_RE = Path(__file__).resolve().parents[1] / "ingest" / "recover_early.py"
_spec = importlib.util.spec_from_file_location("recover_early", str(_RE))
RE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RE)

_fail = 0


def check(name, cond):
    global _fail
    print(("PASS" if cond else "FAIL") + " | " + name)
    if not cond:
        _fail += 1


def run_detect(base, joined, n_lines=200):
    """Call detect_starts with stubbed source detectors. base/joined are {i: tok}."""
    saved_b, saved_j = RE._baseline_starts, RE._joined_starts
    try:
        RE._baseline_starts = lambda lines: dict(base)
        RE._joined_starts = lambda lines: dict(joined)
        lines = [(0, "") for _ in range(n_lines)]
        return RE.detect_starts(lines)
    finally:
        RE._baseline_starts, RE._joined_starts = saved_b, saved_j


# ---- THE regression: two consecutive B-starts 1 line apart are BOTH kept ----
# (1 < MIN_GAP=2, so the old code dropped the second.)
starts = run_detect(base={10: "I", 11: "II"}, joined={})
idxs = [i for (i, _t, _f) in starts]
forms = {i: f for (i, _t, f) in starts}
check("two B-starts 1 line apart (10,11): BOTH kept",
      10 in idxs and 11 in idxs)
check("both kept starts are form 'B'",
      forms.get(10) == "B" and forms.get(11) == "B")

# ---- AFTER >= BEFORE: every B-start survives, regardless of crowding ----
base = {5: "I", 6: "II", 7: "III", 50: "IV", 51: "V"}
starts = run_detect(base=base, joined={})
kept_b = [i for (i, _t, f) in starts if f == "B"]
check("AFTER>=BEFORE: all 5 crowded B-starts survive",
      sorted(kept_b) == sorted(base.keys()))

# ---- A-starts ARE still suppressed by MIN_GAP (precision preserved) ----
# two A-starts 1 apart -> only the first kept.
starts = run_detect(base={}, joined={20: "I", 21: "II"})
idxs = [i for (i, _t, _f) in starts]
check("two A-starts 1 line apart (20,21): second suppressed by MIN_GAP",
      20 in idxs and 21 not in idxs)

# ---- existing guard intact: an A-start inside a B-start's window is dropped ----
# joined hit at 31 sits within MIN_GAP of baseline hit at 30 -> dropped at merge.
starts = run_detect(base={30: "I"}, joined={31: "II"})
idxs = [i for (i, _t, f) in starts]
forms = {i: f for (i, _t, f) in starts}
check("A-start adjacent to a B-start is dropped (B wins the window)",
      30 in idxs and forms.get(30) == "B" and 31 not in idxs)

# ---- mixed: a B-start crowded by a prior B AND a following A ----
# B at 100, B at 101 (both kept), A at 102 (suppressed: within MIN_GAP of last=101).
starts = run_detect(base={100: "I", 101: "II"}, joined={102: "III"})
idxs = [i for (i, _t, _f) in starts]
check("mixed: both crowded B-starts kept, trailing A suppressed",
      100 in idxs and 101 in idxs and 102 not in idxs)

print(("ALL PASS" if _fail == 0 else (str(_fail) + " FAILED")))
raise SystemExit(1 if _fail else 0)
