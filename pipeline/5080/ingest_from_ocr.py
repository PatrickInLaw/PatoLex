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

SCRATCH_ROOT = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch")
LOG_FILE = Path(
    r"C:\Users\PatrickKolasinski\Documents\GitHub\patolex"
    r"\docs\80_PROJECT_HISTORY\run-logs\resume-5090-run.log"
)
PSQL = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"

# session_label -> (session_str, legislature_ordinal, start_year)
# TODO: LEGISLATURE_MAP is duplicated in pipeline/ingest_clean.py.
#       Consolidate into a shared module when the two pipelines are unified.
LEGISLATURE_MAP = {
    "1861": ("1861", "12th"), "1862": ("1862", "13th"),
    "1863": ("1863", "14th"), "1863-64": ("1863-64 adjourned", "15th"),
    "1865-66": ("1865-66", "16th"), "1867-68": ("1867-68", "17th"),
    "1869-70": ("1869-70", "18th"), "1871-72": ("1871-72", "19th"),
    "1873-74": ("1873-74", "20th"), "1875-76": ("1875-76", "21st"),
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


def parse_act_date(text, volume_year=None):
    """Return (iso_date_str, raw_match_str) or (None, "").

    volume_year -- the nominal calendar year of the source volume (e.g. 1855
    for the 1855 session, or 1863 for the "1863-64" session).  When supplied,
    any parsed year that falls OUTSIDE the window
        [volume_year - YEAR_CLAMP_WINDOW, volume_year + YEAR_CLAMP_WINDOW]
    is REJECTED and the next regex match is tried instead of accepting a date
    that is clearly a result of OCR digit corruption (Cluster-A bug) or body-
    text date poisoning (Cluster-B bug).

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
    """
    # Clamp window size (years).  Change here to widen/tighten everywhere.
    YEAR_CLAMP_WINDOW = 3

    def _year_ok(year_int):
        if volume_year is None:
            return True  # no context -> no check (legacy call-sites unaffected)
        return abs(year_int - volume_year) <= YEAR_CLAMP_WINDOW

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
                continue  # Cluster-A: year out of range -> skip, try next match
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
              page_ocr_results, volume_year=None):
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
    iso_date, approved_str = parse_act_date(full, volume_year=volume_year)
    body_text = re.sub(r"[ \t]+", " ", full)
    confident = is_confident_act(full, volume_year=volume_year) and chap_int > 0
    act_rec = {
        "chapter": str(chap_int), "chapter_int": chap_int,
        "chapter_raw": chap_token, "title": title,
        "approved_date": approved_str, "iso_date": iso_date,
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
    for i, (pidx, line) in enumerate(lines):
        is_hdr, token = header_starts_act(lines, i)
        if is_hdr:
            if current_token is not None:
                flush_act(current_token, current_page, current_buf,
                          acts_parsed, acts_flagged, page_ocr_results,
                          volume_year=volume_year)
            current_token, current_page, current_buf = token, pidx, [line]
        elif current_token is not None:
            current_buf.append(line)
    if current_token is not None:
        flush_act(current_token, current_page, current_buf,
                  acts_parsed, acts_flagged, page_ocr_results,
                  volume_year=volume_year)
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
