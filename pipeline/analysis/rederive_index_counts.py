#!/usr/bin/env python3
"""
rederive_index_counts.py  -- READ-ONLY index re-derivation pass.

Re-derives each statute volume's authoritative chapter count + chapter->page
map by parsing the volume's OWN printed INDEX / TABLE OF CONTENTS (the
front-matter "CONTENTS / TITLE OF ACT" pages), and COMPARES it to the existing
oracle (ca_chapter_counts.tsv) WITHOUT overwriting the oracle or any parse.

Precision-first: when the index is absent / garbled / ambiguous, the volume is
flagged NO_INDEX rather than emitting a wrong count.

NEW FILES ONLY. No DB. No edits to existing files. No git commit.

Outputs (under SCRATCH):
  _index_rederivation.tsv          summary table (one row per production volume)
  _index_rederivation_report.md    human-readable report
  production-<label>/index_chapter_map.json   chapter->page map per parsed volume

Usage (on the 5090):
  python rederive_index_counts.py \
      --scratch C:/Users/patolex/PatoLex-scratch \
      --oracle  C:/github/PatoLex/docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

# ----------------------------------------------------------------------------
# Index-detection / extraction regexes
# ----------------------------------------------------------------------------

# Header markers that strongly indicate a CONTENTS / index page.
HEADER_MARKERS = [
    re.compile(r"TITLE\s+OF\s+ACT", re.IGNORECASE),
]
# Secondary (weaker) header tokens; used only to corroborate.
SOFT_HEADER_MARKERS = [
    re.compile(r"\bCONTENTS\b", re.IGNORECASE),
    re.compile(r"Number\s+of", re.IGNORECASE),
    re.compile(r"\bChap\b", re.IGNORECASE),
]

# Marker that ENDS the statutes index -- resolutions are NOT chapters.
# Stop scanning index entries at/after this.
#
# NOTE: We deliberately do NOT use a "CHAPTER N" body header as an END marker.
# Index *titles* routinely contain phrases like "...Article 5, of Chapter 7,
# of Title 11..." which, when line-wrapped, put "Chapter 7" at the start of a
# line and would falsely trip a ^CHAPTER\d marker mid-index (observed killing
# the 1887 scan at ch.101). The resolutions / officers markers below are the
# real post-statutes boundary; the body itself never carries a "TITLE OF ACT"
# header, so a real body page is dropped naturally by the no-header/no-entry
# stop logic instead.
END_MARKERS = [
    re.compile(r"CONCURRENT\s+AND\s+JOINT\s+RESOLUTIONS", re.IGNORECASE),
    re.compile(r"\bJOINT\s+RESOLUTIONS\b", re.IGNORECASE),
    re.compile(r"\bCONCURRENT\s+RESOLUTIONS\b", re.IGNORECASE),
    # "LIST OF OFFICERS" appears AFTER the resolutions block; also a hard stop.
    re.compile(r"LIST\s+OF\s+OFFICERS", re.IGNORECASE),
]

# An index entry line: leading integer (the chapter number), then a column
# separator, then "An Act"/"An act". We REQUIRE "An Act" to follow
# (precision-first) -- this is what distinguishes a statute index row from a
# resolution row ("Senate Concurrent Resolution"), a bill-column token, or
# body text.
#
# Two separator families are seen across eras:
#   * later era (1885+):  "1 | An Act ...", "13 | An Act ..."  (pipe column)
#   * early era (1850s-60s): "1.-An Act", "15.-An Act", "40,-An Act" rendered
#     with an em-dash that OCR/encoding mangles to the U+FFFD replacement char
#     or a literal em/en dash.
# The separator class therefore allows | ) ] ; } : . , - and dash/mojibake
# chars, with an optional leading punctuation (comma/period) before it.
_SEP = r"[|)\];}:.,\-—–‒�•*]"
INDEX_ENTRY = re.compile(
    r"^\s*(\d{1,4})\s*[.,]?\s*" + _SEP + r"+\s*An\s+Act\b",
    re.IGNORECASE,
)
# Looser variant kept for symmetry; same precision guard (must end in An Act).
INDEX_ENTRY_LOOSE = re.compile(
    r"^\s*(\d{1,4})\s*[.,]?\s*" + _SEP + r"{1,4}\s*An\s+[Aa]ct\b",
)

# Trailing page number on an index line (last integer on the line).
TRAILING_PAGE = re.compile(r"(\d{1,4})\s*$")

# Session ordinal phrase, e.g. "twenty-seventh session of the Legislature".
SESSION_ORDINAL = re.compile(
    r"((?:[A-Za-z]+(?:-[A-Za-z]+)?)\s+session\s+of\s+the\s+legislature)",
    re.IGNORECASE,
)
# Also catch "FORTY-NINTH SESSION OF THE LEGISLATURE" style (body header).
SESSION_ORDINAL_CAPS = re.compile(
    r"((?:[A-Z]+(?:-[A-Z]+)?)\s+SESSION\s+OF\s+THE\s+LEGISLATURE)"
)

# Approval-year token in titles, e.g. "approved March 10, 1887".
APPROVAL_YEAR = re.compile(r"approved\s+[A-Za-z]+\.?\s+\d{1,2},?\s+(18\d{2}|19\d{2})",
                           re.IGNORECASE)
# Fallback: any 4-digit 18xx/19xx year preceded by a month-ish context.
ANY_YEAR = re.compile(r"\b(18\d{2}|19\d{2})\b")

# Minimum index-line coverage (distinct chapters in the from-1 run / run top)
# required to TRUST a re-derived count. Below this, the OCR dropped too many
# index lines for the count to be reliable, so we report it as low-confidence
# (treated as NO_INDEX in the discrepancy verdict) rather than assert a wrong
# number -- precision-first, per spec.
COVERAGE_MIN = 0.75

# How many front-matter pages to consider as candidate index pages.
# Large volumes (e.g. 1860 ~455 chapters) need a deep window since the index
# runs many pages; the grow-from-1 max estimator + END markers keep trailing
# junk from inflating the count, so a generous window is safe.
MAX_FRONT_PAGES = 70


# ----------------------------------------------------------------------------
# Oracle loading + label->session mapping
# ----------------------------------------------------------------------------

def load_oracle(path):
    """Return list of dict rows from ca_chapter_counts.tsv."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < len(header):
                parts += [""] * (len(header) - len(parts))
            rows.append(dict(zip(header, parts)))
    return rows


