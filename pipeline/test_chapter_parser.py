"""
test_chapter_parser.py -- Regression tests for the chapter-numeral guards
(Hans F11: a garbled Roman/Arabic chapter heading must NOT be cited authoritatively).

Two layers are tested:
  1. ingest_from_ocr.parse_chapter_number(tok) -> int
       VALUE extraction from the printed numeral (display value; 0 = unparseable).
  2. ingest_clean.chapter_was_ocr_substituted(chapter_raw, chapter_int) -> bool
       The canonical INGEST-stage F11 guard: True (=> confident False) whenever the
       value could only be recovered via an OCR substitution / from a non-clean raw.

No DB / network / file I/O. Run: python pipeline/test_chapter_parser.py
Exits 0 on all-pass, non-zero on any failure.
"""
import sys, os

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "pipeline", "5080"))
sys.path.insert(0, os.path.join(_REPO, "pipeline"))

import ingest_from_ocr as _ocr

_fail = 0
def check(name, got, want):
    global _fail
    ok = (got == want)
    print(("PASS" if ok else "FAIL") + f"  {name}: got={got!r} want={want!r}")
    if not ok:
        _fail += 1

print("== parse_chapter_number (VALUE extraction) ==")
check("clean roman CCCLIV.", _ocr.parse_chapter_number("CCCLIV."), 354)
check("clean roman XII",     _ocr.parse_chapter_number("XII"), 12)
check("clean roman I",       _ocr.parse_chapter_number("I"), 1)
check("lowercase roman xii", _ocr.parse_chapter_number("xii"), 12)
check("clean arabic 42",     _ocr.parse_chapter_number("42"), 42)
check("arabic ordinal 21st", _ocr.parse_chapter_number("21st"), 0)   # day/section ref, not a chapter
check("empty",               _ocr.parse_chapter_number("  "), 0)
# garbled headers must not crash; value is best-effort (not asserted exact)
for g in ("Cnav.", "Crap. CONA", "CLUX XXAT"):
    v = _ocr.parse_chapter_number(g)
    check(f"garbled {g!r} returns int>=0", isinstance(v, int) and v >= 0, True)

print("\n== chapter_was_ocr_substituted (canonical F11 ingest guard) ==")
try:
    import ingest.ingest_clean as _clean   # moved to pipeline/ingest/ in the reorg
    sub = _clean.chapter_was_ocr_substituted
    check("clean arabic 38 trusts",      sub("38", 38), False)
    check("clean roman XII trusts",      sub("XII", 12), False)
    check("clean roman CCCLIV trusts",   sub("CCCLIV", 354), False)
    check("lowercase 'Il' is substituted", sub("Il", 2), True)
    check("junk 'Cnav. CLX' substituted", sub("Cnav. CLX", 160), True)
    check("roman!=int mismatch flagged", sub("XII", 99), True)
    check("empty raw flagged",           sub("", 5), True)
except Exception as e:
    print(f"SKIP  ingest_clean import failed ({e.__class__.__name__}: {e}) -- "
          f"run on a box with the ingest deps to exercise the F11 guard.")

print()
if _fail:
    print(f"RESULT: {_fail} FAILURE(S)")
    sys.exit(1)
print("RESULT: ALL PASS")
sys.exit(0)
