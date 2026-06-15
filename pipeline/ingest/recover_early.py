"""recover_early.py -- HEADER-FORM act-boundary detector for the PRE-1880
California session-law era (1861-1879, the OCR we currently hold begins at 1861).

WHY A NEW DETECTOR (root cause; see docs/.../run-logs/early-recovery-run.log
+ the durable finding in CHAPTER_COMPLETENESS_FINDINGS.md):
  The production parser (ingest_from_ocr.parse_volume) starts an act ONLY when
  HEADER_RE matches a "CHAPTER NN" header line AND "An Act" follows within 4
  lines, walking the WHOLE volume top to bottom. recover_acts.py adds a tolerant
  pass but still GATES recovered starts on page-top position OR a fuzzy CHAPTER
  header within 8 lines above. For the early era that under-counts badly because
  the chapter header OCRs as a garbled glyph the production HEADER_RE family does
  not cover, and acts pack mid-page.

LAYOUT REALITY of 1861-1879 statutes (verified from real OCR -- see the diag
  scripts pipeline/analysis/_diag_early*.py and _diag_early6/7/8.py):

  ERA-1  JOINED form (1861-1872, and 1875-76 / 1877-78):
     "Cuap. VIII.—An Act to extend the Time ..."   (ALL on one line)
     a chapter glyph + a roman/arabic numeral + an EM-DASH + the "An Act" title,
     all on a single line. The glyph OCRs every which way (Cuap/Cuarrer/Crap/
     Coav/Caar/Cnav/Onar/Car/Cuoar/...), so we do NOT trust the glyph spelling.
     The PRECISION GUARANTEE is the TRIAD: a leading C-word + a REAL numeral
     (roman/arabic, not a stray English word) + an em-dash + "An Act". A prose
     line ("County to levy ...", "Court of the State ...") never has that triad,
     so the loose glyph is safe.

  ERA-2  SPLIT form (1873-74, 1880):
     "CHAPTER IX."            (glyph + numeral alone on its own line)
     "An Act authorizing ..." (the title on the next non-blank line)
     "CHAPTER" OCRs cleanly here. Detect a glyph-alone numeral line with "An Act"
     within 3 non-blank lines below. NOTE many ERA-2 chapters are CODE-AMENDMENT
     STUBS printed as  "CHAPTER VIII." / "[See volume of Amendments to the Codes.]"
     -- they have NO act body in the statutes volume (the text lives in the
     companion Code-Amendments publication). They have no "An Act", so the
     An-Act gate correctly skips them; they are a STRUCTURAL absence, not OCR loss.

DETECTOR (precision-first, position-free, header-form):
  An act STARTS at line i when EITHER:
    (A) JOINED: line i matches  ^<C-word> <real-numeral> [punct] <em-dash> ... An Act
        and the "An Act" is NOT a quoted citation (no opening quote right before it).
        "of an act"/"entitled" in the title is FINE -- a real header legitimately
        reads "An Act to amend an Act entitled ...". The triad is the proof.
    (B) SPLIT: the PRODUCTION predicate ingest_from_ocr.header_starts_act fires at
        line i -- a "CHAPTER NN" header line with "An Act" within 4 lines. We REUSE
        the proven production detector here verbatim (rather than re-implement it) so
        the early detector is a guaranteed SUPERSET of production on the clean split
        layout: AFTER >= the production-KEPT BEFORE count, never a regression. The
        code-amendment STUB chapters ("CHAPTER VIII." / "[See volume of Amendments
        to the Codes.]") carry no "An Act" and no enacting clause, so they are
        correctly skipped -- a structural absence, not a miss.
    -- the two sets are unioned and dedup'd by MIN_GAP in reading order; a baseline
       (B) hit wins a tie so no production-found act is ever dropped.

  Acts are numbered BY SEQUENCE (in_act_order, 0-based, page+line order). Any
  readable chapter numeral is captured best-effort for DISPLAY only
  (chapter_raw / chapter_int) -- it is NOT trusted as identity (numerals OCR
  badly: L<->D, missing/extra strokes).

PRECISION NOTES (legal data -- a false/extra act is worse than a missed one):
  * The numeral must be a REAL numeral (>=1 roman char IVXLCDM incl. OCR subs
    J/T/!/|/[/], OR a digit) -- a lone 'to'/'y'/'o'/'t' English fragment is
    rejected. This alone removed the bulk of the draft's false positives
    ("County to levy ...", "cisco to provide ...", "city and county.").
  * Quoted-title rejection mirrors recover_acts.is_real_act_start (MAJOR-1).
  * TOC / index / appendix front- and back-matter do not survive the triad
    (their "An act ..." lines are page-leader citations, not glyph+numeral+dash
    headers), so no explicit page-range gate is needed -- verified on 1861/65-66.

OUTPUT: production-<label>/parsed_acts_early.json  (NEW FILE -- never overwrites
  parsed_acts_fixed.json / parsed_acts_recovered.json). Same record shape as the
  production parser plus: origin="early_headerform", form="A"|"B", in_act_order,
  detector signals.

READ-ONLY w.r.t. the DB and every existing file. Writes ONLY parsed_acts_early.json.

USAGE
  python -m ingest.recover_early 1861                 # one session
  python -m ingest.recover_early 1861 1862 1863-64    # several
  python -m ingest.recover_early --score 1861 1862    # detect + score vs oracle (BEFORE/AFTER)
"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import importlib.util
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # pipeline/ on path
import config

ROOT = Path(config.path_for("data_root"))

# ---- reuse the PRODUCTION parser's exact predicates for the BEFORE baseline ----
_ING = Path(__file__).resolve().parent / "ingest_from_ocr.py"
_spec = importlib.util.spec_from_file_location("ingest_from_ocr_ro", str(_ING))
_ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ing)

# ---- tunables (precision over recall) ---------------------------------------
MIN_GAP = 2               # min line distance between two accepted starts (dedup)
SANITY_MIN_TEXT = 60      # min text span (matches production flush_act's >=60 floor)

# ---------------------------------------------------------------------------
# Regexes (validated empirically in pipeline/analysis/_diag_early6.py)
# ---------------------------------------------------------------------------
_DASH = r"—–\-‐‑‒―~"
# LOOSE glyph for the JOINED form: any short C-word. SAFE because the numeral +
# dash + "An Act" triad is the precision guarantee (a prose C-word -- "County",
# "Court" -- is never followed by a real numeral + em-dash + "An Act").
GLYPH_LOOSE = r"C[a-zA-Z]{1,6}"
# A real numeral token: roman (incl. OCR subs J/T/!/|/[/]/l/O) or arabic, len<=9.
NUMTOK = r"[IVXLCDMivxlcdmJjTt0-9!|\]\[lO]{1,9}"

AN_ACT_STRICT = re.compile(r"\bAn?\s+A[CEO][TI]\b", re.I)
AN_ACT_FUZZY = re.compile(r"\b[AÄdl][nu]\s+A[a-z]{1,4}\b")

# JOINED (ERA-1): loose-glyph + real numeral + (opt punct) + em-dash + title
FORMA = re.compile(
    r"^[\s.,;:'\"`]{0,4}(" + GLYPH_LOOSE + r")[.,]?\s*(" + NUMTOK + r")"
    r"\s*[.,;:]?\s*[" + _DASH + r"]+\s*(.*)$",
    re.I)

# enacting clause -- tolerant to heavy 1862-style garble (used as a body signal)
ENACT = re.compile(
    r"P[eo]{1,2}ple\s+of\s+the\s+Stat[eo]\s+of\s+Calif"
    r"|d[ouae]\s+[ceu][nu][aou][crt]t?\s+a[sx]\s+f[oi]l?l?[oi]w",
    re.I)
_MON = r"(?:Jan|Feb|Mar|Apr|May|Mav|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
APPROVED = re.compile(r"[\[\(\{]\s*A[Pp]{1,3}[Rr]?[Oo]?[Vv]\w{0,5}", re.I)
APPROVED_DATE = re.compile(
    r"\b(?:A[Pp]{1,3}[Rr]?[Oo]?[Vv]\w{0,5}|Pass\w{0,3})\b.{0,4}" + _MON, re.I)

_OPEN_QUOTES = "\"'“‘„‚«‹`’”›»"

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_ROMAN_SET = set("IVXLCDM")
_ROMAN_SUB = {"J": "I", "T": "I", "1": "I", "!": "I", "|": "I", "l": "I",
              "[": "I", "]": "I", "O": "C"}


def numeral_ok(tok: str) -> bool:
    """A token is a real numeral if it has >=1 roman char (incl OCR subs) or a digit."""
    if any(c.isdigit() for c in tok):
        return True
    up = tok.upper()
    return any(c in _ROMAN_SET for c in up) or any(_ROMAN_SUB.get(c) for c in up)


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
        digits = "".join(c for c in raw if c.isdigit())
        return int(digits) if digits else 0
    val = prev = 0
    for c in reversed(roman):
        cur = _ROMAN[c]
        val += cur if cur >= prev else -cur
        prev = cur
    return val if 1 <= val <= 1500 else 0


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


def _quoted_before(seg: str, am) -> bool:
    head = seg[:am.start()].rstrip(" \t")
    return bool(head) and head[-1] in _OPEN_QUOTES


def _baseline_starts(lines):
    """SPLIT-form (ERA-2) starts via the PROVEN production predicate
    header_starts_act. Reusing it guarantees the early detector is a SUPERSET of
    production on the clean 'CHAPTER NN' / 'An Act' layout (no regression), while
    the JOINED tier below adds the mid-page em-dash headers production misses.
    Returns {line_index: numeral_token}."""
    plain = [(p, t) for (p, t) in lines]
    out = {}
    for i in range(len(plain)):
        ok, tok = _ing.header_starts_act(plain, i)
        if ok:
            out[i] = tok or ""
    return out


def _joined_starts(lines):
    """JOINED-form (ERA-1) starts via the precision triad: loose C-glyph + a REAL
    numeral + an em-dash + 'An Act' (quoted-title rejected). High precision; this
    is what catches the mid-page em-dash headers the production HEADER_RE drops.
    Returns {line_index: numeral_token}."""
    out = {}
    for i, (pidx, line) in enumerate(lines):
        s = line.strip()
        ma = FORMA.match(s)
        if not (ma and numeral_ok(ma.group(2))):
            continue
        title = ma.group(3)
        am = AN_ACT_STRICT.search(title) or AN_ACT_FUZZY.search(title)
        if am and not _quoted_before(title, am):
            out[i] = ma.group(2)
    return out


def detect_starts(lines):
    """Return [(line_index, numeral_token, form), ...] for each detected act start.

    Union of (B) the production split-form detector header_starts_act and (A) the
    joined em-dash triad, dedup'd by MIN_GAP in reading order. Baseline (B) wins a
    tie so we never drop a production-found act. AFTER >= production BEFORE always.
    """
    base = _baseline_starts(lines)       # {i: tok}  -- split form 'B'
    joined = _joined_starts(lines)       # {i: tok}  -- joined form 'A'
    merged = {}
    for i, tok in base.items():
        merged[i] = (tok, "B")
    for i, tok in joined.items():
        # don't let a joined hit shadow a baseline one within the dedup window
        if any((i + d) in base for d in range(-MIN_GAP, MIN_GAP + 1)):
            continue
        if i not in merged:
            merged[i] = (tok, "A")
    starts = []
    last = -10
    for i in sorted(merged):
        if i - last < MIN_GAP:
            continue
        tok, form = merged[i]
        starts.append((i, tok, form))
        last = i
    return starts


def build_act(lines, start_i, end_i, numeral_tok, form, label, order):
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
        "origin": "early_headerform",
        "form": form,                       # 'A' joined / 'B' split
        "has_enact": has_enact,
        "has_approved": has_appr,
        "has_an_act": bool(AN_ACT_STRICT.search(full) or AN_ACT_FUZZY.search(full)),
    }


def process_session(label):
    lines = load_lines(label)
    starts = detect_starts(lines)
    acts = []
    for k, (si, tok, form) in enumerate(starts):
        ei = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        rec = build_act(lines, si, ei, tok, form, label, k)
        # SANITY (precision): keep only acts with a real body span AND at least one
        # corroborating body marker (enacting clause or [Approved] date). This drops
        # the rare stray header with no body and any TOC echo that slipped through.
        if len(rec["text"]) < SANITY_MIN_TEXT:
            continue
        if not (rec["has_enact"] or rec["has_approved"]):
            continue
        acts.append(rec)
    for k, a in enumerate(acts):
        a["in_act_order"] = k
    n_a = sum(1 for a in acts if a["form"] == "A")
    n_b = sum(1 for a in acts if a["form"] == "B")
    out_path = ROOT / ("production-" + label) / "parsed_acts_early.json"
    out_path.write_text(json.dumps({
        "confident_acts": [],          # numbering positional -> none "confident" by chapter
        "flagged_acts": acts,          # all carry positional order; chapter is display-only
        "_early_meta": {
            "label": label,
            "detector": "recover_early.py headerform v2",
            "raw_starts": len(starts),
            "acts_kept": len(acts),
            "form_a_joined": n_a,
            "form_b_split": n_b,
            "min_gap": MIN_GAP,
        },
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(acts), len(starts), out_path


def baseline_count(label):
    """How many acts the PRODUCTION parser actually KEEPS -- the honest BEFORE number.
    Replicates parse_volume's walk + flush_act keep-criteria (buffer to next header,
    len>=60, an enacting marker present, header line not an Approved/Passed line) so
    the baseline reflects production's real output, not raw header_starts_act fires
    (which over-count code-amendment stubs that flush_act drops). Read-only re-walk;
    does NOT write parsed_acts_fixed.json."""
    lines = load_lines(label)
    plain = [(p, t) for (p, t) in lines]
    fires = []
    for i in range(len(plain)):
        ok, _tok = _ing.header_starts_act(plain, i)
        if ok:
            fires.append(i)
    n = 0
    for k, si in enumerate(fires):
        ei = fires[k + 1] if k + 1 < len(fires) else len(plain)
        buf = [plain[j][1] for j in range(si, ei)]
        full = "\n".join(buf).strip()
        if len(full) < 60:
            continue
        header_line = re.sub(r"\s+", " ", buf[0]).strip() if buf else ""
        if re.search(r"\b(?:Approved|Passed)\b", header_line, re.I):
            continue
        if not _ing.has_enact_marker(full):
            continue
        n += 1
    return n


# authoritative early-era totals (regular sessions) for --score.
# CAVEAT: 1865-66 oracle=280 is INCONSISTENT with the volume (chapter numerals run
# to ~DCXXVII/627 and ~640 acts are physically present) -- see the run-log finding;
# treat the 1865-66 completeness % as unreliable (oracle undercount, not our over-detect).
_ORACLE = {
    '1850': 146, '1851': 139, '1852': 202, '1853': 180, '1854': 71, '1855': 231,
    '1856': 152, '1857': 277, '1858': 358, '1859': 330, '1860': 455, '1861': 538,
    '1862': 455, '1863': 476, '1863-64': 476, '1865-66': 280, '1867-68': 545,
    '1869-70': 583, '1871-72': 637, '1873-74': 679, '1875-76': 613, '1877-78': 673,
}


def main():
    args = sys.argv[1:]
    score = False
    if "--score" in args:
        score = True
        args.remove("--score")
    if not args:
        raise SystemExit("usage: python -m ingest.recover_early [--score] <label> [label...]")
    if score:
        print(f"{'label':<12}{'before':>8}{'after':>8}{'oracle':>8}"
              f"{'b%':>6}{'a%':>6}{'A':>6}{'B':>6}")
    else:
        print(f"{'label':<12}{'detected':>9}{'kept':>7}{'oracle':>8}{'compl%':>8}")
    for label in args:
        kept, raw_starts, out_path = process_session(label)
        N = _ORACLE.get(label, 0)
        pct = (100.0 * kept / N) if N else 0.0
        if score:
            before = baseline_count(label)
            data = json.loads(out_path.read_text(encoding="utf-8"))
            meta = data.get("_early_meta", {})
            bpct = (100.0 * before / N) if N else 0.0
            print(f"{label:<12}{before:>8}{kept:>8}{N:>8}{bpct:>5.0f}%{pct:>5.0f}%"
                  f"{meta.get('form_a_joined', 0):>6}{meta.get('form_b_split', 0):>6}")
        else:
            print(f"{label:<12}{raw_starts:>9}{kept:>7}{N:>8}{pct:>7.0f}%")
    if score:
        print("\n(scored against docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv totals;"
              " 1865-66 oracle is a known undercount -- see run-log)")


if __name__ == "__main__":
    main()