def label_to_year_key(label):
    """
    Extract the leading 4-digit year and any '-NN' continuation from a
    production folder label.  Returns (year:int, raw_label).
    'production-1885-86' -> 1885 ; 'production-1931-vol1-chapters' -> 1931.
    """
    m = re.match(r"production-(\d{4})", label)
    if not m:
        return None
    return int(m.group(1))


# One-off: the bare 1863 volume (the 14th regular session; its ordinal did not
# OCR) shares its leading year with the 15th (1863-64), so a year key collides
# them. Canonical S14 is RESERVED for it (its oracle row is added in P5).
_SPECIAL_1863 = {"production-1863": "S14", "1863": "S14"}
_SHARED_SESSION_SUFFIXES = ("-code", "-regular")


def _canon_decode(label, oracle_rows):
    """
    Resolve a production/bare label -> canonical_id using the same year/biennium/
    NNchapters decode the completeness tool uses, then look up the matching
    oracle row's canonical_id. Returns canonical_id or None. READ-ONLY; relies on
    chapter_vs_oracle's parse primitives (imported lazily to avoid a load-time
    cycle). Honors the 1863 special case and the shared-session suffixes so a
    -code / -regular volume inherits its main volume's canonical_id.
    """
    try:
        import chapter_vs_oracle as _C
    except Exception:
        return None
    bare = label[len("production-"):] if label.startswith("production-") else label

    # Build the year/type -> canonical_id index FIRST. If the oracle carries no
    # canonical_id column at all (legacy oracle), bail out so the caller uses the
    # original year fallback -- including for the 1863 special case, which a
    # legacy oracle cannot represent (no S14). Behavior on the legacy oracle is
    # therefore unchanged.
    by_year_type = {}
    reg_years = set()
    for r in oracle_rows:
        ym = re.match(r"(\d{4})", r.get("session_year", "") or "")
        cid = (r.get("canonical_id", "") or "").strip()
        if not ym or not cid:
            continue
        y = int(ym.group(1))
        t = (r.get("session_type", "") or "").strip()
        by_year_type[(y, t)] = cid
        if t == "regular":
            reg_years.add(y)
    if not by_year_type:           # legacy oracle (no canonical_id) -> caller falls back
        return None

    if label in _SPECIAL_1863 or bare in _SPECIAL_1863:
        return _SPECIAL_1863.get(label) or _SPECIAL_1863.get(bare)

    for suf in _SHARED_SESSION_SUFFIXES:
        if bare.endswith(suf):
            return _canon_decode(bare[: -len(suf)], oracle_rows)

    year = _C.parse_session_year(bare, reg_years)
    typ = _C.parse_type(bare)
    if (year, typ) in by_year_type:
        return by_year_type[(year, typ)]
    if (year, "regular") in by_year_type:
        return by_year_type[(year, "regular")]
    extras = sorted(t for (y, t) in by_year_type if y == year and t != "regular")
    if extras:
        pick = "extra1" if "extra1" in extras else extras[0]
        return by_year_type[(year, pick)]
    return None


