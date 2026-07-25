"""
test_date_parser_fix.py -- Focused regression tests for the chaptered_date
parser fixes (cc006 forensic, commit a5c4d0d).

Two bug classes:
  Cluster A -- OCR digit misread in early-era (1855-1870) volumes; the year
               in the [Approved ... 18XX] line was corrupted by OCR
               (e.g. 1855->1895, 1860->1880).  parse_act_date() had no
               year sanity check, so the corrupted but syntactically valid
               year was committed.
  Cluster B -- Born-digital 2000-2008 volumes; the permissive APPROVED_RE
               ran before APPROVED_MODERN_RE and finditer() grabbed the
               FIRST match, which was a historical date embedded in the act
               body (boilerplate like B&P §473.15 "initiative measure approved
               June 2, 1913") instead of the real "Approved by Governor ..."
               bracket date.

New behavior (flag-not-muffle):
  When volume_year is set and a date IS found by a regex but its year is
  outside the ±YEAR_CLAMP_WINDOW, parse_act_date() now records the rejected
  candidate in the _rejected_out list (caller-supplied collector) instead of
  silently discarding it.  This lets callers distinguish:
    (None, "", empty _rejected_out)  -> genuinely no date present
    (None, "", non-empty _rejected_out) -> date found but year implausible
                                           (OCR-error suspect -> review worklist)

No DB, no network, no file I/O (except where a test explicitly writes to a
temp path to verify the review worklist mechanism).  Run with:
    python pipeline/test_date_parser_fix.py

Exits 0 on all pass, non-zero on any failure.
"""

import sys
import os
import json
import tempfile
import pathlib

# Ensure pipeline/ is on the path so we can import the fixed modules
_REPO = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(_REPO, "pipeline", "5080"))

# Import the modules under test.
# ingest_from_ocr.py now guards its DB/file main loop with
# `if __name__ == "__main__":` (NITPICK-2 fix), so a plain import is safe
# and side-effect-free.  The _load_module helper is kept below for
# parse_born_digital_prod.py (needs fitz-availability gate) and for
# reparse/parse_born_digital tombstone tests.
import importlib.util as _ilu
import types as _types

def _load_module(path, name, argv_patch=None):
    """Load a source module by path, optionally patching sys.argv during load."""
    spec = _ilu.spec_from_file_location(name, path)
    mod = _types.ModuleType(name)
    mod.__spec__ = spec
    mod.__file__ = str(path)  # needed by modules that use Path(__file__)
    orig_argv = sys.argv
    if argv_patch is not None:
        sys.argv = argv_patch
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = orig_argv
    return mod

_pipeline_dir = os.path.join(os.path.dirname(__file__), "5080")

# cc019 (2026-07-24): this file was DEAD -- it died at import, before its first
# assertion, and had since the module reorg. ingest_from_ocr.py moved from
# pipeline/5080/ to pipeline/ingest/, but this loader still pointed at 5080/,
# raising FileNotFoundError. test_chapter_parser.py:21 was updated for the same
# reorg; this file was missed. Net effect: ZERO live regression coverage on
# parse_act_date (including the _TEXT_NO_DATE case and the +/-3-year clamp).
#
# Nothing caught it: the repo has no CI, no pytest.ini/pyproject.toml, and every
# test is hand-invoked. smoke_imports.py cannot catch this class of breakage --
# it is AST-based and the broken reference is a STRING PATH, not an import.
#
# NOTE: only ingest_from_ocr.py moved. reparse.py and parse_born_digital.py are
# still in pipeline/5080/ -- verified 2026-07-24. Do not blanket-repoint.
_ingest_dir = os.path.join(os.path.dirname(__file__), "ingest")

# ingest_from_ocr.py is now import-safe (NITPICK-2): main loop guarded by
# __name__ == "__main__", so no argv patching needed.
_ingest = _load_module(
    os.path.join(_ingest_dir, "ingest_from_ocr.py"),
    "ingest_from_ocr",
)

