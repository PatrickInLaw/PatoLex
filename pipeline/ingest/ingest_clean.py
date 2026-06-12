"""
ingest_clean.py -- Clean, transactional, UTF-8-faithful act ingest (Phase B).
===============================================================================
Single canonical ingest path that replaces the three divergent scripts
(production_pipeline STAGE6 / re_ingest_fixed / ingest_from_ocr). Fixes Hans
F5/F6/F7/F8/F11/F13.

WHAT CHANGED vs the old ingest (and WHY)
  F5  No more `safe_str` ASCII errors="replace" and no hand-escaped SQL string
      concat. Inserts are **psycopg parameterized** (`%s` placeholders), so §,
      long-s, em-dashes, accents survive verbatim — full UTF-8 committed text.
  F6  The WHOLE VOLUME runs in ONE transaction (the scoped purge + every act's
      enactment + provision + designation_history + change_event). Any failure ->
      rollback the ENTIRE volume (all acts or none) + raise (Hans S2-B: the old
      per-act commit left acts 0..N-1 durably committed on a mid-volume failure).
      The volume is NEVER marked done on a partial ingest, so a gap is always
      revisited, never silent.

  C1  RE-INGEST REPLACES, NEVER SKIPS (Hans pass-3). Inside the volume txn,
      BEFORE the insert loop, ALL prior rows for the resolved source_document are
      PURGED (provision_version, designation_history, change_event, orphan
      provision, enactment). The old EXISTS skip-on-existing + ON CONFLICT DO
      NOTHING are REMOVED — they silently discarded the new consensus text and
      kept lossy version-A. Re-running is now idempotent (purge + reinsert).

  C3  source_document is resolved by content_sha256 (the volume's content
      identity, read from sha256.txt — same source the registry used), NOT by a
      citation LIKE + ORDER BY id (which landed on the stale 1850 skeleton id=1).
      Resolution FAILS LOUD on zero or multiple matches, and explicitly refuses
      the stale 1850 id=1 duplicate.
  F7  ONE within-run physical-act key everywhere: (source_document_id,
      in_act_order). in_act_order is the 0-indexed ordinal position of the act
      in the parsed volume — it survives a garbled chapter number. Chapter
      number is best-effort DISPLAY only, never a dedup key.
      HONESTY (Hans C4): this key is stable ONLY WITHIN A SINGLE PARSE RUN. If
      the parser's act ordering changes between runs, in_act_order N can denote
      a DIFFERENT physical act. That is fine here because the re-ingest does NOT
      match on this key across runs — it PURGES every row for the source_document
      first (see commit_volume / C1) and re-inserts from scratch, so the key only
      ever needs to be unique within the one run that writes it. It is NOT a
      cross-version-stable identity, and nothing treats it as one.
  F8  No hardcoded ocr_cer_estimate=0.015 / scan_quality='good'. The per-volume
      OCR quality estimate is derived from the consensus per-token confidence
      (mean token confidence -> rough CER proxy); scan_quality is bucketed from
      it. Honest, computed, per-volume.
  F11 chapter_number that required an OCR substitution to parse (e.g. roman
      numeral recovered via J->I / 1->I, or any non-clean numeral) is flagged
      confident=False and carries a 'chapter_ocr_substituted' provenance note;
      the change_event trust_level stays 'ocr_uncertain'.
  F13 NO fabricated dates. If a real Approved/Passed date was parsed, it is used
      as operative_date. If NOT, operative_date is committed as NULL with a
      'date_unknown' flag — never the old {year}-01-01 fiction masquerading as a
      parsed date.

DETERMINISM
  Acts are ingested in parsed order (in_act_order = enumerate index). No dict /
  set iteration drives any committed value. Same input -> same rows.

DRY-RUN (this run)
  Default mode is DRY-RUN: it reads the banked parsed acts + the consensus,
  builds the EXACT parameter tuples it WOULD insert, and prints counts + sample
  rows. It opens NO database connection and imports psycopg lazily only when
  --commit is passed. So running it now, while version-A's ingest loop is live,
  touches nothing.

  --commit  : NOT used yet. When run, connects via PATOLEX_PG_DSN (or the
              individual PG* env vars), and performs the transactional inserts.
              Left un-exercised in Phase B per the no-DB-writes constraint.

INPUT
  Per volume <label>:
    parsed acts JSON  (the parser's confident_acts; same shape as
                       ingest_from_ocr.parse_volume output: chapter_int,
                       chapter_raw, title, iso_date, text, source_page, ...)
    consensus per page (optional) for the per-volume quality estimate.
  This module does NOT re-parse or re-OCR; it consumes banked artifacts.

USAGE
  python ingest_clean.py 1858                 # dry-run one volume
  python ingest_clean.py 1858 1861 1862       # dry-run several
  python ingest_clean.py 1858 --commit        # (DEFERRED — do not run in Phase B)
"""

from __future__ import annotations

import os
import re
import sys
import json
import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple
import config

SCRATCH_ROOT = Path(config.path_for("data_root"))
REPO = Path(r"C:\Users\PatrickKolasinski\Documents\GitHub\PatoLex")
LOG_FILE = REPO / "docs" / "80_PROJECT_HISTORY" / "run-logs" / "phaseB-build-run.log"

# Banked per-token consensus artifact name (Phase C disagreement / review
# substrate). Written ALONGSIDE page_ocr_results.json, under ocr_consensus/.
CONSENSUS_OUTPUT_NAME = "consensus_output.json"

# A page is bucketed by its consensus page_confidence (mean per-token confidence,
# weighted by engines present). Thresholds are honest, not tuned to flatter.
PAGE_HIGH_CONF = 0.98   # confidence >  this -> "high"
PAGE_MED_CONF = 0.93    # confidence >  this (and <= HIGH) -> "med"; else "low"