def find_oracle_match(label, oracle_rows):
    """
    Map a production label to the most plausible oracle row. Returns
    (oracle_session_key, oracle_N, year) or (None, None, yr).

    P4: when the oracle carries a `canonical_id` column, the label is resolved to
    its canonical session id (which separates the two 1863 regular sessions a year
    key collides) and matched to THAT row -- the source-grounded join key. The
    year is still returned (third element) for callers that use it descriptively.

    If canonical resolution is unavailable (legacy oracle with no canonical_id
    column, or an unrecognized label), it falls back to the original precision-
    first year match: leading year + 'regular' session type, with the second year
    of a two-year label tried as a fallback. This keeps behavior identical on the
    legacy oracle and for every non-collision volume.
    """
    year = label_to_year_key(label)

    # --- canonical path (preferred when the oracle has canonical_id) ----------
    cid = _canon_decode(label, oracle_rows)
    if cid is not None:
        row = next((r for r in oracle_rows
                    if (r.get("canonical_id", "") or "").strip() == cid), None)
        if row is not None:
            try:
                n = int(row.get("total_chapters", "") or 0)
            except ValueError:
                n = None
            return (row.get("session_label"), n, year)
        # cid resolved but has no row yet (S14 -- reserved, added in P5): report
        # the canonical id as the key, no N. Callers treat None N as "no count".
        return (cid, None, year)

    # --- legacy year fallback (unchanged) -------------------------------------
    if year is None:
        return (None, None, None)
    cands = [r for r in oracle_rows if r.get("session_year") == str(year)]
    if not cands:
        # try the *second* year for two-year labels like 1865-66 -> 1866 oracle
        m = re.match(r"production-\d{4}-(\d{2})", label)
        if m:
            yr2 = (year // 100) * 100 + int(m.group(1))
            cands = [r for r in oracle_rows if r.get("session_year") == str(yr2)]
    if not cands:
        return (None, None, year)
    # Prefer regular session.
    reg = [r for r in cands if r.get("session_type") == "regular"]
    pick = reg[0] if reg else cands[0]
    try:
        n = int(pick.get("total_chapters", "") or 0)
    except ValueError:
        n = None
    return (pick.get("session_label"), n, year)


# Ordinal-word -> CA legislative-session number. The Nth session sat in the
# year 1849 + N (1st = 1849-50, 2nd = 1851 ... 27th = 1887 ...). Used to
# cross-check / disambiguate which calendar year/row a volume's index belongs
# to, since title-page YEAR tokens are often OCR-garbled.
_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
    "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
    "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
    "twentieth": 20, "thirtieth": 30, "fortieth": 40, "fiftieth": 50,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60}


def ordinal_phrase_to_session_no(phrase):
    """'twenty-seventh session...' -> 27 ; 'thirty-fifth' -> 35. None if unknown."""
    if not phrase:
        return None
    p = phrase.lower()
    m = re.search(r"(twenty|thirty|forty|fifty|sixty)-([a-z]+)", p)
    if m and m.group(2) in _ORDINALS:
        return _TENS[m.group(1)] + _ORDINALS[m.group(2)]
    for w, n in _ORDINALS.items():
        if re.search(r"\b" + w + r"\b", p):
            return n
    return None


