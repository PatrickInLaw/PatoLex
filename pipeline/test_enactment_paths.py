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


# ===========================================================================
# CORPUS-MEASURED REGRESSIONS (2026-07-25). Every fixture below is a REAL line
# or act taken from the 1.73M-line corpus scan. Several of these REFUTED an
# earlier "fix" of mine -- keep them.
# ===========================================================================

print("\n=== CORPUS-1: comma separator -- 116 genuine early headings ===\n")
# Removing the comma (round 2) lost these. The printed period was routinely
# OCR'd as a comma in the 1860s-70s. All verbatim from the corpus scan.
REAL_COMMA_HEADINGS = [
    ("Cuap., XXII.—An Act concerning the County Clerk of Del Norte", "XXII"),
    ("Cuap, XLVI.—An Act to legalize the Assessment of Taxes in the", "XLVI"),
    ("CHAP, CXXXVIIL—An Act relative to the assessment in Swamp", "CXXXVIIL"),
    ("Cuap, LIX.—An Act to authorize the Board of State Harbor :", "LIX"),
]
for line, want in REAL_COMMA_HEADINGS:
    m = _ing.HEADER_RE.match(line)
    check("comma heading %r -> %s" % (line[:34], want),
          m.group(1) if m else None, want)

print("\n=== CORPUS-2: ...but comma must NOT admit index lines ===\n")
# All 9 measured false positives. Every one has an ARABIC numeral -- that is the
# discriminator against the Roman-numeral real headings above.
REAL_INDEX_FPS = [
    "crabs, 874", "charges, 1192", "change, 131", "copies, 395",
    "card, 828", "covers, 787", "charges, 1005", "CHAPTER, 1302",
]
for line in REAL_INDEX_FPS:
    check("index line %r blocked" % line, bool(_ing.HEADER_RE.match(line)), False)

print("\n=== CORPUS-3: the 2 real em-dash headings (the whole em-dash gain) ===\n")
# At corpus scale the em-dash form is a TWO-INSTANCE outlier, not an era
# convention. Both verbatim from the scan.
for line, want in [
    ("CHap.—XCI.—An Act to provide for the funding of the levee", "XCI"),
    ("Cuap.—CLXXII—An Act to provide fer the building of a", "CLXXII"),
]:
    m = _ing.HEADER_RE.match(line)
    check("em-dash heading %r -> %s" % (line[:30], want),
          m.group(1) if m else None, want)

print("\n=== CORPUS-4: the ACTUAL poisoning artifact (p.25, not p.24) ===\n")
# Verbatim shape from production-1865-66 page 25.
REAL_POISON = ("379 | Au Act for relief of Pliny M. Whitney, late Collector of Fishing "
               "Licenses—became a law by operation of the Constitution, 380 | An Act to "
               "transfer certain fands—approved March 30, 1866…… | S.B. 812")
check("real p.25 artifact yields NO lapse date",
      _ing.parse_lapse_date(REAL_POISON)[0], None)

print("\n=== CORPUS-5: digit-bearing qualifier is LEGITIMATE (refuted my ban) ===\n")
# 1875-76 ch.250 -- real, correctly printed, carries BOTH a digit and a period.
# The digit ban silently dropped it.
CH250 = ("[Became a law by virtue of Section 17, Article 1V. of the Constitution, "
         "March 18, 1876.)")
check("1875-76 ch.250 dates correctly", _ing.parse_lapse_date(CH250)[0], "1876-03-18")

print("\n=== CORPUS-6: terminator + OCR-noise recall misses ===\n")
# 1865-66 ch.322 -- lapse notice terminated by a COMMA.
CH322 = ("it has become a law this twenty-third day of March, A. D. eighteen "
         "hundred and sixty-six,")
check("comma-terminated lapse notice dates", _ing.parse_lapse_date(CH322)[0], "1866-03-23")
# 1865-66 ch.650 -- asterisk inside the spelled year.
CH650 = ("it has become a law this tenth day of April, A. D. eighteen*hundred "
         "and sixty-six.")
