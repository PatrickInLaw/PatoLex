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


# ===========================================================================
# HANS FAIL REGRESSIONS (2026-07-25). Every case below is a defect Hans found
# by running the regexes against the REAL corpus, not a hypothetical.
# ===========================================================================

print("\n=== HANS-1: cross-act date poisoning (the severe one) ===\n")
# Reproduces the production-1865-66 p.24 shape: a printed CONTENTS page where
# a lapse row is followed by a page-number column and then ANOTHER act with its
# own approved date. The first draft's `[^.]{0,120}?` gap ran straight through
# and stole the NEXT act's date. Same year, weeks off -- the +/-3yr clamp is blind.
POISON_CONTENTS = (
    "379  An Act concerning the office of Sheriff of Humboldt County--"
    "became a law by constitutional provision, March 4, 1866    S. B. 449   797\n"
    "380  An Act to authorize the Board of Supervisors--approved March 30, 1866"
    "   S. B. 462   799"
)
iso, raw = _ing.parse_lapse_date(POISON_CONTENTS)
check("lapse date is ch.379's own (Mar 4), NOT ch.380's (Mar 30)", iso, "1866-03-04")

# Harder shape: the lapse row has NO date of its own. The parser must return
# nothing rather than reaching forward and stealing the next act's date.
POISON_NO_OWN_DATE = (
    "379  An Act concerning the office of Sheriff of Humboldt County--"
    "became a law by constitutional provision    S. B. 449   797\n"
    "380  An Act to authorize the Board of Supervisors--approved March 30, 1866"
)
check("no own date -> None, does NOT steal the next act's date",
      _ing.parse_lapse_date(POISON_NO_OWN_DATE)[0], None)

# Gap must not cross a chapter heading either.
POISON_CROSS_CHAP = (
    "it has become a law\nCHAP. CCCLXXX.--An Act to do something--"
    "approved March 30, 1866."
)
check("gap does not cross a CHAP heading",
      _ing.parse_lapse_date(POISON_CROSS_CHAP)[0], None)

print("\n=== HANS-2: _HDR_SEP must not match index lines ===\n")
# The comma in the first draft's separator class matched back-of-book index
# entries. 55 confirmed on real modern volumes.
INDEX_LINES = [
    "crabs, 47",
    "charges, 1192",
    "chattels, 88",
    "cities, 1204",
    "children, 813",
    "counties, 47",
]
for line in INDEX_LINES:
    check("index line %r does NOT match HEADER_RE" % line,
          bool(_ing.HEADER_RE.match(line)), False)

# ...while the real printed forms still do.
for line, want in [("CHAP. CXLIII.", "CXLIII"), ("CHAP.—XCI.", "XCI"),
                   ("CHAPTER 88.", "88"), ("CHAP.–CLXXIII.", "CLXXIII")]:
    m = _ing.HEADER_RE.match(line)
    check("real form %r still matches -> %s" % (line, want),
          m.group(1) if m else None, want)

print("\n=== HANS-3: spelled_ordinal_to_int must reject impossible days ===\n")
check("'thirty-first' -> 31 (legal)", _ing.spelled_ordinal_to_int("thirty-first"), 31)
for bad in ["thirty-second", "thirty-fifth", "thirty-ninth"]:
    check("%r -> None (no such day)" % bad, _ing.spelled_ordinal_to_int(bad), None)

print("\n=== HANS-4: resolutions must never be confident acts ===\n")
RESOLUTION = """
CONCURRENT RESOLUTION No. 14.

Resolved by the Assembly, the Senate concurring, That the Legislature of the
State of California hereby memorializes the Congress of the United States to
take such action as may be necessary in the premises, and that copies hereof be
transmitted to our Senators and Representatives.

Adopted March 30, 1878.
"""
check("concurrent resolution is NOT a confident act",
      _ing.is_confident_act(RESOLUTION, volume_year=1878), False)

JOINT_RES = """
JOINT RESOLUTION relative to the improvement of the Sacramento River.

Be it resolved by the Senate and Assembly of the State of California, That the
Congress of the United States be requested to appropriate the sum necessary.

Approved March 30, 1878.
"""
check("joint resolution is NOT a confident act",
      _ing.is_confident_act(JOINT_RES, volume_year=1878), False)

print("\n=== HANS-4b: enacting-clause fallback must be ANCHORED early ===\n")
# A quotation of another act's enacting clause deep inside a long body must not
# qualify a buffer that is not itself an act.
LATE_CLAUSE = ("Whereas the following language appears in a prior statute. " * 60
               + " The People of the State of California, represented in Senate and "
                 "Assembly, do enact as follows: [Approved March 30, 1878.]")
check("enacting clause only deep in body -> NOT confident",
      _ing.is_confident_act(LATE_CLAUSE, volume_year=1878), False)

# The genuine 1876 ch.508 case must still pass (clause is early).
check("1876 ch.508-style STILL confident (clause is early)",
      _ing.is_confident_act(NON_AN_ACT, volume_year=1876), True)

print("\n=== HANS: no catastrophic backtracking on adversarial input ===\n")
import time as _time
_adv = "became a law " + ("x" * 5000) + " January 1, 1866"
_t0 = _time.time()
_ing.parse_lapse_date(_adv)
_elapsed = _time.time() - _t0
check("5k-char adversarial input completes < 1s", _elapsed < 1.0, True)

print("\n" + "=" * 60)
print("Results: %d passed, %d failed" % (PASS, FAIL))
print("=" * 60)
sys.exit(1 if FAIL else 0)
