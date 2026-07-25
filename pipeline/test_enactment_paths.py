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


# ===========================================================================
# REGRESSION FIXES from the corpus reparse diff (2026-07-25). The diff found
# 31 chapters the NEW parser lost. 10 were genuine regressions caused by MY
# changes. Fixtures are the REAL OCR text from those acts.
# ===========================================================================

print("\n=== REG-1: ENACT_MARKER_RE must tolerate 1862-63 OCR ===\n")
# flush_act does `if not has_enact_marker(full): return` -- a SILENT DROP, no
# record at all. The strict pattern lost 7 real statutes once correct
# segmentation stopped them borrowing a neighbour's legible clause.
# Verbatim from production-1862 ch.63:
MANGLED_CLAUSE = ("The People of the State af Culffornin, represented in Senate cel "
                  "assembly, do enact ax folloves:")
check("mangled 1862 enacting clause is recognised",
      _ing.has_enact_marker(MANGLED_CLAUSE), True)
for variant in [
    "The People of the State of California, represented in Senate and Assembly, do enact as follows:",
    "the people of the state af Calfornia, represented in senate and assembly",
    "do enaet az follows",
    "do enact ax folloves",
]:
    check("clause variant recognised: %r" % variant[:44],
          _ing.has_enact_marker(variant), True)
# ...but it must not fire on ordinary prose.
for prose in [
    "The people of this county have long desired a wagon road to the valley.",
    "and the State of Nevada shall be reimbursed for all such expenses incurred",
    "This Act shall take effect immediately.",
]:
    check("prose NOT treated as an enacting clause: %r" % prose[:40],
          _ing.has_enact_marker(prose), False)

print("\n=== REG-2: resolution guard v3 -- opening line, not offsets ===\n")
# v2 anchored on the enacting clause. ENACT_MARKER_RE never matches 20th-century
# volumes, so the guard degenerated to "any resolution phrase -> reject" and
# killed three real acts. These are the real openings.
REAL_ACT_NAMING_A_RESOLUTION = (
    "CHAPTER 118. An Act making an appropriation to pay for the expenses incurred by "
    "Assembly Concurrent Resolution No. 6, appointing a joint committee to investigate "
    "the state printing office.\n[Approved March 20, 1897.]\n"
    "The People of the State of California, represented in Senate and Assembly, "
    "do enact as follows:\nSECTION 1. There is hereby appropriated the sum of "
    "two thousand dollars out of any money in the State Treasury not otherwise "
    "appropriated, for the purposes named in said resolution."
)
check("1897 ch.118 (act NAMING a resolution) is confident",
      _ing.is_confident_act(REAL_ACT_NAMING_A_RESOLUTION, volume_year=1897), True)

MODERN_ACT_BLEEDING_INTO_RESOLUTIONS = (
    "CHAPTER 933. An act to repeal Chapter 11, comprising sections 4800 to 4897, "
    "inclusive, of the Business and Professions Code, relating to the practice of "
    "chiropractic.\n[Approved by the Governor July 1, 1937.]\n"
    "SECTION 1. Chapter 11 of Division 2 of the Business and Professions Code is "
    "hereby repealed and all proceedings pending thereunder shall abate.\n"
    "CONCURRENT AND JOINT RESOLUTIONS\n"
    "Assembly Concurrent Resolution No. 1--Relative to adjournment."
)
check("1937 ch.933 (modern act, resolutions header bleeds in) is confident",
      _ing.is_confident_act(MODERN_ACT_BLEEDING_INTO_RESOLUTIONS, volume_year=1937), True)

GENUINE_MODERN_RESOLUTION = (
    "CHAPTER 55. Senate Concurrent Resolution No. 6--Relative to the adjournment of "
    "the Legislature sine die.\n[Filed with Secretary of State April 2, 1917.]\n"
    "WHEREAS, The business of the present session has been concluded; now, therefore, "
    "be it Resolved by the Senate, the Assembly concurring, That the Legislature "
    "adjourn sine die on the fifteenth day of April."
)
check("genuine modern resolution IS rejected",
      _ing.is_confident_act(GENUINE_MODERN_RESOLUTION, volume_year=1917), False)

# The 19th-century resolution (quotes an act title) must still be rejected.
check("1865-66 ch.500 genuine resolution still rejected",
      _ing.is_confident_act(CH500, volume_year=1866), False)
# ...and the 1872 bleed-through act still kept.
check("1871-72 ch.637 still kept", _ing.is_confident_act(CH637, volume_year=1872), True)