check("asterisk in spelled year dates", _ing.parse_lapse_date(CH650)[0], "1866-04-10")

print("\n=== CORPUS-7: resolution bleed-through must NOT reject a real act ===\n")
# production-1871-72 ch.637 -- a GENUINE act; the volume's last chapter, whose
# buffer bleeds into the following resolutions section header.
CH637 = ("CHAPTER DCXXXVII. An Act to protect the wages of labor and the salaries "
         "and fees of subordinate officers. [Approved April 1, 1872.] The People of "
         "the State of California, represented in Senate and Assembly, do enact as "
         "follows: Section 1. Every person who employs laborers upon the public works "
         "of this State, and who fails to pay them, is guilty of a felony and shall be "
         "punished accordingly under the provisions of this Act. "
         "T r T bd 4 Th? CONCURRENT AND JOINT RESOLUTIONS. "
         "Nusmnun [.—Senate Concurrent Resolution. {Adopted March 14, 1872")
check("1871-72 ch.637 IS a confident act (resolution header bleeds in AFTER)",
      _ing.is_confident_act(CH637, volume_year=1872), True)

# ...but a genuine resolution, where the marker comes FIRST, is still rejected.
check("genuine concurrent resolution still rejected",
      _ing.is_confident_act(RESOLUTION, volume_year=1878), False)
check("genuine joint resolution still rejected",
      _ing.is_confident_act(JOINT_RES, volume_year=1878), False)


# ===========================================================================
# ROUND-4 corpus regressions (2026-07-25). From the re-measurement of the
# corrected patterns over the same 1,732,428 lines.
# ===========================================================================

print("\n=== R4-1: the 116th comma heading (comma THEN period) ===\n")
m = _ing.HEADER_RE.match("Cuapv,. CXCIII.—[See volume of Amendments to the Codes.]")
check("'Cuapv,. CXCIII.' -> CXCIII", m.group(1) if m else None, "CXCIII")
# ...and the index lines must STILL be blocked with the widened comma class.
for line in REAL_INDEX_FPS:
    check("index line %r still blocked" % line, bool(_ing.HEADER_RE.match(line)), False)

print("\n=== R4-2: MODERN unsigned-lapse form (40 real matches, R2 found 0) ===\n")
# The 20th-century notice carries BOTH a period and digits inside the qualifier.
# The digit/period ban suppressed this form entirely.
MODERN_LAPSE = ("[Became law without Governor's signature. Filed with Secretary of "
                "State October 1, 1982.] The people of the State of California do "
                "enact as follows: SECTION 1.")
check("1982 modern lapse notice dates", _ing.parse_lapse_date(MODERN_LAPSE)[0], "1982-10-01")
MODERN_1994 = ("CHAPTER 1297 An act to amend Section 21401 of the Vehicle Code. "
               "[Became law without Governor's signature. Filed with Secretary of "
               "State October 4, 1994.]")
check("1994 modern lapse notice dates", _ing.parse_lapse_date(MODERN_1994)[0], "1994-10-04")
# OCR noise seen in the corpus: day read as 'i', period instead of comma.
check("OCR 'October i, 1982' -> day 1",
      _ing.parse_lapse_date("[Became law without Governor's signature. Filed with "
                            "Secretary of State October i, 1982.]")[0], "1982-10-01")

print("\n=== R4-3: digest sentence is NOT an enactment ===\n")
DIGEST = ("this bill would provide that it shall only become operative if both this "
          "bill and SB 765 are enacted and become law effective on or before "
          "January 1, 2000. Ch. 923 (AB 1571)")
check("conditional 'become law effective ...' rejected",
      _ing.parse_lapse_date(DIGEST)[0], None)

