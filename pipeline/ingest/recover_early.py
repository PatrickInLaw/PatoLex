"""recover_early.py -- HEADER-FREE act-boundary detector for the PRE-1880
California session-law era (1850-1879).

WHY A NEW DETECTOR (root cause; see docs/.../run-logs/early-recovery-run.log
+ the durable finding in SCHEMA/DATA notes):
  The production parser (ingest_from_ocr.parse_volume) starts an act ONLY when
  HEADER_RE matches a "CHAPTER NN" line AND "An Act" follows within 4 lines.
  recover_acts.py adds a tolerant pass but still GATES recovered starts on
  page-top position OR a fuzzy CHAPTER header within 8 lines above. BOTH gates
  are wrong for the early era:

  Layout reality of 1850-1879 statutes (verified from real OCR, e.g. 1861 p.45,
  1862 p.49, 1875-76):
    * The act header is a SINGLE line:  "Cuap. II.<em-dash>An Act to ..."
      (chapter glyph + roman/arabic numeral + em-dash + the "An Act" title all
      on ONE line).
    * Acts START MID-PAGE -- the next act begins wherever the previous one ends,
      so the page-top gate (PAGE_TOP_MAX) discards most of them.
    * Immediately below the header: "[Approved <date>]" then the enacting clause
      "The People of the State of California ... do enact as follows".
    * OCR garble is heavy and ERA-DEPENDENT: in 1862 the enacting clause OCR'd as
      "do cart as follows" / "le enact us follows" / "du cunct ax follows" -- an
      EXACT "do enact as follows" probe misses ~70% of 1862 acts. The chapter
      glyph + "[Approved <date>]" bracket is the MOST OCR-robust pairing and is
      what this detector keys on.
    * 1850 (and 1851-54) use "Passed <date>." instead of "[Approved <date>]" and
      print "Chap. NN" on its OWN line with "AN ACT" on the NEXT line -- handled.

DETECTOR (precision-first, position-free, header-free):
  An act STARTS at line i when ALL hold:
    1. line i is a CHAPTER-MARKER line: starts with a chapter glyph (Chap/Cuap/
       Cuarrer/Crap/Ciap/Cnap/Cuav/Cuar/Cap/... OCR variants) followed by a
       numeral-ish token (roman incl. OCR subs, or arabic). The glyph must be at
       the START of the line (a mid-line "Chapter 2 of the Code" is a body ref).
    2. an "An Act" title is on line i OR within ANACT_LOOKAHEAD lines below.
    3. an ACT MARKER (enacting clause OR an "[Approved/Passed <date>]" line)
       appears within MARKER_LOOKAHEAD lines below.
    4. it is NOT a body citation: no body-ref cue ('of an act','entitled',
       'said act','provisions of ... act') on the header line; no opening quote
       immediately before "An Act"; nothing but the chapter glyph before it.
    5. not within MIN_GAP lines of the previously accepted start (dedup).

  Acts are numbered BY SEQUENCE (in_act_order, 0-based, page+line order). Any
  readable chapter numeral is captured best-effort for DISPLAY only
  (chapter_raw / chapter_int) -- it is NOT trusted as identity.

OUTPUT: production-<label>/parsed_acts_early.json  (NEW FILE -- never overwrites
  parsed_acts_fixed.json / parsed_acts_recovered.json). Same record shape as the
  production parser plus: origin="early_headerfree", in_act_order, detector signals.

READ-ONLY w.r.t. the DB and every existing file. Writes ONLY parsed_acts_early.json.

USAGE
  python -m ingest.recover_early 1861                 # one session
  python -m ingest.recover_early 1850 1861 1862 ...   # several
  python -m ingest.recover_early --score 1861 1862    # detect + score vs oracle
"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # pipeline/ on path
import config

ROOT = Path(config.path_for("data_root"))

# ---- tunables (kept conservative; precision over recall) --------------------
ANACT_LOOKAHEAD = 3       # lines at/after the chap-marker to find an "An Act" title
MARKER_LOOKAHEAD = 12     # lines at/after to find enacting clause OR approval line
MIN_GAP = 2               # min line distance between two accepted starts (dedup)

# ---------------------------------------------------------------------------
# Chapter-marker glyph at the START of a line. The early printers set it as
# "Chap." / "Chapter" / "Cuap." etc.; OCR mangles the body of the word but the
# leading 'C' + a vowel + a short tail is stable. We require: line-start, a
# C-word of 3-8 letters whose 2nd char is a vowel-ish glyph (h/u/n/i/o/r/a),
# an optional trailing 'r'/'t', an optional '.', then a NUMERAL-ish token.
# The numeral token is captured but NOT used to gate (numerals OCR badly).
# ---------------------------------------------------------------------------
CHAP_MARKER = re.compile(
    r"^[\s.,;:'\"—–\-]{0,4}"
    r"(C[huniora][a-z]{0,6}\.?)"            # Chap / Cuap / Cuarrer / Crap / Ciap / Cnap / Cuav / Cap ...
    r"[\s.—–\-]{0,3}"
    r"([IVXLCDMivxlcdmJjTtYy0-9!|\]\[lo]{1,8})"   # numeral-ish (roman+arabic+OCR subs)
    r"\b",
    re.I)

# "An Act" title -- strict form (the production regex) + a looser garble form
# for badly-OCR'd titles ("An slet", "dn det", "ln lect", "An det").
AN_ACT_STRICT = re.compile(r"\bAn?\s+A[CEO][TI]\b", re.I)
AN_ACT_FUZZY = re.compile(r"\b[AÄdluo][nun]\s+[AsdБ][a-z]{1,4}\b")

# enacting clause -- tolerant to the heavy 1862-style garble
ENACT = re.compile(
    r"P[eo]{1,2}ple\s+of\s+the\s+State\s+of\s+Calif"
    r"|d[ouae]\s+[ceu][un][aou][crt]t?\s+a[sx]\s+f[oi]l?l?[oi]w",
    re.I)
# "[Approved <Month> <day>, 18xx]" / "(Approved...)" / "Passed <Month>..." -- the
# most OCR-robust act marker. Tolerate bracket variants and Approved/Passed garble.
_MON = r"(?:Jan|Feb|Mar|Apr|May|Mav|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
APPROVED = re.compile(
    r"[\[\(\{]\s*A[Pp]{1,3}[Rr]?[Oo]?[Vv]\w{0,5}",     # "[Approved" (+garble)
    re.I)
APPROVED_DATE = re.compile(
    r"\b(?:A[Pp]{1,3}[Rr]?[Oo]?[Vv]\w{0,5}|Pass\w{0,3})\b.{0,4}" + _MON,
    re.I)

# body-reference cues -- reject these as act starts (they cite another act)
BODYREF = re.compile(
    r"of\s+an\s+act\b|\bentitled\b|\bsaid\s+act\b"
    r"|provisions?\s+of\s+(?:the\s+|an\s+)?act|under\s+an\s+act"
    r"|amendatory\s+of\s+an\s+act|supplement\w*\s+to\s+an\s+act",
    re.I)
_OPEN_QUOTES = "\"'“‘„‚«‹`’”›»"

# roman numeral parse with the common OCR substitutions
_ROMAN = {"I":1,"V":5,"X":10,"L":50,"C":100,"D":500,"M":1000}
_ROMAN_SUB = {"J":"I","T":"I","1":"I","!":"I","|":"I","l":"I","[":"I","]":"I",
              "Y":"V","o":"O"}


def parse_chapter_numeral(tok: str) -> int:
    """Best-effort chapter number from a numeral-ish token. DISPLAY ONLY."""
    raw = (tok or "").strip().strip(".,;:[]")
    if not raw:
        return 0
    if raw.isdigit():
        try:
            return int(raw)
        except ValueError:
            return 0
    sub = "".join(_ROMAN_SUB.get(c, c) for c in raw.upper())
    roman = "".join(c for c in sub if c in _ROMAN)
    if not roman:
        # maybe arabic after substitution
        digits = "".join(c for c in raw if c.isdigit())
        return int(digits) if digits else 0
    val = prev = 0
    for c in reversed(roman):
        cur = _ROMAN[c]
        val += cur if cur >= prev else -cur
        prev = cur
    return val if 1 <= val <= 1200 else 0


def load_lines(label):
    """Return [(page_index, line_text), ...] in page+line reading order."""
    ocr_path = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(ocr_path.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    lines = []
    for pidx in sorted(pages):
        for ln in pages[pidx].get("consensus_text", "").split("\n"):
            lines.append((pidx, ln))
    return lines


def _anact_at(lines, i):
    """An 'An Act' title on line i or within ANACT_LOOKAHEAD lines below."""
    for j in range(i, min(len(lines), i + 1 + ANACT_LOOKAHEAD)):
        t = lines[j][1]
        if AN_ACT_STRICT.search(t) or AN_ACT_FUZZY.search(t):
            return True
    return False


def _marker_ahead(lines, i):
    """An enacting clause OR an Approved/Passed-date marker within MARKER_LOOKAHEAD."""
    for j in range(i, min(len(lines), i + 1 + MARKER_LOOKAHEAD)):
        t = lines[j][1]
        if ENACT.search(t) or APPROVED.search(t) or APPROVED_DATE.search(t):
            return True
    return False


def _is_bodyref_header(line: str, m) -> bool:
    """Reject a chap-marker line that is actually a body citation, not an act start."""
    s = line.strip()
    if BODYREF.search(s):
        return True
    # opening quote immediately before an "An Act" later on the line -> quoted title
    am = AN_ACT_STRICT.search(s) or AN_ACT_FUZZY.search(s)
    if am:
        head = s[:am.start()].rstrip(" \t")
        if head and head[-1] in _OPEN_QUOTES:
            return True
    return False


def detect_starts(lines):
    """Return list of (line_index, numeral_token) for each detected act start."""
    starts = []
    last = -10
    for i, (pidx, line) in enumerate(lines):
        s = line.strip()
        m = CHAP_MARKER.match(s)
        if not m:
            continue
        if i - last < MIN_GAP:
            continue
        if not _anact_at(lines, i):
            continue
        if _is_bodyref_header(line, m):
            continue
        if not _marker_ahead(lines, i):
            continue
        starts.append((i, m.group(2)))
        last = i
    return starts


def build_act(lines, start_i, end_i, numeral_tok, volume_year, label, order):
    buf = [lines[j][1] for j in range(start_i, end_i)]
    start_page = lines[start_i][0]
    full = "\n".join(buf).strip()
    chap_int = parse_chapter_numeral(numeral_tok)
    title = ""
    for ln in buf:
        am = AN_ACT_STRICT.search(ln) or AN_ACT_FUZZY.search(ln)
        if am:
            title = re.sub(r"\s+", " ", ln).strip()[:500]
            break
    if not title and buf:
        title = re.sub(r"\s+", " ", buf[0]).strip()[:300]
    body_text = re.sub(r"[ \t]+", " ", full)
    has_enact = bool(ENACT.search(full))
    has_appr = bool(APPROVED.search(full) or APPROVED_DATE.search(full))
    return {
        "chapter": str(chap_int), "chapter_int": chap_int,
        "chapter_raw": (numeral_tok or "").strip(),
        "title": title,
        "approved_date": "", "iso_date": None,
        "text": body_text[:6000], "source_page": start_page + 1,
        "in_act_order": order,
        "confident": False,                 # numbering is positional, not certified
        "origin": "early_headerfree",
        "has_enact": has_enact,
        "has_approved": has_appr,
        "has_an_act": bool(AN_ACT_STRICT.search(full) or AN_ACT_FUZZY.search(full)),
    }


def process_session(label):
    lines = load_lines(label)
    m = re.match(r"(\d{4})", label)
    volume_year = int(m.group(1)) if m else 0
    starts = detect_starts(lines)
    acts = []
    for k, (si, tok) in enumerate(starts):
        ei = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        rec = build_act(lines, si, ei, tok, volume_year, label, k)
        # minimal sanity: keep only acts with real body + at least one act-marker
        if len(rec["text"]) < 80:
            continue
        if not (rec["has_enact"] or rec["has_approved"]):
            continue
        acts.append(rec)
    # renumber in_act_order densely after the sanity drop
    for k, a in enumerate(acts):
        a["in_act_order"] = k
    out_path = ROOT / ("production-" + label) / "parsed_acts_early.json"
    out_path.write_text(json.dumps({
        "confident_acts": [],          # numbering positional -> none "confident" by chapter
        "flagged_acts": acts,          # all carry positional order; chapter is display-only
        "_early_meta": {
            "label": label,
            "detector": "recover_early.py headerfree v1",
            "raw_starts": len(starts),
            "acts_kept": len(acts),
            "anact_lookahead": ANACT_LOOKAHEAD,
            "marker_lookahead": MARKER_LOOKAHEAD,
        },
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(acts), len(starts), out_path


# authoritative early-era totals (regular sessions) for --score
_ORACLE = {
    '1850':146,'1851':139,'1852':202,'1853':180,'1854':71,'1855':231,'1856':152,
    '1857':277,'1858':358,'1859':330,'1860':455,'1861':538,'1862':455,
    '1863':476,'1863-64':476,'1865-66':280,'1867-68':545,'1869-70':583,
    '1871-72':637,'1873-74':679,'1875-76':613,'1877-78':673,
}


def main():
    args = sys.argv[1:]
    score = False
    if "--score" in args:
        score = True
        args.remove("--score")
    if not args:
        raise SystemExit("usage: python -m ingest.recover_early [--score] <label> [label...]")
    print(f"{'label':<12}{'detected':>9}{'kept':>7}{'oracle':>8}{'compl%':>8}")
    for label in args:
        kept, raw_starts, out_path = process_session(label)
        N = _ORACLE.get(label, 0)
        pct = (100.0 * kept / N) if N else 0.0
        line = f"{label:<12}{raw_starts:>9}{kept:>7}{N:>8}{pct:>7.0f}%"
        print(line)
    if score:
        print("\n(scored against docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv totals)")


if __name__ == "__main__":
    main()
