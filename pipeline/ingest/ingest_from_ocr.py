"""
ingest_from_ocr.py -- Local parse + DB ingest from 5090 OCR outputs.
=====================================================================
Runs on the 5080 box (where Postgres lives). Reads the per-page OCR output
produced by ocr_only_5090.py (synced back into
production-<label>/ocr_consensus/page_ocr_results.json) and performs:

  STAGE5  parse acts  -- the ROUND2 parser, byte-for-byte from reparse.py
                         (garbled-Chap headers, inline em-dash, TOC exclusion).
                         Writes parsed_acts_fixed.json.
  STAGE6  DB ingest    -- faithful copy of production_pipeline.py STAGE6 and
                         re_ingest_fixed.py: update the skeleton source_document
                         (or insert new), then ingest confident acts into
                         enactment / provision / designation_history /
                         change_event. Idempotent (scoped purge per source_doc,
                         then re-insert) -- safe to re-run.

LEGISLATURE_MAP extended to cover 1861-1875-76. No DB access for OCR; this is
the only place rows are written, and only for the volume(s) named on argv.

Faithfulness: committed text is literal OCR consensus; unparseable acts are
flagged, never fabricated; chapter numbers are parsed from the printed numeral.

Usage:
    python ingest_from_ocr.py <session_label>      # one volume
    python ingest_from_ocr.py 1861 1862 1863       # several
"""

import sys
import os
import re
import json
import time
import datetime
import subprocess
from pathlib import Path

import config  # SINGLE source of truth for data paths (the 3060 cutover knob); pipeline/ on sys.path

# ---------------------------------------------------------------------------
# DATE REVIEW WORKLIST
# ---------------------------------------------------------------------------
# When a parsed date's year falls OUTSIDE the ±YEAR_CLAMP_WINDOW, it is an
# OCR-error suspect.  The act is NOT silently committed with a wrong date;
# instead the match is appended here so a human can review and correct it.
# Location: next to the existing run-logs so the same review workflow applies.
DATE_REVIEW_WORKLIST = Path(config.path_for("parse_output_dir", "date-review-worklist.jsonl"))


# cc019: set True for a DRY-RUN parse (parse_volume(..., write=False)) so a
# before/after diff does not pollute the shared worklist.
#
# WHY THIS EXISTS: the worklist is APPEND-ONLY, and _append_date_review is called
# from flush_act -- i.e. during the parse itself, not at write time. So a dry-run
# parse that writes no JSON would STILL have appended a full duplicate generation
# of review records to the shared file. Caught while measuring the reparse cost;
# without this flag the diff harness's "touches nothing" claim was false.
_SUPPRESS_DATE_REVIEW = False


def _append_date_review(record: dict):
    """Append one JSON record (no trailing comma) to the date review worklist.

    The file is append-only; each line is a standalone JSON object (JSONL).
    Fields: session_label, volume_year, raw_match, parsed_year, chapter,
            source_page, in_act_order, timestamp_utc.
    Only call when a date WAS found by a regex but its year is implausible.

    No-op when _SUPPRESS_DATE_REVIEW is set (dry-run / diff parses).
    """
    if _SUPPRESS_DATE_REVIEW:
        return
    line = json.dumps(record, ensure_ascii=False) + "\n"
    DATE_REVIEW_WORKLIST.parent.mkdir(parents=True, exist_ok=True)
    with open(str(DATE_REVIEW_WORKLIST), "a", encoding="utf-8") as fh:
        fh.write(line)

SCRATCH_ROOT = Path(config.path_for("data_root"))
LOG_FILE = Path(config.path_for("vocab_dir", "resume-5090-run.log"))
PSQL = config.PSQL_BIN