def refine_oracle_match(label, oracle_rows, detected_ordinal, modal_year,
                        fallback_key, fallback_n):
    """
    Use the index-derived signals (session ordinal + modal approval year) to
    pick the MOST plausible oracle row, correcting label->oracle artifacts
    (e.g. a '1900-01' bundle that is really the 1901 Regular Session, or a
    label whose leading year hit the wrong regular/extra row).

    Returns (oracle_key, oracle_n). Falls back to the simple match when the
    derived signals are absent/ambiguous.
    """
    # Determine target calendar year: prefer modal approval year, else the
    # session-ordinal-implied year (1849 + N).
    target_year = None
    if modal_year and modal_year.isdigit():
        target_year = int(modal_year)
    sess_no = ordinal_phrase_to_session_no(detected_ordinal)
    if target_year is None and sess_no:
        target_year = 1849 + sess_no

    if target_year is None:
        return (fallback_key, fallback_n)

    # Guard against polluted signals: index titles routinely cite OLDER code
    # dates ("amend the Civil Code, approved March 21, 1872"), which can make
    # the modal approval year far older than the volume. Only trust the derived
    # target year when it is within a few years of the label's leading year;
    # otherwise keep the (label-based) fallback.
    label_year = label_to_year_key(label)
    if label_year is not None:
        # account for two-year labels (1865-66 -> the second year is +1)
        if abs(target_year - label_year) > 3 and abs(target_year - (label_year + 1)) > 3:
            return (fallback_key, fallback_n)

    cands = [r for r in oracle_rows if r.get("session_year") == str(target_year)]
    if not cands:
        return (fallback_key, fallback_n)

    # Type preference: 'extra'/'special' ordinal phrase -> extra row.
    want_extra = bool(detected_ordinal) and bool(
        re.search(r"extra|special", detected_ordinal, re.IGNORECASE))
    reg = [r for r in cands if r.get("session_type") == "regular"]
    ext = [r for r in cands if r.get("session_type", "").startswith("extra")]
    pick = None
    if want_extra and ext:
        pick = ext[0]
    elif reg:
        pick = reg[0]
    else:
        pick = cands[0]
    try:
        n = int(pick.get("total_chapters", "") or 0)
    except ValueError:
        n = None
    return (pick.get("session_label"), n)


# ----------------------------------------------------------------------------
# Core index parse
# ----------------------------------------------------------------------------

def robust_max_chapter(distinct_sorted, gap_tol=15):
    """
    Authoritative chapter count = the top of the CONTIGUOUS-FROM-1 run of index
    chapter numbers.

    A statute index is fundamentally a sequence beginning at chapter 1. We grow
    the run upward from the lowest observed chapter, accepting the next value as
    long as the gap to the previously-accepted value is <= gap_tol (tolerates a
    few index lines the OCR dropped). We STOP at the first large gap. Anything
    above that gap (stray page numbers, a later subject-index section, an OCR
    garble like '3605', or a spurious dense cluster of page numbers at 800-950
    seen in the noisy 1860 scan) is discarded.

    This is robust both to:
      * isolated high outliers (e.g. '131'->'181' in 1885-86), and
      * spurious dense clusters far above the body (e.g. 1860's 730-954 block),
    because neither is reachable from 1 without crossing a large gap.

    A final TRAILING-TRIM removes a lone high value that bridged the gap_tol but
    has no near support just below it (e.g. 1885-86's '131'->'181' misread:
    181-169=12 <= gap_tol, but nothing in 170..180 exists, so 181 is an
    isolated outlier and is trimmed back to 169). A genuine tail (e.g. 1887's
    188 sitting right above 187) is kept because its gap to the prior in-run
    value is tiny.

    Returns the top of the from-1 run, or None if empty.
    """
    if not distinct_sorted:
        return None
    s = distinct_sorted
    run = [s[0]]
    for v in s[1:]:
        if v - run[-1] <= gap_tol:
            run.append(v)
        else:
            break
    # Trailing-trim: drop isolated high outliers that bridged via gap_tol.
    trim_gap = 5
    while len(run) >= 2 and (run[-1] - run[-2]) > trim_gap:
        run.pop()
    return run[-1]


def numeric_page_order(keys):
    def pn(k):
        try:
            return int(k)
        except (TypeError, ValueError):
            return 10 ** 9
    return sorted(keys, key=pn)


