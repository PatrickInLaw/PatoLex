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

# ---------------------------------------------------------------------------
# DATE REVIEW WORKLIST
# ---------------------------------------------------------------------------
# When a parsed date's year falls OUTSIDE the ±YEAR_CLAMP_WINDOW, it is an
# OCR-error suspect.  The act is NOT silently committed with a wrong date;
# instead the match is appended here so a human can review and correct it.
# Location: next to the existing run-logs so the same review workflow applies.
DATE_REVIEW_WORKLIST = Path(
    r"C:\Users\PatrickKolasinski\Documents\GitHub\patolex"
    r"\docs\80_PROJECT_HISTORY\run-logs\date-review-worklist.jsonl"
)


def _append_date_review(record: dict):
    """Append one JSON record (no trailing comma) to the date review worklist.

    The file is append-only; each line is a standalone JSON object (JSONL).
    Fields: session_label, volume_year, raw_match, parsed_year, chapter,
            source_page, in_act_order, timestamp_utc.
    Only call when a date WAS found by a regex but its year is implausible.
    """
    line = json.dumps(record, ensure_ascii=False) + "\n"
    DATE_REVIEW_WORKLIST.parent.mkdir(parents=True, exist_ok=True)
    with open(str(DATE_REVIEW_WORKLIST), "a", encoding="utf-8") as fh:
        fh.write(line)

SCRATCH_ROOT = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch")
LOG_FILE = Path(
    r"C:\Users\PatrickKolasinski\Documents\GitHub\patolex"
    r"\docs\80_PROJECT_HISTORY\run-logs\resume-5090-run.log"
)
PSQL = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"

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
HEADER_RE = re.compile(
    r"^[^A-Za-z0-9]*"
    r"(?:[Cc][HhUuNnRrAaOoEe][AaRrVvPpOo][PpVvRrTt]?[a-zA-Z]{0,3}\.?\s*"
    r"|[Cc][Hh][Aa][Pp][Tt][Ee][Rr]\s*)"
    r"\.?\s*"
    r"([IVXLCDMivxlcdm0-9JjTtYyLl!|]{1,8})"
    r"\s*[.,;:]?"
    r"(?:\s*[" + _DASH + r"].*)?$",
    re.I,
)
AN_ACT_RE = re.compile(r"\bAn?\s+A[CEO][TI]\b", re.IGNORECASE)
ENACT_MARKER_RE = re.compile(
    r"People\s+of\s+the\s+State\s+of\s+California"
    r"|do\s+enact\s+as\s+follow",
    re.I,
)
_MONTHS = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?"
    r"|May|Mav"
    r"|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?"
    r"|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_KW = r"(?:A[Pp]{1,3}[Rr]{1,3}[Oo]?[Vv]\w{0,6}|Pass(?:ed)?)"
# Year broadened from the old 18[3-9]\d (1830-1899, which caused the
# confirmed 1900 date-cliff) to 1850-2008+: (?:18|19|20)\d\d.
_YEAR = r"((?:18|19|20)\d\d)"
APPROVED_RE = re.compile(
    _KW + r"\s*[,.]?\s*" + r"(" + _MONTHS + r")"
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
_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_ROMAN_OCR_SUBST = {"J": "I", "T": "I", "1": "I", "!": "I", "|": "I"}


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
            return int(t)
        except ValueError:
            return 0
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
    return val


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

    return None, ""


def has_enact_marker(full_text):
    return bool(ENACT_MARKER_RE.search(full_text))


def is_confident_act(full_text, volume_year=None):
    has_an_act = bool(AN_ACT_RE.search(full_text))
    has_date, _ = parse_act_date(full_text, volume_year=volume_year)
    return has_an_act and has_date is not None and len(full_text.strip()) >= 100


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
        "text": body_text[:6000], "source_page": (start_page or 0) + 1,
        "confident": confident,
        "page_agreement_ratio": page_ocr_results.get(start_page, {}).get("agreement_ratio", 0.0),
    }
    (acts_parsed if confident else acts_flagged).append(act_rec)


def parse_volume(session_label):
    scratch = SCRATCH_ROOT / ("production-" + session_label)
    ocr_path = scratch / "ocr_consensus" / "page_ocr_results.json"
    out_path = scratch / "parsed_acts_fixed.json"
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
    out_path.write_text(json.dumps(
        {"confident_acts": acts_parsed, "flagged_acts": acts_flagged}, indent=2),
        encoding="utf-8")
    log("STAGE5-PARSE", session_label + ": confident=" + str(len(acts_parsed))
        + " flagged=" + str(len(acts_flagged)) + " | wrote " + out_path.name, "OK")
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