# Load the tombstoned modules for SERIOUS-1/2 tests.
# reparse.py is ARCHIVED/DO-NOT-USE but is still loaded here for the tombstone
# assertions -- do not delete it.
_reparse = _load_module(
    os.path.join(_pipeline_dir, "reparse.py"),
    "reparse_module",
)
# parse_born_digital.py imports fitz at module level; mock it if not installed.
try:
    import fitz as _fitz_check  # noqa: F401 -- just test availability
    _pbd = _load_module(
        os.path.join(_pipeline_dir, "parse_born_digital.py"),
        "parse_born_digital",
    )
    _pbd_available = True
except ImportError:
    _pbd = None
    _pbd_available = False

# parse_born_digital_prod imports fitz (PyMuPDF); mock it if not installed
try:
    import fitz as _fitz_check2  # noqa: F401
    _bd = _load_module(
        os.path.join(_pipeline_dir, "parse_born_digital_prod.py"),
        "parse_born_digital_prod",
    )
    _bd_available = True
except ImportError:
    _bd = None
    _bd_available = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ok(label):
    print(f"  PASS  {label}")

def fail(label, detail):
    print(f"  FAIL  {label}: {detail}")
    return False

PASSES = []
FAILURES = []

def check(label, condition, detail=""):
    if condition:
        ok(label)
        PASSES.append(label)
    else:
        fail(label, detail)
        FAILURES.append(label)


# ---------------------------------------------------------------------------
# CLUSTER A -- OCR year misread (ingest_from_ocr.parse_act_date)
# ---------------------------------------------------------------------------

print("\n=== CLUSTER A: OCR year misread (ingest_from_ocr.py) ===\n")

# Representative body text from the 1855 session where OCR misread "1855" as
# "1895" in the approval line.
_TEXT_1855_CORRUPTED = """\
CHAPTER I.
An Act for the relief of John Smith.
The People of the State of California, represented in Senate and Assembly,
do enact as follows:
Section 1. That John Smith is hereby relieved.
[Approved March 3, 1895.]
"""

# 1. Without volume_year (legacy behaviour): should return the corrupted date.
iso, raw = _ingest.parse_act_date(_TEXT_1855_CORRUPTED, volume_year=None)
check(
    "A1: no volume_year -> accepts corrupted year 1895 (legacy behaviour preserved)",
    iso == "1895-03-03",
    f"got iso={iso!r}",
)

# 2. With correct volume_year=1855: should REJECT the 1895 match (40 years off)
#    and return None because no other match exists.  Flag-not-muffle: the
#    rejected candidate must appear in _rejected_out so callers can write a
#    worklist record rather than silently swallowing the OCR error.
rejected_a2 = []
iso, raw = _ingest.parse_act_date(
    _TEXT_1855_CORRUPTED, volume_year=1855, _rejected_out=rejected_a2)
check(
    "A2: volume_year=1855 -> rejects corrupted year 1895 (40 yrs off) -> None",
    iso is None,
    f"got iso={iso!r}  (expected None)",
)
check(
    "A2b: flag-not-muffle -- rejected_out has the 1895 candidate recorded",
    len(rejected_a2) == 1 and rejected_a2[0]["parsed_year"] == 1895,
    f"got rejected_out={rejected_a2!r}  (expected one entry with parsed_year=1895)",
)

# 3. Correctly-printed year in 1855 session should PASS.
_TEXT_1855_CORRECT = """\
CHAPTER II.
An Act to incorporate the town of Sacramento.
The People of the State of California, represented in Senate and Assembly,
do enact as follows:
Section 1. Said town is hereby incorporated.
[Approved March 7, 1855.]
"""
iso, raw = _ingest.parse_act_date(_TEXT_1855_CORRECT, volume_year=1855)
check(
    "A3: volume_year=1855, correct year 1855 -> accepted",
    iso == "1855-03-07",
    f"got iso={iso!r}",
)

# 4. Year one off (session spanning two calendar years, e.g. 1863-64 session).
#    An act approved January 15, 1864 should pass for volume_year=1863 (within ±3).
_TEXT_1863_64 = """\
CHAPTER V.
An Act to authorise the construction of a bridge.
The People of the State of California do enact as follows:
Section 1. The bridge shall be built.
[Approved January 15, 1864.]
"""
iso, raw = _ingest.parse_act_date(_TEXT_1863_64, volume_year=1863)
check(
    "A4: volume_year=1863, act approved Jan 1864 (1 yr off) -> within ±3, accepted",
    iso == "1864-01-15",
    f"got iso={iso!r}",
)

