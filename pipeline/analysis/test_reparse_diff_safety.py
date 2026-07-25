"""Safety tests for reparse_diff.py -- the BEFORE parser MUST NOT be able to write.

This exists because the first version of the harness had a TypeError fallback
that called `parse_volume(label)` with the default write=True, which would have
overwritten live corpus files with PRE-FIX output on every volume, while the
docstring claimed it touched nothing. These tests make that class of mistake
loud instead of silent.

Run:  python test_reparse_diff_safety.py
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("rpd", str(_HERE / "reparse_diff.py"))
_rpd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rpd)

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


print("\n=== BEFORE source is neutered ===\n")
with tempfile.TemporaryDirectory() as td:
    before = _rpd._materialise_before(_rpd.DEFAULT_BEFORE_REF, td)
    src = before.read_text(encoding="utf-8")

    check("flag constant injected", src.startswith("_DIFF_NEVER_WRITE = False"), True)
    check("write call short-circuited",
          "_DIFF_NEVER_WRITE and out_path.write_text(" in src, True)
    check("no un-guarded out_path.write_text remains",
          src.count("out_path.write_text(") == src.count("_DIFF_NEVER_WRITE and out_path.write_text("),
          True)
    check("date-review worklist neutered",
          "return  # neutered by reparse_diff" in src, True)

    # Load it via the harness's own loader so the sys.path handling is the same
    # code path the real run uses (the parser does `import config` at module
    # level and dies without pipeline/ on the path).
    mod = _rpd._load_parser(before, "ing_before_probe")
    check("_DIFF_NEVER_WRITE is False at runtime", mod._DIFF_NEVER_WRITE, False)

    # The worklist append must be a no-op even if called directly.
    wrote = {"n": 0}
    real_open = open

    def _spy_open(*a, **k):
        if len(a) > 1 and "a" in str(a[1]):
            wrote["n"] += 1
        return real_open(*a, **k)

    import builtins
    builtins.open = _spy_open
    try:
        mod._append_date_review({"probe": 1})
    finally:
        builtins.open = real_open
    check("_append_date_review opens nothing in append mode", wrote["n"], 0)

    # BEFORE must NOT accept write= -- if it does, the ref is wrong (it already
    # contains the cc019 change) and the diff would compare a parser to itself.
    import inspect
    sig = inspect.signature(mod.parse_volume)
    check("BEFORE parse_volume has the PRE-cc019 signature (no write kwarg)",
          "write" in sig.parameters, False)

print("\n=== AFTER parser genuinely honours write=False ===\n")
_after = _rpd._load_parser(_HERE.parent / "ingest" / "ingest_from_ocr.py", "ing_after_probe")

import inspect as _i
check("AFTER parse_volume accepts write=", "write" in _i.signature(_after.parse_volume).parameters, True)
check("AFTER parse_volume accepts out_path=", "out_path" in _i.signature(_after.parse_volume).parameters, True)
check("AFTER has the dry-run suppression flag", hasattr(_after, "_SUPPRESS_DATE_REVIEW"), True)
check("suppression flag defaults to False (normal runs still log)",
      _after._SUPPRESS_DATE_REVIEW, False)

# With the flag set, the worklist append must not open anything.
_after._SUPPRESS_DATE_REVIEW = True
opened = {"n": 0}
_real_open = open


def _spy2(*a, **k):
    opened["n"] += 1
    return _real_open(*a, **k)


import builtins as _b
_b.open = _spy2
try:
    _after._append_date_review({"probe": 1})
finally:
    _b.open = _real_open
    _after._SUPPRESS_DATE_REVIEW = False
check("suppressed _append_date_review opens no file", opened["n"], 0)

print("\n=== no TypeError fallback remains in the harness ===\n")
harness_src = (_HERE / "reparse_diff.py").read_text(encoding="utf-8")
check("no 'except TypeError' fallback", "except TypeError" in harness_src, False)
check("BEFORE is called without a write kwarg",
      "mod_before.parse_volume(label)" in harness_src, True)
check("AFTER is called with write=False",
      "mod_after.parse_volume(label, write=False)" in harness_src, True)
check("baseline fidelity check present", "baseline_fidelity" in harness_src, True)

print("\n" + "=" * 60)
print("Results: %d passed, %d failed" % (PASS, FAIL))
print("=" * 60)
sys.exit(1 if FAIL else 0)