# session_label -> (session_str, legislature_ordinal, start_year)
# TODO: LEGISLATURE_MAP is duplicated in pipeline/ingest_clean.py.
#       Consolidate into a shared module when the two pipelines are unified.
# EXTENDED 2026-06-09 (cc007): mirrored from ingest_clean.py to cover all
# 1850-1994 production labels so the __main__ gate no longer blocks 1877+ volumes.
# The parse step (parse_volume) does NOT use map values -- only ingest_volume does.
# No existing 1861-1875 entries changed; new entries appended.
LEGISLATURE_MAP = {
    # 1st–11th Legislature (1850–1860)
    "1850": ("1849-1850", "1st"), "1851": ("1851", "2nd"), "1852": ("1852", "3rd"),
    "1853": ("1853", "4th"), "1854": ("1854", "5th"), "1855": ("1855", "6th"),
    "1856": ("1856", "7th"), "1857": ("1857", "8th"), "1858": ("1858", "9th"),
    "1859": ("1859", "10th"), "1860": ("1860", "11th"),
    # 12th–21st Legislature (1861–1876) -- original entries unchanged
    "1861": ("1861", "12th"), "1862": ("1862", "13th"),
    "1863": ("1863", "14th"), "1863-64": ("1863-64 adjourned", "15th"),
    "1865-66": ("1865-66", "16th"), "1867-68": ("1867-68", "17th"),
    "1869-70": ("1869-70", "18th"), "1871-72": ("1871-72", "19th"),
    "1873-74": ("1873-74", "20th"),
    "1873-74-code": ("1873-74", "20th"),
    "1875-76": ("1875-76", "21st"),
    "1875-76-code": ("1875-76", "21st"),
    # 22nd Legislature, 1877-78
    "1877-78": ("1877 Regular Session", "22nd"),
    "1877-78-code": ("1877 Regular Session", "22nd"),
    # 23rd Legislature, 1880
    "1880": ("1880 Regular Session", "23rd"),
    "1880-code": ("1880 Regular Session", "23rd"),
    # 24th Legislature, 1881
    "1881": ("1881 Regular Session", "24th"),
    # 25th Legislature, 1883-84
    "1883-84": ("1884 Extra Session", "25th"),
    "1883-84-regular": ("1883 Regular Session", "25th"),
    # 26th Legislature, 1885-86
    "1885-86": ("1885 Regular Session", "26th"),
    # 27th Legislature, 1887
    "1887": ("1887 Regular Session", "27th"),
    # 28th Legislature, 1889
    "1889": ("1889 Regular Session", "28th"),
    # 29th Legislature, 1891
    "1891": ("1891 Regular Session", "29th"),
    # 30th Legislature, 1893
    "1893": ("1893 Regular Session", "30th"),
    # 31st Legislature, 1895
    "1895": ("1895 Regular Session", "31st"),
    # 32nd Legislature, 1897
    "1897": ("1897 Regular Session", "32nd"),
    # 33rd Legislature, 1899
    "1899": ("1899 Regular Session", "33rd"),
    # 34th Legislature, 1901
    "1900-01": ("1901 Regular Session", "34th"),
    # 35th Legislature, 1903
    "1903": ("1903 Regular Session", "35th"),
    # 36th/37th Legislature, 1905/1907
    "1905": ("1905 Regular Session", "36th"),
    "1906-07": ("1907 Regular Session", "37th"),
    # 38th Legislature, 1909
    "1907-09": ("1909 Regular Session", "38th"),
    # 39th Legislature, 1911
    "1910-11": ("1911 Regular Session", "39th"),
    # 40th Legislature, 1913
    "1913-statutes": ("1913 Regular Session", "40th"),
    # 41st Legislature, 1915
    "1915-vol1-chapters": ("1915 Regular Session", "41st"),
    # 42nd Legislature, 1917
    "1917-vol1-chapters": ("1917 Regular Session", "42nd"),
    # 43rd Legislature, 1919
    "1919-vol1-chapters": ("1919 Regular Session", "43rd"),
    # 44th Legislature, 1921
    "1921-vol1-chapters": ("1921 Regular Session", "44th"),
    # 45th Legislature, 1923
    "1923-vol1-chapters": ("1923 Regular Session", "45th"),
    # 46th Legislature, 1925/1926
    "1925-vol1-chapters": ("1925 Regular Session", "46th"),
    "1927-vol1-26chapters": ("1926 Extra Session", "46th"),
    # 47th Legislature, 1927/1928
    "1927-vol1-chapters": ("1927 Regular Session", "47th"),
    "1929-vol1-28chapters": ("1928 Extra Session", "47th"),
    # 48th Legislature, 1929
    "1929-vol1-chapters": ("1929 Regular Session", "48th"),
    "1929-vol1-29chapters": ("1929 Regular Session", "48th"),
    # 49th Legislature, 1931
    "1931-vol1-chapters": ("1931 Regular Session", "49th"),
    # 50th Legislature, 1933/1934
    "1933-vol1-chapters": ("1933 Regular Session", "50th"),
    "1935-vol1-34chapters": ("1934 Extra Session", "50th"),
    # 51st Legislature, 1935
    "1935-vol1-chapters": ("1935 Regular Session", "51st"),
    # 52nd Legislature, 1937/1938
    "1937-vol1-chapters": ("1937 Regular Session", "52nd"),
    "1938-vol1-chapters": ("1938 Extra Session", "52nd"),
    # 53rd Legislature, 1939
    "1939-vol1-chapters": ("1939 Regular Session", "53rd"),
    # 54th Legislature, 1941
    "1941-vol1-41chapters": ("1941 Regular Session", "54th"),
    "1943-vol1-42chapters": ("1941 1st Extra Session", "54th"),
    # 55th Legislature, 1943
    "1943-vol1-chapters": ("1943 Regular Session", "55th"),
    # 56th Legislature, 1945/1946
    "1945-vol1-chapters": ("1945 Regular Session", "56th"),
    "1947-vol1-46chapters": ("1946 1st Extraordinary Session", "56th"),
    # 57th Legislature, 1947/1948
    "1947-vol1-chapters": ("1947 Regular Session", "57th"),
    "1948-vol1-chapters": ("1948 Regular Session", "57th"),
    # 1949-50 session
    "1949-vol1-49chapters-prior": ("1949 1st Extraordinary Session", "1949-50"),
    "1949-vol1-chapters": ("1949 Regular Session", "1949-50"),
    "1950-vol1-chapters": ("1950 Regular Session", "1949-50"),
    # 1951-52 session
    "1951-vol1-50chapters": ("1950 3rd Extraordinary Session", "1949-50"),
    "1951-vol1-chapters": ("1951 Regular Session", "1951-52"),
    "1951-vol2-chapters": ("1951 Regular Session", "1951-52"),
    # 1953-54 session
    "1953-vol1-52chapters": ("1952 Regular Session", "1951-52"),
    "1953-vol1-chapters": ("1953 Regular Session", "1953-54"),
    "1953-vol2-chapters": ("1953 Regular Session", "1953-54"),
    # 1955-56 session
    "1955-vol1-54chapters": ("1954 Regular Session", "1953-54"),
    "1955-vol1-55chapters": ("1955 Regular Session", "1955-56"),
    "1955-vol1-chapters": ("1955 Regular Session", "1955-56"),
    "1955-vol2-chapters": ("1955 Regular Session", "1955-56"),
    # 1957-58 session
    "1957-vol1-56chapters": ("1956 Regular Session", "1955-56"),
    "1957-vol1-57chapters": ("1957 Regular Session", "1957-58"),
    "1957-vol1-chapters": ("1957 Regular Session", "1957-58"),
    "1957-vol2-57chapters": ("1957 Regular Session", "1957-58"),
    # 1959-60 session
    "1959-vol1-58chapters": ("1958 Regular Session", "1957-58"),
    "1959-vol1-59chapters": ("1959 Regular Session", "1959-60"),
    "1959-vol1-chapters": ("1959 Regular Session", "1959-60"),
    "1959-vol2-chapters": ("1959 Regular Session", "1959-60"),
    # 1961-62 session
    "1961-vol1-60chapters": ("1960 Regular Session", "1959-60"),
    "1961-vol1-61chapters": ("1961 Regular Session", "1961-62"),
    "1961-vol1-chapters": ("1961 Regular Session", "1961-62"),
    "1961-vol2-chapters": ("1961 Regular Session", "1961-62"),
    # 1963-64 session
    "1963-vol1-62chapters": ("1962 Regular Session", "1961-62"),
    "1963-vol1-63chapters": ("1963 Regular Session", "1963-64"),
    "1963-vol1-chapters": ("1963 Regular Session", "1963-64"),
    "1963-vol2-chapters": ("1963 Regular Session", "1963-64"),
    # 1965-66 session
    "1965-vol1-chapters": ("1965 Regular Session", "1965-66"),
    "1965-vol1-64chapters": ("1964 Regular Session", "1963-64"),
    "1965-vol1-65chapters": ("1965 Regular Session", "1965-66"),
    "1965-vol2": ("1965 Regular Session", "1965-66"),
    "1965-vol3-chapters": ("1965 Regular Session", "1965-66"),
    "1966-vol1-chapters": ("1966 Regular Session", "1965-66"),
    # 1967-68 session
    "1967-vol1-chapters": ("1967 Regular Session", "1967-68"),
    "1967-vol2": ("1967 Regular Session", "1967-68"),
    "1967-vol3-chapters": ("1967 Regular Session", "1967-68"),
    "1968-vol1-chapters": ("1968 Regular Session", "1967-68"),
    "1968-vol2-chapters": ("1968 Regular Session", "1967-68"),
    # 1969-70 session
    "1969-vol1-chapters": ("1969 Regular Session", "1969-70"),
    "1969-vol2-chapters": ("1969 Regular Session", "1969-70"),
    "1970-vol1-chapters": ("1970 Regular Session", "1969-70"),
    "1970-vol2-chapters": ("1970 Regular Session", "1969-70"),
    # 1971-72 session
    "1971-vol1-chapters": ("1971 Regular Session", "1971-72"),
    "1971-vol2": ("1971 Regular Session", "1971-72"),
    "1971-vol3-chapters": ("1971 Regular Session", "1971-72"),
    "1972-vol1-chapters": ("1972 Regular Session", "1971-72"),
    "1972-vol2-chapters": ("1972 Regular Session", "1971-72"),
    # 1973-74 session
    "1973-vol1-chapters": ("1973 Regular Session", "1973-74"),
    "1973-vol2-chapters": ("1973 Regular Session", "1973-74"),
    "1974-vol1-chapters": ("1974 Regular Session", "1973-74"),
    "1974-vol2-chapters": ("1974 Regular Session", "1973-74"),
    # 1975-76 session
    "1975-vol1-chapters": ("1975 Regular Session", "1975-76"),
    "1975-vol2-chapters": ("1975 Regular Session", "1975-76"),
    "1976-vol1-chapters": ("1976 Regular Session", "1975-76"),
    "1976-vol2": ("1976 Regular Session", "1975-76"),
    "1976-vol3": ("1976 Regular Session", "1975-76"),
    # 1977-78 session
    "1977-vol1-chapters": ("1977 Regular Session", "1977-78"),
    "1977-vol2": ("1977 Regular Session", "1977-78"),
    "1977-vol3-chapters": ("1977 Regular Session", "1977-78"),
    "1978-vol1-chapters": ("1978 Regular Session", "1977-78"),
    "1978-vol2": ("1978 Regular Session", "1977-78"),
    "1978-vol3": ("1978 Regular Session", "1977-78"),
    # 1979-80 session
    "1979-vol1-chapters": ("1979 Regular Session", "1979-80"),
    "1979-vol2": ("1979 Regular Session", "1979-80"),
    "1979-vol3": ("1979 Regular Session", "1979-80"),
    "1980-vol1-chapters": ("1980 Regular Session", "1979-80"),
    "1980-vol2": ("1980 Regular Session", "1979-80"),
    "1980-vol3": ("1980 Regular Session", "1979-80"),
    # 1981-82 session
    "1981-vol1-chapters": ("1981 Regular Session", "1981-82"),
    "1981-vol2": ("1981 Regular Session", "1981-82"),
    "1981-vol3": ("1981 Regular Session", "1981-82"),
    "1982-vol1-chapters": ("1982 Regular Session", "1981-82"),
    "1982-vol2": ("1982 Regular Session", "1981-82"),
    "1982-vol3": ("1982 Regular Session", "1981-82"),
    "1982-vol4": ("1982 Regular Session", "1981-82"),
    "1982-vol5": ("1982 Regular Session", "1981-82"),
    # 1983-84 session
    "1983-vol1-chapters": ("1983 Regular Session", "1983-84"),
    "1983-vol2": ("1983 Regular Session", "1983-84"),
    "1983-vol3": ("1983 Regular Session", "1983-84"),
    "1983-vol4-chapters": ("1983 Regular Session", "1983-84"),
    "1984-vol1-chapters": ("1984 Regular Session", "1983-84"),
    "1984-vol2": ("1984 Regular Session", "1983-84"),
    "1984-vol3": ("1984 Regular Session", "1983-84"),
    # 1985-86 session
    "1985-vol1-chapters": ("1985 Regular Session", "1985-86"),
    "1985-vol2": ("1985 Regular Session", "1985-86"),
    "1985-vol3": ("1985 Regular Session", "1985-86"),
    "1986-vol1-chapters": ("1986 Regular Session", "1985-86"),
    "1986-vol2": ("1986 Regular Session", "1985-86"),
    "1986-vol3": ("1986 Regular Session", "1985-86"),
    # 1987-88 session
    "1987-vol1-chapters": ("1987 Regular Session", "1987-88"),
    "1987-vol2": ("1987 Regular Session", "1987-88"),
    "1987-vol3": ("1987 Regular Session", "1987-88"),
    "1987-vol4-chapters": ("1987 Regular Session", "1987-88"),
    "1988-vol1-chapters": ("1988 Regular Session", "1987-88"),
    "1988-vol2": ("1988 Regular Session", "1987-88"),
    "1988-vol3": ("1988 Regular Session", "1987-88"),
    "1988-vol4-chapters": ("1988 Regular Session", "1987-88"),
    # 1989-90 session
    "1989-vol1-chapters": ("1989 Regular Session", "1989-90"),
    "1989-vol2": ("1989 Regular Session", "1989-90"),
    "1989-vol3": ("1989 Regular Session", "1989-90"),
    "1990-vol1-chapters": ("1990 Regular Session", "1989-90"),
    "1990-vol2": ("1990 Regular Session", "1989-90"),
    "1990-vol3": ("1990 Regular Session", "1989-90"),
    "1990-vol4": ("1990 Regular Session", "1989-90"),
    "1990-vol5-reg-session": ("1990 Regular Session", "1989-90"),
    "1990-vol5-firstextra": ("1989-90 1st Extra Session", "1989-90"),
    # 1991-92 session
    "1991-vol1": ("1991 Regular Session", "1991-92"),
    "1991-vol2": ("1991 Regular Session", "1991-92"),
    "1991-vol3": ("1991 Regular Session", "1991-92"),
    "1992-vol1-statutes": ("1992 Regular Session", "1991-92"),
    "1992-vol2": ("1992 Regular Session", "1991-92"),
    "1992-vol3": ("1992 Regular Session", "1991-92"),
    "1992-vol4": ("1992 Regular Session", "1991-92"),
    # 1993-94 session
    "1993-vol1": ("1993 Regular Session", "1993-94"),
    "1993-vol2": ("1993 Regular Session", "1993-94"),
    "1993-vol3": ("1993 Regular Session", "1993-94"),
    "1993-vol4": ("1993 Regular Session", "1993-94"),
    "1993-vol5": ("1993 Regular Session", "1993-94"),
    "1994-vol1": ("1994 Regular Session", "1993-94"),
    "1994-vol2": ("1994 Regular Session", "1993-94"),
    "1994-vol3": ("1994 Regular Session", "1993-94"),
    "1994-vol4": ("1994 Regular Session", "1993-94"),
    "1994-vol5": ("1994 Regular Session", "1993-94"),
    # 1995-96 session (not in ingest_clean.py yet -- added here for parse coverage)
    "1995-vol1": ("1995 Regular Session", "1995-96"),
    "1995-vol2": ("1995 Regular Session", "1995-96"),
    "1995-vol3": ("1995 Regular Session", "1995-96"),
    "1995-vol4": ("1995 Regular Session", "1995-96"),
    "1995-vol5": ("1995 Regular Session", "1995-96"),
    "1996-vol1": ("1996 Regular Session", "1995-96"),
    "1996-vol2": ("1996 Regular Session", "1995-96"),
    "1996-vol3": ("1996 Regular Session", "1995-96"),
    "1996-vol4": ("1996 Regular Session", "1995-96"),
    "1996-vol5": ("1996 Regular Session", "1995-96"),
    "1996-vol6": ("1996 Regular Session", "1995-96"),
    # 1997-98 session
    "1997-vol1": ("1997 Regular Session", "1997-98"),
    "1997-vol2": ("1997 Regular Session", "1997-98"),
    "1997-vol3": ("1997 Regular Session", "1997-98"),
    "1997-vol4": ("1997 Regular Session", "1997-98"),
    "1997-vol5": ("1997 Regular Session", "1997-98"),
    "1997-vol6": ("1997 Regular Session", "1997-98"),
    "1998-vol1": ("1998 Regular Session", "1997-98"),
    "1998-vol2": ("1998 Regular Session", "1997-98"),
    "1998-vol3": ("1998 Regular Session", "1997-98"),
    "1998-vol4": ("1998 Regular Session", "1997-98"),
    "1998-vol5": ("1998 Regular Session", "1997-98"),
    "1998-vol6": ("1998 Regular Session", "1997-98"),
    # 1999-00 session
    "1999-vol1": ("1999 Regular Session", "1999-00"),
    "1999-vol2": ("1999 Regular Session", "1999-00"),
    "1999-vol3": ("1999 Regular Session", "1999-00"),
    "1999-vol4": ("1999 Regular Session", "1999-00"),
    "1999-vol5": ("1999 Regular Session", "1999-00"),
}