# session_label -> (session_str, legislature_ordinal). Superset of both old maps.
# TODO: LEGISLATURE_MAP is duplicated in pipeline/5080/ingest_from_ocr.py.
#       Consolidate into a shared module when the two pipelines are unified.
LEGISLATURE_MAP = {
    "1850": ("1849-1850", "1st"), "1851": ("1851", "2nd"), "1852": ("1852", "3rd"),
    "1853": ("1853", "4th"), "1854": ("1854", "5th"), "1855": ("1855", "6th"),
    "1856": ("1856", "7th"), "1857": ("1857", "8th"), "1858": ("1858", "9th"),
    "1859": ("1859", "10th"), "1860": ("1860", "11th"), "1861": ("1861", "12th"),
    "1862": ("1862", "13th"), "1863": ("1863", "14th"),
    "1863-64": ("1863-64 adjourned", "15th"), "1865-66": ("1865-66", "16th"),
    "1867-68": ("1867-68", "17th"), "1869-70": ("1869-70", "18th"),
    "1871-72": ("1871-72", "19th"), "1873-74": ("1873-74", "20th"),
    "1873-74-code": ("1873-74", "20th"),
    "1875-76": ("1875-76", "21st"), "1875-76-code": ("1875-76", "21st"),
    # -----------------------------------------------------------------------
    # 22nd–57th ordinal era (1877–1948)
    # CRITICAL: keys are the EXACT production-folder labels (the part after
    # "production-"). Every suffix variant of the same session maps to the
    # same (session_str, legislature_ordinal). Resolved ambiguities noted.
    # session_str format: "<year> Regular Session" for ordinary sessions;
    # printed extraordinary-session name for special ones.
    # -----------------------------------------------------------------------
    # 22nd Legislature, 1877-78
    "1877-78": ("1877 Regular Session", "22nd"), "1877-78-code": ("1877 Regular Session", "22nd"),
    # 23rd Legislature, 1880
    "1880": ("1880 Regular Session", "23rd"), "1880-code": ("1880 Regular Session", "23rd"),
    # 24th Legislature, 1881
    "1881": ("1881 Regular Session", "24th"),
    # 25th Legislature, 1883-84
    # "1883-84" = 1884 Extra Session (verified title page); "1883-84-regular" = 1883 regular session.
    "1883-84": ("1884 Extra Session", "25th"), "1883-84-regular": ("1883 Regular Session", "25th"),
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
    # 34th Legislature, 1901 — folder "1900-01" documents the 34th Session (resolved)
    "1900-01": ("1901 Regular Session", "34th"),
    # 35th Legislature, 1903
    "1903": ("1903 Regular Session", "35th"),
    # 36th Legislature = 1905. Folder "1906-07" documents the 37th Session, 1907
    # (verified via title page: "SENATORS—THIRTY-SEVENTH SESSION, 1907"; span-label
    # documents the LATER year, same pattern as 1907-09 -> 38th/1909).
    "1905": ("1905 Regular Session", "36th"), "1906-07": ("1907 Regular Session", "37th"),
    # 38th Legislature, 1909 — folder "1907-09" documents the 38th Session (resolved)
    "1907-09": ("1909 Regular Session", "38th"),
    # 39th Legislature, 1911
    # NOTE: "1910-11" folder's session determined by year prefix (1910 = even →
    # second half of 39th Legislature, 1911 session)
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
    # 46th Legislature, 1925
    "1925-vol1-chapters": ("1925 Regular Session", "46th"),
    # 47th Legislature, 1927
    # "1927-vol1-26chapters" = 1926 Extra Session of the 46th Legislature (verified ADD).
    "1927-vol1-chapters": ("1927 Regular Session", "47th"),
    "1927-vol1-26chapters": ("1926 Extra Session", "46th"),
    # 48th Legislature, 1929
    # "1929-vol1-28chapters" = 1928 Extra Session of the 47th Legislature (verified ADD).
    "1929-vol1-chapters": ("1929 Regular Session", "48th"),
    "1929-vol1-28chapters": ("1928 Extra Session", "47th"),
    "1929-vol1-29chapters": ("1929 Regular Session", "48th"),
    # 49th Legislature, 1931
    "1931-vol1-chapters": ("1931 Regular Session", "49th"),
    # 50th Legislature, 1933
    "1933-vol1-chapters": ("1933 Regular Session", "50th"),
    # 51st Legislature, 1935
    # "1935-vol1-34chapters" = 1934 Extra Session of the 50th Legislature (verified).
    # "1935-vol1-chapters"   = 1935 Regular Session of the 51st Legislature (verified).
    "1935-vol1-34chapters": ("1934 Extra Session", "50th"),
    "1935-vol1-chapters": ("1935 Regular Session", "51st"),
    # 52nd Legislature, 1937
    "1937-vol1-chapters": ("1937 Regular Session", "52nd"),
    # 1938 Extra Session of the 52nd Legislature (verified title page: "EXTRA SESSION
    # OF THE FIFTY-SECOND LEGISLATURE", Gov. Merriam proclamation; distinct from 52nd regular 1937).
    "1938-vol1-chapters": ("1938 Extra Session", "52nd"),
    # 53rd Legislature, 1939
    "1939-vol1-chapters": ("1939 Regular Session", "53rd"),
    # 54th Legislature, 1941
    # "1941-vol1-41chapters" = 1941 Regular Session of the 54th Legislature (the only 1941 vol).
    # "1943-vol1-42chapters" = 1941 1st Extra Session of the 54th Legislature (mislabeled folder).
    "1941-vol1-41chapters": ("1941 Regular Session", "54th"),
    # 55th Legislature, 1943
    # "1943-vol1-42chapters" contains the 1941 1st Extra Session (mislabeled folder — session is 1941/42).
    "1943-vol1-42chapters": ("1941 1st Extra Session", "54th"),
    "1943-vol1-chapters": ("1943 Regular Session", "55th"),
    # 56th Legislature, 1945
    "1945-vol1-chapters": ("1945 Regular Session", "56th"),
    # 57th Legislature, 1947-48
    # "1947-vol1-46chapters" = 1946 1st Extraordinary Session of the 56th Legislature (verified).
    # "1947-vol1-chapters"   = 1947 Regular Session of the 57th Legislature (verified).
    # "1948-vol1-chapters"   = 1948 Regular Session of the 57th Legislature (verified).
    "1947-vol1-46chapters": ("1946 1st Extraordinary Session", "56th"),
    "1947-vol1-chapters": ("1947 Regular Session", "57th"),
    "1948-vol1-chapters": ("1948 Regular Session", "57th"),
    # -----------------------------------------------------------------------
    # Year-based era (1949-50 onward) — California abandoned ordinals.
    # legislature field carries the 2-year term string, e.g. "1949-50".
    # Even-year folders belong to the preceding odd-year-started term.
    # session_str format: "<year> Regular Session" or "<year> [Nth] Extraordinary Session".
    # -----------------------------------------------------------------------
    # 1949-50 session
    # "1949-vol1-49chapters-prior" = 1949 1st Extraordinary Session (verified).
    # "1949-vol1-chapters"         = 1949 Regular Session (verified).
    # "1950-vol1-chapters"         = 1950 Regular Session (verified).
    "1949-vol1-49chapters-prior": ("1949 1st Extraordinary Session", "1949-50"),
    "1949-vol1-chapters": ("1949 Regular Session", "1949-50"),
    "1950-vol1-chapters": ("1950 Regular Session", "1949-50"),
    # 1951-52 session
    # "1951-vol1-50chapters" = 1950 3rd Extraordinary Session (verified).
    # "1951-vol1-chapters"   = 1951 Regular Session (verified).
    # "1951-vol2-chapters"   = 1951 Regular Session (verified).
    "1951-vol1-50chapters": ("1950 3rd Extraordinary Session", "1949-50"),
    "1951-vol1-chapters": ("1951 Regular Session", "1951-52"),
    "1951-vol2-chapters": ("1951 Regular Session", "1951-52"),
    # 1953-54 session
    # "1953-vol1-52chapters" = 1952 Regular Session (verified, even-year → 1951-52 term).
    # "1953-vol1-chapters"   = 1953 Regular Session (verified).
    # "1953-vol2-chapters"   = 1953 Regular Session (verified).
    "1953-vol1-52chapters": ("1952 Regular Session", "1951-52"),
    "1953-vol1-chapters": ("1953 Regular Session", "1953-54"),
    "1953-vol2-chapters": ("1953 Regular Session", "1953-54"),
    # 1955-56 session
    # "1955-vol1-54chapters" = 1954 Regular Session (verified, even-year → 1953-54 term).
    # "1955-vol1-55chapters" = 1955 Regular Session (verified).
    # "1955-vol1-chapters"   = 1955 Regular Session (verified).
    # "1955-vol2-chapters"   = 1955 Regular Session (verified).
    "1955-vol1-54chapters": ("1954 Regular Session", "1953-54"),
    "1955-vol1-55chapters": ("1955 Regular Session", "1955-56"),
    "1955-vol1-chapters": ("1955 Regular Session", "1955-56"),
    "1955-vol2-chapters": ("1955 Regular Session", "1955-56"),
    # 1957-58 session
    # "1957-vol1-56chapters"  = 1956 Regular Session (verified, even-year → 1955-56 term).
    # "1957-vol1-57chapters"  = 1957 Regular Session (verified).
    # "1957-vol1-chapters"    = 1957 Regular Session (inferred — normalize).
    # "1957-vol2-57chapters"  = 1957 Regular Session (verified).
    "1957-vol1-56chapters": ("1956 Regular Session", "1955-56"),
    "1957-vol1-57chapters": ("1957 Regular Session", "1957-58"),
    "1957-vol1-chapters": ("1957 Regular Session", "1957-58"),
    "1957-vol2-57chapters": ("1957 Regular Session", "1957-58"),
    # 1959-60 session
    # "1959-vol1-58chapters" = 1958 Regular Session (verified, even-year → 1957-58 term).
    # "1959-vol1-59chapters" = 1959 Regular Session (verified).
    # "1959-vol1-chapters"   = 1959 Regular Session (inferred — normalize).
    # "1959-vol2-chapters"   = 1959 Regular Session (verified).
    "1959-vol1-58chapters": ("1958 Regular Session", "1957-58"),
    "1959-vol1-59chapters": ("1959 Regular Session", "1959-60"),
    "1959-vol1-chapters": ("1959 Regular Session", "1959-60"),
    "1959-vol2-chapters": ("1959 Regular Session", "1959-60"),
    # 1961-62 session
    # "1961-vol1-60chapters" = 1960 Regular Session (verified, even-year → 1959-60 term).
    # "1961-vol1-61chapters" = 1961 Regular Session (verified).
    # "1961-vol1-chapters"   = 1961 Regular Session (inferred — normalize).
    # "1961-vol2-chapters"   = 1961 Regular Session (verified).
    "1961-vol1-60chapters": ("1960 Regular Session", "1959-60"),
    "1961-vol1-61chapters": ("1961 Regular Session", "1961-62"),
    "1961-vol1-chapters": ("1961 Regular Session", "1961-62"),
    "1961-vol2-chapters": ("1961 Regular Session", "1961-62"),
    # 1963-64 session
    # "1963-vol1-62chapters" = 1962 Regular Session (verified, even-year → 1961-62 term).
    # "1963-vol1-63chapters" = 1963 Regular Session (verified).
    # "1963-vol1-chapters"   = 1963 Regular Session (inferred — normalize).
    # "1963-vol2-chapters"   = 1963 Regular Session (verified).
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
    # 1989-90 First Extraordinary Session (verified via internal refs + Resolution Ch.1:
    # "1989-90 First Extraordinary Session"; chapters approved Nov 1989, post-Loma Prieta).
    "1990-vol5-firstextra": ("1989-90 1st Extra Session", "1989-90"),
    # 1991-92 session
    "1991-vol1": ("1991 Regular Session", "1991-92"),
    "1991-vol2": ("1991 Regular Session", "1991-92"),
    "1991-vol3": ("1991 Regular Session", "1991-92"),
    "1992-vol1-statutes": ("1992 Regular Session", "1991-92"),
    "1992-vol2": ("1992 Regular Session", "1991-92"),
    "1992-vol3": ("1992 Regular Session", "1991-92"),
    "1992-vol4": ("1992 Regular Session", "1991-92"),
    # 1993-94 session (odd-year start vols + 1994 even-year mid-session vols)
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
}