def page_has_index_header(text):
    """Strong: has 'TITLE OF ACT'. Returns True/False."""
    return any(rx.search(text) for rx in HEADER_MARKERS)


def page_end_marker_pos(text):
    """Return char offset of the earliest END marker in text, or None."""
    best = None
    for rx in END_MARKERS:
        m = rx.search(text)
        if m:
            if best is None or m.start() < best:
                best = m.start()
    return best


# Bill-column token, e.g. "A. B. 267", "S. B. 140", "A.C. R.4". The integer
# inside it must NOT be mistaken for a page number.
BILL_TOKEN = re.compile(r"[ASB]\s*\.?\s*[ABCJR]\s*\.?\s*(?:R\s*\.?\s*)?\d{1,4}",
                        re.IGNORECASE)


def extract_entries_from_text(text):
    """
    Parse index entries from a block of text.

    Each index entry begins on a line like "13 | An Act ..." and may WRAP over
    several physical lines, with the destination Page number on the LAST line
    of the entry (after a bill-column token like "A. B. 122"). We therefore
    parse statefully: a chapter "block" runs from its number-line up to the
    next chapter number-line; the entry's page is the last plausible integer in
    the block AFTER removing bill-column tokens.

    Returns list of (chap:int, page:int|None) tuples, in order encountered.
    """
    lines = text.splitlines()
    # First pass: find the indices of chapter-number lines.
    starts = []
    for i, raw in enumerate(lines):
        m = INDEX_ENTRY.match(raw) or INDEX_ENTRY_LOOSE.match(raw)
        if not m:
            continue
        try:
            chap = int(m.group(1))
        except ValueError:
            continue
        if chap < 1 or chap > 5000:
            continue
        starts.append((i, chap))

    entries = []
    for idx, (line_i, chap) in enumerate(starts):
        # Block = from this chapter line up to (not including) the next.
        end_i = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        block = " ".join(lines[line_i:end_i])
        # Strip bill-column tokens so their integers don't pose as pages.
        cleaned = BILL_TOKEN.sub(" ", block)
        # Page = last integer in the cleaned block (the right-hand Page column).
        ints = re.findall(r"\d{1,4}", cleaned)
        page = None
        if ints:
            try:
                cand = int(ints[-1])
                # Don't let the leading chapter number itself be the page when
                # the block has no other numbers.
                if not (len(ints) == 1 and cand == chap):
                    if 1 <= cand <= 20000:
                        page = cand
            except ValueError:
                page = None
        entries.append((chap, page))
    return entries


