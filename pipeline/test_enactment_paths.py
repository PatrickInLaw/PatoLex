"""cc019 DEFECT 1 regression tests -- acts that became law WITHOUT the
Governor's signature.

Fixtures are transcribed from the ACTUAL printed volumes (verified visually
during the cc019 contents-anchored recovery; see
docs/80_PROJECT_HISTORY/RESIDUAL_71_CONTENTS_RECOVERY_2026-07-24.md), NOT
invented strings. That matters: the wording of the lapse notice is not stable
across volumes, and a test built from one made-up phrasing would have passed
while the real corpus kept failing.

Run:  python test_enactment_paths.py
"""
import os
import sys
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_ING = os.path.join(_HERE, "ingest", "ingest_from_ocr.py")

_spec = importlib.util.spec_from_file_location("ingest_from_ocr", _ING)
_ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ing)

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


# ---------------------------------------------------------------------------
# Real body text: 1866 ch.143 (printed p.126). Became law unsigned.
# No "[Approved ...]" bracket anywhere in this act.
# ---------------------------------------------------------------------------
BODY_1866_CH143 = """
CHAP. CXLIII.--An Act for the relief of J. B. Cook, County Treasurer of Lake County.

The People of the State of California, represented in Senate and Assembly, do enact as follows:

SECTION 1. J. B. Cook, the County Treasurer of Lake County, and the sureties on his
official bond, shall be released from the payment of the sum of eighteen hundred and
thirty-eight dollars, stolen from the said J. B. Cook as Treasurer of Lake County, on the
night of the twenty-fourth day of October, eighteen hundred and sixty-five.

SEC. 3. This Act shall take effect from and after its passage.

JOHN YULE,
Speaker of the Assembly.
S. P. WRIGHT,
President of the Senate pro tem.

This bill having remained with the Governor ten days, (Sundays excepted,) and the
Senate and Assembly being in session, it has become a law this twenty-seventh day of
February, A. D. eighteen hundred and sixty-six.
"""

# ---------------------------------------------------------------------------
# Real contents-table text: three DIFFERENT printed phrasings for the same
# constitutional path. This is the whole point of the fix.
# ---------------------------------------------------------------------------
CONTENTS_1866_CH143 = ("An Act for the relief of J. B. Cook, County Treasurer of Lake "
                       "County--became law by the operation of Constitution, February 27, 1866")
CONTENTS_1866_CH198 = ("An Act to authorize the executors of Joseph L. Folsom, deceased, to "
                       "sell real estate of their testator at private sale without notice--"
                       "became law by operation of the Constitution, March 8, 1866")
CONTENTS_1870_CH431 = ("An Act granting certain privileges to the Central Railroad Company of "
                       "San Francisco--became a law by constitutional provision April 3, 1870")

# Path 3 -- veto override, constitutionally distinct from a lapse.
CONTENTS_1870_CH143 = ("An Act to provide and pay for services rendered for the City and County "
                       "of San Francisco--became a law by a constitutional majority of both "
                       "Houses, over the Governor's objections, March 4, 1870")

# Control: an ordinary signed act (1876 ch.91, printed p.60).
CONTENTS_1876_CH91 = ("An Act to provide for the funding of the levee indebtedness of the City "
                      "of Marysville--approved February 18, 1876")


print("\n=== spelled_ordinal_to_int ===\n")
check("'twenty-seventh' -> 27", _ing.spelled_ordinal_to_int("twenty-seventh"), 27)
check("'first' -> 1", _ing.spelled_ordinal_to_int("first"), 1)
check("'thirtieth' -> 30", _ing.spelled_ordinal_to_int("thirtieth"), 30)
check("'thirty-first' -> 31", _ing.spelled_ordinal_to_int("thirty-first"), 31)
check("space variant 'twenty seventh' -> 27", _ing.spelled_ordinal_to_int("twenty seventh"), 27)
check("garbage -> None", _ing.spelled_ordinal_to_int("bananas"), None)

print("\n=== spelled_year_to_int ===\n")
check("'eighteen hundred and sixty-six' -> 1866",
      _ing.spelled_year_to_int("eighteen hundred and sixty-six"), 1866)
