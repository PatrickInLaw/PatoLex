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

No DB, no network, no file I/O.  Run with:
    python pipeline/test_date_parser_fix.py

Exits 0 on all pass, non-zero on any failure.
"""

import sys
import os

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

# ingest_from_ocr.py is now import-safe (NITPICK-2): main loop guarded by
# __name__ == "__main__", so no argv patching needed.
_ingest = _load_module(
    os.path.join(_pipeline_dir, "ingest_from_ocr.py"),
    "ingest_from_ocr",
)

# Load the tombstoned modules for SERIOUS-1/2 tests.
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
#    and return None because no other match exists.
iso, raw = _ingest.parse_act_date(_TEXT_1855_CORRUPTED, volume_year=1855)
check(
    "A2: volume_year=1855 -> rejects corrupted year 1895 (40 yrs off) -> None",
    iso is None,
    f"got iso={iso!r}  (expected None)",
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
_TEXT_1860_CORRUPTED = """\
CHAPTER X.
An Act concerning public schools.
The People of the State of California do enact as follows:
Section 1. The common school fund is hereby established.
[Approved April 10, 1880.]
"""
iso, raw = _ingest.parse_act_date(_TEXT_1860_CORRUPTED, volume_year=1860)
check(
    "A5: volume_year=1860, corrupted year 1880 (20 yrs off) -> rejected -> None",
    iso is None,
    f"got iso={iso!r}  (expected None)",
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
_TEXT_2000_BODY_ONLY = """\
CHAPTER 43.
An Act concerning historical measures.
The people of the State of California do enact as follows:
SECTION 1. The initiative measure approved June 2, 1913, is cited.
"""
iso, raw = _ingest.parse_act_date(_TEXT_2000_BODY_ONLY, volume_year=2000)
check(
    "B3: volume_year=2000, body has only 1913 date (no modern bracket) -> clamped, returns None",
    iso is None,
    f"got iso={iso!r}  (expected None — year 1913 is 87 yrs off from 2000)",
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

# year one beyond boundary (volume_year + 4): should be rejected
_TEXT_EDGE_PLUS4 = "An Act.\nThe People of the State of California do enact as follows:\n[Approved May 5, 1859.]"
iso, raw = _ingest.parse_act_date(_TEXT_EDGE_PLUS4, volume_year=1855)
check(
    "BOUND2: volume_year=1855, year=1859 (+4) -> rejected (outside boundary)",
    iso is None,
    f"got iso={iso!r}  (expected None)",
)


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
