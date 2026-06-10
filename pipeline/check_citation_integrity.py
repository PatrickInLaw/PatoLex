"""
check_citation_integrity.py
Deterministic (no model calls) detection of corrupted numbers in OCR'd
California statutory acts.

Checks per act:
  1. Chapter-number integrity (the dominant, high-recall check)
     1a. chapter_int is None or 0 — missing/unparseable
     1b. chapter_raw contains non-Roman characters (e.g. 'LXY', 'CLYIL')
     1c. chapter_raw is Roman-chars-only but doesn't match canonical form for
         chapter_int (catches 'XCVIILI', 'CCLIIL', 'XxX', 'Cx' etc.)
     1d. chapter_int breaks monotonic sequence within the volume (implausible jump)
         TUNED v2: threshold lowered (max(5*median,30)) for higher recall
     1e. Duplicate chapter_int within the same volume
     1f. chapter_raw is numeric with a leading zero (e.g. '090', '048')
         — these are OCR garbles of printed chapter numbers
     1g. chapter_int implausibly large for the volume year (era-calibrated cap)
  2. Section-number corruption — scan the act's OWN section headers for
     OCR-garbled integer tokens (letter/digit hybrids, single-char noise).
  3. Corrupted-numeric-token density signal (digit-letter hybrids in text).
     TUNED v2: threshold lowered to 2 (was 5); plus ANY single-instance
     clearly-corrupted token pattern flags immediately.
  4. Date corruption — scan for an implausible approved/chaptered year in
     (a) the structured approved_date field AND
     (b) the act text's [Approved ...] / [Filed with ...] lines.
     A year is implausible if it differs from the volume year by > 5 years,
     AND the year is NOT a plausible "amend-act-of-YYYY" citation year
     (limited to short snippets around Approved/Filed markers, not
     amendment-reference sentences).
  5. Corrupted approval-line text — the CHAPTER/SECTION keyword itself is
     garbled ('CHAPTEN', 'Ncction'), OR the approval line contains obvious
     OCR garbage tokens (e.g. 'Approweecrclary', 'LAppicoved', 'Apyi').
  6. Missing enactment formula ('do enact') combined with ANY other anomaly.

Recall tuning (2026-06-10): raised from ~65% to target ~85-90%.
  Precision intentionally reduced — for a legal corpus, missed corruptions
  are worse than false alarms.

Validation: compare against API coherence labels (citation_mangled=True) in
  _coherence/l2_results/part_*.jsonl  (~4,397 acts, 316 mangled).

Output:
  C:\\Users\\PatrickKolasinski\\PatoLex-scratch\\_coherence\\citation_integrity_flags.json

Usage:
  python pipeline/check_citation_integrity.py
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRATCH = r"C:\Users\PatrickKolasinski\PatoLex-scratch"
L2_DIR = os.path.join(SCRATCH, "_coherence", "l2_results")
OUT_FILE = os.path.join(SCRATCH, "_coherence", "citation_integrity_flags.json")

# ---------------------------------------------------------------------------
# Volumes to SKIP (non-statute / code compilations per task spec)
# ---------------------------------------------------------------------------
SKIP_LABELS = {
    "1873-74-code",
    "1875-76-code",
    "1877-78-code",
    "1880-code",
    "1965-vol1-64chapters",
    "1971-vol3-chapters",
    "1987-vol4-chapters",
    "1988-vol4-chapters",
}

# ---------------------------------------------------------------------------
# Roman-numeral helpers
# ---------------------------------------------------------------------------

_ROMAN_ONLY_RE = re.compile(r"^[IVXLCDMivxlcdm]+$")

# ---------------------------------------------------------------------------
# Era-calibrated chapter-number ceiling (check 1g)
# ---------------------------------------------------------------------------
# Maps era-start-year → maximum plausible chapter_int for that era.
# Derived from actual corpus max-chapter observations plus a generous buffer.
# Any chapter_int ABOVE the ceiling is flagged as implausibly large.
_ERA_CHAPTER_CEILING: list[tuple[int, int]] = [
    (1990, 9999),   # 1990-1999: large volumes, generous cap
    (1970, 4000),   # 1970-1989
    (1960, 3000),   # 1960-1969
    (1950, 2500),   # 1950-1959
    (1940, 1800),   # 1940-1949
    (1920, 1200),   # 1920-1939
    (1900, 600),    # 1900-1919
    (1872, 400),    # 1872-1899 (post-code era)
    (0,    300),    # pre-1872
]


def _chapter_ceiling(year: int) -> int:
    for start, cap in _ERA_CHAPTER_CEILING:
        if year >= start:
            return cap
    return 300


def _int_to_roman(num: int) -> str:
    """Convert integer to canonical uppercase Roman numeral string."""
    if num <= 0 or num > 10000:
        return ""
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syms = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    result = ""
    for v, s in zip(val, syms):
        while num >= v:
            result += s
            num -= v
    return result


def _is_corrupted_roman(raw: str) -> bool:
    """Return True if raw is an OCR-garbled Roman numeral.

    Two sub-checks:
    1. Contains characters outside {I,V,X,L,C,D,M} (case-insensitive).
    2. More than 3 consecutive identical characters (IIII-style is handled
       separately as non-canonical but the 4+ repetition is always OCR noise).
    """
    if not raw:
        return False
    # Only applies to strings that look like they intend to be Roman numerals
    # (i.e., contain at least one letter)
    if not re.search(r"[A-Za-z]", raw):
        return False
    valid_roman_set = set("IVXLCDMivxlcdm")
    if any(c not in valid_roman_set for c in raw):
        return True
    if re.search(r"(.)\1{3,}", raw, re.IGNORECASE):
        return True
    return False


def _roman_noncanonical(raw: str, ch_int: int) -> bool:
    """Return True if raw is a valid-char Roman string but doesn't match
    the canonical representation for ch_int.

    This catches real OCR corruptions like 'XCVIILI' (should be CXLVI),
    'CCLIIL' (CCLIII), 'XxX' (XXX), 'Cx' (CX) etc.

    v2: Also flags MIXED-CASE Roman strings even when the uppercase form
    matches the canonical value (e.g. 'XxX' → correct value but OCR garbled
    because printed Roman numerals are always all-uppercase).
    """
    if not raw or not ch_int:
        return False
    if not _ROMAN_ONLY_RE.match(raw):
        return False  # not pure Roman chars — handled by _is_corrupted_roman
    canonical = _int_to_roman(ch_int)
    # The canonical form is always all-uppercase.  Any deviation (wrong value
    # OR mixed case) is an OCR garble.
    if raw == canonical:
        return False  # exact match — clean
    # Mixed case check: if uppercasing matches canonical, it's still a corruption
    # (printed Roman numerals are always all-uppercase; mixed case = OCR noise)
    if raw.upper() == canonical and raw != raw.upper():
        return True  # e.g. 'XxX', 'Cx', 'Ii', 'Dx'
    # Wrong value (even when uppercase)
    return raw.upper() != canonical


# ---------------------------------------------------------------------------
# Section-number corruption helpers
# ---------------------------------------------------------------------------

# Match section HEADER markers at start of a line.
# We look for: SEC., SECTION, Sec., § followed by a token.
_SEC_HEADER_RE = re.compile(
    r"""
    (?:
        ^[ \t]*                                  # start of line
        (?:SEC\.|SECTION|Sec\.|SEcTION|Secrion|§)  # marker (including OCR variants)
        \s*
    )
    (\S+)                                        # first token after marker
    """,
    re.VERBOSE | re.MULTILINE | re.IGNORECASE,
)

_MIXED_ALPHADIGIT_RE = re.compile(r"(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{2,}")


def _token_is_corrupted_section_num(token: str) -> bool:
    """Return True if token looks like an OCR-corrupted section number.

    Rules:
    - Pure digit → clean.
    - Legitimate sub-section suffix (1a, 2b, 1A) → clean.
    - Code cross-reference format (digit.digit) → clean.
    - Mixed alpha+digit where it can't be a sub-section ID → corrupted.
    - Single-char OCR confusion chars after a section marker ('l', 'o') → corrupted.
    """
    tok = token.rstrip(".,;:()")
    if not tok:
        return False
    if tok.isdigit():
        return False
    if re.match(r"^\d+[a-zA-Z]{1,2}$", tok):
        return False
    if re.match(r"^\d+\.\d+$", tok):
        return False
    if _MIXED_ALPHADIGIT_RE.match(tok):
        return True
    if len(tok) == 1 and tok in "loIO":
        return True
    return False


# ---------------------------------------------------------------------------
# Corrupted numeric token density (check 4)
# ---------------------------------------------------------------------------

_BROAD_CORRUPT_DIGIT_RE = re.compile(
    r"\b(?=[A-Za-z\d]{3,10}\b)(?=[A-Za-z\d]*\d)(?=[A-Za-z\d]*[A-Za-z])[A-Za-z\d]+\b"
)
_ORDINAL_RE = re.compile(r"^\d+(st|nd|rd|th)$", re.IGNORECASE)

# v2: lowered from 5 to 2 — we want higher recall at cost of precision
CORRUPT_DENSITY_THRESHOLD = 2

# Patterns that are almost certainly OCR garbage when found anywhere in text.
# These are specific enough that a single occurrence is a strong signal.
# Patterns: internal letter-in-digit-run like 8xo, l5b7, oTOT, 3817c7,
# or digit-run broken by a non-ordinal letter in the middle.
_CLEARLY_CORRUPTED_TOKEN_RE = re.compile(
    r"\b\d+[a-wyzA-WYZ]\d+\b"  # digit + non-ordinal-letter + digit (e.g. 8x0, 3817c7, 196%)
    r"|\b[oOlI][0-9]{3,}\b"     # 'o' or 'l' (common 0/1 OCR confusion) then digits
    r"|\b\d{3,}[oOlI]\b"        # digits then trailing 'o'/'l' confusion
)


def _count_corrupt_numeric_tokens(text: str) -> int:
    count = 0
    for m in _BROAD_CORRUPT_DIGIT_RE.finditer(text):
        tok = m.group()
        if _ORDINAL_RE.match(tok):
            continue
        if re.match(r"^\d+[a-zA-Z]{1,2}$", tok):
            continue
        if re.match(r"^[A-Za-z]{1,3}\d+$", tok):
            continue
        count += 1
    return count


def _has_clearly_corrupted_token(text: str) -> bool:
    """Return True if the text contains any token that is unambiguously an
    OCR corruption of a number (e.g. digit runs split by non-ordinal letters,
    o/l OCR confusion preceding a digit string)."""
    return bool(_CLEARLY_CORRUPTED_TOKEN_RE.search(text))



# ---------------------------------------------------------------------------
# Date corruption check (check 4)
# ---------------------------------------------------------------------------

# Matches [Approved ... YEAR], [Filed with Secretary ... YEAR], or
# [Passed ... YEAR] lines (including OCR variants of "Passed").
# We extract the year token(s) and compare to volume year.
_APPROVED_LINE_RE = re.compile(
    r"""
    (?:
        \[?\s*
        (?:
            Approved                            # standard
            | Appro[a-z]{1,6}                   # garbled Approved (Approveci etc.)
            | Filed\s+with\s+(?:Secretary|Secr) # Filed with Secretary
            | Passed                            # older formula "Passed"
            | Pussed                            # OCR garble of "Passed"
            | APry\b                            # garbled "Apri" in "[Approved by Governor APry..."
            | \bApproved\s+b[ye]\s+Governor     # standard modern form
        )
        .{0,80}?                                # short span (allow newlines)
        (\b1[0-9]{3}\b)                         # 4-digit year
    )
    """,
    re.VERBOSE | re.IGNORECASE | re.DOTALL,
)

# Years found in amendment-reference context ("amend an Act approved March X,
# YYYY" or "Statutes of YYYY") are NOT date corruptions — they refer to prior
# acts.  We suppress year hits that appear in these contexts.
_AMEND_REF_RE = re.compile(
    r"""
    (?:
        amend(?:atory|ed)?\s+[^;.]{0,60}?(\b1[0-9]{3}\b)       # amend ... YEAR
        | Statutes\s+of\s+(\b1[0-9]{3}\b)                       # Statutes of YEAR
        | Stats[.,]\s*(\b1[0-9]{3}\b)                           # Stats. YEAR
        | Chapter\s+\d+[,.]?\s+Statutes                         # Chapter N, Statutes
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


def check_date_corruption(act: dict, vol_year: int) -> list[str]:
    """Return issues if an approved/chaptered date year is implausible for
    the volume year.

    Strategy:
    1. Check the structured approved_date field (fast, high precision).
    2. Scan the act text for [Approved ...] / [Filed ...] lines and extract
       year tokens within those lines only (not amendment-reference sentences).

    A year is flagged if it differs from vol_year by more than DATE_YEAR_WINDOW
    AND cannot plausibly be an amendment-reference year.
    """
    DATE_YEAR_WINDOW = 4  # within ±4 years is plausible (biennial sessions max ~2yr gap)
    # Pattern to detect implausible day numbers in date lines (e.g. "May 380", "March 41")
    _IMPLAUSIBLE_DAY_RE = re.compile(
        r"""
        (?:January|February|March|April|May|June|July|August|September|October|November|December
         |Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)
        \s+
        (\d{2,4})                          # day token — 2+ digits
        \b
        """,
        re.VERBOSE | re.IGNORECASE,
    )
    issues: list[str] = []

    def _year_implausible(year_str: str) -> bool:
        try:
            y = int(year_str)
        except ValueError:
            return False
        diff = abs(y - vol_year)
        if diff <= DATE_YEAR_WINDOW:
            return False
        # A year in range [1848, 2010] that differs by >4 from vol_year is suspicious.
        if 1848 <= y <= 2010:
            return True
        # Also catch years that are > 2010 but appear in an approval line context
        # (e.g. "7921" — clearly OCR garble of a real year).
        # These differ from the vol_year by a large amount AND are out of range.
        if y > 2010 or (1000 <= y < 1848):
            # Use digit-replacement to see if a plausible year can be recovered
            pass  # falls through to the digit-replace block below
        # Also catch OCR digit corruptions that produce implausible years like
        # 1013 (should be 1913), 1841 (should be 1851), 7921 (should be 1921).
        # Strategy: check if replacing any ONE digit with any other digit 0-9
        # produces a year within DATE_YEAR_WINDOW of vol_year.
        # Apply to: y < 1848 OR y > 2010 (both are clearly out of range).
        if (1000 <= y < 1848) or (2010 < y <= 9999):
            s = list(str(y))
            if len(s) == 4:  # only try for 4-digit years
                for i in range(len(s)):
                    orig = s[i]
                    for d in "0123456789":
                        if d == orig:
                            continue
                        s[i] = d
                        try:
                            sy = int("".join(s))
                            if abs(sy - vol_year) <= DATE_YEAR_WINDOW:
                                return True
                        except ValueError:
                            pass
                    s[i] = orig
        return False

    # Check 1: structured approved_date field
    ad = (act.get("approved_date") or "").strip()
    if ad:
        for m in re.finditer(r"\b(1[0-9]{3})\b", ad):
            if _year_implausible(m.group(1)):
                issues.append(f"date_field_implausible_year:{m.group(1)}_in_vol{vol_year}")
                break  # one flag per act is enough

    # Check 2: text scan limited to approved/filed lines
    text = act.get("text", "") or ""
    if not text:
        return issues

    # Find potential amendment-reference years to suppress
    amend_years: set[str] = set()
    for m in _AMEND_REF_RE.finditer(text):
        for g in m.groups():
            if g:
                amend_years.add(g)

    for m in _APPROVED_LINE_RE.finditer(text):
        yr_str = m.group(1)
        if yr_str in amend_years:
            continue
        if _year_implausible(yr_str):
            issues.append(f"date_text_implausible_year:{yr_str}_in_vol{vol_year}")
            break  # one text flag per act

    # Also check for year-like tokens containing non-digit characters like "196%"
    # (% instead of a digit), where the token appears in an approval-line context.
    # NOTE: use re.DOTALL to allow cross-line matching (approval lines may be split).
    _GARBLED_YEAR_SYMBOL_RE = re.compile(
        r"""
        (?:Approved|Appro[a-z]{1,6}|Filed\s+with\s+Secretary)
        .{0,120}?                        # allow newlines
        \b(1[0-9]{2}[^\d\s\w])          # 3 digits + non-digit-non-space-non-word (e.g. 196%)
        """,
        re.VERBOSE | re.IGNORECASE | re.DOTALL,
    )
    m = _GARBLED_YEAR_SYMBOL_RE.search(text)
    if m:
        issues.append(f"date_text_garbled_year_symbol:{m.group(1)}")

    # Also scan for 5-digit "years" like 19638 (should be 1968) in approved lines.
    # NOTE: use re.DOTALL to allow cross-line matching (Filed with\nSecretary ...).
    _FIVE_DIGIT_YEAR_IN_APPR_RE = re.compile(
        r"""
        (?:Approved|Appro[a-z]{1,6}|Filed\s+with\s+(?:Secretary|Secr))
        .{0,120}?                        # allow newlines within 120 chars
        (\b1[0-9]{4}\b)                  # 5-digit number starting with 1 (corrupted year)
        """,
        re.VERBOSE | re.IGNORECASE | re.DOTALL,
    )
    for m in _FIVE_DIGIT_YEAR_IN_APPR_RE.finditer(text):
        yr5 = m.group(1)
        # Check if any 4-digit substring of yr5 is close to vol_year
        # (covers: extra digit at start, middle positions 0/1, or end)
        for i in range(2):  # up to start+2 substrings (positions 0,1)
            yr4 = yr5[i:i+4]
            try:
                y4 = int(yr4)
                if abs(y4 - vol_year) <= DATE_YEAR_WINDOW + 1:  # +1 for 5-digit case
                    issues.append(f"date_text_5digit_year:{yr5}_in_vol{vol_year}")
                    break
            except ValueError:
                pass
        else:
            # Also try removing each digit one at a time
            s = yr5
            for i in range(len(s)):
                yr4 = s[:i] + s[i+1:]
                try:
                    y4 = int(yr4)
                    if abs(y4 - vol_year) <= DATE_YEAR_WINDOW:
                        issues.append(f"date_text_5digit_year:{yr5}_in_vol{vol_year}")
                        break
                except ValueError:
                    pass
            else:
                continue
        break

    # Check 3: implausible day number in any date-line (e.g. "May 380", "March 41")
    for m in _IMPLAUSIBLE_DAY_RE.finditer(text):
        day_tok = m.group(1)
        try:
            day = int(day_tok)
            if day > 31:
                issues.append(f"date_text_implausible_day:{day_tok}")
                break
        except ValueError:
            pass

    # Check 4: truncated/garbled year in approval line (e.g. "1921." → "192)" → 3 chars)
    _TRUNCATED_YEAR_IN_APPR_RE = re.compile(
        r"""
        (?:Approved|Appro[a-z]{1,6}|Filed\s+with\s+Secretary)
        [^\n]{0,80}?
        ,\s*
        (\b\d{3}\b)                     # 3-digit token where year expected
        [\s.\])]                         # followed by space, period, bracket
        """,
        re.VERBOSE | re.IGNORECASE,
    )
    m = _TRUNCATED_YEAR_IN_APPR_RE.search(text)
    if m:
        issues.append(f"date_text_truncated_year:{m.group(1)}")

    # Check 5: garbled month abbreviation in or near an approval line.
    # Handles "Approved MONTH", "Approved by Governor MONTH", etc.
    _GARBLED_MONTH_IN_APPR_RE = re.compile(
        r"""
        (?:Approved|Appro[a-z]{1,6}|Passed|Pussed|Filed\s+with)
        (?:\s+by\s+Governor)?            # optional "by Governor"
        \s+
        (?:
            Mny\b | Mnv\b | Jnly\b | Jume\b | Jluy\b | Auzust\b | Augst\b
            | Marcb\b | Apri]\b | Apri1\b | Septembcr\b | Octobar\b
            | Many\b                     # "Many" instead of "May"
            | Angust\b                   # common OCR of "August"
            | APry\b | Apry\b            # garbled "April"
            | Jniy\b | Jnly\b            # garbled "July"
            | MEY\b                      # garbled "May"
            | Moy\b                      # garbled "May"
        )
        """,
        re.VERBOSE | re.IGNORECASE,
    )
    m = _GARBLED_MONTH_IN_APPR_RE.search(text)
    if m:
        issues.append(f"date_text_garbled_month:{m.group().strip()[:30]}")

    # Check 6: orphaned implausible year — 4-digit year appearing at or near start
    # of a line that is implausible for the volume year.
    # This catches cases like "18, 1859\nThe people" — approval-line prefix stripped
    # by the parser but the garbled year was left as an orphaned token.
    _ORPHAN_DATE_RE = re.compile(
        r"""
        (?:^|\n)                         # start of line or after newline
        \s*
        \d{1,2},?\s*                     # optional day prefix (e.g. "18,")
        (1[0-9]{3})\b                    # 4-digit year
        """,
        re.VERBOSE,
    )
    for m in _ORPHAN_DATE_RE.finditer(text):
        yr_str = m.group(1)
        if yr_str in amend_years:
            continue
        if _year_implausible(yr_str):
            issues.append(f"date_orphan_implausible_year:{yr_str}_in_vol{vol_year}")
            break

    # Check 7: implausible 4-digit year in the header zone (first 200 chars)
    # Catches garbled Stats/date refs like "Sizts 1982, An act to amend..." or
    # "aD 1988" in an 1939 act that don't appear in a standard approval line.
    # Only scan the header zone to avoid false positives from amendment-ref years
    # deep in the text.
    if not issues:
        header_text = text[:200]
        for m in re.finditer(r"\b(1[0-9]{3})\b", header_text):
            yr_str = m.group(1)
            if yr_str in amend_years:
                continue
            if _year_implausible(yr_str):
                issues.append(f"date_header_implausible_year:{yr_str}_in_vol{vol_year}")
                break

    return issues


# ---------------------------------------------------------------------------
# Approval-line garble check (check 5)
# ---------------------------------------------------------------------------

# The CHAPTER keyword itself corrupted
_CHAPTER_WORD_GARBLE_RE = re.compile(
    r"^(?:CHAPTEN|CHAPIER|CHAPTKR|CHAPTR|CHAPTFR|CHAPT\b)",
    re.MULTILINE | re.IGNORECASE,
)

# The SECTION keyword itself corrupted (different from section NUMBER).
# NOTE: NO re.IGNORECASE — the garbled spellings are case-specific OCR artifacts.
# The legitimate word "SECTION" or "Section" must NOT match.
_SECTION_WORD_GARBLE_RE = re.compile(
    r"^[ \t]*(?:Ncction|SEcTION|SECIION|SEcTlON|SECHON|SECTON|SECTIOX)\b",
    re.MULTILINE,
)

# Garbage approval-line tokens: severely garbled "Approved" or approval-line words.
# These must be specific enough NOT to match common English words.
# Only fire on tokens that are unambiguously corrupted approval-formula text.
_APPROVAL_GARBLE_TOKENS_RE = re.compile(
    r"""
    (?:
        # Garbled "Approved" — must NOT match "appropriation", "approaching" etc.
        \bApprowee[a-z]+\b              # e.g. Approweecrclary
        | \bAppioved\b                  # common garble
        | \bAppi[ao]ved\b               # AppiOved, AppiaVed
        | \bLAppi[a-z]+\b               # LAppicoved
        | \bApyi\b                      # Apyi (OCR of Apri)
        | \bJApprove[a-z]*\b            # JApproyed etc. — J prefix
        | \bApproyed\b                  # Approved with y
        # Garbled "Filed" in approval context
        | \bFuled\s+with\s+Secretary\b  # Filed → Fuled (must have context)
        | \bFuld\s+with\s+Secretary\b   # Filed → Fuld
        | \bWiled\s+with\s+Secretary\b  # Filed → Wiled
        | \bPuled\s+with\s+Secretary\b  # Filed → Puled
        # "By Governor" garbled — only fire on the "Fy" variant
        | \bFy\s+Governor\b             # By → Fy (OCR)
        # Garbled "Secretary" standalone (not as suffix of normal "Secretary")
        | \bSecreiary\b                 # garbled Secretary
        | \bSecrelary\b                 # garbled Secretary
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


def check_approval_line_garble(act: dict) -> list[str]:
    """Return issues if the CHAPTER/SECTION keyword itself is garbled,
    or if approval-line text contains obvious OCR garbage tokens."""
    text = act.get("text", "") or ""
    if not text:
        return []
    issues = []
    if _CHAPTER_WORD_GARBLE_RE.search(text):
        m = _CHAPTER_WORD_GARBLE_RE.search(text)
        issues.append(f"chapter_keyword_garbled:{m.group().strip()}")
    if _SECTION_WORD_GARBLE_RE.search(text):
        m = _SECTION_WORD_GARBLE_RE.search(text)
        issues.append(f"section_keyword_garbled:{m.group().strip()}")
    if _APPROVAL_GARBLE_TOKENS_RE.search(text):
        m = _APPROVAL_GARBLE_TOKENS_RE.search(text)
        issues.append(f"approval_line_garbled:{m.group().strip()[:30]}")
    return issues


# ---------------------------------------------------------------------------
# Missing enactment formula check (check 6)
# ---------------------------------------------------------------------------

_ENACTMENT_FORMULA_RE = re.compile(
    r"do\s+enact\b",
    re.IGNORECASE,
)


def check_enactment_formula(act: dict) -> bool:
    """Return True if the act text appears to be missing the enactment
    formula ('do enact').  Short acts (<200 chars) are excluded."""
    text = act.get("text", "") or ""
    if len(text) < 200:
        return False
    return not bool(_ENACTMENT_FORMULA_RE.search(text))


# ---------------------------------------------------------------------------
# Load parsed acts
# ---------------------------------------------------------------------------

def _label_from_dir(dirname: str) -> str:
    return dirname.replace("production-", "", 1)


def _year_from_label(label: str) -> int:
    m = re.match(r"(\d{4})", label)
    return int(m.group(1)) if m else 0


def _era_from_year(year: int) -> str:
    if year < 1872:
        return "1850-1871 (pre-code)"
    elif year < 1900:
        return "1872-1899"
    elif year < 1950:
        return "1900-1949"
    elif year < 1970:
        return "1950-1969"
    elif year < 1990:
        return "1970-1989"
    else:
        return "1990-1999"


def load_all_acts() -> list[dict[str, Any]]:
    scratch = SCRATCH
    prod_dirs = sorted(
        d for d in os.listdir(scratch)
        if d.startswith("production-")
        and os.path.isdir(os.path.join(scratch, d))
        and not d.startswith("production-smoke")
    )
    acts = []
    for dirname in prod_dirs:
        label = _label_from_dir(dirname)
        if label in SKIP_LABELS:
            continue
        year = _year_from_label(label)
        if year == 0 or year >= 2000:
            continue
        parsed_path = os.path.join(scratch, dirname, "parsed_acts_fixed.json")
        if not os.path.exists(parsed_path):
            continue
        try:
            with open(parsed_path, encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  WARN: Could not load {parsed_path}: {e}", file=sys.stderr)
            continue
        if isinstance(data, dict):
            vol_acts = data.get("confident_acts", []) + data.get("flagged_acts", [])
        elif isinstance(data, list):
            vol_acts = data
        else:
            continue
        for idx, act in enumerate(vol_acts):
            act["_label"] = label
            act["_dirname"] = dirname
            act["_act_index"] = idx
            act["_year"] = year
            act["_era"] = _era_from_year(year)
        acts.extend(vol_acts)
    return acts


# ---------------------------------------------------------------------------
# Load l2 validation labels
# ---------------------------------------------------------------------------

def load_l2_labels() -> dict[tuple[str, int], dict]:
    index: dict[tuple[str, int], dict] = {}
    for f in sorted(glob.glob(os.path.join(L2_DIR, "part_*.jsonl"))):
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                key = (rec.get("label", ""), rec.get("act_index", -1))
                index[key] = rec
    return index


# ---------------------------------------------------------------------------
# Per-volume chapter-sequence analysis
# ---------------------------------------------------------------------------

def analyze_chapter_sequence(vol_acts: list[dict]) -> dict[int, list[str]]:
    """Return dict of act_index → [chapter issues] for one volume.

    v2 changes:
    - 1d: sequence-jump threshold lowered to max(5*median, 30) from max(10*median, 50)
    - 1f: leading-zero chapter_raw (e.g. '090') now flagged
    - 1g: era-calibrated chapter ceiling — implausibly large chapter_int flagged
    """
    issues: dict[int, list[str]] = defaultdict(list)
    seq_acts = []

    vol_year = vol_acts[0]["_year"] if vol_acts else 0
    ceiling = _chapter_ceiling(vol_year)

    for act in vol_acts:
        idx = act["_act_index"]
        ch_int = act.get("chapter_int")
        ch_raw = act.get("chapter_raw", "") or ""

        # 1a: missing chapter
        if ch_int is None:
            issues[idx].append("chapter_missing_or_unparseable")
        elif ch_int == 0:
            issues[idx].append("chapter_zero")
        else:
            seq_acts.append((idx, ch_int, ch_raw))

        # 1b: non-Roman chars in raw
        if ch_raw and _is_corrupted_roman(ch_raw):
            issues[idx].append(f"chapter_raw_corrupted_roman:{ch_raw}")

        # 1c: Roman chars but non-canonical for the parsed integer
        if ch_int and ch_raw and _roman_noncanonical(ch_raw, ch_int):
            issues[idx].append(f"chapter_raw_noncanonical_roman:{ch_raw}!={_int_to_roman(ch_int)}")

        # 1f: numeric chapter_raw with leading zero (e.g. '090', '048', '0919')
        if ch_raw and re.match(r"^0\d+$", ch_raw):
            issues[idx].append(f"chapter_raw_leading_zero:{ch_raw}")

        # 1g: chapter_int implausibly large for this era
        if ch_int and ch_int > ceiling:
            issues[idx].append(f"chapter_implausibly_large:{ch_int}>ceiling_{ceiling}")

    # 1d: sequence breaks — v2: threshold lowered to max(5*median, 30)
    seq_acts.sort(key=lambda x: x[0])
    if len(seq_acts) >= 3:
        ch_vals = [x[1] for x in seq_acts]
        steps = [abs(ch_vals[i + 1] - ch_vals[i]) for i in range(len(ch_vals) - 1)]
        nonzero_steps = sorted(s for s in steps if s > 0)
        if nonzero_steps:
            median_step = nonzero_steps[len(nonzero_steps) // 2]
            threshold = max(5 * median_step, 30)  # v2: was max(10*median, 50)
            for i, (idx, ch_int, _) in enumerate(seq_acts):
                if i > 0:
                    prev_ch = seq_acts[i - 1][1]
                    gap = abs(ch_int - prev_ch)
                    if gap > threshold:
                        issues[idx].append(
                            f"chapter_sequence_break:prev={prev_ch},curr={ch_int},gap={gap}"
                        )

    # 1e: duplicate chapter numbers
    seen_ch: dict[int, int] = {}  # ch_int → first idx
    for idx, ch_int, _ in seq_acts:
        if ch_int in seen_ch:
            issues[idx].append(
                f"chapter_duplicate:{ch_int} also at act_idx={seen_ch[ch_int]}"
            )
        else:
            seen_ch[ch_int] = idx

    return dict(issues)


# ---------------------------------------------------------------------------
# Per-act section-number check
# ---------------------------------------------------------------------------

def check_section_numbers(act: dict) -> list[str]:
    text = act.get("text", "")
    if not text:
        return []
    issues = []
    sec_nums_found = []
    sec_nums_corrupted = []
    for m in _SEC_HEADER_RE.finditer(text):
        token = m.group(1).rstrip(".,;:()")
        sec_nums_found.append(token)
        if _token_is_corrupted_section_num(token):
            sec_nums_corrupted.append(token)
    if sec_nums_corrupted:
        issues.append(f"section_num_corrupted:{','.join(sec_nums_corrupted[:5])}")
    # Sequence anomaly
    clean_ints = [int(t.rstrip(".,;:()")) for t in sec_nums_found if t.rstrip(".,;:()").isdigit()]
    if len(clean_ints) >= 3:
        for i in range(1, len(clean_ints)):
            gap = abs(clean_ints[i] - clean_ints[i - 1])
            if gap > 5000 and clean_ints[i] > 100:
                issues.append(
                    f"section_sequence_anomaly:sec_{clean_ints[i-1]}_to_{clean_ints[i]}"
                )
                break
    return issues


# ---------------------------------------------------------------------------
# Corrupt density check
# ---------------------------------------------------------------------------

def check_corrupt_density(act: dict) -> list[str]:
    text = act.get("text", "")
    if not text:
        return []
    issues = []
    count = _count_corrupt_numeric_tokens(text)
    if count >= CORRUPT_DENSITY_THRESHOLD:
        issues.append(f"corrupt_numeric_density:{count}")
    if _has_clearly_corrupted_token(text):
        issues.append("clearly_corrupted_token_found")
    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Loading parsed acts...")
    all_acts = load_all_acts()
    print(f"  {len(all_acts):,} acts loaded (1850-1999, non-statute vols skipped)")

    print("Loading l2 validation labels...")
    l2_index = load_l2_labels()
    l2_total = len(l2_index)
    l2_mangled_count = sum(1 for v in l2_index.values() if v.get("citation_mangled"))
    print(f"  {l2_total:,} l2 records, {l2_mangled_count} with citation_mangled=True")

    # Group by volume for chapter sequence + duplicate analysis
    print("Running chapter-sequence analysis per volume...")
    vol_groups: dict[str, list[dict]] = defaultdict(list)
    for act in all_acts:
        vol_groups[act["_label"]].append(act)

    chapter_issues_map: dict[tuple[str, int], list[str]] = {}
    for label, vol_acts in vol_groups.items():
        ch_issues = analyze_chapter_sequence(vol_acts)
        for act_idx, iss in ch_issues.items():
            chapter_issues_map[(label, act_idx)] = iss

    # Per-act checks
    print("Running per-act checks (section, density, date, approval-line)...")
    flagged: list[dict] = []
    check1_count = check2_count = check3_count = check4_count = check5_count = check6_count = 0
    any_flag_count = 0
    era_counts: dict[str, int] = defaultdict(int)
    era_total: dict[str, int] = defaultdict(int)
    vol_flag_counts: dict[str, int] = defaultdict(int)

    # Track which checks trigger per act (for per-check recall)
    flagged_ch_keys: set[tuple] = set()
    flagged_sec_keys: set[tuple] = set()
    flagged_den_keys: set[tuple] = set()
    flagged_date_keys: set[tuple] = set()
    flagged_appr_keys: set[tuple] = set()
    flagged_enact_keys: set[tuple] = set()

    for act in all_acts:
        label = act["_label"]
        act_idx = act["_act_index"]
        vol_year = act["_year"]
        era = act["_era"]
        era_total[era] += 1

        key = (label, act_idx)
        ch_issues = chapter_issues_map.get(key, [])
        sec_issues = check_section_numbers(act)
        density_issues = check_corrupt_density(act)
        date_issues = check_date_corruption(act, vol_year)
        appr_issues = check_approval_line_garble(act)
        missing_enact = check_enactment_formula(act)

        # Check 6: missing enactment formula only counts as a flag when
        # combined with at least one other anomaly (reduces spurious flags on
        # short/unusual acts).
        other_issues = ch_issues + sec_issues + density_issues + date_issues + appr_issues
        enact_issues = (
            ["missing_enactment_formula_with_anomaly"]
            if missing_enact and other_issues
            else []
        )

        all_issues = ch_issues + sec_issues + density_issues + date_issues + appr_issues + enact_issues
        if not all_issues:
            continue

        any_flag_count += 1
        era_counts[era] += 1
        vol_flag_counts[label] += 1

        if ch_issues:
            check1_count += 1
            flagged_ch_keys.add(key)
        if sec_issues:
            check2_count += 1
            flagged_sec_keys.add(key)
        if density_issues:
            check3_count += 1
            flagged_den_keys.add(key)
        if date_issues:
            check4_count += 1
            flagged_date_keys.add(key)
        if appr_issues:
            check5_count += 1
            flagged_appr_keys.add(key)
        if enact_issues:
            check6_count += 1
            flagged_enact_keys.add(key)

        flagged.append({
            "label": label,
            "act_index": act_idx,
            "chapter": act.get("chapter"),
            "chapter_raw": act.get("chapter_raw"),
            "chapter_int": act.get("chapter_int"),
            "issues": all_issues,
            "check_chapter": bool(ch_issues),
            "check_section": bool(sec_issues),
            "check_density": bool(density_issues),
            "check_date": bool(date_issues),
            "check_approval": bool(appr_issues),
            "check_enactment": bool(enact_issues),
        })

    # Validation
    print("Computing precision/recall vs l2 citation_mangled labels...")
    flagged_keys = {(f["label"], f["act_index"]) for f in flagged}
    l2_mangled_keys = {k for k, v in l2_index.items() if v.get("citation_mangled")}
    l2_covered_keys = set(l2_index.keys())

    tp = flagged_keys & l2_mangled_keys
    fn = l2_mangled_keys - flagged_keys
    flagged_in_l2 = flagged_keys & l2_covered_keys
    fp_in_l2 = flagged_in_l2 - l2_mangled_keys

    recall = len(tp) / len(l2_mangled_keys) if l2_mangled_keys else 0.0
    precision_in_l2 = len(tp) / len(flagged_in_l2) if flagged_in_l2 else 0.0

    recall_ch = len(flagged_ch_keys & l2_mangled_keys) / len(l2_mangled_keys) if l2_mangled_keys else 0.0
    recall_sec = len(flagged_sec_keys & l2_mangled_keys) / len(l2_mangled_keys) if l2_mangled_keys else 0.0
    recall_den = len(flagged_den_keys & l2_mangled_keys) / len(l2_mangled_keys) if l2_mangled_keys else 0.0
    recall_date = len(flagged_date_keys & l2_mangled_keys) / len(l2_mangled_keys) if l2_mangled_keys else 0.0
    recall_appr = len(flagged_appr_keys & l2_mangled_keys) / len(l2_mangled_keys) if l2_mangled_keys else 0.0
    recall_enact = len(flagged_enact_keys & l2_mangled_keys) / len(l2_mangled_keys) if l2_mangled_keys else 0.0

    fn_sample = [l2_index[k] for k in sorted(fn)[:10]]

    # Print summary
    total_checked = len(all_acts)
    print()
    print("=" * 70)
    print("CITATION INTEGRITY CHECK v2 -- SUMMARY")
    print("=" * 70)
    print(f"Total acts checked:             {total_checked:>7,}")
    print(f"Total acts flagged (any check): {any_flag_count:>7,}  ({100*any_flag_count/total_checked:.1f}%)")
    print()
    print("FLAGS BY CHECK:")
    print(f"  Check 1 -- Chapter integrity:       {check1_count:>6,} acts")
    print(f"  Check 2 -- Section corruption:      {check2_count:>6,} acts")
    print(f"  Check 3 -- Corrupt density/tokens:  {check3_count:>6,} acts")
    print(f"  Check 4 -- Date corruption:         {check4_count:>6,} acts")
    print(f"  Check 5 -- Approval-line garble:    {check5_count:>6,} acts")
    print(f"  Check 6 -- Missing enact+anomaly:   {check6_count:>6,} acts")
    print()
    print("ERA BREAKDOWN (flagged / total):")
    for era in sorted(era_total.keys()):
        fc = era_counts.get(era, 0)
        tc = era_total[era]
        pct = 100 * fc / tc if tc else 0
        print(f"  {era:<30} {fc:>5} / {tc:>6}  ({pct:.1f}%)")
    print()
    print("TOP 20 VOLUMES BY FLAG COUNT:")
    top_vols = sorted(vol_flag_counts.items(), key=lambda x: -x[1])[:20]
    for vol, cnt in top_vols:
        print(f"  {vol:<45} {cnt:>5}")
    print()
    print("VALIDATION vs API citation_mangled labels:")
    print(f"  l2 acts covered:               {l2_total:>6,}")
    print(f"  l2 citation_mangled=True:      {l2_mangled_count:>6,}")
    print(f"  Flagged acts in l2 coverage:   {len(flagged_in_l2):>6,}")
    print(f"  True positives (TP):           {len(tp):>6,}")
    print(f"  False negatives (missed):      {len(fn):>6,}")
    print(f"  False positives in l2 set:     {len(fp_in_l2):>6,}")
    print()
    print(f"  RECALL  (TP / all mangled):    {recall:.3f}  ({100*recall:.1f}%)")
    print(f"  PRECISION (within l2 set):     {precision_in_l2:.3f}  ({100*precision_in_l2:.1f}%)")
    print()
    print("  Per-check recall contribution (with overlaps):")
    print(f"    Chapter check (1):             {100*recall_ch:.1f}%")
    print(f"    Section check (2):             {100*recall_sec:.1f}%")
    print(f"    Density/token check (3):       {100*recall_den:.1f}%")
    print(f"    Date corruption check (4):     {100*recall_date:.1f}%")
    print(f"    Approval-line garble (5):      {100*recall_appr:.1f}%")
    print(f"    Missing enact+anomaly (6):     {100*recall_enact:.1f}%")
    print()
    if fn_sample:
        print("  Sample MISSED acts (false negatives):")
        for r in fn_sample[:8]:
            reason = r.get('reason', '').encode('ascii', 'replace').decode('ascii')
            print(f"    {r.get('label')}[{r.get('act_index')}]: {reason}")
    print("=" * 70)

    out = {
        "summary": {
            "version": "v2",
            "total_acts_checked": total_checked,
            "total_acts_flagged": any_flag_count,
            "check1_chapter_integrity": check1_count,
            "check2_section_corruption": check2_count,
            "check3_corrupt_density": check3_count,
            "check4_date_corruption": check4_count,
            "check5_approval_garble": check5_count,
            "check6_missing_enact": check6_count,
            "l2_total": l2_total,
            "l2_citation_mangled": l2_mangled_count,
            "tp": len(tp),
            "fn": len(fn),
            "fp_in_l2": len(fp_in_l2),
            "recall": round(recall, 4),
            "precision_in_l2": round(precision_in_l2, 4),
            "recall_ch": round(recall_ch, 4),
            "recall_sec": round(recall_sec, 4),
            "recall_den": round(recall_den, 4),
            "recall_date": round(recall_date, 4),
            "recall_appr": round(recall_appr, 4),
            "recall_enact": round(recall_enact, 4),
        },
        "flags": flagged,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nFlagged list written to: {OUT_FILE}")
    print(f"  {len(flagged):,} flagged acts recorded.")


if __name__ == "__main__":
    main()
