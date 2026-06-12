"""
reparse.py — PatoLex parser fix + re-parse for 1850-1860 volumes
=================================================================
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
DO NOT USE THIS SCRIPT FOR NEW PARSING.  It is ARCHIVED / UNSAFE.

The local parse_act_date() in this file still uses the OLD, unfixed regex
(APPROVED_RE captures only 18[3-9]\\d, no volume_year clamp) and will
reproduce the Cluster-A year-misread bug (e.g. returning 1895 for an 1855
volume) if invoked.

Use ingest_from_ocr.py for all current and future parse + ingest work.
That script contains the ROUND2 parser with all Cluster-A/B fixes applied.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

CPU-only, read-only on banked OCR. SAFE to run (batch is stopped).
- Reads only:  production-{year}/ocr_consensus/page_ocr_results.json  (read-only)
- Writes only: production-{year}/parsed_acts_fixed.json                (overwritten)
  Does NOT touch parsed_acts.json (the original pipeline output).

No DB writes here — see re_ingest_fixed.py for ingest.

=====================================================================
ROUND 2 (2026-06-02, parser-completeness session)
=====================================================================
Diagnosis of the remaining undercount after the comma/date fix:

The ORIGINAL CHAP_RE only matched a chapter header when EITHER
  (a) the line was exactly "Chapter <num>." (number then end-of-line), or
  (b) "Chapter <num>. AN ACT" on a single line with a SPACE before AN ACT.
Neither matched the real corpus layouts:

  * 1850-1857 bodies put "CHAPTER <roman>." (or "Chap. <arabic>.") on its
    OWN line, then "AN ACT ..." on the NEXT line(s) — separated by a newline,
    not a space. OCR also wraps the header in leading/trailing noise
    ("., CHAPTER I. ;", ". Chap. 2.", "CHAPTER Y." where Y=V), so the
    end-of-line anchor "[.,]?\\s*$" failed.
  * 1858-1860 bodies use an INLINE em-dash header:
        "Cuap. XXVI.—An Act for the relief of ..."
    where "Chap" is heavily OCR-garbled (Cuap, Cuar, Cnap, Crap, Caap, Car,
    Coar, ...) and the separator before "An Act" is U+2014 (—), NOT a space.
    The chapter number is a Roman numeral, itself OCR-garbled
    (Il=II, XXVIIL=XXVIII, LITI=LIII, XLVIJ=XLVII, ...).
  * Every 1858-1860 act ALSO appears once in a front-matter Table of Contents
    as "<arabic>.—An Act ... <leader dots> <page-no>". Those are index
    entries (no statute body) and must NOT be ingested as acts.

FIX (this version):
  * HEADER_RE matches a chapter header tolerant of:
      - garbled "Chap" prefix  (C + 1-3 letters, e.g. Cuap/Cnar/Crap/Car/Coar)
        OR the full word CHAPTER,
      - leading/trailing OCR punctuation noise,
      - roman OR arabic numeral (with OCR-garble letters J/T/L/1/| treated as I),
      - an OPTIONAL inline "—An Act ..." tail (em/en/hyphen dashes).
  * An act STARTS at a header only if "AN ACT" appears on the header line OR
    within the next few non-empty lines (covers the separate-line layout).
  * TOC exclusion: a detected act is only emitted if its accumulated buffer
    contains a genuine enactment marker — the clause
    "People of the State of California ... do enact as follows" (or an
    "[Approved/Passed <date>]" bracket). TOC index lines have neither, so they
    are dropped entirely (not even flagged), preventing index pollution.
  * Chapter number: parsed from the OCR numeral with conservative Roman-OCR
    normalization (J/T/L-as-I etc.). This is faithful to what is printed.
    The raw OCR numeral token is preserved in `chapter_raw`. No sequence is
    fabricated; if two acts misparse to the same number the idempotent ingest
    simply skips the duplicate citation.

FAITHFULNESS: literal text preserved; unparseable acts are flagged, never
fabricated; no structure is invented. Date handling (comma after APPROVED,
OCR keyword variants, ordinal-day artifacts, full-buffer date scan) is carried
forward from the previous fix.
"""

import re
import json
import datetime
from pathlib import Path

import config

# ---------------------------------------------------------------------------
SCRATCH_ROOT = Path(config.path_for("data_root"))
VOLUMES = ["1850", "1851", "1852", "1853", "1854", "1855", "1856",
           "1857", "1858", "1859", "1860"]