def derive_from_volume(ocr_path):
    """
    Parse one volume's page_ocr_results.json.

    Returns a dict with keys:
      status: 'INDEX' | 'NO_INDEX'
      index_max_chapter, index_distinct_count
      detected_session_ordinal, modal_approval_year
      chapter_map: {chap: page}
      index_pages: [page-keys used]
      note: short reason when NO_INDEX
    """
    out = {
        "status": "NO_INDEX",
        "index_max_chapter": None,
        "index_distinct_count": 0,
        "coverage": 0.0,
        "detected_session_ordinal": "",
        "modal_approval_year": "",
        "chapter_map": {},
        "index_pages": [],
        "note": "",
    }
    try:
        with open(ocr_path, "r", encoding="utf-8") as f:
            pages = json.load(f)
    except Exception as e:  # noqa
        out["note"] = "ocr_json_unreadable: %s" % (e,)
        return out
    if not isinstance(pages, dict) or not pages:
        out["note"] = "ocr_json_empty"
        return out

    ordered = numeric_page_order(pages.keys())
    front = ordered[:MAX_FRONT_PAGES]

    # ---- Identify the contiguous index region in the front matter. ----
    # An index page = has 'TITLE OF ACT' header OR yields >=3 index entries.
    # We collect entries page-by-page and STOP at the first END marker, even
    # mid-page (only entries BEFORE the marker count).
    all_entries = []
    index_pages = []
    session_ord = ""
    approval_years = []
    ended = False

    for k in front:
        rec = pages.get(k) or {}
        text = rec.get("consensus_text") or ""
        if not text.strip():
            continue

        # Truncate at an END marker if present on this page.
        end_pos = page_end_marker_pos(text)
        scan_text = text if end_pos is None else text[:end_pos]

        has_header = page_has_index_header(scan_text)
        entries = extract_entries_from_text(scan_text)

        # Capture session ordinal (first occurrence anywhere in front matter).
        if not session_ord:
            mo = SESSION_ORDINAL.search(text) or SESSION_ORDINAL_CAPS.search(text)
            if mo:
                session_ord = re.sub(r"\s+", " ", mo.group(1)).strip()

        # Collect approval years from index/title text on this page.
        for ym in APPROVAL_YEAR.finditer(scan_text):
            approval_years.append(ym.group(1))

        is_index_page = has_header or len(entries) >= 3
        if is_index_page:
            index_pages.append(k)
            all_entries.extend(entries)

        if end_pos is not None and (has_header or entries):
            # We hit the resolutions/officers/body boundary on a real index
            # page -- stop the index scan here.
            ended = True
            break
        # If we've already seen index pages and now hit a page with NO header
        # and NO entries, the index has likely ended -- stop to stay precise.
        if index_pages and not is_index_page:
            ended = True
            break

    # ---- Decide status. ----
    chaps = [c for (c, _p) in all_entries]
    distinct = sorted(set(chaps))

    if not distinct:
        out["note"] = "no_index_entries_found"
        return out

    # Precision guard: require a minimum amount of evidence that this really
    # is an index (not a stray body page). At least 5 distinct chapters and at
    # least one page carrying the 'TITLE OF ACT' header, OR a long run.
    header_seen = any(
        page_has_index_header((pages.get(k) or {}).get("consensus_text") or "")
        for k in index_pages
    )
    if len(distinct) < 5 or (not header_seen and len(distinct) < 12):
        out["note"] = (
            "insufficient_index_evidence (distinct=%d header=%s)"
            % (len(distinct), header_seen)
        )
        return out

    # Build chapter->page map (last page value wins if duplicated).
    cmap = {}
    for (c, p) in all_entries:
        if p is not None and 1 <= p <= 20000:
            cmap[c] = p

    # Modal approval year.
    modal_year = ""
    if approval_years:
        modal_year = Counter(approval_years).most_common(1)[0][0]

    rmax = robust_max_chapter(distinct)

    # Coverage = distinct index chapters within the from-1 run / run top.
    # Low coverage means OCR dropped many index lines -> the max is still the
    # best estimate (robust to missed lines) but the count is less certain.
    in_run = [c for c in distinct if c <= rmax]
    coverage = (len(in_run) / rmax) if rmax else 0.0
    cov_note = "cov=%.2f(%d/%d)" % (coverage, len(in_run), rmax)
    base_note = "ended_at_marker" if ended else "ran_to_front_limit"

    # Truncation guard: if MORE distinct chapters were seen than the from-1 run
    # top, the run was cut short by an OCR gap while higher chapters exist above
    # it -- the max is then an UNDERcount and any verdict (esp. ORACLE_HIGH) is
    # unreliable. Flag low coverage so the verdict downgrades to NO_INDEX.
    if len(distinct) > rmax:
        cov_note += ";run_truncated(distinct>%d)" % rmax
        coverage = min(coverage, COVERAGE_MIN - 0.01)

    out.update({
        "status": "INDEX",
        "index_max_chapter": rmax,
        "index_distinct_count": len(distinct),
        "coverage": coverage,
        "detected_session_ordinal": session_ord,
        "modal_approval_year": modal_year,
        "chapter_map": {str(k): v for k, v in sorted(cmap.items())},
        "index_pages": index_pages,
        "note": base_note + ";" + cov_note,
    })
    return out


# ----------------------------------------------------------------------------
# Optional: our HAVE distinct from a floor parse, if easily available.
# ----------------------------------------------------------------------------