print("\n=== R4-4: resolution guard must NOT be inert ===\n")
# 1865-66 ch.500 -- a GENUINE resolution that QUOTES a bill title, so AN_ACT_RE
# fires BEFORE the resolution marker. Using "An Act" as act-evidence made the
# guard reject nothing at all across 3,091 buffers. Only the enacting clause is
# exclusive to an act.
CH500 = ("charged- Insane Asylum be and he is hereby discharged. [Adopted March 17, "
         "1866.) Resolved, By the Senate, the Assembly concurring, that the "
         "Governor be and is hereby requested to return Senate Bill Number Three "
         "Hundred and Thirteen, (318,) entitled an Act to amend an Act to provide "
         "for the establishment and maintenance of public and private roads, "
         "approved May sixteenth, eighteen hundred and sixty-one, to the Senate.")
check("genuine resolution quoting an act title IS rejected",
      _ing.is_confident_act(CH500, volume_year=1866), False)
check("real act with resolution header bleeding in AFTER is still kept",
      _ing.is_confident_act(CH637, volume_year=1872), True)
check("RESOLUTION_RE matches 'Resolved, By the Senate' (comma form)",
      bool(_ing.RESOLUTION_RE.search("Resolved, By the Senate, the Assembly concurring")), True)


# ===========================================================================
# ★ WIRING TEST (2026-07-25). The unit tests above all passed while
# detect_enactment_path() was called BY NOTHING BUT THEM. A corpus-wide diff
# reported the enactment-path distribution as 100% "approved" across 70,230
# acts -- because flush_act() never wrote the field onto the act record.
#
# A tested function that nothing calls is not a feature. These tests assert the
# RECORD, not the function.
# ===========================================================================

print("\n=== WIRING: the act RECORD must carry enactment_path ===\n")


def _flush(text, volume_year, chap="CXLIII"):
    """Run the real flush_act and return the single record it produced."""
    parsed, flagged = [], []
    _ing.flush_act(
        chap, 0, text.split("\n"), parsed, flagged, {},
        volume_year=volume_year, session_label="test", in_act_order=0,
    )
    recs = parsed + flagged
    return recs[0] if recs else None


rec = _flush(BODY_1866_CH143, 1866)
check("flush_act produced a record", rec is not None, True)
if rec:
    check("record HAS an enactment_path key", "enactment_path" in rec, True)
    check("1866 ch.143 record path == unsigned_lapse",
          rec.get("enactment_path"), _ing.ENACTMENT_PATH_UNSIGNED)
    check("record still dates correctly", rec.get("iso_date"), "1866-02-27")

SIGNED_BODY = """
CHAP. XCI.--An Act to provide for the funding of the levee indebtedness of the City of Marysville.

[Approved February 18, 1876.]

The People of the State of California, represented in Senate and Assembly, do enact as follows:

SECTION 1. The Funding Commissioners of the City of Marysville are hereby authorized and
empowered to fund the indebtedness represented by the warrants outstanding against the Levee
Fund of said city on the first day of April, eighteen hundred and seventy-six.
"""
rec2 = _flush(SIGNED_BODY, 1876, chap="XCI")
check("signed act produced a record", rec2 is not None, True)
if rec2:
    check("signed act path == approved",
          rec2.get("enactment_path"), _ing.ENACTMENT_PATH_APPROVED)

VETO_BODY = """
CHAPTER CXLIII.--An Act to provide and pay for services rendered for the City and County of San Francisco.

The People of the State of California, represented in Senate and Assembly, do enact as follows:

SECTION 1. The Auditor of the City and County of San Francisco is hereby authorized and directed
to audit the demands herein named, and the Treasurer shall pay the same out of the General Fund.

This bill, having been returned by the Governor with his objections, became a law by a
constitutional majority of both Houses, over the Governor's objections, March 4, 1870.
"""
rec3 = _flush(VETO_BODY, 1870)
check("veto-override act produced a record", rec3 is not None, True)
if rec3:
    check("veto-override path is NOT collapsed into unsigned",
          rec3.get("enactment_path"), _ing.ENACTMENT_PATH_VETO_OVERRIDE)

print("\n" + "=" * 60)
print("Results: %d passed, %d failed" % (PASS, FAIL))
print("=" * 60)
sys.exit(1 if FAIL else 0)