LOG_FILE = Path(
    r"C:\Users\PatrickKolasinski\Documents\GitHub\patolex"
    r"\docs\80_PROJECT_HISTORY\run-logs\parser-completeness-run.log"
)

# ---------------------------------------------------------------------------
# PATTERNS
# ---------------------------------------------------------------------------

# Dash family used as the "—An Act" separator: em, en, figure, hyphen, NB-hyphen,
# plus ASCII hyphen-minus.
_DASH = "—–‒‐‑\\-"

# Chapter HEADER line.
#   group(1) = numeral token (roman/arabic, possibly OCR-garbled)
#   Optional inline tail beginning with a dash (the "—An Act ..." form).
# Prefix: garbled "Chap" (C + 1-4 letters, dot optional) OR full "CHAPTER".
HEADER_RE = re.compile(
    r"^[^A-Za-z0-9]*"                                   # leading OCR noise
    r"(?:[Cc][HhUuNnRrAaOoEe][AaRrVvPpOo][PpVvRrTt]?[a-zA-Z]{0,3}\.?\s*"
    r"|[Cc][Hh][Aa][Pp][Tt][Ee][Rr]\s*)"               # garble OR full CHAPTER
    r"\.?\s*"
    r"([IVXLCDMivxlcdm0-9JjTtYyLl!|]{1,8})"             # numeral token
    r"\s*[.,;:]?"
    r"(?:\s*[" + _DASH + r"].*)?$",                     # optional inline —An Act…
    re.I,
)

# "AN ACT" with common OCR variants: AN ACT / AN AOT / AN AET / A CT, etc.
AN_ACT_RE = re.compile(r"\bAn?\s+A[CEO][TI]\b", re.IGNORECASE)

# Enactment clause — the DEFINITIVE proof a header begins a real statute body
# (not a Table-of-Contents index entry). TOC entries quote "approved <date>"
# but NEVER contain the enacting clause, so we require the clause itself.
# OCR-tolerant: the phrase "People of the State of California" or the
# "...do enact as follows" tail (allowing OCR noise between words).
ENACT_MARKER_RE = re.compile(
    r"People\s+of\s+the\s+State\s+of\s+California"
    r"|do\s+enact\s+as\s+follow",
    re.I,
)

SEC_RE = re.compile(r"^[§Ss]ec(?:tion|\.)?\s*\.?\s*(\d+)", re.IGNORECASE)

# Month pattern: full names + OCR abbreviations + "Mav" (OCR for May)
_MONTHS = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?"
    r"|May|Mav"
    r"|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?"
    r"|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)

# Keyword pattern for all observed OCR garbling of "APPROVED" / "Passed".
_KW = r"(?:A[Pp]{1,3}[Rr]{1,3}[Oo]?[Vv]\w{0,6}|Pass(?:ed)?)"

# APPROVED_RE — captures (month, day, year); handles 1852+ comma format,
# ordinal day artifacts, "28. 1852" period separator, OCR keyword variants.
APPROVED_RE = re.compile(
    _KW
    + r"\s*[,.]?\s*"
    + r"(" + _MONTHS + r")"
    + r"\s+((?:[IilOo]?\d+|[IilOo])(?:st|nd|rd|th)?)"
    + r"[,.]?\s*(18[3-9]\d)\b",
    re.IGNORECASE,
)

_MONTH_NORM = {
    "jan": "January", "feb": "February", "mar": "March", "apr": "April",
    "may": "May", "mav": "May",
    "jun": "June", "jul": "July", "aug": "August", "sep": "September",
    "oct": "October", "nov": "November", "dec": "December",
}

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
# OCR letters that stand in for 'I' inside roman numerals in this corpus.
_ROMAN_OCR_SUBST = {"J": "I", "T": "I", "1": "I", "!": "I", "|": "I"}