# A "clean" chapter numeral required no OCR substitution to parse.
# Roman is UPPERCASE-only on purpose: a lowercase 'l' (as in OCR 'Il' for 'II')
# is an OCR artifact the parser had to substitute, so it must NOT count as clean.
_CLEAN_ARABIC = re.compile(r"^\d{1,4}$")
_CLEAN_ROMAN = re.compile(r"^[IVXLCDM]{1,12}$")

_ROMAN_VAL = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(s: str) -> int:
    val = prev = 0
    for c in reversed(s):
        cur = _ROMAN_VAL.get(c, 0)
        val += cur if cur >= prev else -cur
        prev = cur
    return val


def log(phase, description, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    line = f"[{ts}] {phase} | {description} | {status}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.rstrip(), flush=True)


# --------------------------------------------------------------------------- #
# Provenance / quality helpers
# --------------------------------------------------------------------------- #

def chapter_was_ocr_substituted(chapter_raw: str, chapter_int: int) -> bool:
    """
    True if recovering chapter_int from chapter_raw required an OCR substitution
    (Hans F11). A clean arabic ('38') or clean roman ('XII') numeral that parses
    to the same value is NOT a substitution; anything else (J/T/1/!/| -> I, 'l'
    -> I, garbage chars) is.
    """
    raw = (chapter_raw or "").strip().strip(".,;:")
    if not raw:
        return True
    if _CLEAN_ARABIC.match(raw):
        return int(raw) != chapter_int
    if _CLEAN_ROMAN.match(raw):
        # clean UPPERCASE roman: trust only if it actually evaluates to chapter_int
        return _roman_to_int(raw) != chapter_int
    return True  # contained chars only recoverable via substitution (e.g. 'Il','XXITI')


def estimate_volume_quality(
    page_confidences: List[float],
) -> Tuple[Optional[float], str]:
    """
    Honest per-volume OCR quality estimate (Hans F8). Derives a CER proxy from
    the mean consensus per-token confidence: cer_proxy ~= 1 - mean_confidence.
    Buckets scan_quality. Returns (cer_proxy_rounded, scan_quality_bucket).

    If no confidences are available, returns (None, 'unknown') — NOT -1.0
    (Hans S2-C): ocr_cer_estimate carries a `>= 0` CHECK constraint, so an
    "unknown" estimate MUST be committed as SQL NULL, never a sentinel that
    would violate the constraint (or, worse, masquerade as a real CER).
    """
    if not page_confidences:
        return None, "unknown"
    mean_conf = sum(page_confidences) / len(page_confidences)
    cer_proxy = round(max(0.0, 1.0 - mean_conf), 4)
    if cer_proxy <= 0.02:
        bucket = "good"
    elif cer_proxy <= 0.07:
        bucket = "fair"
    else:
        bucket = "poor"
    return cer_proxy, bucket


# --------------------------------------------------------------------------- #
# Planned-row model (what we WOULD insert)
# --------------------------------------------------------------------------- #

@dataclass
class PlannedAct:
    in_act_order: int                 # CANONICAL key part 2 (key part 1 = src_doc_id)
    chapter_int: int
    chapter_raw: str
    citation: str
    title: str
    operative_date: Optional[str]     # ISO date or None (NEVER fabricated)
    date_unknown: bool                # True -> operative_date is NULL, flagged
    chapter_ocr_substituted: bool     # True -> chapter_number is uncertain
    confident: bool                   # False if any uncertainty flag set
    new_text: str                     # full UTF-8 committed text
    page_ref: str
    trust_level: str                  # always 'ocr_uncertain' for this corpus
    designation: str
    section_number: str
    # --- capture-ALL-signals: per-act OCR consensus signal (Phase C substrate) -
    confidence: Optional[float]       # agreement ratio in [0,1] or None (-> NULL)
    ocr_provenance: dict              # full jsonb provenance written to change_event


def _page_index(page_rec: dict, fallback_key) -> Optional[str]:
    """Normalized 1-indexed page-number string for a page_ocr_results record.

    page_ocr_results.json is keyed by page number; records also carry
    'page_1indexed'. We key our consensus cache by the STRING page number so an
    act's source_page (also a string) maps directly with no int/str ambiguity.
    """
    pi = page_rec.get("page_1indexed", fallback_key)
    if pi is None:
        return None
    return str(pi)


def build_page_consensus(session_label: str) -> dict:
    """
    Build the per-page token consensus for a volume ONCE (with per-engine
    candidates captured) and assemble the banked consensus_output.json payload +
    the per-volume distribution stats. Reads only banked artifacts; no DB.

    Returns a dict:
      {
        "by_page": { page_str: ConsensusResult-as-dict-with-low-conf-summary },
        "page_confs": [float, ...],           # for quality estimate
        "stats": { mean/median/high/med/low/engines/n_pages },
        "output_payload": { ... }             # what gets written to consensus_output.json
        "output_path": Path | None
      }
    """
    scratch = SCRATCH_ROOT / ("production-" + session_label)
    ocr_path = scratch / "ocr_consensus" / "page_ocr_results.json"
    out_path = scratch / "ocr_consensus" / CONSENSUS_OUTPUT_NAME
    by_page: dict = {}
    page_confs: List[float] = []
    engines_seen: set = set()
    pages_payload: dict = {}

    if not ocr_path.exists():
        return {
            "by_page": {}, "page_confs": [], "stats": _empty_stats(),
            "output_payload": None, "output_path": None,
        }

    sys.path.insert(0, str(REPO / "pipeline"))
    from ocr.consensus import (  # noqa: E402  (consensus moved to pipeline/ocr/ in the reorg)
        consensus_from_page_record, LOW_CONFIDENCE_THRESHOLD,
    )

    raw = json.loads(ocr_path.read_text(encoding="utf-8"))
    for k, page in raw.items():
        res = consensus_from_page_record(page, capture_candidates=True)
        if not res.n_tokens:
            continue
        page_key = _page_index(page, k)
        page_confs.append(res.page_confidence)
        engines_seen.update(res.engines_used)

        # --- low-confidence (Phase C review) tokens for THIS page -------------
        low_tokens = []
        for t in res.tokens:
            if t.confidence < LOW_CONFIDENCE_THRESHOLD:
                low_tokens.append({
                    "surface": t.surface,
                    "confidence": t.confidence,
                    "n_agree": t.n_agree,
                    "n_present": t.n_present,
                    "candidates": t.candidates or [],
                })

        # banked per-token record (FULL token stream + the low-conf disagreement)
        pages_payload[page_key] = {
            "page_confidence": res.page_confidence,
            "token_agreement_ratio": res.token_agreement_ratio,
            "method": res.method,
            "engines_used": res.engines_used,
            "n_tokens": res.n_tokens,
            "tokens": [
                {
                    "surface": t.surface,
                    "confidence": t.confidence,
                    "n_agree": t.n_agree,
                    "n_present": t.n_present,
                    "candidates": t.candidates or [],
                }
                for t in res.tokens
            ],
            "low_confidence_token_count": len(low_tokens),
        }
        # compact per-page handle the act provenance step uses (avoid re-walking
        # the full token list per act)
        by_page[page_key] = {
            "page_confidence": res.page_confidence,
            "token_agreement_ratio": res.token_agreement_ratio,
            "method": res.method,
            "engines_used": res.engines_used,
            "low_confidence_tokens": low_tokens,
        }

    stats = _distribution_stats(page_confs, sorted(engines_seen))
    output_payload = {
        "session_label": session_label,
        "consensus_module": "consensus.py token_majority (S1-A/S1-B)",
        "low_confidence_threshold": float(
            __import__("consensus").LOW_CONFIDENCE_THRESHOLD
        ),
        "n_pages": len(pages_payload),
        "stats": stats,
        "pages": pages_payload,
    }
    return {
        "by_page": by_page,
        "page_confs": page_confs,
        "stats": stats,
        "output_payload": output_payload,
        "output_path": out_path,
    }


def _empty_stats() -> dict:
    return {
        "mean_agreement": None, "median_agreement": None,
        "high_count": 0, "med_count": 0, "low_count": 0,
        "engines": [], "n_pages": 0,
    }


def _distribution_stats(page_confs: List[float], engines: List[str]) -> dict:
    if not page_confs:
        return {**_empty_stats(), "engines": engines}
    s = sorted(page_confs)
    n = len(s)
    mid = n // 2
    median = s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0
    high = sum(1 for c in page_confs if c > PAGE_HIGH_CONF)
    med = sum(1 for c in page_confs if PAGE_MED_CONF < c <= PAGE_HIGH_CONF)
    low = sum(1 for c in page_confs if c <= PAGE_MED_CONF)
    return {
        "mean_agreement": round(sum(page_confs) / n, 4),
        "median_agreement": round(median, 4),
        "high_count": high, "med_count": med, "low_count": low,
        "engines": engines, "n_pages": n,
    }


def bank_consensus_output(plan: dict) -> Optional[str]:
    """
    Persist the per-token consensus_output.json (Phase C substrate) ALONGSIDE
    page_ocr_results.json. No DB. Idempotent: overwrites with the freshly-derived
    deterministic payload. Returns the written path (or None if no consensus).

    Hans H2: commit_volume calls this ONLY AFTER a successful DB commit, so a
    rolled-back volume never leaves an orphan file dangling off a
    source_document with no committed rows. Idempotence (overwrite) means a
    later successful re-run re-banks cleanly.

    This is what makes the Phase C disagreement/review queue a QUERY over
    persisted data: source_document.ocr_stats.consensus_output_path points here,
    and each change_event.ocr_provenance.disagreement summarizes the per-act slice.
    """
    payload = plan.get("consensus_output_payload")
    path_str = plan.get("consensus_output_path")
    if not payload or not path_str:
        log("INGEST-CONSENSUS",
            f"{plan['session_label']}: no consensus payload to bank "
            f"(no page_ocr_results / no tokens)", "WARN")
        return None
    out_path = Path(path_str)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log("INGEST-CONSENSUS",
        f"{plan['session_label']}: banked {out_path.name} "
        f"({payload['n_pages']} pages, "
        f"low_conf_threshold={payload['low_confidence_threshold']})", "OK")
    return str(out_path)


def _derive_act_page_spans(confident_acts: list) -> List[Tuple[int, int]]:
    """
    Hans H3: derive each act's INCLUSIVE [start_page, end_page] page span so the
    per-act confidence can aggregate over EVERY page the act spans, not just its
    start page.

    SOURCE LIMITATION (documented honestly): the parser records only a single
    `source_page` per act (the act's START page). It does NOT record an end page
    or an explicit page range. We therefore DERIVE the end page as the start
    page of the NEXT act that begins on a strictly later page (minus none — the
    next act may begin on the same page, so the span is inclusive up to that
    next act's start page). For the LAST act we cannot know its end page from
    this data, so its span is just its own start page (single page). This is a
    best-effort span, not a parser-certified one; where it is wrong it can only
    OVER-include a neighbouring page (widening uncertainty), never hide it.

    Deterministic: depends only on the parsed-order source_page sequence.
    """
    starts: List[int] = []
    for a in confident_acts:
        try:
            starts.append(int(str(a.get("source_page", "")).strip() or 0))
        except ValueError:
            starts.append(0)
    n = len(starts)
    spans: List[Tuple[int, int]] = []
    for i, sp in enumerate(starts):
        end = sp
        # find the next act that begins on a strictly later page
        for j in range(i + 1, n):
            if starts[j] > sp:
                end = starts[j]   # inclusive: the next act may share its 1st page
                break
        if end < sp:
            end = sp
        spans.append((sp, end))
    return spans


def _aggregate_span_signal(by_page: dict, start_page: int, end_page: int):
    """
    Aggregate the per-page consensus signals across an act's INCLUSIVE page span
    (Hans H3). Returns (agreement, engines, method, low_tokens, n_present,
    pages_covered, page_ref) using only pages that actually have consensus.

      agreement  = mean page_confidence over covered pages (None if none covered)
      engines    = sorted union of engines across covered pages
      method     = the covered pages' method if unanimous, else "mixed"
      low_tokens = concatenation of low-confidence tokens across ALL covered pages
      n_present  = max engines present on any covered page (page-level proxy)
    """
    covered = []
    for p in range(start_page, end_page + 1):
        pc = by_page.get(str(p))
        if pc is not None:
            covered.append((p, pc))
    if not covered:
        return None, [], None, [], None, [], "p. " + str(start_page)

    confs = [pc["page_confidence"] for _, pc in covered]
    agreement = round(sum(confs) / len(confs), 4)
    engines_set: set = set()
    methods: set = set()
    low_tokens: list = []
    for _, pc in covered:
        engines_set.update(pc["engines_used"])
        methods.add(pc["method"])
        low_tokens.extend(pc["low_confidence_tokens"])
    engines = sorted(engines_set)
    method = methods.pop() if len(methods) == 1 else "mixed"
    n_present = max(len(pc["engines_used"]) for _, pc in covered) or None
    pages_covered = [p for p, _ in covered]
    if start_page == end_page:
        page_ref = "p. " + str(start_page)
    else:
        page_ref = f"pp. {start_page}-{end_page}"
    return agreement, engines, method, low_tokens, n_present, pages_covered, page_ref


def plan_volume(session_label: str) -> dict:
    """
    Build the full set of PlannedActs for a volume from banked artifacts.
    Reads:
      parsed_acts_fixed.json  (confident_acts)  -- required
      ocr_consensus/page_ocr_results.json       -- optional, drives ALL signals
    Does NOT touch the DB. Returns a plan dict.

    capture-ALL-signals: the per-page token consensus is built ONCE (with
    per-engine candidates), banked as consensus_output.json, summarized into
    per-volume ocr_stats, and joined per-act (by source_page) into the act's
    ocr_provenance + confidence. Nothing computed is discarded (Patrick).
    """
    scratch = SCRATCH_ROOT / ("production-" + session_label)
    acts_path = scratch / "parsed_acts_fixed.json"
    if not acts_path.exists():
        raise FileNotFoundError(
            f"{session_label}: parsed_acts_fixed.json not found at {acts_path}"
        )
    data = json.loads(acts_path.read_text(encoding="utf-8"))
    confident_acts = data.get("confident_acts", [])

    session_str, legis_num = LEGISLATURE_MAP.get(
        session_label, (session_label, session_label)
    )

    # ---- per-page consensus (once) + bank consensus_output.json + stats ------
    consensus = {"by_page": {}, "page_confs": [], "stats": _empty_stats(),
                 "output_payload": None, "output_path": None}
    try:
        consensus = build_page_consensus(session_label)
    except Exception as e:  # never fatal — signals are best-effort, ingest still runs
        log("INGEST-PLAN",
            f"{session_label}: consensus build skipped ({str(e)[:80]})", "WARN")

    page_confs = consensus["page_confs"]
    by_page = consensus["by_page"]
    stats = consensus["stats"]
    cer_proxy, scan_quality = estimate_volume_quality(page_confs)

    consensus_output_path = (
        str(consensus["output_path"]) if consensus["output_path"] else None
    )
    ocr_stats = {
        "mean_agreement": stats["mean_agreement"],
        "median_agreement": stats["median_agreement"],
        "high_count": stats["high_count"],
        "med_count": stats["med_count"],
        "low_count": stats["low_count"],
        "engines": stats["engines"],
        "n_pages": stats["n_pages"],
        "consensus_output_path": consensus_output_path,
    }

    # Hans H3: derive each act's inclusive page span ONCE (parsed-order based),
    # so per-act confidence can aggregate across EVERY page the act spans.
    act_spans = _derive_act_page_spans(confident_acts)

    planned: List[PlannedAct] = []
    for idx, act in enumerate(confident_acts):
        chapter_int = int(act.get("chapter_int", 0) or 0)
        chapter_raw = str(act.get("chapter_raw", ""))
        iso_date = (act.get("iso_date") or "").strip()
        date_unknown = not bool(iso_date)
        operative_date = iso_date if iso_date else None  # F13: NEVER fabricate
        chap_subst = chapter_was_ocr_substituted(chapter_raw, chapter_int)

        citation = f"Stats. {session_label} ch. {chapter_int}"
        designation = citation
        confident = (not date_unknown) and (not chap_subst) and chapter_int > 0

        # ---- H3: aggregate the consensus signal across ALL pages this act spans
        # (not just the start page). The parser records only a start page, so the
        # span is derived (see _derive_act_page_spans); the aggregate UNDERSTATES
        # uncertainty no more than the single-page proxy did, and usually states
        # it more honestly (a 4-page act now reflects all 4 pages' agreement +
        # every low-confidence token across them).
        start_page, end_page = act_spans[idx]
        (agreement, engines, method, low_toks, n_present,
         pages_covered, page_ref) = _aggregate_span_signal(
            by_page, start_page, end_page
        )
        # per-token n_agree lives in consensus_output.json; the per-act page-level
        # proxy is the span's aggregate agreement (n_present above).
        n_agree = None

        ocr_provenance = {
            "engines": engines,
            "consensus_method": method,
            "agreement": agreement,
            "chapter_raw": chapter_raw,
            "chapter_ocr_substituted": chap_subst,
            "date_unknown": date_unknown,
            "page_ref": page_ref,
            "n_agree": n_agree,
            "n_present": n_present,
            # H3: the exact pages this act's signal was aggregated over (derived
            # span; start page is parser-certified, end page is derived — see
            # _derive_act_page_spans). page_span_derived flags the limitation.
            "page_span": {
                "start_page": start_page,
                "end_page": end_page,
                "pages_with_consensus": pages_covered,
                "page_span_derived": start_page != end_page,
            },
            "disagreement": {
                # aggregated across ALL covered pages of the act's span (H3),
                # not just the start page.
                "low_confidence_token_count": len(low_toks),
                # cap the inline list so a pathological span can't bloat the row;
                # the FULL per-token stream lives in consensus_output.json, which
                # this provenance references via source_document.ocr_stats.
                "low_confidence_tokens": low_toks[:50],
            },
        }

        planned.append(PlannedAct(
            in_act_order=idx,
            chapter_int=chapter_int,
            chapter_raw=chapter_raw,
            citation=citation,
            title=(act.get("title", "") or "")[:500],
            operative_date=operative_date,
            date_unknown=date_unknown,
            chapter_ocr_substituted=chap_subst,
            confident=confident,
            new_text=act.get("text", "") or "",     # FULL UTF-8, no truncation-mangling
            page_ref=page_ref,
            trust_level="ocr_uncertain",
            designation=designation,
            section_number=str(chapter_int),
            confidence=agreement,                    # None -> SQL NULL (S2-C convention)
            ocr_provenance=ocr_provenance,
        ))

    return {
        "session_label": session_label,
        "session_str": session_str,
        "legislature": legis_num,
        "scan_quality": scan_quality,
        "ocr_cer_estimate": cer_proxy,            # None means unknown -> SQL NULL (S2-C)
        "n_pages_with_consensus": len(page_confs),
        "ocr_stats": ocr_stats,
        "consensus_output_payload": consensus["output_payload"],
        "consensus_output_path": consensus_output_path,
        "acts": planned,
    }


# --------------------------------------------------------------------------- #
# Parameterized SQL (psycopg style: %s placeholders, values passed separately)
# --------------------------------------------------------------------------- #

ENACTMENT_SQL = (
    "INSERT INTO enactment "
    "(source_document_id, citation, jurisdiction, session, legislature, "
    " chapter_number, chaptered_date, effective_date, operative_date, title, "
    " bill_number, kind) "
    "VALUES (%s, %s, 'CA', %s, %s, %s, %s, %s, %s, %s, NULL, 'statute') "
    "RETURNING id;"
)
PROVISION_SQL = (
    "INSERT INTO provision (jurisdiction, unit_type, current_designation, status) "
    "VALUES ('CA', 'act_section', %s, 'active') RETURNING id;"
)
DESIGNATION_SQL = (
    "INSERT INTO designation_history "
    "(provision_id, code, section_number, label, valid_range) "
    "VALUES (%s, %s, %s, %s, %s);"
)
CHANGE_EVENT_SQL = (
    "INSERT INTO change_event "
    "(enactment_id, provision_id, action, new_text, operative_date, in_act_order, "
    " chaptered_out, trust_level, source_document_id, page_ref, "
    " confident, confidence, ocr_provenance) "
    "VALUES (%s, %s, 'enact', %s, %s, %s, false, %s, %s, %s, %s, %s, %s) "
    # Hans C2/C1 DECISION: NO `ON CONFLICT`. commit_volume purges ALL rows for
    # this source_document INSIDE the same transaction BEFORE this insert loop,
    # so there is provably nothing to conflict with: in_act_order = enumerate
    # index is unique by construction within one parse run. A plain INSERT is
    # therefore correct and removes the old apply-order circular dependency
    # (the insert no longer requires the UNIQUE index to pre-exist). The UNIQUE
    # index (migration 0004) is a durable post-ingest GUARANTEE, applied AFTER
    # the re-ingest + zero-dup check — it is not needed for this INSERT to run.
    "RETURNING id;"
)
# Per-volume source_document quality signals (capture-ALL-signals). Writes the
# REAL scan_quality + ocr_cer_estimate (NULL if unknown — never -1.0/hardcoded)
# + the ocr_stats jsonb. Targets the resolved production source_document row.
SOURCE_DOC_UPDATE_SQL = (
    "UPDATE source_document "
    "SET scan_quality = %s, ocr_cer_estimate = %s, ocr_stats = %s "
    "WHERE id = %s;"
)
# --------------------------------------------------------------------------- #
# Hans C1: SCOPED IDEMPOTENT PURGE of ALL prior rows for one source_document.
# --------------------------------------------------------------------------- #
# Runs INSIDE the per-volume transaction, BEFORE the insert loop, so a re-ingest
# REPLACES version-A rather than skipping it (the old EXISTS skip silently
# discarded the new consensus text and kept the lossy version-A rows). Modeled
# on ingest_from_ocr.py:366-381 but parameterized (psycopg %s) and adapted to
# this schema (provision_version carries source_document_id + source_change_
# event_id; provision is purged only when orphaned of BOTH change_event and
# designation_history, and only for THIS volume's designation namespace).
#
# Order matters (FK-safe, child-before-parent):
#   0. lineage_edge       — edges this doc's enactments caused (FK → enactment.id,
#                           provision.id); MUST precede the enactment/provision
#                           deletes or those FKs block. Empty for enact-from-
#                           nothing volumes (1850-1875 pre-code), but covered so
#                           the purge's "ALL prior rows" claim is honest and a
#                           future recodification re-ingest (1872+) does not block.
#   1. provision_version  — read model rows produced from this doc's events
#   2. designation_history — joined to provisions touched by this doc's events
#   3. change_event       — this doc's events
#   4. provision          — now-orphaned act_section provisions for this volume
#   5. enactment          — this doc's enactments
PURGE_COUNT_SQL = (
    "SELECT count(*) FROM enactment WHERE source_document_id = %s;"
)
# Edges are stamped with the enactment that caused them, so scoping by this
# doc's enactments is correct + sufficient: any provision this volume created is
# purged only when orphaned (no surviving event/designation references it), and
# a surviving edge to it would keep it referenced -> not orphaned -> not deleted.
PURGE_LINEAGE_EDGE_SQL = (
    "DELETE FROM lineage_edge "
    "WHERE enactment_id IN "
    "      (SELECT id FROM enactment WHERE source_document_id = %s);"
)
PURGE_PROVISION_VERSION_SQL = (
    "DELETE FROM provision_version "
    "WHERE source_document_id = %s "
    "   OR source_change_event_id IN "
    "      (SELECT id FROM change_event WHERE source_document_id = %s);"
)
PURGE_DESIGNATION_HISTORY_SQL = (
    "DELETE FROM designation_history dh "
    "USING provision p, change_event ce "
    "WHERE dh.provision_id = p.id AND ce.provision_id = p.id "
    "  AND ce.source_document_id = %s;"
)
PURGE_CHANGE_EVENT_SQL = (
    "DELETE FROM change_event WHERE source_document_id = %s;"
)
# Orphan provisions: act_section provisions in THIS volume's designation
# namespace ('Stats. <label> %') that no longer have any change_event or
# designation_history pointing at them (i.e. they were created only by this
# volume's now-deleted events). The LIKE namespace prevents touching other
# volumes' provisions that happen to be orphaned for unrelated reasons.
PURGE_ORPHAN_PROVISION_SQL = (
    "DELETE FROM provision p "
    "WHERE p.jurisdiction = 'CA' AND p.unit_type = 'act_section' "
    "  AND p.current_designation LIKE %s "
    "  AND NOT EXISTS (SELECT 1 FROM change_event ce WHERE ce.provision_id = p.id) "
    "  AND NOT EXISTS (SELECT 1 FROM designation_history dh WHERE dh.provision_id = p.id);"
)
PURGE_ENACTMENT_SQL = (
    "DELETE FROM enactment WHERE source_document_id = %s;"
)


def _daterange(operative_date: Optional[str]) -> str:
    """valid_range for designation_history. Open-bounded if date unknown."""
    if operative_date:
        return f"[{operative_date},)"
    return "(,)"  # unknown lower bound, open upper — honest, not a fake date


def enactment_params(src_doc_id, plan, act: PlannedAct):
    return (
        src_doc_id, act.citation, plan["session_str"], plan["legislature"],
        act.chapter_int, act.operative_date, act.operative_date,
        act.operative_date, act.title,
    )


def build_param_plan(src_doc_id, plan) -> List[dict]:
    """Build the parameter tuples for every act (no DB). For dry-run display."""
    rows = []
    for act in plan["acts"]:
        rows.append({
            "in_act_order": act.in_act_order,
            "enactment": enactment_params(src_doc_id, plan, act),
            "provision": (act.designation,),
            "designation_history": (
                None,  # provision_id filled at commit time
                f"Statutes of California {plan['session_label']}",
                act.section_number, act.designation, _daterange(act.operative_date),
            ),
            "change_event": (
                None, None, act.new_text, act.operative_date, act.in_act_order,
                act.trust_level, src_doc_id, act.page_ref,
                act.confident, act.confidence,
                act.ocr_provenance,  # wrapped as Jsonb at commit time
            ),
            "flags": {
                "confident": act.confident,
                "confidence": act.confidence,
                "date_unknown": act.date_unknown,
                "chapter_ocr_substituted": act.chapter_ocr_substituted,
                "low_confidence_token_count":
                    act.ocr_provenance.get("disagreement", {})
                    .get("low_confidence_token_count", 0),
            },
        })
    return rows


# --------------------------------------------------------------------------- #
# DRY-RUN
# --------------------------------------------------------------------------- #

def dry_run(session_label: str):
    plan = plan_volume(session_label)
    acts = plan["acts"]
    # placeholder src_doc_id for display only; the real id is resolved at commit
    placeholder_src = f"<source_document_id for Stats. {session_label}>"

    n = len(acts)
    n_confident = sum(1 for a in acts if a.confident)
    n_date_unknown = sum(1 for a in acts if a.date_unknown)
    n_chap_subst = sum(1 for a in acts if a.chapter_ocr_substituted)
    n_nonascii = sum(1 for a in acts if any(ord(c) > 127 for c in a.new_text))

    log("INGEST-DRYRUN",
        f"{session_label}: WOULD insert {n} acts "
        f"(confident={n_confident}, date_unknown={n_date_unknown}, "
        f"chapter_ocr_substituted={n_chap_subst}) | "
        f"scan_quality={plan['scan_quality']} cer_est={plan['ocr_cer_estimate']} "
        f"pages_with_consensus={plan['n_pages_with_consensus']} | "
        f"acts_with_nonascii_text={n_nonascii} (UTF-8 preserved)")

    print(f"\n=== DRY-RUN PLAN: Stats. {session_label} ===")
    print(f"  source_document key   : {placeholder_src}")

    # ---- C3: how the source_document WOULD be resolved (by content identity) --
    try:
        sha = _read_volume_sha256(session_label)
        print(f"  resolve by (C3)       : content_sha256 = {sha}")
        print(f"    resolver SQL        : SELECT id FROM source_document "
              f"WHERE content_sha256 = %s ORDER BY id;  -- FAIL if 0 or >1 rows")
        if session_label == "1850":
            print(f"    stale-1850 guard    : refuse if id=1 OR a 'CA Statutes 1850%' "
                  f"id=1 skeleton still exists (manual purge required — see runbook)")
    except RuntimeError as e:
        print(f"  resolve by (C3)       : !! {e}")

    # ---- C1: the SCOPED PURGE that WOULD run inside the txn BEFORE inserts -----
    print(f"\n  --- C1 SCOPED PURGE (WOULD run inside the volume txn, BEFORE inserts) ---")
    print(f"    (replaces version-A; re-ingest is idempotent purge+reinsert; "
          f"skip-on-existing / ON CONFLICT REMOVED)")
    print(f"    1. {PURGE_COUNT_SQL}")
    print(f"    2. {PURGE_PROVISION_VERSION_SQL}")
    print(f"    3. {PURGE_DESIGNATION_HISTORY_SQL}")
    print(f"    4. {PURGE_CHANGE_EVENT_SQL}")
    print(f"    5. {PURGE_ORPHAN_PROVISION_SQL}")
    print(f"       (param: {('Stats. ' + session_label + ' %')!r})")
    print(f"    6. {PURGE_ENACTMENT_SQL}")
    print(f"    change_event INSERT (no ON CONFLICT — plain INSERT post-purge):")
    print(f"      {CHANGE_EVENT_SQL.strip()}")

    print(f"\n  within-run act key    : (source_document_id, in_act_order) "
          f"[unique per parse run; purge+reinsert, NOT cross-version-stable]")
    print(f"  acts to ingest        : {n}")
    print(f"    confident=True      : {n_confident}")
    print(f"    date_unknown        : {n_date_unknown}  (operative_date -> NULL, flagged)")
    print(f"    chapter_ocr_subst   : {n_chap_subst}    (confident=False, flagged)")
    print(f"  per-volume quality    : scan_quality={plan['scan_quality']} "
          f"cer_estimate={plan['ocr_cer_estimate']} "
          f"(from {plan['n_pages_with_consensus']} consensus pages)")
    print(f"  acts w/ non-ASCII text: {n_nonascii} (e.g. §, em-dash preserved verbatim)")

    # ---- WOULD-WRITE: source_document per-volume signal row -------------------
    st = plan["ocr_stats"]
    print("\n  --- source_document UPDATE (per-volume signals; WOULD write) ---")
    print(f"    scan_quality      : {plan['scan_quality']!r}")
    print(f"    ocr_cer_estimate  : {plan['ocr_cer_estimate']!r} "
          f"(None -> SQL NULL, never -1.0/hardcoded)")
    print(f"    ocr_stats (jsonb) : mean_agreement={st['mean_agreement']} "
          f"median_agreement={st['median_agreement']} "
          f"high/med/low={st['high_count']}/{st['med_count']}/{st['low_count']} "
          f"engines={st['engines']} n_pages={st['n_pages']}")
    print(f"    ocr_stats.consensus_output_path: {st['consensus_output_path']!r}")

    # ---- WOULD-BANK: consensus_output.json (no write in dry-run) --------------
    payload = plan.get("consensus_output_payload")
    print("\n  --- consensus_output.json (Phase C substrate; WOULD bank, NOT written in dry-run) ---")
    if payload:
        n_low_pages = sum(
            1 for p in payload["pages"].values()
            if p["low_confidence_token_count"] > 0
        )
        total_low = sum(
            p["low_confidence_token_count"] for p in payload["pages"].values()
        )
        print(f"    path              : {plan['consensus_output_path']}")
        print(f"    pages             : {payload['n_pages']} "
              f"(low_conf_threshold={payload['low_confidence_threshold']})")
        print(f"    pages w/ low-conf : {n_low_pages}  total low-conf tokens: {total_low}")
        # show one sample low-confidence token (the crowd-correction unit)
        sample_low = None
        for p in payload["pages"].values():
            for t in p["tokens"]:
                if t["confidence"] < payload["low_confidence_threshold"]:
                    sample_low = t
                    break
            if sample_low:
                break
        if sample_low:
            print(f"    sample low-conf token: surface={sample_low['surface']!r} "
                  f"conf={sample_low['confidence']} "
                  f"n_agree/n_present={sample_low['n_agree']}/{sample_low['n_present']}")
            print(f"      disagreeing candidates: {sample_low['candidates']}")
    else:
        print("    (no consensus payload — no page_ocr_results.json / no tokens)")

    print("\n  --- SAMPLE ROWS (first 3 acts; parameters shown, values bound, never concatenated) ---")
    for act in acts[:3]:
        print(f"\n  act in_act_order={act.in_act_order} citation={act.citation!r} "
              f"chapter_raw={act.chapter_raw!r} confident={act.confident}")
        print(f"    enactment   params: {enactment_params(placeholder_src, plan, act)}")
        print(f"    provision   params: ({act.designation!r},)")
        print(f"    designation params: (<prov_id>, "
              f"{('Statutes of California ' + session_label)!r}, "
              f"{act.section_number!r}, {act.designation!r}, "
              f"{_daterange(act.operative_date)!r})")
        snippet = act.new_text[:120].replace("\n", " ")
        print(f"    change_event new_text[:120]: {snippet!r}")
        print(f"    change_event operative_date: {act.operative_date!r} "
              f"(NULL = unknown, never fabricated)")
        print(f"    change_event confident     : {act.confident}")
        print(f"    change_event confidence    : {act.confidence!r} "
              f"(real 0-1, None -> SQL NULL)")
        prov = act.ocr_provenance
        print(f"    change_event ocr_provenance: engines={prov['engines']} "
              f"method={prov['consensus_method']!r} agreement={prov['agreement']} "
              f"chapter_raw={prov['chapter_raw']!r} "
              f"chapter_ocr_substituted={prov['chapter_ocr_substituted']} "
              f"date_unknown={prov['date_unknown']} "
              f"n_agree/n_present={prov['n_agree']}/{prov['n_present']}")
        dis = prov["disagreement"]
        print(f"      disagreement: low_confidence_token_count="
              f"{dis['low_confidence_token_count']} "
              f"(inline list capped at 50; full stream in consensus_output.json)")

    # show a flagged example if any
    flagged = [a for a in acts if not a.confident]
    if flagged:
        ex = flagged[0]
        print(f"\n  --- FLAGGED EXAMPLE (confident=False) ---")
        print(f"    in_act_order={ex.in_act_order} citation={ex.citation!r} "
              f"chapter_raw={ex.chapter_raw!r}")
        print(f"    date_unknown={ex.date_unknown} "
              f"chapter_ocr_substituted={ex.chapter_ocr_substituted}")
    print("")
    return plan


# --------------------------------------------------------------------------- #
# COMMIT (DEFERRED — not exercised in Phase B)
# --------------------------------------------------------------------------- #

def _connect():
    """Lazy psycopg connect. Only called under --commit (not used in Phase B)."""
    import psycopg  # imported lazily so dry-run needs no driver / no DB
    dsn = os.environ.get("PATOLEX_PG_DSN")
    if dsn:
        return psycopg.connect(dsn)
    return psycopg.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "patolex"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", "postgres"),
    )