print("\n=== REG-2b: opening_line() strips the chapter heading ===\n")
check("strips 'CHAPTER 933.'",
      _ing.opening_line("CHAPTER 933. An act to repeal Chapter 11").startswith("An act"), True)
check("strips 'CHAP. CXLIII.--'",
      _ing.opening_line("CHAP. CXLIII.--An Act for the relief of J. B. Cook").startswith("An Act"), True)
check("heading-only first line falls through to the next",
      _ing.opening_line("CHAPTER 55.\nSenate Concurrent Resolution No. 6").startswith("Senate"), True)
check("empty input -> empty string", _ing.opening_line(""), "")


# ===========================================================================
# VERIFICATION-RUN FIXES (2026-07-25). The re-run diff confirmed fixes 1 and 4,
# but found veto_override still 0 corpus-wide and one new resolution leak.
# ===========================================================================

print("\n=== VER-1: veto_override must fire on the BODY form ===\n")
# The corpus body NEVER says "became a law" for a veto override -- only the
# CONTENTS table does, and the parser reads bodies. Verbatim corpus wording:
VETO_BODY_FORM = ("Passed the Assembly notwithstanding the veto of the Governor, by the "
                  "requisite Constitutional majority, January 31, 1855.")
check("body-form veto override detected",
      _ing.detect_enactment_path(VETO_BODY_FORM), _ing.ENACTMENT_PATH_VETO_OVERRIDE)
check("VETO_OVERRIDE_RE matches 'notwithstanding the veto of the Governor'",
      bool(_ing.VETO_OVERRIDE_RE.search(VETO_BODY_FORM)), True)
# The contents form must still work.
check("contents-form veto override still detected",
      _ing.detect_enactment_path(CONTENTS_1870_CH143), _ing.ENACTMENT_PATH_VETO_OVERRIDE)
# ...and a plain lapse must NOT be mislabelled as a veto override.
check("plain lapse is still unsigned_lapse, not veto",
      _ing.detect_enactment_path(CONTENTS_1870_CH431), _ing.ENACTMENT_PATH_UNSIGNED)
check("ordinary signed act unaffected",
      _ing.detect_enactment_path(CONTENTS_1876_CH91), _ing.ENACTMENT_PATH_APPROVED)

print("\n=== VER-2: garbled WHEREAS preamble is a resolution ===\n")
# 1917 ch.55 -- a genuine "Senate Concurrent Resolution No. 24" that LEAKED
# THROUGH as a confident act because its first content line OCR'd as
# "Wuenrrss, By an act entitled...".
CH55_1917 = (
    "CHAPTER 55.\n"
    "Wuenrrss, By an act entitled an act granting certain tidelands to the city "
    "of San Diego, approved May 1, 1911, certain lands were granted; and\n"
    "Wuenrrss, It is desirable that the terms of said grant be clarified; now, "
    "therefore, be it\n"
    "Resolved by the Senate, the Assembly concurring, That the Legislature "
    "hereby requests the Attorney General to institute proceedings.\n"
    "[Filed with Secretary of State April 2, 1917.]"
)
check("garbled-WHEREAS resolution IS rejected",
      _ing.is_confident_act(CH55_1917, volume_year=1917), False)
check("RESOLUTION_HEAD_RE matches the garbled WHEREAS line",
      bool(_ing.RESOLUTION_HEAD_RE.search("Wuenrrss, By an act entitled an act granting")), True)
check("clean WHEREAS also matches",
      bool(_ing.RESOLUTION_HEAD_RE.search("WHEREAS, By an act entitled")), True)

# ...but the WHEREAS arm must NOT fire on act titles or ordinary prose.
for not_res in [
    "An act to provide for the funding of the levee indebtedness of the City of Marysville.",
    "Witnesses, being duly sworn, shall be examined in open court.",
    "The People of the State of California, represented in Senate and Assembly",
    "Whenever the Board of Supervisors shall determine that a road is necessary",
]:
    check("WHEREAS arm does NOT fire on %r" % not_res[:38],
          bool(_ing.RESOLUTION_HEAD_RE.search(not_res)), False)

# And the three real acts recovered by fix 2 must STILL be confident.
check("1897 ch.118 still confident",
      _ing.is_confident_act(REAL_ACT_NAMING_A_RESOLUTION, volume_year=1897), True)
check("1937 ch.933 still confident",
      _ing.is_confident_act(MODERN_ACT_BLEEDING_INTO_RESOLUTIONS, volume_year=1937), True)
check("1871-72 ch.637 still confident",
      _ing.is_confident_act(CH637, volume_year=1872), True)