# 5. 1860 volume with OCR misread 1860->1880 (20 years off) -> should be rejected.
#    Flag-not-muffle: _rejected_out must capture the 1880 candidate.
_TEXT_1860_CORRUPTED = """\
CHAPTER X.
An Act concerning public schools.
The People of the State of California do enact as follows:
Section 1. The common school fund is hereby established.
[Approved April 10, 1880.]
"""
rejected_a5 = []
iso, raw = _ingest.parse_act_date(
    _TEXT_1860_CORRUPTED, volume_year=1860, _rejected_out=rejected_a5)
check(
    "A5: volume_year=1860, corrupted year 1880 (20 yrs off) -> rejected -> None",
    iso is None,
    f"got iso={iso!r}  (expected None)",
)
check(
    "A5b: flag-not-muffle -- rejected_out has the 1880 candidate recorded",
    len(rejected_a5) == 1 and rejected_a5[0]["parsed_year"] == 1880,
    f"got rejected_out={rejected_a5!r}  (expected one entry with parsed_year=1880)",
)

# 6. No date present at all (genuinely dateless act): _rejected_out must remain
#    EMPTY so callers can distinguish "OCR error" from "legitimately no date".
_TEXT_NO_DATE = """\
CHAPTER XI.
An Act granting lands to settlers.
The People of the State of California do enact as follows:
Section 1. Certain lands are hereby granted.
"""
rejected_a6 = []
iso, raw = _ingest.parse_act_date(
    _TEXT_NO_DATE, volume_year=1860, _rejected_out=rejected_a6)
check(
    "A6: genuinely no date in text -> returns None AND rejected_out is empty",
    iso is None and len(rejected_a6) == 0,
    f"got iso={iso!r}  rejected_out={rejected_a6!r}  (expected None and empty list)",
)


# ---------------------------------------------------------------------------
# CLUSTER B -- born-digital date poisoning (ingest_from_ocr.py modern path)
# ---------------------------------------------------------------------------

print("\n=== CLUSTER B: born-digital date poisoning (ingest_from_ocr.py modern path) ===\n")

# Representative 2000-era act body: contains a historical date reference in the
# body text (boilerplate) and the real "Approved by Governor" bracket near the end.
# Without the fix: APPROVED_RE would grab "June 2, 1913" (first match).
# With the fix: APPROVED_MODERN_RE is tried first for volume_year >= 1915, so
# "Approved by Governor October 15, 2000" is found and returned.
_TEXT_2000_POISONED = """\
CHAPTER 42.
An Act to amend Section 473.15 of the Business and Professions Code.
The people of the State of California do enact as follows:
SECTION 1. Section 473.15 is amended to read:
473.15. The initiative measure approved June 2, 1913, is hereby amended
to provide for the following.
[Approved by Governor October 15, 2000. Filed with Secretary of State
October 16, 2000.]
"""

# B1. After SERIOUS-4 fix: APPROVED_MODERN_RE is always tried first, even with
# no volume_year.  The unguarded call now correctly returns the modern date
# because APPROVED_MODERN_RE matches "Approved by Governor October 15, 2000"
# before APPROVED_RE can grab the body's 1913 date.
iso, raw = _ingest.parse_act_date(_TEXT_2000_POISONED, volume_year=None)
check(
    "B1: no volume_year -> SERIOUS-4 fix: MODERN_RE first, grabs 2000-10-15 (not body date 1913)",
    iso == "2000-10-15",
    f"got iso={iso!r}  (expected 2000-10-15: MODERN_RE now always tried first)",
)

# B2. With volume_year=2000: APPROVED_MODERN_RE tried first -> returns real date.
iso, raw = _ingest.parse_act_date(_TEXT_2000_POISONED, volume_year=2000)
check(
    "B2: volume_year=2000 -> APPROVED_MODERN_RE first -> returns real date 2000-10-15",
    iso == "2000-10-15",
    f"got iso={iso!r}  (expected 2000-10-15)",
)