def _read_volume_sha256(session_label: str) -> str:
    """
    Hans C3: the volume's content_sha256 is its IDENTITY. The registry
    (ingest_from_ocr.py:306-315) keyed source_document by the sha written to
    <scratch>/production-<label>/sha256.txt. We read that SAME file so the
    resolver lands on the SAME row the registry created — never on a citation
    LIKE near-match (which the old resolver used, and which sorted by id and so
    landed on the stale 1850 skeleton id=1). The sha is NOT carried in the
    banked parsed_acts JSON, so we read sha256.txt directly (identical source
    to the registry; not recomputed here, to avoid a divergent hash).
    """
    scratch = SCRATCH_ROOT / ("production-" + session_label)
    sha_path = scratch / "sha256.txt"
    if not sha_path.exists():
        raise RuntimeError(
            f"{session_label}: sha256.txt not found at {sha_path} — cannot "
            f"resolve source_document by content identity; refusing to ingest."
        )
    sha = sha_path.read_text(encoding="utf-8").strip()
    if not sha:
        raise RuntimeError(
            f"{session_label}: sha256.txt is empty — cannot resolve "
            f"source_document by content identity; refusing to ingest."
        )
    return sha


def _resolve_source_document_id(cur, session_label: str) -> int:
    """
    Resolve the production source_document by content_sha256 (Hans C3).

    FAIL LOUD on:
      * no match            — volume not registered / not ready,
      * multiple matches    — ambiguous identity (must never silently pick),
      * the stale 1850 dup  — if resolution would target id=1 (the 26-row
                              skeleton duplicate), refuse and require the manual
                              purge documented in the runbook / 0004 notes.

    The old resolver used `citation LIKE ... ORDER BY id LIMIT 1`, which on the
    live DB lands on the LOWEST id — for 1850 that is the stale skeleton id=1 —
    producing a split-brain corpus. content_sha256 is the content-derived
    identity (uq_source_document_content_sha256), so it is unambiguous when the
    data is clean and FAILS rather than guesses when it is not.
    """
    sha = _read_volume_sha256(session_label)
    cur.execute(
        "SELECT id FROM source_document WHERE content_sha256 = %s ORDER BY id;",
        (sha,),
    )
    rows = cur.fetchall()
    if not rows:
        raise RuntimeError(
            f"{session_label}: no source_document with content_sha256={sha[:12]}… "
            f"— volume not registered/ready; refusing to ingest."
        )
    if len(rows) > 1:
        ids = ", ".join(str(r[0]) for r in rows)
        raise RuntimeError(
            f"{session_label}: AMBIGUOUS source_document — {len(rows)} rows share "
            f"content_sha256={sha[:12]}… (ids: {ids}). Refusing to ingest; "
            f"resolve the duplicate manually before re-running."
        )
    src_doc_id = int(rows[0][0])

    # Explicit stale-1850-duplicate guard (Hans C3). The known bad row is the
    # 1850 skeleton source_document id=1 (26 skeleton rows, NULL/placeholder
    # content). It must NEVER be the ingest target. If the sha resolution itself
    # somehow lands on id=1, OR a stale id=1 still exists alongside the real
    # 1850 row, refuse and point at the documented manual purge.
    if session_label == "1850":
        if src_doc_id == 1:
            raise RuntimeError(
                "1850: resolver targeted source_document id=1, the STALE "
                "skeleton duplicate. Refusing to ingest. Run the manual purge "
                "documented in drizzle/0004_*.sql notes / the runbook "
                "(dedup_precheck.sql) to remove id=1 first, then re-run."
            )
        cur.execute(
            "SELECT id FROM source_document "
            "WHERE id = 1 AND citation LIKE 'CA Statutes 1850%';"
        )
        if cur.fetchone() is not None:
            raise RuntimeError(
                "1850: a STALE skeleton source_document id=1 still exists "
                "alongside the resolved production row "
                f"id={src_doc_id}. Refusing to ingest (ambiguous 1850 corpus). "
                "Purge id=1 manually first — see dedup_precheck.sql / runbook."
            )
    return src_doc_id