def our_have_distinct(vol_dir):
    """
    Best-effort: read a parsed_acts*.json in the volume dir and count distinct
    chapter numbers. Returns int or "" if not easily available. READ-ONLY.
    """
    try:
        cand = []
        for fn in os.listdir(vol_dir):
            if fn.startswith("parsed_acts") and fn.endswith(".json"):
                cand.append(os.path.join(vol_dir, fn))
        if not cand:
            return ""
        cand.sort()
        with open(cand[0], "r", encoding="utf-8") as f:
            data = json.load(f)
        chaps = set()
        recs = data if isinstance(data, list) else data.get("acts") or data.get("records") or []
        if isinstance(recs, dict):
            recs = list(recs.values())
        for r in recs:
            if not isinstance(r, dict):
                continue
            for key in ("chapter", "chapter_number", "chap", "chapterNo"):
                if key in r and r[key] not in (None, ""):
                    try:
                        chaps.add(int(re.sub(r"[^0-9]", "", str(r[key])) or 0))
                    except ValueError:
                        pass
                    break
        chaps.discard(0)
        return len(chaps) if chaps else ""
    except Exception:  # noqa
        return ""


# ----------------------------------------------------------------------------
# Discrepancy classification
# ----------------------------------------------------------------------------

def classify(index_max, oracle_n, status, coverage=1.0):
    if status != "INDEX" or index_max is None:
        return "NO_INDEX"
    # Low-coverage parses are not trustworthy enough to assert a verdict.
    if coverage < COVERAGE_MIN:
        return "NO_INDEX"
    if oracle_n is None:
        return "NO_ORACLE"
    if index_max == oracle_n:
        return "MATCH"
    # Tolerance band of +/-1 still counts as MATCH (OCR can clip the last row).
    if abs(index_max - oracle_n) <= 1:
        return "MATCH"
    if index_max > oracle_n:
        return "ORACLE_LOW"   # oracle UNDERcounts (like 1887)
    return "ORACLE_HIGH"      # oracle OVERcounts vs the printed index


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--oracle", required=True)
    ap.add_argument("--only", default="", help="comma list of labels to limit to")
    args = ap.parse_args()

    scratch = args.scratch.replace("\\", "/").rstrip("/")
    oracle_rows = load_oracle(args.oracle)

    only = set(s.strip() for s in args.only.split(",") if s.strip())

    vol_dirs = []
    for name in sorted(os.listdir(scratch)):
        if not name.startswith("production-"):
            continue
        full = os.path.join(scratch, name)
        if not os.path.isdir(full):
            continue
        if only and name not in only:
            continue
        vol_dirs.append((name, full))

    tsv_rows = []
    report_lines = []

    for label, vol_dir in vol_dirs:
        ocr_path = os.path.join(vol_dir, "ocr_consensus", "page_ocr_results.json")
        oracle_key, oracle_n, _yr = find_oracle_match(label, oracle_rows)

        if not os.path.exists(ocr_path):
            res = {
                "status": "NO_INDEX",
                "index_max_chapter": None,
                "index_distinct_count": 0,
                "detected_session_ordinal": "",
                "modal_approval_year": "",
                "chapter_map": {},
                "index_pages": [],
                "note": "ocr_consensus_missing",
            }
        else:
            res = derive_from_volume(ocr_path)

        # Refine the oracle row using the index-derived session signals, but
        # ONLY for trusted INDEX parses (otherwise the signals are unreliable).
        if res["status"] == "INDEX" and res.get("coverage", 1.0) >= COVERAGE_MIN:
            r_key, r_n = refine_oracle_match(
                label, oracle_rows,
                res.get("detected_session_ordinal", ""),
                res.get("modal_approval_year", ""),
                oracle_key, oracle_n,
            )
            if r_key and r_key != oracle_key:
                res["note"] = res["note"] + (";oracle_remapped:%s" % r_key)
            oracle_key, oracle_n = r_key, r_n

        disc = classify(res["index_max_chapter"], oracle_n, res["status"],
                        res.get("coverage", 1.0))
        have = our_have_distinct(vol_dir)

        tsv_rows.append([
            label,
            oracle_key or "",
            "" if oracle_n is None else str(oracle_n),
            "" if res["index_max_chapter"] is None else str(res["index_max_chapter"]),
            str(res["index_distinct_count"]),
            res["detected_session_ordinal"],
            res["modal_approval_year"],
            "" if have == "" else str(have),
            disc,
            res["note"],
        ])

        # Write per-volume chapter map ONLY for TRUSTED parsed volumes
        # (status INDEX and coverage above the trust threshold). Low-coverage
        # parses are reported as NO_INDEX and do not get an authoritative map.
        if res["status"] == "INDEX" and res["chapter_map"] \
                and res.get("coverage", 1.0) >= COVERAGE_MIN:
            map_path = os.path.join(vol_dir, "index_chapter_map.json")
            try:
                with open(map_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "label": label,
                        "oracle_session_key": oracle_key,
                        "oracle_N": oracle_n,
                        "index_max_chapter": res["index_max_chapter"],
                        "index_distinct_count": res["index_distinct_count"],
                        "detected_session_ordinal": res["detected_session_ordinal"],
                        "modal_approval_year": res["modal_approval_year"],
                        "index_pages": res["index_pages"],
                        "chapter_to_page": res["chapter_map"],
                    }, f, indent=2)
            except Exception as e:  # noqa
                report_lines.append("WARN could not write map for %s: %s" % (label, e))

    # ---- Write summary TSV. ----
    tsv_path = os.path.join(scratch, "_index_rederivation.tsv")
    header = [
        "label", "oracle_session_key", "oracle_N", "index_max_chapter",
        "index_distinct_count", "detected_session_ordinal", "modal_approval_year",
        "our_HAVE_distinct", "discrepancy", "note",
    ]
    with open(tsv_path, "w", encoding="utf-8") as f:
        f.write("\t".join(header) + "\n")
        for r in tsv_rows:
            f.write("\t".join(r) + "\n")

    # ---- Build report. ----
    from collections import Counter as C
    disc_counts = C(r[8] for r in tsv_rows)
    total = len(tsv_rows)

    def rows_with(disc):
        return [r for r in tsv_rows if r[8] == disc]

    def gap(r):
        try:
            return int(r[3]) - int(r[2])
        except (ValueError, TypeError):
            return 0

    oracle_low = sorted(rows_with("ORACLE_LOW"), key=lambda r: -gap(r))
    oracle_high = sorted(rows_with("ORACLE_HIGH"), key=lambda r: gap(r))

    lines = []
    lines.append("# Index Re-derivation Report (READ-ONLY)\n")
    lines.append("Re-derived each volume's chapter count from its OWN printed "
                 "INDEX / TABLE OF CONTENTS and compared to the oracle "
                 "(ca_chapter_counts.tsv). Oracle and parses were NOT modified.\n")
    lines.append("## Corpus-wide tally\n")
    lines.append("- Volumes examined: **%d**" % total)
    for k in ("MATCH", "ORACLE_LOW", "ORACLE_HIGH", "NO_INDEX", "NO_ORACLE"):
        lines.append("- %s: **%d**" % (k, disc_counts.get(k, 0)))
    lines.append("")

    lines.append("## Biggest ORACLE_LOW (oracle UNDERcounts -- denominator errors)\n")
    lines.append("| label | oracle_N | index_max | gap | session | modal_year |")
    lines.append("|---|---|---|---|---|---|")
    for r in oracle_low[:40]:
        lines.append("| %s | %s | %s | +%d | %s | %s |"
                     % (r[0], r[2], r[3], gap(r), r[5], r[6]))
    lines.append("")

    lines.append("## Biggest ORACLE_HIGH (oracle OVERcounts vs printed index)\n")
    lines.append("| label | oracle_N | index_max | gap | session | modal_year |")
    lines.append("|---|---|---|---|---|---|")
    for r in oracle_high[:40]:
        lines.append("| %s | %s | %s | %d | %s | %s |"
                     % (r[0], r[2], r[3], gap(r), r[5], r[6]))
    lines.append("")

    lines.append("## NO_INDEX volumes (index absent/garbled -- flagged, not guessed)\n")
    ni = rows_with("NO_INDEX")
    lines.append("Count: %d" % len(ni))
    lines.append("")
    lines.append("| label | oracle_N | note |")
    lines.append("|---|---|---|")
    for r in ni:
        lines.append("| %s | %s | %s |" % (r[0], r[2], r[9]))
    lines.append("")

    report_path = os.path.join(scratch, "_index_rederivation_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines + report_lines) + "\n")

    # ---- stdout summary (small). ----
    print("WROTE", tsv_path)
    print("WROTE", report_path)
    print("TOTAL", total)
    for k in ("MATCH", "ORACLE_LOW", "ORACLE_HIGH", "NO_INDEX", "NO_ORACLE"):
        print(k, disc_counts.get(k, 0))


if __name__ == "__main__":
    main()