def log(phase, description, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    entry = "[" + ts + "] " + phase + " | " + description + " | " + status + "\n"
    with open(str(LOG_FILE), "a", encoding="utf-8") as f:
        f.write(entry)
    print(entry.strip(), flush=True)


def psql_query(sql_str, retries=3):
    env = dict(os.environ)
    # PGPASSWORD must be supplied via the environment (no hardcoded secret).
    env["PGPASSWORD"] = os.environ.get("PGPASSWORD", "postgres")
    args = [PSQL, "-U", "postgres", "-d", "patolex", "-t", "-A",
            "--set=client_encoding=UTF8", "-c", sql_str]
    for attempt in range(retries):
        r = subprocess.run(args, capture_output=True, encoding="utf-8",
                           errors="replace", env=env, timeout=120)
        if r.returncode == 0:
            lines = [ln for ln in r.stdout.strip().splitlines()
                     if ln.strip()
                     and not ln.strip().startswith(("INSERT", "UPDATE", "DELETE"))]
            return lines[0] if lines else ""
        if "deadlock" in r.stderr.lower() or "serialization" in r.stderr.lower():
            time.sleep(0.5 * (attempt + 1))
            continue
        raise RuntimeError("psql error: " + r.stderr.strip()[:300])
    raise RuntimeError("psql failed after retries")


def safe_str(s, maxlen=None):
    s = s.encode("ascii", errors="replace").decode("ascii")
    s = s.replace("'", "''")
    if maxlen:
        s = s[:maxlen]
    return s


# ===========================================================================
# STAGE 5 PARSER -- byte-for-byte port of reparse.py ROUND2
# ===========================================================================
_DASH = "—–‒‐‑\\-"
# Separator between the CHAP./CHAPTER glyph and the numeral.
#
# cc019 (2026-07-24): the era-variant fix. Chapter-heading punctuation is NOT
# uniform across the corpus -- verified against the printed page:
#     1866      "CHAP. CXLIII."     period + SPACE
#     1876/78   "CHAP.—XCI."        period + EM DASH, no space
# The original pattern used `\.?\s*` here, which matches the 1866 form and is
# blind to every em-dash volume. _DASH was already defined below but used ONLY
# in the trailing "—An Act to..." position; the later typesetters put the dash
# on the other side of the numeral. Measured effect of this class: the canonical
# regex matched 5/9 real printed forms before, 9/9 after, with 0 false positives
# against body text, running heads, enacting clauses and [Approved] lines.
# See lessons/LESSON_2026-07-24_residual_71_is_parser_grammar_not_ocr.md defect 2.
#
# NOTE: keep the numeral character class letter-free. parse_chapter_number()
# silently strips non-Roman characters, so an over-capturing group does not
# fail loudly -- it returns a plausible WRONG number (e.g. "XCIAN" -> 91).
# Separator between the CHAP glyph and the numeral. Three rounds to get right;
# ALL numbers below are MEASURED on 1,732,428 real corpus lines / 27,595 pages
# across 19 volumes (early-era 1865-66/1871-72/1875-76/1877-78 + 15 modern).
#
#   round 1 (cc019)  r"[\s.,—–‒‐‑-]*"   comma+period. Claimed "0 false positives"
#                    -- FALSE, measured against a 6-line hand-written set.
#   round 2 (Hans)   r"[\s—–‒‐‑-]*"     comma removed on Hans's report of 55 FPs.
#                    OVER-CORRECTION: Hans's 55 is refuted (the real number is 9),
#                    and removing the comma LOST 116 GENUINE early-era headings.
#                    The 1860s-70s printed period was routinely OCR'd as a comma:
#                        'Cuap., XXII.—An Act concerning the County Clerk...'
#                        'Cuap, XLVI.—An Act to legalize the Assessment...'
#                        'CHAP, CXXXVIIL—An Act relative to the assessment...'
#                    Per-volume loss: 1865-66 -34, 1871-72 -1, 1875-76 -39,
#                    1877-78 -42. A net recall regression on exactly the era the
#                    pattern exists to serve.
#   round 3 (this)   comma allowed ONLY when the numeral is ROMAN.
#                    Every one of the 116 genuine comma headings has a Roman
#                    numeral; every one of the 9 index false positives has an
#                    Arabic one ('crabs, 874', 'charges, 1192', 'CHAPTER, 1302').
#                    Recovers 115/116, blocks all 9, adds 0 new junk (measured:
#                    R3 is a strict subset of R1; implausible-token count 62,
#                    identical to R2).
#   round 4 (this)   the 116th: 1877-78 p308 prints "Cuapv,. CXCIII.—" -- comma
#                    THEN period. Allowing `[\s.]*` after the comma recovers it.
#                    The Roman lookahead still blocks all 9 index lines, since
#                    every one of them carries an Arabic numeral.
#
# Implemented as an optional comma with a Roman lookahead, so HEADER_RE still has
# exactly ONE capture group (group(1) is consumed downstream -- do not add one).
#
# Reality check on the em-dash form this all started from: at corpus scale it is
# a TWO-INSTANCE outlier (1875-76 p124, 1877-78 p273), not a systematic era
# convention -- 1875-76/1877-78 print "Cuap. XXI.—" (period+space) in 379 of 462
# headings. The em-dash fix is still correct, but it is worth +2 headings, not a
# campaign. The earlier "5/9 -> 9/9" figure was a hand-built fixture set, not a
# corpus measurement.
_HDR_SEP = r"[\s—–‒‐‑-]*(?:,[\s.]*(?=[IVXLCDMivxlcdm]))?[\s—–‒‐‑-]*"
HEADER_RE = re.compile(
    r"^[^A-Za-z0-9]*"
    r"(?:[Cc][HhUuNnRrAaOoEe][AaRrVvPpOo][PpVvRrTt]?[a-zA-Z]{0,3}\.?\s*"
    r"|[Cc][Hh][Aa][Pp][Tt][Ee][Rr]\s*)"
    r"\.?" + _HDR_SEP +
    r"([IVXLCDMivxlcdm0-9JjTtYyLl!|]{1,8})"
    r"\s*[.,;:]?"
    r"(?:\s*[" + _DASH + r"].*)?$",
    re.I,
)
AN_ACT_RE = re.compile(r"\bAn?\s+A[CEO][TI]\b", re.IGNORECASE)
# The enacting clause. THIS GATE SILENTLY DROPS ACTS -- flush_act does
#     if not has_enact_marker(full): return
# i.e. no record at all, not even in flagged_acts. So its OCR tolerance is
# load-bearing in a way the other patterns are not.
#
# cc019 REGRESSION FIX (2026-07-25). The strict form below dropped SEVEN REAL
# STATUTES once the comma-header fix started segmenting acts correctly:
#     1862 ch.10, 21, 63, 114, 123   1863 ch.211, 440
# They were never "found" before either -- the OLD parser merged them into a
# 500-1,000-line blob that ran on until it hit a LEGIBLE enacting clause in a
# LATER act, so the gate passed on BORROWED EVIDENCE. Correct segmentation
# exposed that each act's own clause is OCR-mangled, e.g. 1862 ch.63:
#     "The People of the State af Culffornin, represented in Senate cel
#      assembly, do enact ax folloves"
# Neither "State of California" nor "do enact as follow" matches that.
#
# Tolerances added, each justified by a real corpus reading:
#   of -> [oa][fa]                  "State af"  -- BOTH letters rot, not just one
#   California -> C[a-z]{5,12}      "Culffornin", "Calfornia", "Culiforuia"
#   enact -> en[a-z]{2,4}           "enact", "enaet" (the c itself is lost), "enarct"
#   as -> a[a-z]                    "ax", "az"
#   follow -> foll[a-z]*            "folloves", "followes"
# The "People of the State [oa][fa] C..." arm still requires five literal anchor
# words, so it cannot fire on ordinary prose. The "do en.. a. foll.." arm is
# bounded on both sides by literal "do" and "foll", so its loose middle is safe.
# cc021 ROUND 2 -- AN ASYMMETRY I INTRODUCED, and it cost a real statute.
# The first attempt loosened the SECOND "of" ("State [oa][fa] California") but
# left the FIRST one literal. 1862 ch.10 prints:
#     "The Prople af the State of California, represented in Senaie and"
#     "du enact an fellows"
# -- the rot is in the FIRST "of", and "do"/"follows" are hit too. Both arms
# failed, and flush_act's `if not has_enact_marker(full): return` DROPPED THE ACT
# WITH NO RECORD AT ALL -- not even in flagged_acts, so it never reaches the
# review worklist. Its own "[Approved February 11, 1862.]" parses cleanly; that
# single gate was the only thing standing between it and full confidence.
# Also recovers the co-resident 1862 ch.11 ("The People af the State af
# California").
# Loosened symmetrically: both "of" slots, "do" -> d[ou], and the follow-word to
# f[aeiou]l... ("fellows", "filloes", "folluics" all occur).
ENACT_MARKER_RE = re.compile(
    r"P[er]?[eo]ple\s+[oa][fa]\s+the\s+State\s+[oa][fa]\s+C[a-z]{5,12}"
    r"|d[ou]\s+en[a-z]{2,4}\s+a[a-z]\s+f[aeiou]l[a-z]*",
    re.I,
)
_MONTHS = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?"
    r"|May|Mav"
    r"|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?"
    r"|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
# ===========================================================================
# cc021 (2026-07-25) -- THE DOMINANT flagged_acts CAUSE, and it was NOT what
# anyone assumed.
#
# 7,822 acts sit in flagged_acts corpus-wide. 99.4% carry BOTH "An Act" and an
# enacting clause and are >=200 chars; ZERO fail the length gate. The date gate
# is essentially the only thing flagging them.
#
# The assumed cause was a mangled approval KEYWORD ("Pussed March 20, 1850",
# "Arprovep. Avril 30. 1852"). MEASURED ACROSS ALL 208 VOLUMES: fixing keyword
# spelling alone recovers 60-77 acts. A rounding error.
#
# THE REAL CAUSE IS STRICT ADJACENCY. Holding _KW completely unchanged and only
# allowing a gap between it and the month: 2 -> 1,598 recoveries. 800x, with no
# keyword change at all. Gap-length is bimodal -- 3.4% of gaps are <=10 chars,
# then it jumps to 48% at <=15 and 85% at <=40. That cliff is exactly the width
# of one phrase:
#     239 " by Governor "     236 " hy Governor "    100 " bv Governor "
#      84 " by the Governor "   40 " by Guvernor "     36 "tary of State "
#      27 " by Governo: "       26 " bs Governor "     24 " by Covernor "
#
# APPROVED_MODERN_RE ALREADY models this idiom -- but it requires the LITERAL
# strings "Governor" / "Secretary of State", so every OCR variant falls through
# to APPROVED_RE, which then dies on adjacency.
#
# FIX CHOSEN: a TARGETED connector arm, not a blanket gap. Measured:
#     K2 + guarded 40-char gap   1,748 recovered / 22 earlier-date FPs   (79:1)
#     K2 + fuzzy-Governor arm    1,364 recovered /  1 earlier-date FP  (1364:1)
# The blanket gap is a LOOSENING that admits cross-reference prose ("proved
# April 30th, 1855" inside an amending clause on an 1856 act). The connector arm
# fixes an actual unmodeled idiom. For a corpus ingested exactly once, a flagged
# record is VISIBLE and recoverable later; a wrong date is SILENT and permanent.
#
# A POSITIONAL rule (accept a bare Month-DD-YYYY triple in the head window) was
# measured and REJECTED: 3,701 recovered but 491 earlier-date FPs -- a 1.5%
# corruption rate on confident acts vs 0.21% here. 12.8% of its no-keyword tier
# sits in OPERATIVE-date language ("shall take effect ... July 1, 1909"), which
# would stamp a wrong date on a real act.
#
# STILL MISSES ~4,000 (51%): 1,049 have a clean month but a corrupt year
# ("Approven, May 4, 185"), 112 need a fuzzy month ("Avril", "jApal"), 203
# neither. Day/year/month corruption is a separate axis this does not touch.
# ===========================================================================
#
# K2 keyword: adds garbled APPROVED/PASSED forms. Worth only ~77 acts alone, but
# combined with the connector arm it lifts 1,108 -> 1,364 at the same 1 FP.
_KW = (r"(?:[AP][A-Za-z]{1,4}[OoUu0][VvUuYy][A-Za-z]{0,5}"
       r"|A[Pp]{1,3}[Rr]{1,3}[Oo]?[Vv]\w{0,6}"
       r"|P[A-Za-z]{2,4}[Ee][Dd]"
       r"|Pass(?:ed)?)")

# The connector between keyword and date. OPTIONAL, and it must CONTAIN a
# recognisable Governor / Secretary-of-State token -- that requirement is what
# keeps it from behaving like a blanket gap and swallowing cross-reference prose.
# Cannot cross a sentence boundary or a newline.
_APPROVAL_CONNECTOR = (
    r"(?:[^\n.;:]{0,20}?"
    r"(?:[GC][a-z]{0,3}[vu][a-z]{0,4}n[a-z]{0,2}"   # Governor / Guvernor / Covernor / Governo
    r"|tary\s+of\s+State)"                           # (Secre)tary of State
    # Trailing slack allows the punctuation the OCR often leaves on the token
    # itself ("by Governo:" is a real corpus form, 27 instances). Kept short and
    # lazy so it cannot run into the next sentence.
    r"[^\n;]{0,12}?)?"
)
# Year broadened from the old 18[3-9]\d (1830-1899, which caused the
# confirmed 1900 date-cliff) to 1850-2008+: (?:18|19|20)\d\d.
_YEAR = r"((?:18|19|20)\d\d)"
APPROVED_RE = re.compile(
    _KW + _APPROVAL_CONNECTOR + r"\s*[,.]?\s*" + r"(" + _MONTHS + r")"
    # Day ordinal suffix allows bare "d" ("2d", "3d", "23d") -- the standard
    # 19th-century legal-printing abbreviation for "nd"/"rd". Without it the
    # 1877-1910 general statutes hit a date-cliff (many "Approved <Mon> Nd, YYYY"
    # approval lines failed to parse). Confirmed against banked 1880/1885 OCR.
    + r"\s+((?:[IilOo]?\d+|[IilOo])(?:st|nd|rd|th|d)?)"
    + r"[,.]?\s*" + _YEAR + r"\b",
    re.IGNORECASE,
)
# Modern born-digital / 1915+ approval language, e.g.
#   "Approved by Governor February 28, 2008."
#   "Filed with Secretary of State March 14, 2008."
# The bracket/date frequently span a line break, so allow whitespace
# (including newlines) between the keyword phrase and the date. This is a
# DATE-RECOGNITION alternative only; it does not mutate any text.
APPROVED_MODERN_RE = re.compile(
    r"(?:Approved\s+by\s+(?:the\s+)?Governor"
    r"|Filed\s+with\s+Secretary\s+of\s+State)"
    r"\s+(" + _MONTHS + r")"
    r"\s+(\d{1,2})"
    r"\s*,?\s*" + _YEAR + r"\b",
    re.IGNORECASE | re.DOTALL,
)
_MONTH_NORM = {
    "jan": "January", "feb": "February", "mar": "March", "apr": "April",
    "may": "May", "mav": "May", "jun": "June", "jul": "July",
    "aug": "August", "sep": "September", "oct": "October",
    "nov": "November", "dec": "December",
}

# ===========================================================================
# cc019 (2026-07-24) -- DEFECT 1: acts that became law WITHOUT the Governor's
# signature.
#
# There are THREE constitutionally distinct routes by which a California act
# became law in this era. Before this change the pipeline modelled only the
# first, so acts taking the other two were structurally invisible: they carry
# NO "[Approved <date>]" bracket at all, parse_act_date returned None, and
# is_confident_act() then demoted them to flagged_acts -- regardless of how
# clean the scan was.
#
#   1. Signed by the Governor        -> "[Approved February 18, 1876.]"
#   2. Became law UNSIGNED (10-day)  -> signature block + lapse notice
#   3. Passed OVER the Governor's veto -> constitutional-majority notice
#
# Verified against the printed volumes (cc019 contents-anchored recovery, see
# docs/80_PROJECT_HISTORY/RESIDUAL_71_CONTENTS_RECOVERY_2026-07-24.md). The
# printed CONTENTS tables state the path explicitly, e.g.:
#   1866 ch.143 "became law by the operation of Constitution, February 27, 1866"
#   1866 ch.198 "became law by operation of the Constitution, March 8, 1866"
#   1870 ch.431 "became a law by constitutional provision April 3, 1870"
#   1870 ch.143 "became a law by a constitutional majority of both Houses,
#                over the Governor's objections, March 4, 1870"   <- veto override
#
# NOTE the wording is NOT stable -- three different phrasings for path 2 alone.
# So we anchor on the stable core "became (a) law" and treat the qualifier as
# free text. Do NOT tighten this to any single phrasing.
#
# These CLUSTER: 1870 ch.428/429/430/431 are four consecutive unsigned
# enactments all dated April 3, 1870 -- bills passed at the close of session
# hit the ten-day window together.
#
# In the BODY the date is spelled out in words, not digits:
#   "This bill having remained with the Governor ten days, (Sundays excepted,)
#    and the Senate and Assembly being in session, it has become a law this
#    twenty-seventh day of February, A. D. eighteen hundred and sixty-six."
# No spelled-out-date parser existed anywhere in the pipeline before this.
# ===========================================================================

_ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "thirtieth": 30,
}
_ORDINAL_TENS = {"twenty": 20, "thirty": 30}
_CARDINAL_UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_CARDINAL_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}