def _purge_source_document(cur, src_doc_id: int, session_label: str) -> int:
    """
    Hans C1: scoped, idempotent purge of ALL prior rows for one source_document,
    INSIDE the caller's open transaction (no commit/rollback here). Returns the
    count of enactments that existed before the purge (0 on a first ingest).

    This is what makes the re-ingest REPLACE version-A instead of skipping it,
    and what makes re-running idempotent (purge + reinsert). Child-before-parent
    order keeps every FK satisfied at each step.
    """
    cur.execute(PURGE_COUNT_SQL, (src_doc_id,))
    purge_before = int(cur.fetchone()[0])
    cur.execute(PURGE_LINEAGE_EDGE_SQL, (src_doc_id,))
    cur.execute(PURGE_PROVISION_VERSION_SQL, (src_doc_id, src_doc_id))
    cur.execute(PURGE_DESIGNATION_HISTORY_SQL, (src_doc_id,))
    cur.execute(PURGE_CHANGE_EVENT_SQL, (src_doc_id,))
    cur.execute(PURGE_ORPHAN_PROVISION_SQL, (f"Stats. {session_label} %",))
    cur.execute(PURGE_ENACTMENT_SQL, (src_doc_id,))
    return purge_before


def commit_volume(session_label: str):
    """
    Transactional, fail-loud commit. NOT used in Phase B (no DB writes allowed).

    Hans S2-B: the ENTIRE volume is ONE transaction (all acts or none). ANY
    error -> `conn.rollback()` discards the WHOLE volume + raise (volume FAILS,
    is NEVER marked done). UTF-8 preserved via parameter binding.

    Hans C1: the transaction FIRST resolves the source_document by content
    identity (C3), then PURGES all of that document's prior rows (version-A),
    then re-inserts. So a re-ingest REPLACES version-A; it never silently skips.
    Re-running is idempotent (purge + reinsert -> same final rows). The old
    EXISTS skip-on-existing + ON CONFLICT DO NOTHING are GONE: after the purge
    there is nothing to conflict with, and in_act_order (enumerate index) is
    unique within one parse run, so a plain INSERT is correct.

    Hans H2: consensus_output.json is banked ONLY AFTER the DB commit succeeds,
    so a rolled-back volume never leaves an orphan file dangling off a
    source_document that has no committed rows. (bank_consensus_output is itself
    idempotent — it overwrites — so a later successful re-run re-banks cleanly.)
    """
    plan = plan_volume(session_label)

    from psycopg.types.json import Jsonb  # jsonb param wrapper (commit-path only)

    conn = _connect()
    conn.autocommit = False  # ONE explicit transaction for the whole volume
    inserted = 0
    purged = 0
    try:
        with conn.cursor() as cur:
            src_doc_id = _resolve_source_document_id(cur, session_label)
            # ---- C1: purge version-A for THIS source_document, in-txn --------
            purged = _purge_source_document(cur, src_doc_id, session_label)
            for act in plan["acts"]:
                cur.execute(ENACTMENT_SQL, enactment_params(src_doc_id, plan, act))
                enact_id = cur.fetchone()[0]
                cur.execute(PROVISION_SQL, (act.designation,))
                prov_id = cur.fetchone()[0]
                cur.execute(DESIGNATION_SQL, (
                    prov_id, f"Statutes of California {session_label}",
                    act.section_number, act.designation,
                    _daterange(act.operative_date),
                ))
                cur.execute(CHANGE_EVENT_SQL, (
                    enact_id, prov_id, act.new_text, act.operative_date,
                    act.in_act_order, act.trust_level, src_doc_id, act.page_ref,
                    act.confident, act.confidence, Jsonb(act.ocr_provenance),
                ))
                # plain INSERT (no ON CONFLICT): post-purge there is nothing to
                # conflict with, so RETURNING always yields the new id.
                cur.fetchone()
                inserted += 1
            # ---- per-volume source_document signals (real, computed) ----------
            cur.execute(SOURCE_DOC_UPDATE_SQL, (
                plan["scan_quality"],
                plan["ocr_cer_estimate"],          # None -> SQL NULL (S2-C)
                Jsonb(plan["ocr_stats"]),
                src_doc_id,
            ))
        conn.commit()  # COMMIT ONCE — all acts or none (S2-B / F6)
        log("INGEST-COMMIT",
            f"{session_label}: purged(prior_enactments)={purged} inserted={inserted} | "
            f"scan_quality={plan['scan_quality']} cer={plan['ocr_cer_estimate']} | "
            f"volume REPLACED atomically (single txn, purge+reinsert)",
            "OK")
    except Exception as e:
        conn.rollback()  # discard the ENTIRE volume — nothing durable on failure
        # FAIL THE VOLUME — never mark done on partial ingest (F6/S2-B)
        raise RuntimeError(
            f"{session_label}: volume FAILED ({str(e)[:200]}) — entire volume "
            f"rolled back (0 acts committed/purged), NOT marked done."
        ) from e
    finally:
        conn.close()

    # ---- H2: bank consensus_output.json ONLY AFTER a successful commit -------
    # If the txn rolled back we never reach here, so no orphan file is left
    # pointing at a source_document with no committed rows. bank_consensus_output
    # is idempotent (overwrite), so a later re-run re-banks deterministically.
    bank_consensus_output(plan)


# --------------------------------------------------------------------------- #
# MAIN
# --------------------------------------------------------------------------- #

def main(argv):
    commit = "--commit" in argv
    volumes = [a for a in argv if not a.startswith("--")]
    if not volumes:
        print("Usage: python ingest_clean.py <session_label> [...] [--commit]")
        return 2

    mode = "COMMIT" if commit else "DRY-RUN"
    log("INGEST", f"=== ingest_clean.py {mode}: {', '.join(volumes)} ===",
        "OK" if not commit else "WARN")

    if commit:
        log("INGEST",
            "--commit requested. Phase B forbids DB writes; refusing unless "
            "PATOLEX_ALLOW_COMMIT=1 is explicitly set.", "WARN")
        if os.environ.get("PATOLEX_ALLOW_COMMIT") != "1":
            log("INGEST", "PATOLEX_ALLOW_COMMIT != 1 -> aborting (no DB writes).", "FAIL")
            return 3
        for vol in volumes:
            commit_volume(vol)
    else:
        for vol in volumes:
            try:
                dry_run(vol)
            except FileNotFoundError as e:
                log("INGEST-DRYRUN", str(e), "WARN")

    log("INGEST", f"=== ingest_clean.py {mode} done ===", "OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