check("'one thousand eight hundred and seventy' -> 1870",
      _ing.spelled_year_to_int("one thousand eight hundred and seventy"), 1870)
check("'eighteen hundred and seventy-eight' -> 1878",
      _ing.spelled_year_to_int("eighteen hundred and seventy-eight"), 1878)
check("out-of-range -> None", _ing.spelled_year_to_int("three"), None)
check("garbage -> None", _ing.spelled_year_to_int("bananas hundred"), None)

print("\n=== parse_lapse_date -- REAL body text, spelled-out date ===\n")
iso, raw = _ing.parse_lapse_date(BODY_1866_CH143)
check("1866 ch.143 body -> 1866-02-27", iso, "1866-02-27")

print("\n=== parse_lapse_date -- REAL contents rows, three phrasings ===\n")
check("'by the operation of Constitution'",
      _ing.parse_lapse_date(CONTENTS_1866_CH143)[0], "1866-02-27")
check("'by operation of the Constitution'",
      _ing.parse_lapse_date(CONTENTS_1866_CH198)[0], "1866-03-08")
check("'by constitutional provision'",
      _ing.parse_lapse_date(CONTENTS_1870_CH431)[0], "1870-04-03")
check("veto override phrasing still yields a date",
      _ing.parse_lapse_date(CONTENTS_1870_CH143)[0], "1870-03-04")

print("\n=== detect_enactment_path ===\n")
check("signed act -> approved",
      _ing.detect_enactment_path(CONTENTS_1876_CH91), _ing.ENACTMENT_PATH_APPROVED)
check("1866 ch.143 body -> unsigned_lapse",
      _ing.detect_enactment_path(BODY_1866_CH143), _ing.ENACTMENT_PATH_UNSIGNED)
check("1870 ch.431 -> unsigned_lapse",
      _ing.detect_enactment_path(CONTENTS_1870_CH431), _ing.ENACTMENT_PATH_UNSIGNED)
check("1870 ch.143 -> veto_override (NOT collapsed into unsigned)",
      _ing.detect_enactment_path(CONTENTS_1870_CH143), _ing.ENACTMENT_PATH_VETO_OVERRIDE)

print("\n=== parse_act_date -- the integration that was broken ===\n")
# THE core regression: before cc019 this returned (None, "") and the act was
# demoted to flagged_acts despite a perfectly legible page.
check("1866 ch.143 body now dates via parse_act_date",
      _ing.parse_act_date(BODY_1866_CH143, volume_year=1866)[0], "1866-02-27")
check("year clamp still applies to lapse dates (1866 act vs volume_year=1900)",
      _ing.parse_act_date(BODY_1866_CH143, volume_year=1900)[0], None)

print("\n=== parse_act_date -- signed acts UNCHANGED (no regression) ===\n")
check("ordinary [Approved ...] still parses",
      _ing.parse_act_date("[Approved February 18, 1876.]", volume_year=1876)[0], "1876-02-18")
check("no date at all still returns None",
      _ing.parse_act_date("SEC. 2. This Act shall take effect immediately.",
                          volume_year=1876)[0], None)

print("\n=== is_confident_act ===\n")
check("1866 ch.143 is now a confident act",
      _ing.is_confident_act(BODY_1866_CH143, volume_year=1866), True)

# FINDING D -- heading that never says "An Act", but has an enacting clause.
NON_AN_ACT = """
[An amendment to the Code, but which also repeals the Act of March twenty-eighth,
eighteen hundred and seventy-four, in relation to solvent debts.]

The People of the State of California, represented in Senate and Assembly, do enact as follows:

SECTION 1. Section three thousand six hundred and twenty-seven of the Political Code
is hereby amended to read as follows, and the provisions herein shall apply to all
solvent debts owing to any person within this State.

[Approved April 3, 1876.]
"""
check("1876 ch.508-style heading (no 'An Act') is confident via enacting clause",
      _ing.is_confident_act(NON_AN_ACT, volume_year=1876), True)

check("random prose is NOT a confident act",
      _ing.is_confident_act("The quick brown fox jumped over the lazy dog. " * 5,
                            volume_year=1876), False)

print("\n" + "=" * 60)
print("Results: %d passed, %d failed" % (PASS, FAIL))
print("=" * 60)
sys.exit(1 if FAIL else 0)