def spelled_ordinal_to_int(tok):
    """'twenty-seventh' -> 27.  Returns None if not a day-of-month ordinal.

    Accepts hyphen, en/em dash, or whitespace between the tens and units word
    (19th-century printing and OCR are inconsistent about this).
    """
    if not tok:
        return None
    t = re.sub(r"[\s‐-―-]+", "-", tok.strip().lower())
    if t in _ORDINAL_WORDS:
        return _ORDINAL_WORDS[t]
    if "-" in t:
        tens, _, units = t.partition("-")
        if tens in _ORDINAL_TENS and units in _ORDINAL_WORDS:
            v = _ORDINAL_TENS[tens] + _ORDINAL_WORDS[units]
            # HANS (2026-07-25): the first draft accepted 21-39, admitting
            # impossible days 32-39 ("thirty-fifth" -> 35). Only 21-29 and 31
            # are legal constructed days; "thirtieth" is a whole word handled
            # above. Rejecting here means a garbled ordinal returns None and the
            # act falls through to "no date" rather than getting a fabricated one.
            if 21 <= v <= 31:
                return v
    return None


def spelled_year_to_int(tok):
    """'eighteen hundred and sixty-six' -> 1866.

    Also accepts the longer legal form 'one thousand eight hundred and
    sixty-six'. Returns None if it does not parse to a plausible year.
    """
    if not tok:
        return None
    t = tok.strip().lower()
    # Normalise ANY non-letter run to a single space before tokenising.
    # Measured miss (1865-66 ch.650): the corpus contains "eighteen*hundred and
    # sixty-six" -- an OCR artefact where the word space became "*". Splitting
    # only on whitespace/hyphen left "eighteen*hundred" as one unknown token and
    # returned None for a perfectly readable year.
    t = re.sub(r"[^a-z]+", " ", t)
    t = t.replace(" and ", " ")
    words = [w for w in t.split() if w]

    total = 0
    current = 0
    for w in words:
        if w == "thousand":
            current = (current or 1) * 1000
            total += current
            current = 0
        elif w == "hundred":
            current = (current or 1) * 100
            total += current
            current = 0
        elif w in _CARDINAL_UNITS:
            current += _CARDINAL_UNITS[w]
        elif w in _CARDINAL_TENS:
            current += _CARDINAL_TENS[w]
        else:
            return None
    total += current
    return total if 1800 <= total <= 2100 else None


# The stable core. Deliberately loose on the qualifier between "law" and the
# date -- observed variants include "by the operation of Constitution",
# "by operation of the Constitution", "by constitutional provision", and
# "by a constitutional majority of both Houses, over the Governor's objections".
# NOTE the vowel class: the BODY prints "it has become a law" while the
# CONTENTS prints "became law" -- bec[ao]me covers both. An earlier draft used
# a bare "become" and silently failed on every contents row.
# The article is optional: "became law" and "became a law" both occur.
# The trailing lookaheads exclude PROSPECTIVE/CONDITIONAL uses of "become law",
# which are statements ABOUT a future enactment rather than a record OF one.
# Measured false positive (1999 digest volume, the only one in 58 matches):
#     "...would provide that it shall only become operative if both this bill and
#      SB 765 are enacted and become law effective on or before January 1, 2000."
# That is a digest sentence; the date is a condition, not an enactment date.
_LAPSE_CORE = (r"bec[ao]me(?:s)?\s+(?:a\s+)?law"
               r"(?!\s+effective)(?!\s+operative)(?!\s+on\s+or\s+before)")

# The free-text qualifier between "became law" and the date.
#
# CROSS-ACT DATE POISONING guard. Verified against the real artifact:
# production-1865-66 **page 25** (a printed CONTENTS page -- exactly the source
# type this feature reads). The original `[^.]{0,120}?` ran past a page-number
# column AND a second act's title and captured chapter 380's APPROVED date as
# chapter 379's LAPSE date:
#
#   "379 | Au Act for relief of Pliny M. Whitney ... became a law by operation
#    of the Constitution, 380 | An Act to transfer certain fands--approved
#    March 30, 1866"
#
# The +/-3-year clamp CANNOT catch this -- the stolen date is the same year, only
# weeks off. Silent, plausible, wrong: the worst failure mode for a corpus that
# is ingested exactly once.
#
# WHAT ACTUALLY BLOCKS IT is the "An Act" / "CHAP" / "|" guards, NOT a digit ban.
# Measured: the poisoning span contains both "An Act" and a "|" page column, so
# it is blocked twice over; the current gap yields 0 matches on that page.
#
# The first fix ALSO banned digits, on the stated reasoning that the qualifier
# "never legitimately contains a digit". CORPUS MEASUREMENT REFUTED THAT --
# 1875-76 ch.250 is a real, correctly printed lapse notice:
#     "[Became a law by virtue of Section 17, Article 1V. of the Constitution,
#      March 18, 1876.)"
# It carries BOTH a digit ("Section 17") and a period ("1V."), and the digit ban
# silently dropped it. Cost/benefit measured: the ban killed 1 poisoning and 1
# true positive. Guarding on act-boundary tokens instead keeps both.
#
# So: forbid only true act-boundary markers, and cap the window tightly (70) so
# the gap cannot wander into a following sentence.
# Window sizing is measured, not guessed. The LONGEST legitimate qualifier in the
# corpus is the veto-override form, at 77 chars:
#     "by a constitutional majority of both Houses, over the Governor's objections, "
# A 70-char cap silently dropped it. 90 clears the longest real form with margin
# while staying far short of the next act. Length is NOT the poisoning guard --
# the "An Act" / "CHAP" / "|" boundary tokens are; those block the p.25 artifact
# regardless of window size.
_LAPSE_GAP = r"(?:(?!\bAn\s+Act\b)(?![Cc][Hh][Aa][Pp])[^|]){0,90}?"