# B3. Year clamp also blocks 1913 even if APPROVED_MODERN_RE found nothing:
#     a hypothetical text with only the APPROVED_RE-style 1913 body date and
#     NO "Approved by Governor" bracket.
#     Flag-not-muffle: _rejected_out must capture 1913 so callers can flag this
#     as an OCR-suspect rather than treating it as a legitimately dateless act.
_TEXT_2000_BODY_ONLY = """\
CHAPTER 43.
An Act concerning historical measures.
The people of the State of California do enact as follows:
SECTION 1. The initiative measure approved June 2, 1913, is cited.
"""
rejected_b3 = []
iso, raw = _ingest.parse_act_date(
    _TEXT_2000_BODY_ONLY, volume_year=2000, _rejected_out=rejected_b3)
check(
    "B3: volume_year=2000, body has only 1913 date (no modern bracket) -> clamped, returns None",
    iso is None,
    f"got iso={iso!r}  (expected None — year 1913 is 87 yrs off from 2000)",
)
check(
    "B3b: flag-not-muffle -- rejected_out has the 1913 body-date candidate recorded",
    len(rejected_b3) == 1 and rejected_b3[0]["parsed_year"] == 1913,
    f"got rejected_out={rejected_b3!r}  (expected one entry with parsed_year=1913)",
)

# B4. 2008 act with ONLY a modern bracket (normal case, no body noise) -> accepted.
_TEXT_2008_CLEAN = """\
CHAPTER 77.
An Act to amend Section 100 of the Health and Safety Code.
The people of the State of California do enact as follows:
SECTION 1. This act takes effect immediately.
[Approved by Governor February 28, 2008. Filed with Secretary of State
March 1, 2008.]
"""
iso, raw = _ingest.parse_act_date(_TEXT_2008_CLEAN, volume_year=2008)
check(
    "B4: volume_year=2008, clean modern bracket -> returns 2008-02-28",
    iso == "2008-02-28",
    f"got iso={iso!r}",
)


# ---------------------------------------------------------------------------
# CLUSTER B -- parse_born_digital_prod.py (same fix, separate copy)
# ---------------------------------------------------------------------------

if _bd_available:
    print("\n=== CLUSTER B (parse_born_digital_prod.py copy) ===\n")

    iso, raw = _bd.parse_act_date(_TEXT_2000_POISONED, volume_year=2000)
    check(
        "BD1: parse_born_digital_prod volume_year=2000 -> returns real date 2000-10-15",
        iso == "2000-10-15",
        f"got iso={iso!r}",
    )

    iso, raw = _bd.parse_act_date(_TEXT_2000_POISONED, volume_year=None)
    check(
        "BD2: parse_born_digital_prod no volume_year -> MODERN_RE still tried first -> 2000-10-15",
        iso == "2000-10-15",
        f"got iso={iso!r}  (expected 2000-10-15: MODERN_RE always tried first in both "
        f"parse_born_digital_prod and ingest_from_ocr.py after SERIOUS-4 fix)",
    )

    iso, raw = _bd.parse_act_date(_TEXT_2008_CLEAN, volume_year=2008)
    check(
        "BD3: parse_born_digital_prod clean 2008 act -> 2008-02-28",
        iso == "2008-02-28",
        f"got iso={iso!r}",
    )
else:
    print("\n=== CLUSTER B (parse_born_digital_prod.py) -- SKIPPED (fitz/PyMuPDF not installed) ===\n")
    print("  (Run on the 5080/5090 where fitz is installed to exercise the BD tests)")


# ---------------------------------------------------------------------------
# SERIOUS-3: tombstone tests
# ---------------------------------------------------------------------------
# reparse.py:parse_act_date must raise RuntimeError (SERIOUS-1 fix).

print("\n=== SERIOUS-1: reparse.py parse_act_date is tombstoned ===\n")

_reparse_raised = False
try:
    _reparse.parse_act_date("Approved March 3, 1855.")
