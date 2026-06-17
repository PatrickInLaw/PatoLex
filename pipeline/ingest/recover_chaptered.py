"""recover_chaptered.py -- ADDITIVE recovery pass for the CHAPTERED ERA (1880-1999)
California session laws. PRECISION-FIRST. READ-ONLY w.r.t. the DB and every existing
file; writes ONLY a NEW parsed_acts_chaptered_v2.json per volume (never touches
parsed_acts_fixed.json / parsed_acts_recovered.json / parsed_acts_early.json).

(An earlier sequence-numbering draft of this file is preserved alongside as
 _archived_recover_chaptered_v1_seqnum.py.txt. THIS version implements the
 approval-footer-witness recommendation from the detection-miss diagnosis.)

WHY (see docs/80_PROJECT_HISTORY/run-logs/chaptered-detection-diag.md):
  The production parser (ingest_from_ocr) and recover_acts KEEP an act only when
  has_enact_marker(full) is True -- i.e. "People of the State of California" or "do
  enact as follow" appears in the body. In the chaptered era a large class of REAL acts
  has NO enacting clause by design: the out-of-sequence "redirect-stub" entries whose
  printed text was chaptered elsewhere, leaving only

      CHAPTER 88.
      An act to amend section 809 of the Agricultural Code ...
      [Approved by the Governor April 13, 1933. In effect August 21, 1933]
      Note.--For text see Stats. 1933, Ch. 25.

  Header + "An Act" + an [Approved ...] / "Filed with Secretary of State" footer is, by
  itself, a complete and valid act boundary. These were silently dropped (dominant 1933
  miss, ~94 acts in one volume). Two OTHER classes inflate the apparent "gap" but are
  NOT real statutes / not act-starts and must be EXCLUDED, not counted as misses:
    * RESOLUTIONS (Concurrent/Constitutional Resolutions, charter approvals) -- carry a
      CHAPTER number but never "An Act"; they live in a separate section whose chapter
      numbers RESTART at 1, so counting them would also corrupt numbering. EXCLUDED.
    * BODY cross-references ("...to repeal chapter 32, Statutes of 1911...") -- a CHAPTER
      token mid-sentence, never an act start. EXCLUDED by the line-head anchor + case.

WHAT THIS DETECTOR DOES (the diagnosis's recommendation):
  1. Detect an act START only at a LINE-HEAD "CHAPTER <numeral>" (anchored ^, UPPERCASE
     CHAP glyph). Never mid-sentence -> removes the body-reference false misses.
  2. Replace the enacting-clause keep-gate with an APPROVAL-FOOTER witness: keep when the
     entry has the header + an "An Act" title (within a widened lookahead that steps over
     "Note.--"/"Stats ..." margin lines) AND an [Approved <date>] / "Filed with Secretary
     of State" / "In effect" footer -- EVEN WITHOUT "do enact".
  3. Re-segment stacked headers (each line-head header is its own act start; the buffer
     runs to the NEXT line-head header) so two acts on one page are two acts.
  4. Tolerate a trailing garbled glyph on the numeral ("CHAPTER 25,#", "CHAPTER 92#.").
  5. EXCLUDE resolutions (no "An Act"). Keep quoted-title / body-ref guards on the title.
  6. FLAG redirect-stubs (status="codes_redirect") when a "see Stats. ... Ch." note is
     present AND there is no enacting clause (text lives in the Codes volume) -- counted
     as REAL chapters, marked distinctly for later text-join.
  7. Number by the header's OWN clean numeral. A second line-head header bearing a chapter
     number already emitted in THIS volume is flagged (status="dup_number") and NOT counted
     toward the distinct-chapter set -> 0 new duplicate chapter numbers in the output.

OUTPUT record fields:
  chapter, chapter_int, chapter_raw, title, approved_date, iso_date, text, source_page,
  has_an_act, has_enact, has_approval, has_redirect_note, status, origin="chaptered_v2"
  status in: "chaptered" | "codes_redirect" | "dup_number".
  Resolutions and body cross-references are never emitted.

USAGE
  python -m ingest.recover_chaptered 1933-vol1-chapters
  python -m ingest.recover_chaptered --score 1931-vol1-chapters 1933-vol1-chapters
  python -m ingest.recover_chaptered 1893 1895 1897
"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import importlib.util
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # pipeline/ on path
import config

ROOT = Path(config.path_for("data_root"))

# ---- reuse the PRODUCTION parser's exact predicates ----
_ING = Path(__file__).resolve().parent / "ingest_from_ocr.py"
_spec = importlib.util.spec_from_file_location("ingest_from_ocr_chap_ro", str(_ING))
ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ing)

# ---------------------------------------------------------------------------
# Regexes -- precision over recall
# ---------------------------------------------------------------------------
# LINE-HEAD chapter header. Anchored ^ with only light leading noise. The glyph must be
# an UPPERCASE "CHAP..." family token (body cross-refs read lowercase "chapter N, Statutes
# of ..."). Numeral group is arabic (the chaptered era prints arabic). We allow a trailing
# garble glyph + punctuation AFTER the numeral, plus a SHORT margin note ("Stats 1931,")
# -- but the line must NOT run on into a full sentence (guarded in is_header_line()).
#   matches: "CHAPTER 88."  "CHAPTER 25,"  "CHAPTER 92#."  "CHAP. 17"  "CHAPTER 4,"
#   rejects: "chapter 400. Laws of 1931" (lowercase) , mid-sentence "...chapter 32,"
HEAD_RE = re.compile(
    r"^[^A-Za-z0-9]{0,4}"
    r"(C[Hh][A-Za-z]{0,5}\.?)"          # C-leading glyph (CHAPTER/CHAP./garble), case kept
    r"[.,\s]+"
    r"([0-9]{1,4})"                     # arabic numeral
    r"(?:[^0-9A-Za-z\s]{0,2})"          # optional trailing garble glyph(s)
    r"\s*[.,;:]?\s*(.*)$")

AN_ACT_RE = ing.AN_ACT_RE                      # r"\bAn?\s+A[CEO][TI]\b" (case-insensitive)
APPROVAL_RE = re.compile(
    r"\[?\s*Approved\b"
    r"|Filed\s+with\s+Secretary\s+of\s+State"
    r"|In\s+effe[ce]t\b"
    r"|Approved\s+by\s+(?:the\s+)?Governor", re.I)
# Redirect-stub "Note" line. The leading "Note" token OCRs wildly in this era
# (Norz / Notze / NoTE / Nore / Notre / Nonrr / Norr / Nortre ...) -- but every misread
# is a "No"+>=2-letters token, NOT the body footnote abbreviation "No." (number). The
# prior `\bN[A-Za-z]{1,5}` latitude admitted "No. ... see Stats. ..." body footnotes
# as redirect notes (MAJOR-B3). FIX: anchor strictly on a genuine NOTE-family token --
# "No" + 2-5 MORE letters (Note/NoTE/Norz/Notze/Nore/Notre/Norr/Norte/...) -- so the
# bare 2-letter "No." abbreviation can never anchor a match. The "(For text) see/Xce
# Stats. 19xx" pointer is kept as the precise cue ("Xce" is the common OCR read of
# "See"); a chapter "Ch. n" pointer is NOT required because it frequently sits on the
# next OCR line (page-break truncation) -- requiring it dropped 7 genuine 1933
# redirect-stubs. "No. see Stats." no longer matches (No. carries no Note-family tail).
REDIRECT_NOTE_RE = re.compile(
    r"\bNo[A-Za-z]{2,5}\.?\s*[.\-—–~]*\s*(?:For\s+text\s+)?(?:[Xx]ce|[sS]ee)"
    r"\s+Stats\.?\s*,?\s*\d{2,4}",
    re.I)
RESOLUTION_RE = re.compile(
    r"Concurrent\s+Resolution"
    r"|Constitutional\s+Amendment"
    r"|Joint\s+Resolution"
    r"|\bResolution\s+No", re.I)

_OPEN_QUOTES = "\"'“‘„‚«‹`’”›»"
# a body-ref cue at the START of the title line means this "An act" is a citation
BODYREF_HEAD_CUE = re.compile(r"^\s*(?:of\s+an\s+act\b|an\s+act\s+of\s+congress|under\s+an\s+act)", re.I)

AN_ACT_LOOKAHEAD = 6        # lines past the header to find the "An Act" title (steps over Note/margin)
APPROVAL_LOOKAHEAD = 40     # lines past the header to find the approval footer
CA_CEILING = 4000           # chaptered-era max ~ a few thousand; reject OCR-garble above
# a header glyph must be one of these (uppercased) OR a short CH-leading token
_GLYPH_OK = {"CHAPTER", "CHAP", "CHAP.", "CHAPT", "CHAPT.", "CHAPTER.", "CHAPER",
             "CHAPTR", "CHAPTEH", "CHAPTEK", "CHAPTKR", "CHAPTHR"}


def is_header_line(s: str):
    """Return (chapter_int, raw_token, trailing_text) if s is a LINE-HEAD chapter
    header, else None. Rejects lowercase 'chapter' body refs and run-on sentences."""
    m = HEAD_RE.match(s)
    if not m:
        return None
    glyph = m.group(1)
    # CASE GUARD: a real printed header sets "CHAPTER" in uppercase; a body / citation
    # cross-reference reads lowercase or Title-case "Chapter" ("...repeal Chapter 32,
    # Statutes of 1911..."). HEAD_RE's class is broad, so re-check the ORIGINAL glyph
    # casing -- the .upper() allowlist alone let Title-case "Chapter" (which uppercases
    # to the allowed "CHAPTER") slip through (MAJOR-B1).
    if not glyph[:1].isupper():
        return None
    gbare = glyph.rstrip(".")
    gu = gbare.upper()
    # uppercase-dominance of the PRINTED glyph (all letters upper, or all-but-one for a
    # single OCR-lowercased stroke). This is the real header signal.
    _letters = [c for c in gbare if c.isalpha()]
    _upper_dominant = bool(_letters) and \
        sum(1 for c in _letters if c.isupper()) >= len(_letters) - 1
    # accept ONLY when the printed glyph is uppercase-dominant OR is exactly the
    # uppercase canonical "CHAPTER"/"CHAP" -- a Title-case "Chapter" citation is rejected
    # even though it uppercases into the allowlist.
    _exact_caps = gbare in ("CHAPTER", "CHAP")
    if not (_upper_dominant or _exact_caps):
        return None
    if gu not in {g.rstrip(".") for g in _GLYPH_OK}:
        # OCR-garble path: be permissive but require short + CH-leading (dominance
        # already enforced above).
        if len(glyph) > 7 or not gu.startswith("CH"):
            return None
    num = int(m.group(2))
    trailing = (m.group(3) or "").strip()
    # RUN-ON GUARD: a real header line is just "CHAPTER N." possibly + a short margin
    # note ("Stats 1931,"). A long prose tail means a body line that merely begins with
    # an uppercase-misread token -> reject. Allow a short margin token only.
    if len(trailing) > 24:
        return None
    return num, m.group(2), trailing


def load_lines(label):
    ocr = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(ocr.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    lines = []
    for pidx in sorted(pages):
        for k, ln in enumerate(pages[pidx].get("consensus_text", "").split("\n")):
            lines.append((pidx, ln, k))
    return lines


def _quoted_before(seg, am):
    head = seg[:am.start()].rstrip(" \t")
    return bool(head) and head[-1] in _OPEN_QUOTES


def find_title(lines, start_i, end_i):
    """First "An Act" line in [start_i, start_i+AN_ACT_LOOKAHEAD) that is a genuine title
    (not a quoted citation, not a body-ref). Steps over blank/Note/margin lines. Returns
    (title_str, an_act_line_index) or (None, -1)."""
    lim = min(end_i, start_i + 1 + AN_ACT_LOOKAHEAD)
    for j in range(start_i, lim):
        seg = lines[j][1]
        am = AN_ACT_RE.search(seg)
        if not am:
            continue
        if _quoted_before(seg, am):
            continue                              # quoted title of a cited act
        if BODYREF_HEAD_CUE.search(seg):
            continue
        head = seg[:am.start()].strip(" \t.,:;\"'`-")
        # a short margin note ("Stats 1931,", a single capitalized word) before "An act"
        # is FINE; a long prose prefix means this "An act" is mid-sentence -> reject.
        if head and not re.match(r"^(?:Stats?\.?\s*\d{0,4}[.,]?|[A-Z][a-zA-Z]{0,9}\.?)$", head):
            if len(head) > 14:
                continue
        title = re.sub(r"\s+", " ", seg).strip()[:500]
        return title, j
    return None, -1


def has_approval(lines, start_i, end_i):
    lim = min(end_i, start_i + APPROVAL_LOOKAHEAD)
    for j in range(start_i, lim):
        if APPROVAL_RE.search(lines[j][1]):
            return True
    return False


def detect_headers(lines):
    """All LINE-HEAD chapter headers in reading order: [(i, chapter_int, raw), ...]."""
    out = []
    for i, (p, ln, k) in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        r = is_header_line(s)
        if r:
            num, raw, _trail = r
            out.append((i, num, raw))
    return out


def build_act(lines, start_i, end_i, chapter_int, chapter_raw, volume_year, label):
    buf = [lines[j][1] for j in range(start_i, end_i)]
    full = "\n".join(buf).strip()
    title, an_idx = find_title(lines, start_i, end_i)
    has_an_act = title is not None
    appr = has_approval(lines, start_i, end_i)
    redirect = bool(REDIRECT_NOTE_RE.search(full))
    has_enact = bool(ing.has_enact_marker(full))
    iso_date, approved_str = ing.parse_act_date(full, volume_year=volume_year)
    body_text = re.sub(r"[ \t]+", " ", full)
    return {
        "chapter": str(chapter_int), "chapter_int": chapter_int,
        "chapter_raw": chapter_raw, "title": title or "",
        "approved_date": approved_str, "iso_date": iso_date,
        "text": body_text[:6000], "source_page": lines[start_i][0] + 1,
        "has_an_act": bool(has_an_act),
        "has_enact": has_enact,
        "has_approval": bool(appr),
        "has_redirect_note": redirect,
        "origin": "chaptered_v2",
        "_volume": label,
    }


def _load_before(label):
    """Existing BEFORE set from parsed_acts_recovered.json (the best prior parse).
    Returns (confident_acts_list, dedup_chapter_int_set).

    The first element is the CONFIDENT floor only (used as the AFTER >= BEFORE
    confident base). The SECOND element -- the dedup floor -- includes the
    chapter_ints of BOTH confident_acts AND flagged_acts (CRITICAL-B1): a chapter
    already present as a FLAGGED before-act must not be re-emitted here as a brand-
    new confident act. If the file is absent (early-only volumes), returns
    ([], set())."""
    p = ROOT / ("production-" + label) / "parsed_acts_recovered.json"
    if not p.exists():
        return [], set()
    d = json.loads(p.read_text(encoding="utf-8"))
    acts = d.get("confident_acts", [])
    flagged = d.get("flagged_acts", [])

    def _ints(seq):
        return {a["chapter_int"] for a in seq
                if isinstance(a.get("chapter_int"), int) and a["chapter_int"] > 0}

    # dedup floor = confident numbers UNION flagged numbers
    nums = _ints(acts) | _ints(flagged)
    return acts, nums


def process_label(label):
    """ADDITIVE / NON-REGRESSING. Start from the BEFORE confident set
    (parsed_acts_recovered.json) as a FLOOR, then ADD line-head approval-witness acts
    (chiefly redirect-stubs) whose clean header numeral is NOT already in BEFORE. This
    guarantees AFTER >= BEFORE (no regression on header-garble volumes like 1931) while
    still recovering the enact-clause-less redirect-stubs (the 1933 win). 0 duplicate
    chapter numbers: an addition is rejected if its numeral is already present."""
    lines = load_lines(label)
    m = re.match(r"(\d{4})", label)
    volume_year = int(m.group(1)) if m else None
    headers = detect_headers(lines)

    before_acts, before_nums = _load_before(label)
    # plausibility ceiling for an ADDED numeral: the BEFORE parse already spans the real
    # chapter range, so an addition whose numeral sits far above the BEFORE max is an
    # OCR-garbled numeral (e.g. "3501" in a 1220-chapter volume). We KEEP the act (it is
    # real) but mark it chapter_number_suspect and route it to flagged so it can NEVER
    # inflate the distinct-confidence count or collide. Generous margin (precision = do
    # not silently drop a real act; just don't trust its garbled number).
    before_max = max(before_nums) if before_nums else CA_CEILING
    add_ceiling = int(before_max * 1.25) + 50

    emitted = []
    seen_numbers = set(before_nums)   # FLOOR: never collide with a BEFORE chapter number
    added_numbers = set()
    n_resolution = n_no_witness = n_no_anact = n_already = n_suspect = 0

    for k, (si, num, raw) in enumerate(headers):
        ei = headers[k + 1][0] if k + 1 < len(headers) else len(lines)
        rec = build_act(lines, si, ei, num, raw, volume_year, label)

        # --- keep-gate (precision) ---
        # (1) must have an "An Act" title (excludes resolutions + bare headers)
        if not rec["has_an_act"]:
            win = "\n".join(lines[j][1] for j in range(si, min(ei, si + 6)))
            if RESOLUTION_RE.search(win):
                n_resolution += 1
            else:
                n_no_anact += 1
            continue
        # (2) approval-footer witness OR redirect-note OR enact marker
        if not (rec["has_approval"] or rec["has_redirect_note"] or rec["has_enact"]):
            n_no_witness += 1
            continue
        # (3) plausible numeral
        if not (1 <= num <= CA_CEILING):
            n_no_witness += 1
            continue

        # --- de-dup by header numeral (vs BEFORE floor AND vs earlier additions) ---
        if num in seen_numbers:
            # already covered (by BEFORE or an earlier line-head header this pass)
            if num in before_nums:
                n_already += 1            # BEFORE already has this chapter -> skip silently
                continue
            rec["status"] = "dup_number"  # collides with another NEW line-head header
            emitted.append(rec)
            continue
        if num > add_ceiling:
            # real act, but the header numeral is an implausible OCR outlier -> quarantine
            rec["status"] = "chapter_number_suspect"
            rec["chapter_number_suspect"] = True
            n_suspect += 1
            emitted.append(rec)
            continue
        if rec["has_redirect_note"] and not rec["has_enact"]:
            rec["status"] = "codes_redirect"
        else:
            rec["status"] = "chaptered_new"   # a line-head act BEFORE missed
        seen_numbers.add(num)
        added_numbers.add(num)
        emitted.append(rec)

    # ADD records (new line-head acts) + the dup/suspect flags
    added = [a for a in emitted if a["status"] in ("chaptered_new", "codes_redirect")]
    flagged = [a for a in emitted if a["status"] in ("dup_number", "chapter_number_suspect")]

    # AFTER confident = BEFORE floor (tagged origin) + the new additions.
    floor = []
    for a in before_acts:
        b = dict(a)
        b.setdefault("status", "before_recovered")
        b["origin"] = a.get("origin", "recovered")
        floor.append(b)
    confident = floor + added

    meta = {
        "label": label,
        "detector": "recover_chaptered.py v2 (approval-footer witness, additive)",
        "line_head_headers": len(headers),
        "before_confident": len(before_acts),
        "before_distinct": len(before_nums),
        "added_new": len(added),
        "added_chaptered": sum(1 for a in added if a["status"] == "chaptered_new"),
        "codes_redirect": sum(1 for a in added if a["status"] == "codes_redirect"),
        "after_confident": len(confident),
        "flagged_dup": sum(1 for a in flagged if a["status"] == "dup_number"),
        "flagged_number_suspect": n_suspect,
        "add_ceiling": add_ceiling,
        "already_in_before": n_already,
        "excluded_resolutions": n_resolution,
        "excluded_no_anact": n_no_anact,
        "excluded_no_witness": n_no_witness,
        "after_distinct_chapter_numbers": len(seen_numbers),
    }
    return confident, flagged, meta


def write_label(label):
    confident, flagged, meta = process_label(label)
    out_path = ROOT / ("production-" + label) / "parsed_acts_chaptered_v2.json"
    out_path.write_text(json.dumps({
        "confident_acts": confident,
        "flagged_acts": flagged,
        "_chaptered_meta": meta,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta, out_path


def main():
    args = sys.argv[1:]
    if "--score" in args:
        args.remove("--score")      # scoring is done out-of-band by chapter_vs_oracle.py
    if not args:
        raise SystemExit("usage: python -m ingest.recover_chaptered [--score] <label> ...")
    for label in args:
        meta, out_path = write_label(label)
        print(f"{label}: before={meta['before_confident']} "
              f"+added={meta['added_new']} (new_chaptered={meta['added_chaptered']} "
              f"redirect={meta['codes_redirect']}) -> after={meta['after_confident']} "
              f"distinct#={meta['after_distinct_chapter_numbers']} "
              f"| dup_flag={meta['flagged_dup']} num_suspect={meta['flagged_number_suspect']} "
              f"excl: reso={meta['excluded_resolutions']} "
              f"no_anact={meta['excluded_no_anact']} no_wit={meta['excluded_no_witness']} "
              f"-> {out_path.name}")


if __name__ == "__main__":
    main()