# Body form: "...it has become a law this twenty-seventh day of February,
#             A. D. eighteen hundred and sixty-six."
LAPSE_SPELLED_RE = re.compile(
    _LAPSE_CORE
    + _LAPSE_GAP
    + r"\bthis\s+([a-z]+(?:[\s‐-―-]+[a-z]+)?)\s+day\s+of\s+"
    + r"(" + _MONTHS + r")\s*,?\s*"
    + r"(?:A\.?\s*D\.?\s*,?\s*)?"           # optional "A. D."
    # Spelled-out year. The `*` and `.` in the class are OCR noise tolerance:
    # measured miss on 1865-66 ch.650, printed/OCR'd "eighteen*hundred and
    # sixty-six." spelled_year_to_int() re-splits on non-word chars, so admitting
    # them here costs nothing and recovers the act.
    + r"([a-z][a-z\s‐-―*.-]{8,60}?)"
    # Terminator. Measured miss on 1865-66 ch.322, which ends the lapse notice
    # with a COMMA, and on 1875-76 ch.250, which ends with ")". The original
    # `[.;]` dropped both.
    + r"\s*[.;,)]",
    re.IGNORECASE,
)

# Contents/short form, digits: "became law by operation of the Constitution,
#                               February 27, 1866"
LAPSE_NUMERIC_RE = re.compile(
    _LAPSE_CORE
    + _LAPSE_GAP
    + r"(" + _MONTHS + r")\s+"
    + r"((?:[IilOo]?\d+|[IilOo])(?:st|nd|rd|th|d)?)"
    + r"[,.]?\s*" + _YEAR + r"\b",
    re.IGNORECASE,
)

# Path-3 discriminator. If this matches inside the enactment clause, the act
# passed OVER a veto rather than lapsing unsigned. Constitutionally distinct --
# record it distinctly, do not collapse into "unsigned".
VETO_OVERRIDE_RE = re.compile(
    r"over\s+the\s+Governor'?s?\s+objection"
    r"|constitutional\s+majority\s+of\s+both\s+Houses"
    r"|notwithstanding\s+the\s+objections?\s+of\s+the\s+Governor"
    # cc021: the BODY form. The contents table prints "became a law by a
    # constitutional majority ... over the Governor's objections", but the act
    # ITSELF prints the passage record, which does NOT contain "became a law":
    #     "Passed the Assembly notwithstanding the veto of the Governor, by the
    #      requisite Constitutional majority, January 31, 1855"
    # Missing this is why veto_override was 0 across the whole corpus.
    r"|notwithstanding\s+the\s+veto\s+of\s+the\s+Governor"
    r"|Passed\s+the\s+(?:Assembly|Senate)\s+notwithstanding",
    re.IGNORECASE,
)

# Corroborating marker for the ten-day lapse. Not required (the wording varies)
# but useful for classification confidence.
TEN_DAY_LAPSE_RE = re.compile(
    r"remained\s+with\s+the\s+Governor\s+ten\s+days"
    r"|having\s+remained\s+with\s+the\s+Governor",
    re.IGNORECASE,
)

# These volumes carry a "Concurrent and Joint Resolutions" section after the
# chapters (confirmed in all seven biennial volumes -- the printed CONTENTS runs
# a SECOND table under that heading). Resolutions are NOT chapters and must never
# be committed as acts. They use "Resolved by the Assembly, the Senate
# concurring" rather than the enacting clause, so they should not reach the
# fallback gate in is_confident_act -- but that gate is new, so reject them
# explicitly rather than relying on the absence of a marker.
# NOTE the optional comma in "Resolved, By the Senate" -- measured: 1865-66
# ch.500 prints exactly that, and a pattern requiring "Resolved by the" missed
# the single clearest resolution marker in the buffer.
RESOLUTION_RE = re.compile(
    r"\b(?:CONCURRENT|JOINT)\s+RESOLUTION\b"
    r"|\bResolved\s*,?\s+by\s+the\s+(?:Assembly|Senate)\b"
    r"|\bBe\s+it\s+resolved\b",
    re.IGNORECASE,
)

# A genuine resolution ANNOUNCES ITSELF on its first content line:
#     "Senate Concurrent Resolution No. 14--Relative to ..."
#     "Assembly Joint Resolution No. 3--..."
# A real act's first content line begins "An act to ...". That difference is the
# discriminator; the mere PRESENCE of resolution words is not, because acts
# routinely reference resolutions in their own titles.
RESOLUTION_HEAD_RE = re.compile(
    r"^\W{0,4}(?:(?:Senate|Assembly)\s+)?(?:Concurrent|Joint)\s+Resolution\b"
    r"|^\W{0,4}Resolution\s+No\b"
    r"|^\W{0,4}Resolved\s*,?\s+by\s+the\s+(?:Assembly|Senate)\b"
    # cc021: a WHEREAS preamble, OCR-tolerant. Measured leak -- 1917 ch.55 is
    # unambiguously "Senate Concurrent Resolution No. 24", but its first content
    # line OCR'd as "Wuenrrss, By an act entitled..." so none of the arms above
    # fired and it passed as a confident ACT.
    # An act's first content line is its TITLE ("An act to..."); only a
    # resolution opens with a WHEREAS preamble. Kept tight: must start with W/V,
    # be a single 6-11 letter word ending in s, then a comma, then one of a few
    # expected continuations -- so it cannot fire on ordinary prose or a title.
    r"|^\W{0,4}[WV][A-Za-z]{4,9}[sS]\s*[,.]\s+(?:By|That|the|it|in|whereas)\b",
    re.IGNORECASE,
)

_CHAP_HEAD_STRIP_RE = re.compile(
    r"^[^A-Za-z0-9]*(?:CHAPTER|CHAP)[^A-Za-z0-9]*[IVXLCDMivxlcdm0-9]{1,8}[^A-Za-z0-9]*",
    re.IGNORECASE,
)