except RuntimeError:
    _reparse_raised = True
except Exception as _e:
    pass
check(
    "T1: reparse.py:parse_act_date raises RuntimeError (tombstoned)",
    _reparse_raised,
    "expected RuntimeError; got no exception or wrong exception type",
)

# parse_born_digital.py:parse_born_digital_volume must raise NotImplementedError
# (SERIOUS-2 fix).

print("\n=== SERIOUS-2: parse_born_digital.py parse_born_digital_volume is tombstoned ===\n")

if _pbd_available:
    _pbd_raised = False
    try:
        _pbd.parse_born_digital_volume("dummy.pdf")
    except NotImplementedError:
        _pbd_raised = True
    except Exception as _e2:
        pass
    check(
        "T2: parse_born_digital.py:parse_born_digital_volume raises NotImplementedError (tombstoned)",
        _pbd_raised,
        "expected NotImplementedError; got no exception or wrong exception type",
    )
else:
    print("  SKIP  T2: parse_born_digital.py tombstone test -- fitz not installed")


# ---------------------------------------------------------------------------
# BOUNDARY: ±3-year window edges
# ---------------------------------------------------------------------------

print("\n=== BOUNDARY: ±3-year clamp edges ===\n")

# year exactly at the boundary (volume_year + 3): should be accepted
_TEXT_EDGE_PLUS3 = "[Approved May 5, 1858.]\nThe People of the State of California do enact as follows: Section 1."
iso, raw = _ingest.parse_act_date(
    "An Act.\nThe People of the State of California do enact as follows:\n" + _TEXT_EDGE_PLUS3,
    volume_year=1855,
)
check(
    "BOUND1: volume_year=1855, year=1858 (+3) -> accepted (on boundary)",
    iso == "1858-05-05",
    f"got iso={iso!r}",
)

# year one beyond boundary (volume_year + 4): should be rejected.
# Flag-not-muffle: the 1859 candidate must appear in _rejected_out.
_TEXT_EDGE_PLUS4 = "An Act.\nThe People of the State of California do enact as follows:\n[Approved May 5, 1859.]"
rejected_bound2 = []
iso, raw = _ingest.parse_act_date(
    _TEXT_EDGE_PLUS4, volume_year=1855, _rejected_out=rejected_bound2)
check(
    "BOUND2: volume_year=1855, year=1859 (+4) -> rejected (outside boundary)",
    iso is None,
    f"got iso={iso!r}  (expected None)",
)
check(
    "BOUND2b: flag-not-muffle -- rejected_out has the 1859 candidate",
    len(rejected_bound2) == 1 and rejected_bound2[0]["parsed_year"] == 1859,
    f"got rejected_out={rejected_bound2!r}",
)


# ---------------------------------------------------------------------------
# WORKLIST FILE: verify _append_date_review writes a valid JSONL record
# ---------------------------------------------------------------------------
# This test patches DATE_REVIEW_WORKLIST to a temp path, calls _append_date_review
# directly, and verifies the written record has the required fields.

print("\n=== WORKLIST FILE: _append_date_review writes a valid JSONL record ===\n")

import tempfile, pathlib as _pl