def log_entry(phase, description, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    entry = "[" + ts + "] " + phase + " | " + description + " | " + status + "\n"
    with open(str(LOG_FILE), "a", encoding="utf-8") as f:
        f.write(entry)
    print(entry.strip())


def parse_chapter_number(tok):
    """OCR-tolerant chapter-number parse. Returns int (0 if unparseable).

    Roman numerals in this corpus are heavily OCR-garbled. Conservative
    substitutions applied (in order):
      - lowercase 'l' -> 'I'  (II frequently OCR'd "Il")
      - J, T, 1, !, | -> 'I'
      - a trailing run of 'L' immediately after an 'I' -> 'I'
        (XXVIIL=XXVIII, VIIL=VIII, XXVIL=XXVII)
      - a leading 'A' before an 'L' (ALL=>... seen for XIII-ish) is dropped
        only when it would otherwise yield a non-roman lead; we keep it simple
        and just strip any non-roman letters that remain.
    The parsed value is faithful to the printed (garbled) numeral; it is NOT
    used as a uniqueness key on its own (ingest dedups on citation+page).
    """
    raw = tok.strip().strip(".,;:")
    if not raw:
        return 0
    # Reject ordinal-day artifacts that fired as a header token:
    #   "2d", "3d", "89d", "1st", "4th" -> not chapter numbers.
    if re.fullmatch(r"\d+(?:st|nd|rd|th|d)", raw, re.I):
        return 0
    # lowercase l -> I before uppercasing (preserves "Il" = II)
    raw = raw.replace("l", "I")
    t = raw.upper()
    if t.isdigit():
        try:
            return int(t)
        except ValueError:
            return 0
    sub = "".join(_ROMAN_OCR_SUBST.get(c, c) for c in t)
    # trailing L-run right after an I -> I  (OCR tail artifact)
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
    s = re.sub(r"(?i)(st|nd|rd|th)$", "", s)
    if s.upper() in ("I", "L"):
        return "1"
    if s.upper() == "O":
        return "0"
    s = re.sub(r"^[Il](?=\d)", "1", s)
    s = re.sub(r"^O(?=\d)", "0", s)
    return s if s else "1"


def normalize_month(month_str):
    key = month_str.lower()[:3]
    return _MONTH_NORM.get(key, month_str.capitalize())


def parse_act_date(text):
    # TOMBSTONED (SERIOUS-1 fix, cc006): this function uses the OLD unfixed
    # APPROVED_RE (18[3-9]\\d, no volume_year clamp) and will reproduce the
    # Cluster-A year-misread bug.  Use ingest_from_ocr.py:parse_act_date()
    # for all current and future work.
    raise RuntimeError(
        "reparse.py is archived/unsafe for date parsing (Cluster-A year-misread bug); "
        "use ingest_from_ocr.py"
    )


def has_enact_marker(full_text):
    return bool(ENACT_MARKER_RE.search(full_text))


def is_confident_act(full_text):
    has_an_act = bool(AN_ACT_RE.search(full_text))
    has_date, _ = parse_act_date(full_text)
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
    """A header line starts an act iff AN ACT appears on it or just after."""
    ln = lines[i][1].strip()
    if not HEADER_RE.match(ln):
        return False, None
    m = HEADER_RE.match(ln)
    window = " ".join([ln] + _next_nonempty(lines, i, 4))
    if AN_ACT_RE.search(window):
        return True, m.group(1)
    return False, None


def flush_act(chap_token, start_page, buf, acts_parsed, acts_flagged,
              page_ocr_results):
    """Emit an act ONLY if it has a genuine enactment marker (excludes TOC)."""
    if not buf:
        return
    full = "\n".join(buf).strip()
    if len(full) < 60:
        return

    # TOC / index guard #1: the HEADER line of a real statute body is just the
    # chapter line ("Cuap. XXVI.—An Act ...") — it never carries the approval
    # date inline. A Table-of-Contents entry packs the whole summary onto one
    # line ("Chapter 200,—An Act to change ... approved May fourth, <page>").
    # If the header line itself contains an inline approval/passage keyword, it
    # is an index entry; drop it (its body clause was bled in from a neighbour).
    header_line = re.sub(r"\s+", " ", buf[0]).strip()
    if re.search(r"\b(?:Approved|Passed)\b", header_line, re.I):
        return
    # TOC / index guard #2: a real statute body always carries the enactment
    # clause. Index entries never do.
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

    iso_date, approved_str = parse_act_date(full)
    body_text = re.sub(r"[ \t]+", " ", full)
    # Confident requires AN ACT + parseable date + a parseable chapter number.
    # chapter_int == 0 means the printed chapter numeral was unreadable; we keep
    # the act but flag it rather than citing it as "ch. 0".
    confident = is_confident_act(full) and chap_int > 0

    act_rec = {
        "chapter": str(chap_int),
        "chapter_int": chap_int,
        "chapter_raw": chap_token,
        "title": title,
        "approved_date": approved_str,
        "iso_date": iso_date,
        "text": body_text[:6000],
        "source_page": (start_page or 0) + 1,
        "confident": confident,
        "page_agreement_ratio": page_ocr_results.get(
            start_page, {}
        ).get("agreement_ratio", 0.0),
    }
    if confident:
        acts_parsed.append(act_rec)
    else:
        acts_flagged.append(act_rec)


def reparse_volume(session_label):
    scratch = SCRATCH_ROOT / ("production-" + session_label)
    ocr_path = scratch / "ocr_consensus" / "page_ocr_results.json"
    out_path = scratch / "parsed_acts_fixed.json"

    if not ocr_path.exists():
        log_entry("REPARSE", session_label + ": OCR file missing: " + str(ocr_path), "FAIL")
        return None

    # BEFORE = the existing fixed parse (comma-fix output); fall back to original.
    before_conf = before_flag = 0
    fixed_old = scratch / "parsed_acts_fixed.json"
    orig_old = scratch / "parsed_acts.json"
    src_old = fixed_old if fixed_old.exists() else orig_old
    if src_old.exists():
        try:
            old = json.loads(src_old.read_text(encoding="utf-8"))
            before_conf = len(old.get("confident_acts", []))
            before_flag = len(old.get("flagged_acts", []))
        except Exception:
            pass

    raw_ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
    page_ocr_results = {int(k): v for k, v in raw_ocr.items()}

    lines = []  # list of (page_index, line_text)
    for pidx in sorted(page_ocr_results.keys()):
        text = page_ocr_results[pidx].get("consensus_text", "")
        for line in text.split("\n"):
            lines.append((pidx, line))

    acts_parsed = []
    acts_flagged = []
    current_token = None
    current_page = None
    current_buf = []

    for i, (pidx, line) in enumerate(lines):
        is_hdr, token = header_starts_act(lines, i)
        if is_hdr:
            if current_token is not None:
                flush_act(current_token, current_page, current_buf,
                          acts_parsed, acts_flagged, page_ocr_results)
            current_token = token
            current_page = pidx
            current_buf = [line]
        elif current_token is not None:
            current_buf.append(line)

    if current_token is not None:
        flush_act(current_token, current_page, current_buf,
                  acts_parsed, acts_flagged, page_ocr_results)

    after_conf = len(acts_parsed)
    after_flag = len(acts_flagged)
    result = {"confident_acts": acts_parsed, "flagged_acts": acts_flagged}
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log_entry(
        "REPARSE",
        session_label
        + ": BEFORE confident=" + str(before_conf) + " flagged=" + str(before_flag)
        + " | AFTER confident=" + str(after_conf) + " flagged=" + str(after_flag)
        + " | delta_confident=" + ("+" if after_conf >= before_conf else "")
        + str(after_conf - before_conf)
        + " | wrote " + out_path.name,
        "OK",
    )
    return {
        "volume": session_label,
        "before_confident": before_conf,
        "before_flagged": before_flag,
        "after_confident": after_conf,
        "after_flagged": after_flag,
    }


# ---------------------------------------------------------------------------
# Guard: importing this ARCHIVED module must be side-effect-free (for tests).
# The main reparse loop should never be run; use ingest_from_ocr.py instead.
if __name__ == "__main__":
    log_entry("REPARSE", "=== reparse.py ROUND2 starting -- chapter-format completeness fix ===", "OK")
    log_entry(
        "REPARSE",
        "Handles: separate-line CHAPTER/AN ACT (1850-1857), inline garbled "
        "'Cuap. <roman>.—An Act' (1858-1860), em-dash separators, garbled "
        "Chap prefixes & roman numerals; excludes front-matter TOC via "
        "enactment-marker gate.",
        "OK",
    )

    results = []
    for vol in VOLUMES:
        r = reparse_volume(vol)
        if r:
            results.append(r)

    log_entry("REPARSE", "=== SUMMARY (before->after confident) ===", "OK")
    for r in results:
        log_entry(
            "REPARSE",
            "  " + r["volume"]
            + ": confident " + str(r["before_confident"]) + " -> " + str(r["after_confident"])
            + ", flagged " + str(r["before_flagged"]) + " -> " + str(r["after_flagged"]),
            "OK",
        )
    log_entry("REPARSE", "Output: parsed_acts_fixed.json per volume. Run re_ingest_fixed.py next.", "OK")