def opening_line(full_text):
    """First line of real content, with any leading CHAPTER heading removed.

    Used by the resolution guard. Returns "" if nothing but headings.
    """
    for ln in (full_text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        s = _CHAP_HEAD_STRIP_RE.sub("", s).strip()
        if s:
            return s
    return ""


ENACTMENT_PATH_APPROVED = "approved"
ENACTMENT_PATH_UNSIGNED = "unsigned_lapse"
ENACTMENT_PATH_VETO_OVERRIDE = "veto_override"


def detect_enactment_path(text):
    """Classify HOW the act became law.

    Returns one of ENACTMENT_PATH_*. Defaults to 'approved' -- the overwhelming
    majority -- so existing behaviour is unchanged for signed acts.
    """
    if not text:
        return ENACTMENT_PATH_APPROVED
    # cc021 FIX: veto override is checked INDEPENDENTLY, not nested inside the
    # lapse check. The first version required _LAPSE_CORE ("became a law") to
    # match first -- but the BODY form of a veto override never says that:
    #     "Passed the Assembly notwithstanding the veto of the Governor, by the
    #      requisite Constitutional majority, January 31, 1855"
    # Only the CONTENTS table uses the "became a law by a constitutional
    # majority ... over the Governor's objections" wording, and the parser reads
    # bodies, not contents. Result: veto_override was 0 across all 70,408 acts
    # in the corpus -- the branch was effectively unreachable.
    if VETO_OVERRIDE_RE.search(text):
        return ENACTMENT_PATH_VETO_OVERRIDE
    if re.search(_LAPSE_CORE, text, re.IGNORECASE):
        return ENACTMENT_PATH_UNSIGNED
    return ENACTMENT_PATH_APPROVED


def parse_lapse_date(text):
    """Date for an act that became law WITHOUT the Governor's signature.

    Returns (iso_date_str, raw_match_str) or (None, ""). Tries the spelled-out
    body form first, then the numeric contents form.
    """
    for m in LAPSE_SPELLED_RE.finditer(text or ""):
        day = spelled_ordinal_to_int(m.group(1))
        year = spelled_year_to_int(m.group(3))
        if day is None or year is None:
            continue
        month_str = normalize_month(m.group(2))
        try:
            d = datetime.datetime.strptime(
                "%s %d %d" % (month_str, day, year), "%B %d %Y")
        except Exception:
            continue
        return d.strftime("%Y-%m-%d"), re.sub(r"\s+", " ", m.group(0)).strip()

    for m in LAPSE_NUMERIC_RE.finditer(text or ""):
        month_str = normalize_month(m.group(1))
        day_str = normalize_day(m.group(2))
        try:
            d = datetime.datetime.strptime(
                month_str + " " + day_str + " " + m.group(3), "%B %d %Y")
        except Exception:
            continue
        return d.strftime("%Y-%m-%d"), re.sub(r"\s+", " ", m.group(0)).strip()

    return None, ""
_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_ROMAN_OCR_SUBST = {"J": "I", "T": "I", "1": "I", "!": "I", "|": "I"}

# ===========================================================================
# cc021 (2026-07-25) -- CHAPTER-NUMERAL PLAUSIBILITY. All figures MEASURED over
# 216 volumes / 71,443 confident acts.
#
# THE CENSUS: 992 duplicated chapter keys / 2,027 acts / 134 of 216 volumes.
#   611 of them are on the ARABIC path -- which performs NO VALIDATION AT ALL
#   (`int(t)` accepts anything). 355 confident acts carry out-of-range Arabic
#   chapters: 1967-vol2 ch.90956, 1957-vol2 ch.14383, 1907-09 ch.6548.
#   That is the LARGER defect and no Roman rule touches it.
#
# WHY STRICT CANONICAL ROMAN IS THE WRONG FIX -- measured, and it is not close:
#   * 19th-century California printed the 400s ADDITIVELY: CCCCV, CCCCXXI,
#     CCCCXCI -- not CDV. Strict canonical is simply the wrong grammar for this
#     corpus. Applied post-substitution it rejects 396 of 6,959 presumed-correct
#     Roman acts (5.7%) to fix 122 keys. Applied to the RAW token it rejects
#     1,199 (17.2%).
#   * It is BLIND to all four named damage cases anyway: CXCVIL->CXCVII,
#     CCCVIIT->CCCVIII, CCCLY->CCCL, CXXXVIIL->CXXXVIII are all CANONICAL AFTER
#     TRANSFORMATION. The substitution rules MANUFACTURE well-formed numerals
#     out of garbage, so a validator placed downstream of them cannot see it.
#   * A RELAXED ADDITIVE validator rejects only 9 of 6,959 (0.13%) -- and all 9
#     are genuine garbage (CCLIXVII, XLX, DLIIX, DCDXX, CCCXXIIV).
#
# WHAT THIS CHANGE DOES: makes implausible numerals VISIBLE, without mutating
# any value. Nothing here guesses a "corrected" chapter number -- that requires
# sequence inference and is a separate, explicitly-deferred decision (see the
# lesson file). An act whose numeral fails these checks gets chapter_int 0,
# which routes it to flagged_acts WITH its chapter_raw intact for review --
# visible and recoverable, rather than silently ingested under a wrong key.
# ===========================================================================

# No California session has ever had anything close to this many chapters (the
# largest, 1945, had 1,527). A value above this is definitionally an OCR artefact.
MAX_PLAUSIBLE_CHAPTER = 5000

# Relaxed ADDITIVE Roman grammar -- accepts the corpus's real CCCC-style 400s,
# rejects only structurally impossible strings. Measured: 9 rejections corpus-wide.
_ROMAN_ADDITIVE_RE = re.compile(r"^M*(CM|CD|D?C*)(XC|XL|L?X*)(IX|IV|V?I*)$")


def numeral_is_plausible(value, roman_norm=None):
    """Is a parsed chapter number structurally believable?

    Returns (ok, reason). Does NOT correct anything.
    """
    if not isinstance(value, int) or value <= 0:
        return False, "unparseable"
    if value > MAX_PLAUSIBLE_CHAPTER:
        return False, "out_of_range"
    if roman_norm and not _ROMAN_ADDITIVE_RE.match(roman_norm):
        return False, "non_additive_roman"
    return True, ""


def parse_chapter_number(tok):
    raw = tok.strip().strip(".,;:")
    if not raw:
        return 0
    if re.fullmatch(r"\d+(?:st|nd|rd|th|d)", raw, re.I):
        return 0
    raw = raw.replace("l", "I")
    t = raw.upper()
    if t.isdigit():
        try:
            v = int(t)
        except ValueError:
            return 0
        # cc021: THE ARABIC PATH HAD NO VALIDATION AT ALL -- `int(t)` accepted
        # anything, producing confident acts at chapter 90956 (1967-vol2), 14383
        # (1957-vol2), 6548 (1907-09). 355 such acts corpus-wide, and 611 of the
        # 992 duplicate chapter keys are on this path. Returning 0 routes them to
        # flagged_acts WITH chapter_raw intact -- visible for review instead of
        # silently ingested under an impossible key.
        return v if 0 < v <= MAX_PLAUSIBLE_CHAPTER else 0
    sub = "".join(_ROMAN_OCR_SUBST.get(c, c) for c in t)
    sub = re.sub(r"(?<=I)L+$", lambda m: "I" * len(m.group(0)), sub)
    roman = "".join(c for c in sub if c in _ROMAN)
    if not roman:
        return 0
    val = prev = 0
    for c in reversed(roman):
        cur = _ROMAN[c]
        val += cur if cur >= prev else -cur
        prev = cur
    # Same bound on the Roman path. Deliberately NOT applying a canonical-Roman
    # validator here: 19th-c California printed the 400s additively (CCCCV, not
    # CDV), so strict canonical would reject 396 CORRECT chapters to fix 122
    # keys -- and it is blind to the real damage anyway, because the
    # substitutions above manufacture canonical numerals out of garbage.
    return val if 0 < val <= MAX_PLAUSIBLE_CHAPTER else 0


def normalize_day(day_str):
    s = day_str.strip()
    # Strip ordinal suffix incl. bare "d" ("2d","3d","23d" -> "2","3","23").
    s = re.sub(r"(?i)(st|nd|rd|th|d)$", "", s)
    if s.upper() in ("I", "L"):
        return "1"
    if s.upper() == "O":
        return "0"
    s = re.sub(r"^[Il](?=\d)", "1", s)
    s = re.sub(r"^O(?=\d)", "0", s)
    return s if s else "1"


def normalize_month(month_str):
    return _MONTH_NORM.get(month_str.lower()[:3], month_str.capitalize())


def parse_act_date(text, volume_year=None, _rejected_out=None):
    """Return (iso_date_str, raw_match_str) or (None, "").

    volume_year -- the nominal calendar year of the source volume (e.g. 1855
    for the 1855 session, or 1863 for the "1863-64" session).  When supplied,
    any parsed year that falls OUTSIDE the window
        [volume_year - YEAR_CLAMP_WINDOW, volume_year + YEAR_CLAMP_WINDOW]
    is REJECTED as a likely OCR digit corruption (Cluster-A bug) or body-text
    date poisoning (Cluster-B bug).

    YEAR_CLAMP_WINDOW = 3:
      * The entire documented Cluster-A set (28 rows) had parsed years 20–40
        years off (e.g. 1855→1895, 1860→1880).  A window of ±3 rejects all of
        them while still accepting a correctly-read date for an act signed in
        the year before or after the session nominal year (some sessions span
        two calendar years, e.g. the 1863-64 adjourned session).
      * Cluster-B dates were historical boilerplate years, typically 50-100
        years before the source volume year (e.g. a 2000 volume containing a
        1913 body reference).  ±3 rejects all of them.
      * A future re-ingest that spans a session straddling a year boundary
        (e.g. a late-December approval in a session nominally labelled with the
        NEXT year) is within ±1 and therefore WITHIN the window — safe.

    _rejected_out -- optional list.  When provided AND volume_year is set, each
    out-of-window match (a date that was FOUND by a regex but whose year is
    implausible) is appended as a dict {"raw": str, "parsed_year": int}.
    "No match at all" is NOT appended — only implausible matches are.
    Callers that don't need this can omit it (the default None is a no-op).

    Distinguishing "no date found" vs "date found but implausible":
      * Return (None, "") with empty _rejected_out -> genuinely no date present.
      * Return (None, "") with non-empty _rejected_out -> date(s) found but all
        out-of-window; this is an OCR-error suspect, not a legitimately dateless act.
    """
    # Clamp window size (years).  Change here to widen/tighten everywhere.
    YEAR_CLAMP_WINDOW = 3

    def _year_ok(year_int):
        if volume_year is None:
            return True  # no context -> no check (legacy call-sites unaffected)
        return abs(year_int - volume_year) <= YEAR_CLAMP_WINDOW

    def _record_rejected(raw_str, year_int):
        """If caller passed a collector, record this out-of-window hit."""
        if _rejected_out is not None:
            _rejected_out.append({"raw": raw_str, "parsed_year": year_int})

    # Always try APPROVED_MODERN_RE ("Approved by Governor …" / "Filed with
    # Secretary of State …") FIRST, regardless of volume_year.  This pattern is
    # highly specific to the modern chaptered-statute footer format and will
    # never match 19th-century "[Approved ... 18XX]" text, so it is universally
    # safe.  Trying it first prevents the Cluster-B "date poisoning" bug on
    # modern volumes without any era-conditional branching.  (SERIOUS-4 fix)
    for m in APPROVED_MODERN_RE.finditer(text):
        month_str = normalize_month(m.group(1))
        day_str = m.group(2)
        year_raw = m.group(3)
        try:
            d = datetime.datetime.strptime(
                month_str + " " + day_str + " " + year_raw, "%B %d %Y")
            if not _year_ok(d.year):
                _record_rejected(re.sub(r"\s+", " ", m.group(0)).strip(), d.year)
                continue
            raw = re.sub(r"\s+", " ", m.group(0)).strip()
            return d.strftime("%Y-%m-%d"), raw
        except Exception:
            continue

    # Pre-1900 / OCR-fuzzy format (all volumes; primary path for early era).
    for m in APPROVED_RE.finditer(text):
        month_str = normalize_month(m.group(1))
        day_str = normalize_day(m.group(2))
        year_raw = m.group(3)
        try:
            d = datetime.datetime.strptime(
                month_str + " " + day_str + " " + year_raw, "%B %d %Y")
            if not _year_ok(d.year):
                # Cluster-A: year out of range -> record the rejection, try next match
                _record_rejected(re.sub(r"\s+", " ", m.group(0)).strip(), d.year)
                continue
            raw = re.sub(r"\s+", " ", m.group(0)).strip()
            return d.strftime("%Y-%m-%d"), raw
        except Exception:
            continue

    # cc019 DEFECT 1: acts that became law WITHOUT the Governor's signature.
    # Tried LAST so signed acts are completely unaffected -- this branch is only
    # reached when neither approval pattern matched, which previously always
    # meant "(None, '')" and a silent demotion to flagged_acts.
    iso, raw = parse_lapse_date(text)
    if iso:
        year_int = int(iso[:4])
        if _year_ok(year_int):
            return iso, raw
        _record_rejected(raw, year_int)

    return None, ""


def has_enact_marker(full_text):
    return bool(ENACT_MARKER_RE.search(full_text))


def is_confident_act(full_text, volume_year=None):
    """Is this buffer a real act we can commit?

    cc019 DEFECT 1 + FINDING D -- two gates were too strict and silently
    demoted real, legible acts to flagged_acts:

      * has_date: unsigned/veto-override acts carry no "[Approved ...]" bracket
        at all. parse_act_date now understands the lapse forms, so this gate is
        satisfied for them too -- no change needed here beyond that.
      * has_an_act: AN_ACT_RE requires the literal "An Act". Verified
        counter-examples from the printed volumes (cc019 contents recovery):
            1876 ch.508  "[An amendment to the Code, but which also repeals
                          the Act of March 28, 1874, in relation to solvent
                          debts]"     <- printed on p.772, a REAL act
            1870 ch.427  "Charter of the City of Stockton--An Act to
                          reincorporate the City of Stockton"
        So accept an explicit enactment marker ("The People of the State of
        California ... do enact as follows") as an ALTERNATIVE to the literal
        "An Act". The enacting clause is the legally operative signal; the
        title wording is a printing convention.

    HANS NOTE (2026-07-25): making the enacting clause an ALTERNATIVE gate makes
    ENACT_MARKER_RE load-bearing where it previously was not, and it is
    unanchored. Two guards were added:
      * the clause must appear EARLY (first 2000 chars). An enacting clause is
        printed immediately under the act title; a match deep in the body is a
        quotation of another act, not this act's own clause.
      * an explicit RESOLUTION guard. These volumes carry a Concurrent and Joint
        Resolutions section which is NOT chapters. Resolutions use "Resolved by
        the Assembly, the Senate concurring" rather than the enacting clause, so
        they should not reach here -- but the fallback path is new, so reject
        them explicitly rather than relying on that.
    """
    head = full_text[:2000]
    m_an_act = AN_ACT_RE.search(head)
    m_clause = ENACT_MARKER_RE.search(head)
    m_res = RESOLUTION_RE.search(head)

    # Reject resolutions -- but ONLY when the resolution marker comes FIRST.
    #
    # CORPUS MEASUREMENT (2026-07-25): a flat "resolution marker in the first 600
    # chars -> reject" rule wrongly rejected a GENUINE statute. production-1871-72
    # ch.637 ("An Act to protect the wages of labor...", [Approved April 1, 1872])
    # is the LAST chapter in its volume, so its buffer bleeds into the following
    # "CONCURRENT AND JOINT RESOLUTIONS." section header at offset 554 -- inside
    # the window. It has both "An Act" AND the full enacting clause well before
    # that point.
    #
    # Position, not presence, is the discriminator: in a real resolution the
    # resolution language comes first; in a bleed-through it comes after the act's
    # own enacting clause.
    #
    # THE ANCHOR MUST BE THE ENACTING CLAUSE ALONE -- NOT "An Act".
    # Measured (2026-07-25): using AN_ACT_RE as act-evidence made this guard
    # COMPLETELY INERT (0 rejections across 3,091 act buffers). 1865-66 ch.500 is
    # a genuine resolution that QUOTES a bill title -- "...requested to return
    # Senate Bill Number Three Hundred and Thirteen, entitled an Act to amend an
    # Act to provide for..." -- so AN_ACT_RE fired at offset 270, before the
    # resolution marker at 522, and the buffer was kept.
    #
    # A quoted act title proves nothing: resolutions routinely name the bills
    # they concern. Only the ENACTING CLAUSE ("The People of the State of
    # California ... do enact as follows") is legally exclusive to an act --
    # resolutions never carry it. Measured discriminator:
    #     ch.500 (real resolution)  ENACT@None -> rejected
    #     ch.637 (real act)         ENACT@138  -> kept
    # ---- v3 (2026-07-25): decide on the FIRST CONTENT LINE ----
    # The two comment blocks above describe v1 and v2. BOTH WERE WRONG, each
    # measured against the corpus:
    #   v1 "resolution phrase in first 600 chars -> reject" killed the GENUINE
    #      1871-72 ch.637, whose buffer bleeds into the following
    #      "CONCURRENT AND JOINT RESOLUTIONS" section header.
    #   v2 "reject if the phrase precedes the ENACTING CLAUSE" looked principled
    #      -- resolutions never carry that clause -- but ENACT_MARKER_RE NEVER
    #      MATCHES 20th-CENTURY VOLUMES; they do not print the 19th-century
    #      formula. So m_clause is None for the entire modern era and the guard
    #      degenerated straight back to "any resolution phrase -> reject",
    #      killing three real acts:
    #        1897 ch.118  appropriation act that NAMES a resolution in its own
    #                     title ("...expenses incurred by Assembly Concurrent
    #                     Resolution No. 6...")
    #        1937 ch.933  real act, buffer bleeds into the resolutions header --
    #                     the very case v1 was supposed to fix
    #        1939 ch.1124 same bleed-through
    #
    # A genuine resolution ANNOUNCES ITSELF on its opening line ("Senate
    # Concurrent Resolution No. 14--Relative to..."); a real act opens "An act
    # to...". Measured across all 10 modern cases: 7/7 correct rejections kept,
    # 3/3 false rejections removed -- without depending on a clause that does
    # not exist in that era.
    if RESOLUTION_HEAD_RE.search(opening_line(full_text)):
        return False

    has_an_act = m_an_act is not None
    # Anchor the fallback: enacting clause must be in the act's opening.
    has_enacting_clause = m_clause is not None
    has_date, _ = parse_act_date(full_text, volume_year=volume_year)
    return (
        (has_an_act or has_enacting_clause)
        and has_date is not None
        and len(full_text.strip()) >= 100
    )


def _next_nonempty(lines, i, k=4):
    out = []
    j = i + 1
    while j < len(lines) and len(out) < k:
        s = lines[j][1].strip()
        if s:
            out.append(s)
        j += 1
    return out


def header_starts_act(lines, i):
    ln = lines[i][1].strip()
    m = HEADER_RE.match(ln)
    if not m:
        return False, None
    window = " ".join([ln] + _next_nonempty(lines, i, 4))
    if AN_ACT_RE.search(window):
        return True, m.group(1)
    return False, None


def flush_act(chap_token, start_page, buf, acts_parsed, acts_flagged,
              page_ocr_results, volume_year=None, session_label=None,
              in_act_order=None):
    if not buf:
        return
    full = "\n".join(buf).strip()
    if len(full) < 60:
        return
    header_line = re.sub(r"\s+", " ", buf[0]).strip()
    if re.search(r"\b(?:Approved|Passed)\b", header_line, re.I):
        return
    if not has_enact_marker(full):
        return
    chap_int = parse_chapter_number(chap_token)
    title = ""
    for line in buf:
        if AN_ACT_RE.search(line):
            title = re.sub(r"\s+", " ", line).strip()[:500]
            break
    if not title:
        title = re.sub(r"\s+", " ", buf[0]).strip()[:300] if buf else ""

    # Collect implausible-date candidates via _rejected_out side-channel so we
    # can distinguish "no date in text" (legitimately dateless) from "date found
    # but year is out-of-window" (OCR corruption suspect).
    rejected = []
    iso_date, approved_str = parse_act_date(
        full, volume_year=volume_year, _rejected_out=rejected)

    # If the regex found a date but the year was implausible, flag it.
    # Implausible-date acts are flagged to the review worklist and EXCLUDED from
    # DB ingest pending date correction (they remain in the JSON stage file under
    # flagged_acts).  Whether flagged acts should instead be ingested-with-a-flag
    # is a pending design decision.
    # DECISION PENDING: change the routing below (acts_parsed vs acts_flagged)
    # only after that decision is made — do not silently alter ingest behavior.
    date_needs_review = False
    if iso_date is None and rejected:
        date_needs_review = True
        act_citation = (
            ("Stats. " + session_label + " ch. " + str(chap_int))
            if session_label else ("ch. " + str(chap_int))
        )
        for rej in rejected:
            review_rec = {
                "timestamp_utc": datetime.datetime.utcnow().isoformat() + "Z",
                "session_label": session_label or "",
                "volume_year": volume_year,
                "raw_match": rej["raw"],
                "parsed_year": rej["parsed_year"],
                "year_delta": (
                    abs(rej["parsed_year"] - volume_year) if volume_year else None
                ),
                "citation": act_citation,
                "source_page": (start_page or 0) + 1,
                "in_act_order": in_act_order,
                "reason": "year_out_of_window",
            }
            _append_date_review(review_rec)
        log(
            "STAGE5-PARSE",
            (session_label or "?") + " ch." + str(chap_int)
            + " page=" + str((start_page or 0) + 1)
            + ": date found but year implausible "
            + str([r["parsed_year"] for r in rejected])
            + " (volume_year=" + str(volume_year) + ")"
            + " -- flagged for date review, EXCLUDED from DB ingest, worklist updated",
            "WARN",
        )

    body_text = re.sub(r"[ \t]+", " ", full)
    # NOTE: is_confident_act() re-runs parse_act_date() internally, so this is a
    # double-parse.  The cost is negligible for the sequential OCR ingest path
    # (no pool), but should be collapsed if this function is ever parallelised.
    confident = (
        is_confident_act(full, volume_year=volume_year)
        and chap_int > 0
        and not date_needs_review  # implausible-date acts are NOT confident
    )
    act_rec = {
        "chapter": str(chap_int), "chapter_int": chap_int,
        "chapter_raw": chap_token, "title": title,
        "approved_date": approved_str, "iso_date": iso_date,
        "date_needs_review": date_needs_review,
        # cc019 DEFECT 1 -- HOW this act became law. Three constitutionally
        # distinct routes; only "approved" was ever modelled before.
        #
        # WIRED IN 2026-07-25, after a corpus-wide diff reported the path
        # distribution as 100% "approved" / 0 unsigned / 0 veto_override across
        # 70,230 acts. detect_enactment_path() existed, was unit-tested, and was
        # CALLED BY NOTHING BUT ITS OWN TESTS. The date fix worked (parse_act_date
        # dates lapse acts correctly) but the PATH was never recorded, so the
        # legally meaningful distinction was silently dropped on the floor.
        #
        # A tested function that nothing calls is not a feature. The unit tests
        # passed the whole time because they invoked it directly.
        "enactment_path": detect_enactment_path(full),
        "text": body_text[:6000], "source_page": (start_page or 0) + 1,
        "in_act_order": in_act_order,  # 0-based reading-order position (Hans F7 act key)
        "confident": confident,
        "page_agreement_ratio": page_ocr_results.get(start_page, {}).get("agreement_ratio", 0.0),
    }
    (acts_parsed if confident else acts_flagged).append(act_rec)


def parse_volume(session_label, out_path=None, write=True):
    """Parse one volume from banked OCR consensus text.

    NO OCR IS PERFORMED. This reads `ocr_consensus/page_ocr_results.json` and
    consumes the already-banked `consensus_text`; no engine runs and no GPU is
    touched. A "reparse" is therefore CPU-over-JSON, not a re-OCR.

    Writes ONLY `parsed_acts_fixed.json`. It does NOT touch
    parsed_acts_merged.json / _clauserec.json / _visual.json / _certified.json --
    those are produced by the downstream recovery passes and carry the cc015-cc018
    campaign's work.

    cc019: `out_path` / `write` added so a before/after diff can run WITHOUT
    mutating the corpus. Defaults preserve the original behaviour exactly.
      out_path -- write somewhere other than the volume dir (used by the diff
                  harness so the live corpus is never touched).
      write    -- False returns the parse result and writes nothing at all.
    """
    scratch = SCRATCH_ROOT / ("production-" + session_label)
    ocr_path = scratch / "ocr_consensus" / "page_ocr_results.json"
    out_path = Path(out_path) if out_path else (scratch / "parsed_acts_fixed.json")
    if not ocr_path.exists():
        log("STAGE5-PARSE", session_label + ": OCR file missing: " + str(ocr_path), "FAIL")
        return None

    # Derive the nominal calendar year from the session label for the year-
    # sanity clamp.  Labels like "1863-64" yield 1863 (the opening year).
    # (NITPICK-1) Guard against malformed labels with no leading 4-digit year.
    _year_match = re.match(r'(\d{4})', session_label)
    if not _year_match:
        log("STAGE5-PARSE", session_label + ": cannot parse 4-digit year from label -- skipping", "FAIL")
        return None
    volume_year = int(_year_match.group(1))

    # Dry-run must be side-effect-free EVERYWHERE, not just for the JSON write.
    # _append_date_review fires from flush_act during the parse, so suppress it
    # for the duration of a write=False run.
    global _SUPPRESS_DATE_REVIEW
    _prev_suppress = _SUPPRESS_DATE_REVIEW
    _SUPPRESS_DATE_REVIEW = (not write) or _prev_suppress
    try:
        return _parse_volume_inner(
            session_label, scratch, ocr_path, out_path, volume_year, write)
    finally:
        _SUPPRESS_DATE_REVIEW = _prev_suppress


def _parse_volume_inner(session_label, scratch, ocr_path, out_path,
                        volume_year, write):
    raw_ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
    page_ocr_results = {int(k): v for k, v in raw_ocr.items()}
    lines = []
    for pidx in sorted(page_ocr_results.keys()):
        for line in page_ocr_results[pidx].get("consensus_text", "").split("\n"):
            lines.append((pidx, line))
    acts_parsed, acts_flagged = [], []
    current_token = current_page = None
    current_buf = []
    act_order = 0  # sequential counter within this volume (0-based)
    for i, (pidx, line) in enumerate(lines):
        is_hdr, token = header_starts_act(lines, i)
        if is_hdr:
            if current_token is not None:
                flush_act(current_token, current_page, current_buf,
                          acts_parsed, acts_flagged, page_ocr_results,
                          volume_year=volume_year, session_label=session_label,
                          in_act_order=act_order)
                act_order += 1
            current_token, current_page, current_buf = token, pidx, [line]
        elif current_token is not None:
            current_buf.append(line)
    if current_token is not None:
        flush_act(current_token, current_page, current_buf,
                  acts_parsed, acts_flagged, page_ocr_results,
                  volume_year=volume_year, session_label=session_label,
                  in_act_order=act_order)
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(
            {"confident_acts": acts_parsed, "flagged_acts": acts_flagged}, indent=2),
            encoding="utf-8")
        log("STAGE5-PARSE", session_label + ": confident=" + str(len(acts_parsed))
            + " flagged=" + str(len(acts_flagged)) + " | wrote " + out_path.name, "OK")
    else:
        log("STAGE5-PARSE", session_label + ": confident=" + str(len(acts_parsed))
            + " flagged=" + str(len(acts_flagged)) + " | DRY-RUN, nothing written", "OK")
    return {"confident": acts_parsed, "flagged": acts_flagged,
            "page_count": len(page_ocr_results), "mean_agreement":
            round(sum(v.get("agreement_ratio", 0) for v in page_ocr_results.values())
                  / max(1, len(page_ocr_results)), 4)}