# ===========================================================================
# cc021 APPROVAL CONNECTOR (2026-07-25). Measured across all 208 volumes:
# the dominant flagged_acts cause was NOT a mangled keyword (60-77 acts) but
# STRICT ADJACENCY between an intact keyword and an intact date -- with a
# garbled "by Governor" sitting in the gap. Every fixture below is a real
# corpus form from that measurement.
# ===========================================================================

print("\n=== KW-1: garbled 'by Governor' connector (the 1,364-act fix) ===\n")
_CONNECTOR_FORMS = [
    ("Approved by Governor March 4, 1889.", "1889-03-04"),
    ("Approved hy Governor March 4, 1889.", "1889-03-04"),
    ("Approved bv Governor March 4, 1889.", "1889-03-04"),
    ("Approved by the Governor March 4, 1889.", "1889-03-04"),
    ("Approved by Guvernor March 4, 1889.", "1889-03-04"),
    ("Approved by Covernor March 4, 1889.", "1889-03-04"),
    ("Approved bs Governor March 4, 1889.", "1889-03-04"),
    ("Approved by Governo: March 4, 1889.", "1889-03-04"),
    ("Filed with Secretary of State March 4, 1889.", "1889-03-04"),
]
for text, want in _CONNECTOR_FORMS:
    check("connector %r" % text[:38], _ing.parse_act_date(text, volume_year=1889)[0], want)

print("\n=== KW-2: K2 keyword garbles ===\n")
for text, want in [
    ("Pussed March 20, 1850.", "1850-03-20"),
    ("Paseed March 27, 1850.", "1850-03-27"),
    ("Arprovep March 30, 1852.", "1852-03-30"),
    ("Approven, May 4, 1852.", "1852-05-04"),
]:
    check("keyword %r" % text[:26], _ing.parse_act_date(text, volume_year=int(want[:4]))[0], want)

print("\n=== KW-3: the connector must NOT become a blanket gap ===\n")
# KNOWN PRE-EXISTING LIMITATION, documented not asserted away.
# A cross-reference date inside an amending clause ("...to amend an Act approved
# April 30th, 1855...") is ADJACENT to the keyword, so the baseline parser
# already matched it and returned the FIRST in-window hit. The connector does not
# cause this and does not fix it. An earlier draft of this test asserted the
# corrected answer -- i.e. claimed a fix that was never made. Recording the real
# behaviour instead.
#
# This IS the 22-FP class the measurement found for the rejected blanket-gap
# option; it exists at baseline too, at lower volume. Fixing it needs
# approval-line POSITION logic, not keyword tolerance. Not attempted here.
CROSSREF = ("An Act to amend an Act approved April 30th, 1855, relating to the "
            "office of County Surveyor. Approved March 12, 1856.")
check("cross-reference date wins (PRE-EXISTING, not caused by the connector)",
      _ing.parse_act_date(CROSSREF, volume_year=1856)[0], "1855-04-30")

# Arbitrary prose between keyword and month must NOT bridge.
for text in [
    "Approved in principle by the committee on ways and means March 4, 1889.",
    "Approved for publication in the several newspapers of March 4, 1889.",
]:
    check("non-Governor prose does NOT bridge: %r" % text[:40],
          _ing.parse_act_date(text, volume_year=1889)[0], None)

print("\n=== KW-4: existing behaviour unchanged ===\n")
check("plain adjacent approval still parses",
      _ing.parse_act_date("[Approved February 18, 1876.]", volume_year=1876)[0], "1876-02-18")
check("modern 'Approved by Governor' still parses",
      _ing.parse_act_date("Approved by Governor February 28, 2008.", volume_year=2008)[0],
      "2008-02-28")
check("bare ordinal day still parses",
      _ing.parse_act_date("Approved March 2d, 1880.", volume_year=1880)[0], "1880-03-02")
check("no date still returns None",
      _ing.parse_act_date("SEC. 2. This Act shall take effect immediately.",
                          volume_year=1876)[0], None)
check("year clamp still rejects out-of-window",
      _ing.parse_act_date("Approved by Governor March 4, 1889.", volume_year=1950)[0], None)


print("\n=== REG-3: 1862 ch.10 -- the ONE true regression of the 17 ===\n")
# My first ENACT_MARKER_RE loosening was ASYMMETRIC: it tolerated rot in the
# SECOND "of" but left the FIRST literal. 1862 ch.10's clause is hit in both
# places, so both arms failed and flush_act DROPPED THE ACT ENTIRELY -- no
# record, not even flagged, so it never reached the review worklist. Verbatim:
CH10_1862_CLAUSE = ("The Prople af the State of California, represented in Senaie and "
                    "Assembly, du enact an fellows:")
