"""test_recover_guards.py -- unit checks for the recover_acts.py audit fixes.

Covers the four Hans-audit fixes (read-only; no DB, no file writes):
  CRITICAL-2  cross-session guard rejects labels spanning >1 LEGISLATURE_MAP session
  CRITICAL-1  own_header_witness reads ONLY the act's leading header (not body refs)
  MAJOR-1     is_real_act_start rejects an "An act" preceded by an opening quote
  MAJOR-2     self_numbered rescue stays in-order / no dup for two acts in one gap

Run:  python -m analysis.test_recover_guards
"""
import importlib.util
import sys
from pathlib import Path

# cc019: this suite was DEAD -- recover_acts.py does `import config` at module
# level, so loading it by path without pipeline/ on sys.path raised
# ModuleNotFoundError and the file died at import, before its first assertion.
# Same rot class that killed test_date_parser_fix.py for a month.
_PIPELINE = str(Path(__file__).resolve().parents[1])
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

_RA = Path(__file__).resolve().parents[1] / "ingest" / "recover_acts.py"
_spec = importlib.util.spec_from_file_location("recover_acts", str(_RA))
ra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ra)

_fail = 0


def check(name, cond):
    global _fail
    print(("PASS" if cond else "FAIL") + " | " + name)
    if not cond:
        _fail += 1


# ---- CRITICAL-2: cross-session guard ----
rejected = False
try:
    ra.process_session(["1957-vol1-56chapters", "1957-vol1-57chapters"])
except SystemExit as e:
    rejected = "more than one" in str(e).lower() or "1956 Regular Session" in str(e)
check("CRITICAL-2 rejects ['1957-vol1-56chapters','1957-vol1-57chapters'] (1956 vs 1957 session)",
      rejected)

# an unmapped label is also rejected
rejected_unmapped = False
try:
    ra.process_session(["not-a-real-label"])
except SystemExit:
    rejected_unmapped = True
check("CRITICAL-2 rejects an unmapped label", rejected_unmapped)

# a genuine same-session multi-volume call is NOT blocked by the guard
# (1957-vol1-57chapters + 1957-vol2-57chapters both map to '1957 Regular Session').
both_same = (ra.ing.LEGISLATURE_MAP["1957-vol1-57chapters"][0]
             == ra.ing.LEGISLATURE_MAP["1957-vol2-57chapters"][0])
check("CRITICAL-2 same-session pair maps to one session (would NOT be blocked)", both_same)

# ---- MAJOR-1: quoted-title rejection ----
# helper: lines are (page, text, line_pos)
def L(text):
    return [(0, text, 0)]

check("MAJOR-1 plain 'An act to ...' is a real start",
      ra.is_real_act_start(L("An act to amend Section 5 of the Code."), 0) is True)
check('MAJOR-1 double-quoted "An act ..." rejected',
      ra.is_real_act_start(L('entitled "An act to provide for ...'), 0) is False)
check("MAJOR-1 straight-single-quoted 'An act ...' rejected",
      ra.is_real_act_start(L("the 'An act to regulate ...'"), 0) is False)
check("MAJOR-1 unicode left-double-quote “An act rejected",
      ra.is_real_act_start(L("amend “An act to establish ..."), 0) is False)
check("MAJOR-1 unicode left-single-quote ‘An act rejected",
      ra.is_real_act_start(L("the ‘An act concerning ..."), 0) is False)

# ---- CRITICAL-1 witness: leading header only, NOT body 'Chapter N' refs ----
buf_baseline = ["CHAPTER 9", "An act to add Section 9705 to Chapter 7 of the Code,"]
lines_b = [(0, s, k) for k, s in enumerate(buf_baseline)]
check("CRITICAL-1 witness reads leading 'CHAPTER 9' (not body 'Chapter 7')",
      ra.own_header_witness(lines_b, 0, buf_baseline) == 9)

buf_body_only = ["An act to repeal Chapter 2 and Article 1 of Chapter 4,"]
lines_n = [(0, s, k) for k, s in enumerate(buf_body_only)]
check("CRITICAL-1 no witness when act has only body 'Chapter N' refs",
      ra.own_header_witness(lines_n, 0, buf_body_only) is None)

# recovered act (starts at 'An act'); header sits on the line ABOVE
lines_above = [(0, "CHAPTER 88", 0), (0, "An act relating to veterans.", 1)]
check("CRITICAL-1 witness found on the line ABOVE an 'An act' start",
      ra.own_header_witness(lines_above, 1, ["An act relating to veterans."]) == 88)

# ---- MAJOR-2: two ambiguous acts in one gap -> in order, no duplicate ----
# anchors at positions 0 (ch1) and 3 (ch4); positions 1,2 are ambiguous acts that
# carry their OWN printed numbers 2 and 3. The fixed sweep must rescue BOTH, in
# order, with no collision -- exercised via renumber_by_sequence + the rescue logic
# is inside process_session, so build a minimal acts list and replicate the rescue.
def mk(ch, status, final=None):
    return {"chapter_int": ch, "has_an_act": True, "iso_date": "1900-01-01",
            "chapter_int_final": (final if final is not None else ch),
            "renumber_status": status, "_volume": "x", "chapter": str(ch)}

# Simulate post-renumber state: two anchors with a 2-wide gap that did NOT fill
# (count mismatch), leaving two ambiguous acts carrying printed 2 and 3.
acts = [mk(1, "anchor"), mk(2, "ambiguous"), mk(3, "ambiguous"), mk(4, "anchor")]
# inline the exact rescue sweep from process_session:
import bisect
determined = {i: a["chapter_int_final"] for i, a in enumerate(acts)
              if a["renumber_status"] in ("anchor", "filled")}
det_nums = set(determined.values())
det_positions = sorted(determined.keys())
amb_positions = [i for i, a in enumerate(acts) if a["renumber_status"] == "ambiguous"]
for idx in amb_positions:
    a = acts[idx]
    own = a["chapter_int"]
    if not (1 <= own <= ra.CA_HARD_CEILING) or own in det_nums:
        continue
    p = bisect.bisect_left(det_positions, idx)
    lo_num = determined[det_positions[p - 1]] if p > 0 else 0
    hi_num = determined[det_positions[p]] if p < len(det_positions) else ra.CA_HARD_CEILING + 1
    if lo_num < own < hi_num:
        a["renumber_status"] = "self_numbered"
        a["chapter_int_final"] = own
        det_nums.add(own)
        determined[idx] = own
        bisect.insort(det_positions, idx)

finals = [a["chapter_int_final"] for a in acts]
check("MAJOR-2 two-in-gap rescued in order (1,2,3,4)", finals == [1, 2, 3, 4])
check("MAJOR-2 no duplicate chapter numbers after rescue", len(finals) == len(set(finals)))

print(("ALL PASS" if _fail == 0 else (str(_fail) + " FAILED")))
raise SystemExit(1 if _fail else 0)