# ===========================================================================
# STAGE 6 INGEST -- faithful copy of pipeline STAGE6 + re_ingest_fixed purge
# ===========================================================================
def ingest_volume(session_label, parse_result):
    scratch = SCRATCH_ROOT / ("production-" + session_label)
    confident_acts = parse_result["confident"]
    total_pages = parse_result["page_count"]
    mean_agree = parse_result["mean_agreement"]
    # (NITPICK-1) Guard against malformed labels.
    _sy_match = re.match(r'(\d{4})', session_label)
    if not _sy_match:
        log("STAGE6-INGEST", session_label + ": cannot parse 4-digit year from label -- skipping", "FAIL")
        return
    start_year = int(_sy_match.group(1))
    session_str, legis_num = LEGISLATURE_MAP[session_label]

    sha_path = scratch / "sha256.txt"
    computed_sha = sha_path.read_text(encoding="utf-8").strip() if sha_path.exists() else ""
    if not computed_sha:
        log("STAGE6-INGEST", session_label + ": sha256.txt missing -- cannot key source_document", "FAIL")
        return

    # Idempotency: if a PRODUCTION row already has this SHA, the volume is loaded.
    existing_prod = psql_query(
        "SELECT id FROM source_document WHERE content_sha256 = '" + computed_sha
        + "' AND page_count IS NOT NULL;")

    citation_str = "Stats. " + session_label + ", Statutes of California"
    note_str = safe_str("Produced by ocr_only_5090.py + ingest_from_ocr.py session="
                        + session_label + " mean_agree=" + str(mean_agree), 300)
    source_url = ("https://clerk.assembly.ca.gov/sites/clerk.assembly.ca.gov/files/"
                  "archive/Statutes/" + str(start_year) + "/" + session_label + "_Statutes.pdf")
    ocr_engine_str = "surya+doctr+tesseract-5"

    # Find skeleton row (pipeline-style: 'CA Statutes <label>%' with NULL sha)
    skeleton = psql_query(
        "SELECT id FROM source_document WHERE citation LIKE 'CA Statutes "
        + session_label + "%' AND content_sha256 IS NULL LIMIT 1;")

    if existing_prod:
        src_doc_id = int(existing_prod)
        log("STAGE6-INGEST", session_label + ": production source_document exists id="
            + str(src_doc_id) + " -- reusing (will purge+re-ingest acts idempotently)", "OK")
    elif skeleton:
        src_doc_id = int(skeleton)
        upd = ("UPDATE source_document SET citation='" + citation_str
               + "', source_uri='" + safe_str(source_url, 500)
               + "', scan_quality='good', ocr_engine='" + ocr_engine_str
               + "', ocr_cer_estimate=0.015, trust_level='ocr_uncertain', retrieved_at=NOW(),"
               + " clean_channel=true, content_sha256='" + computed_sha
               + "', claimed_year=" + str(start_year) + ", edition_year=" + str(start_year)
               + ", coverage_start_year=" + str(start_year) + ", coverage_end_year=" + str(start_year)
               + ", verification_note='" + note_str + "', file_name='" + session_label
               + "_Statutes.pdf', page_count=" + str(total_pages) + " WHERE id=" + str(src_doc_id) + ";")
        psql_query(upd)
        log("STAGE6-INGEST", session_label + ": updated skeleton source_document id=" + str(src_doc_id), "OK")
    else:
        ins = ("INSERT INTO source_document (type, citation, jurisdiction, source_channel,"
               " source_uri, scan_quality, ocr_engine, ocr_cer_estimate, trust_level,"
               " retrieved_at, clean_channel, content_sha256, edition_year, claimed_year,"
               " verification_note, file_name, corpus, coverage_start_year, coverage_end_year,"
               " page_count, media_format) VALUES ('session_law', '" + citation_str
               + "', 'CA', 'clerk.assembly.ca.gov', '" + safe_str(source_url, 500)
               + "', 'good', '" + ocr_engine_str + "', 0.015, 'ocr_uncertain', NOW(), true, '"
               + computed_sha + "', " + str(start_year) + ", " + str(start_year) + ", '"
               + note_str + "', '" + session_label + "_Statutes.pdf', 'uncodified_statutes', "
               + str(start_year) + ", " + str(start_year) + ", " + str(total_pages)
               + ", 'pdf') ON CONFLICT DO NOTHING RETURNING id;")
        rid = psql_query(ins)
        if rid:
            src_doc_id = int(rid)
        else:
            src_doc_id = int(psql_query("SELECT id FROM source_document WHERE content_sha256='"
                                        + computed_sha + "';"))
        log("STAGE6-INGEST", session_label + ": inserted new source_document id=" + str(src_doc_id), "OK")

    # ---- Scoped idempotent purge of prior acts for THIS source_document -----
    purge_before = psql_query("SELECT count(*) FROM enactment WHERE source_document_id=" + str(src_doc_id) + ";")
    psql_query("DELETE FROM provision_version WHERE source_document_id=" + str(src_doc_id)
               + " OR source_change_event_id IN (SELECT id FROM change_event WHERE source_document_id="
               + str(src_doc_id) + ");")
    psql_query("DELETE FROM designation_history dh USING provision p, change_event ce "
               "WHERE dh.provision_id=p.id AND ce.provision_id=p.id AND ce.source_document_id="
               + str(src_doc_id) + ";")
    psql_query("DELETE FROM change_event WHERE source_document_id=" + str(src_doc_id) + ";")
    psql_query("DELETE FROM provision p WHERE p.jurisdiction='CA' AND p.unit_type='act_section' "
               "AND NOT EXISTS (SELECT 1 FROM change_event ce WHERE ce.provision_id=p.id) "
               "AND NOT EXISTS (SELECT 1 FROM designation_history dh WHERE dh.provision_id=p.id) "
               "AND p.current_designation LIKE 'Stats. " + session_label + " %';")
    psql_query("DELETE FROM enactment WHERE source_document_id=" + str(src_doc_id) + ";")
    log("STAGE6-INGEST", session_label + ": purged prior enactments=" + str(purge_before)
        + " | ingesting " + str(len(confident_acts)) + " confident acts", "OK")

    enact_inserted = prov_inserted = ce_inserted = errors = 0
    for order_idx, act in enumerate(confident_acts):
        chap_num = act.get("chapter_int", 0)
        act_citation = "Stats. " + session_label + " ch. " + str(chap_num)
        iso_date = act.get("iso_date") or ""
        operative_date = iso_date if iso_date else (str(start_year) + "-01-01")
        title_esc = safe_str(act.get("title", ""), 500)
        text_esc = safe_str(act.get("text", ""), 8000)
        source_page = act.get("source_page", 0)
        try:
            e_sql = ("INSERT INTO enactment (source_document_id, citation, jurisdiction,"
                     " session, legislature, chapter_number, chaptered_date, effective_date,"
                     " operative_date, title, bill_number, kind) VALUES (" + str(src_doc_id)
                     + ", '" + act_citation + "', 'CA', '" + safe_str(session_str, 100) + "', '"
                     + safe_str(legis_num, 50) + "', " + str(chap_num) + ", '" + operative_date
                     + "', '" + operative_date + "', '" + operative_date + "', '" + title_esc
                     + "', NULL, 'statute') RETURNING id;")
            enact_id = int(psql_query(e_sql))
            enact_inserted += 1
        except Exception as e:
            log("STAGE6-INGEST", session_label + " ch." + str(chap_num) + ": enactment FAIL: "
                + str(e)[:120], "WARN")
            errors += 1
            continue
        try:
            desig = "Stats. " + session_label + " ch. " + str(chap_num)
            p_sql = ("INSERT INTO provision (jurisdiction, unit_type, current_designation, status)"
                     " VALUES ('CA', 'act_section', '" + safe_str(desig, 200) + "', 'active') RETURNING id;")
            prov_id = int(psql_query(p_sql))
            prov_inserted += 1
        except Exception as e:
            log("STAGE6-INGEST", session_label + " ch." + str(chap_num) + ": provision FAIL: "
                + str(e)[:120], "WARN")
            errors += 1
            continue
        try:
            desig_esc = safe_str(desig, 200)
            dh_sql = ("INSERT INTO designation_history (provision_id, code, section_number, label,"
                      " valid_range) VALUES (" + str(prov_id) + ", 'Statutes of California "
                      + session_label + "', '" + str(chap_num) + "', '" + desig_esc + "', '["
                      + operative_date + ",)');")
            psql_query(dh_sql)
        except Exception as e:
            log("STAGE6-INGEST", session_label + " ch." + str(chap_num) + ": designation_history WARN: "
                + str(e)[:100], "WARN")
        try:
            page_ref = "p. " + str(source_page)
            ce_sql = ("INSERT INTO change_event (enactment_id, provision_id, action, new_text,"
                      " operative_date, in_act_order, chaptered_out, trust_level, source_document_id,"
                      " page_ref) VALUES (" + str(enact_id) + ", " + str(prov_id) + ", 'enact', '"
                      + text_esc + "', '" + operative_date + "', " + str(order_idx)
                      + ", false, 'ocr_uncertain', " + str(src_doc_id) + ", '" + page_ref + "') RETURNING id;")
            psql_query(ce_sql)
            ce_inserted += 1
        except Exception as e:
            log("STAGE6-INGEST", session_label + " ch." + str(chap_num) + ": change_event FAIL: "
                + str(e)[:120], "WARN")
            errors += 1

    log("STAGE6-INGEST", session_label + ": enactments=" + str(enact_inserted)
        + " provisions=" + str(prov_inserted) + " change_events=" + str(ce_inserted)
        + " errors=" + str(errors), "OK" if errors == 0 else "WARN")

    # Running totals
    try:
        sd = psql_query("SELECT count(*) FROM source_document;")
        en = psql_query("SELECT count(*) FROM enactment;")
        pv = psql_query("SELECT count(*) FROM provision;")
        ce = psql_query("SELECT count(*) FROM change_event;")
        log("STAGE6-INGEST", session_label + ": DB TOTALS source_document=" + sd
            + " enactment=" + en + " provision=" + pv + " change_event=" + ce, "OK")
    except Exception as e:
        log("STAGE6-INGEST", session_label + ": total count failed: " + str(e)[:80], "WARN")


# ===========================================================================
# MAIN
# ===========================================================================
# Guard: importing this module (e.g. by tests) must be side-effect-free.
# All DB / file I/O below only runs when executed directly.  (NITPICK-2 fix)
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingest_from_ocr.py <session_label> [<session_label> ...]")
        sys.exit(1)

    volumes = [a.strip() for a in sys.argv[1:]]
    log("INGEST", "=== ingest_from_ocr.py start: " + ", ".join(volumes) + " ===", "OK")
    for vol in volumes:
        if vol not in LEGISLATURE_MAP:
            log("INGEST", vol + ": not in LEGISLATURE_MAP -- skipping", "FAIL")
            continue
        pr = parse_volume(vol)
        if pr is None:
            continue
        ingest_volume(vol, pr)
    log("INGEST", "=== ingest_from_ocr.py done ===", "OK")