_tmp_worklist = pathlib.Path(tempfile.mktemp(suffix=".jsonl"))
# Monkey-patch the module-level path for the duration of this test.
_orig_worklist = _ingest.DATE_REVIEW_WORKLIST
_ingest.DATE_REVIEW_WORKLIST = _tmp_worklist
try:
    _sample_record = {
        "timestamp_utc": "2026-06-09T00:00:00Z",
        "session_label": "1860",
        "volume_year": 1860,
        "raw_match": "Approved April 10, 1880.",
        "parsed_year": 1880,
        "year_delta": 20,
        "citation": "Stats. 1860 ch.10",
        "source_page": 42,
        "in_act_order": 9,
        "reason": "year_out_of_window",
    }
    _ingest._append_date_review(_sample_record)
    _written_lines = _tmp_worklist.read_text(encoding="utf-8").strip().splitlines()
    _parsed_rec = json.loads(_written_lines[0])
    check(
        "WL1: _append_date_review writes exactly one JSONL line",
        len(_written_lines) == 1,
        f"got {len(_written_lines)} lines",
    )
    check(
        "WL2: worklist record has required fields",
        all(k in _parsed_rec for k in (
            "timestamp_utc", "session_label", "volume_year",
            "raw_match", "parsed_year", "year_delta",
            "citation", "source_page", "in_act_order", "reason"
        )),
        f"missing fields in: {list(_parsed_rec.keys())}",
    )
    check(
        "WL3: worklist record values are correct",
        _parsed_rec["parsed_year"] == 1880
        and _parsed_rec["session_label"] == "1860"
        and _parsed_rec["reason"] == "year_out_of_window",
        f"got {_parsed_rec!r}",
    )
    # Verify append semantics: a second write produces a second line.
    _ingest._append_date_review(_sample_record)
    _lines2 = _tmp_worklist.read_text(encoding="utf-8").strip().splitlines()
    check(
        "WL4: _append_date_review appends (does not overwrite) on second call",
        len(_lines2) == 2,
        f"got {len(_lines2)} lines after second write",
    )
finally:
    _ingest.DATE_REVIEW_WORKLIST = _orig_worklist
    if _tmp_worklist.exists():
        _tmp_worklist.unlink()


# ---------------------------------------------------------------------------
# WORKLIST INTEGRATION: out-of-window parse_act_date hit writes to worklist
# ---------------------------------------------------------------------------
# This test verifies the end-to-end path: parse_act_date detects an out-of-window
# date -> _rejected_out is populated -> caller (simulating flush_act behaviour)
# writes to the worklist.

print("\n=== WORKLIST INTEGRATION: out-of-window date -> worklist record ===\n")

_tmp_wl2 = pathlib.Path(tempfile.mktemp(suffix=".jsonl"))
_orig_wl2 = _ingest.DATE_REVIEW_WORKLIST
_ingest.DATE_REVIEW_WORKLIST = _tmp_wl2
try:
    _rej2 = []
    iso, raw = _ingest.parse_act_date(
        _TEXT_1855_CORRUPTED, volume_year=1855, _rejected_out=_rej2)
    # Simulate what flush_act does: write each rejected candidate to the worklist.
    for _r in _rej2:
        _ingest._append_date_review({
            "timestamp_utc": "2026-06-09T00:00:00Z",
            "session_label": "1855",
            "volume_year": 1855,
            "raw_match": _r["raw"],
            "parsed_year": _r["parsed_year"],
            "year_delta": abs(_r["parsed_year"] - 1855),
            "citation": "Stats. 1855 ch.1",
            "source_page": 1,
            "in_act_order": 0,
            "reason": "year_out_of_window",
        })
    _wi_lines = _tmp_wl2.read_text(encoding="utf-8").strip().splitlines() if _tmp_wl2.exists() else []
    check(
        "WI1: out-of-window date produces exactly one worklist record",
        len(_wi_lines) == 1,
        f"got {len(_wi_lines)} lines",
    )
    if _wi_lines:
        _wi_rec = json.loads(_wi_lines[0])
        check(
            "WI2: worklist record year matches the rejected candidate (1895)",
            _wi_rec["parsed_year"] == 1895 and _wi_rec["session_label"] == "1855",
            f"got {_wi_rec!r}",
        )
finally:
    _ingest.DATE_REVIEW_WORKLIST = _orig_wl2
    if _tmp_wl2.exists():
        _tmp_wl2.unlink()


# ---------------------------------------------------------------------------
# CONCURRENCY FIX: born-digital path returns review records (not write in worker)
# ---------------------------------------------------------------------------
# Verifies that parse_born_digital_volume() returns review records in the
# third element of its return tuple, rather than writing directly to the JSONL
# worklist file.  This is the fix for the multiprocessing concurrency race:
# worker subprocesses must NOT write to the shared file; the main process does.
#
# Also verifies that calling _append_date_review() from the main process with
# the returned records produces correct JSONL output.