check("1862 ch.10 clause now recognised", _ing.has_enact_marker(CH10_1862_CLAUSE), True)
# Co-resident ch.11 -- rot in BOTH "of" slots.
check("1862 ch.11 clause ('People af the State af California') recognised",
      _ing.has_enact_marker("The People af the State af California, represented in Senate"),
      True)
# Other real follow-word garbles from the same volumes.
for v in ["du enact an fellows", "do enact as filloes", "do enact ax folluics"]:
    check("follow-word garble %r" % v, _ing.has_enact_marker(v), True)

# The full act must now be confident -- its own [Approved] parses cleanly.
CH10_1862 = (
    "Crap. X.--An Act amendutory of and supplemental to an Act entitled an Act to "
    "grant the right to construct a Turnpike Road between the Town of Jackson and "
    "Ione City, in the County of Amador.\n"
    "[Approved February 11, 1862.]\n"
    + CH10_1862_CLAUSE + "\n"
    "SECTION 1. The rights and privileges granted by the Act to which this is "
    "amendatory are hereby extended for the term of five years from the passage hereof."
)
check("1862 ch.10 is a confident act again",
      _ing.is_confident_act(CH10_1862, volume_year=1862), True)

# Guard: the widened clause must still not fire on ordinary prose.
for prose in [
    "The people af this county have long desired a road to the valley.",
    "and the State of Nevada shall be reimbursed for all expenses",
    "due enactment of the foregoing shall follow the usual course",
]:
    check("prose still NOT an enacting clause: %r" % prose[:38],
          _ing.has_enact_marker(prose), False)


print("\n=== NUM-1: implausible chapter numbers are rejected, not ingested ===\n")
# MEASURED: 355 confident acts carried out-of-range ARABIC chapters because the
# arabic path had NO validation -- int(t) accepted anything. 611 of the 992
# duplicate chapter keys are on this path.
for tok, want in [("90956", 0), ("14383", 0), ("6548", 0), ("5001", 0)]:
    check("implausible arabic %r -> 0 (routes to flagged)" % tok,
          _ing.parse_chapter_number(tok), want)
for tok, want in [("1", 1), ("88", 88), ("1527", 1527), ("5000", 5000)]:
    check("plausible arabic %r kept" % tok, _ing.parse_chapter_number(tok), want)

print("\n=== NUM-2: the ADDITIVE 400s must survive ===\n")
# 19th-c California printed the 400s ADDITIVELY. Strict canonical Roman would
# reject 396 CORRECT chapters to fix 122 duplicate keys -- measured, and refused.
for tok, want in [("CCCCV", 405), ("CCCCXXI", 421), ("CCCCXCI", 491),
                  ("CCCCXL", 440), ("DCCCC", 900)]:
    check("additive Roman %r -> %d" % (tok, want), _ing.parse_chapter_number(tok), want)
# ...and ordinary Roman still works.
for tok, want in [("CXLIII", 143), ("XCI", 91), ("CLXXIII", 173), ("MCXXVII", 1127)]:
    check("Roman %r -> %d" % (tok, want), _ing.parse_chapter_number(tok), want)

print("\n=== NUM-3: numeral_is_plausible() reports WITHOUT correcting ===\n")
check("in-range value ok", _ing.numeral_is_plausible(143)[0], True)
check("out-of-range flagged", _ing.numeral_is_plausible(90956), (False, "out_of_range"))
check("zero flagged", _ing.numeral_is_plausible(0), (False, "unparseable"))
check("negative flagged", _ing.numeral_is_plausible(-3), (False, "unparseable"))
# The RELAXED ADDITIVE validator accepts the real corpus forms and rejects only
# structurally impossible ones (9 corpus-wide, all genuine garbage).
for good in ["CCCCV", "CXLIII", "XCI", "MCXXVII", "CCCCXCI"]:
    check("additive validator accepts %r" % good,
          _ing.numeral_is_plausible(1, roman_norm=good)[0], True)
for bad in ["CCLIXVII", "XLX", "DLIIX", "DCDXX", "CCCXXIIV"]:
    check("additive validator rejects %r" % bad,
          _ing.numeral_is_plausible(1, roman_norm=bad), (False, "non_additive_roman"))

print("\n" + "=" * 60)
print("Results: %d passed, %d failed" % (PASS, FAIL))
print("=" * 60)
sys.exit(1 if FAIL else 0)