if _bd_available:
    print("\n=== CONCURRENCY FIX: parse_born_digital_volume returns review records ===\n")

    # Build a minimal mock PDF that has CHAPTER headers and an act with an
    # implausible date.  We exercise parse_born_digital_volume directly by
    # patching fitz.open to return a synthetic page sequence.

    import types as _types_bd
    import unittest.mock as _mock

    # Synthetic volume text: one chapter with an implausible year (1913, volume
    # is 2000) so date_needs_review will be True for that act.
    _BD_SYNTHETIC_TEXT = (
        "CHAPTER 1\n"
        "An Act to test the concurrency fix.\n"
        "The People of the State of California do enact as follows:\n"
        "SECTION 1. This section is effective.\n"
        "Approved June 2, 1913.\n"
    )

    class _FakePage:
        def get_text(self):
            return _BD_SYNTHETIC_TEXT

    class _FakeDoc:
        page_count = 1
        def __getitem__(self, i):
            return _FakePage()
        def close(self):
            pass

    # Patch fitz.open and label_for/year_of so no real PDF is needed.
    with _mock.patch.object(_bd.fitz, "open", return_value=_FakeDoc()):
        with _mock.patch.object(_bd, "year_of", return_value=2000):
            with _mock.patch.object(_bd, "label_for", return_value="2000_Vol1"):
                _bd_acts, _bd_meta, _bd_review = _bd.parse_born_digital_volume(
                    "dummy_2000_Vol1.pdf")

    check(
        "CONC1: parse_born_digital_volume returns a 3-tuple (acts, meta, review_records)",
        isinstance(_bd_review, list),
        f"third element type={type(_bd_review)!r}  (expected list)",
    )
    check(
        "CONC2: implausible-date act produces at least one review record in returned list",
        len(_bd_review) >= 1,
        f"got {len(_bd_review)} review records (expected >= 1 for the 1913 date in a 2000 volume)",
    )
    if _bd_review:
        _br = _bd_review[0]
        check(
            "CONC3: review record has required fields",
            all(k in _br for k in (
                "timestamp_utc", "session_label", "volume_year",
                "raw_match", "parsed_year", "citation", "reason"
            )),
            f"missing fields in: {list(_br.keys())}",
        )
        check(
            "CONC4: review record reason is year_out_of_window",
            _br["reason"] == "year_out_of_window",
            f"got reason={_br['reason']!r}",
        )

    # Verify that writing the returned records via _append_date_review (simulating
    # the main process) produces valid JSONL.
    _tmp_bd_wl = pathlib.Path(tempfile.mktemp(suffix=".jsonl"))
    _orig_bd_wl = _bd.DATE_REVIEW_WORKLIST
    _bd.DATE_REVIEW_WORKLIST = _tmp_bd_wl
    try:
        for _rev_rec in _bd_review:
            _bd._append_date_review(_rev_rec)
        _bd_wl_lines = (
            _tmp_bd_wl.read_text(encoding="utf-8").strip().splitlines()
            if _tmp_bd_wl.exists() else []
        )
        check(
            "CONC5: main-process write of returned review records produces correct JSONL line count",
            len(_bd_wl_lines) == len(_bd_review),
            f"got {len(_bd_wl_lines)} JSONL lines, expected {len(_bd_review)}",
        )
        if _bd_wl_lines:
            _bd_wl_rec = json.loads(_bd_wl_lines[0])
            check(
                "CONC6: JSONL record from main-process write is valid JSON with required fields",
                all(k in _bd_wl_rec for k in (
                    "timestamp_utc", "session_label", "citation", "reason"
                )),
                f"missing fields in: {list(_bd_wl_rec.keys())}",
            )
    finally:
        _bd.DATE_REVIEW_WORKLIST = _orig_bd_wl
        if _tmp_bd_wl.exists():
            _tmp_bd_wl.unlink()

else:
    print("\n=== CONCURRENCY FIX tests -- SKIPPED (fitz/PyMuPDF not installed) ===\n")
    print("  (Run on the 5080/5090 where fitz is installed to exercise CONC tests)")


# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"Results: {len(PASSES)} passed, {len(FAILURES)} failed")
if FAILURES:
    print("FAILED tests:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("All tests passed.")
    sys.exit(0)
