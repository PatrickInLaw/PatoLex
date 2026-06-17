"""recover_multiengine_headers.py -- ADDITIVE, PRECISION-FIRST recovery of MODERN-format
chapter headers (1910+) that the token-majority `consensus_text` parse MISSED because the
clean header survives only in a per-engine field (surya_text / doctr_text / tess_text).

CONTEXT (verified 2026-06-17, see docs run-log multiengine-headers-run.md):
  The production parse reads ONE text per page -- the majority-vote `consensus_text`. When
  two engines garble the numeral on a "CHAPTER N." header line, the consensus inherits the
  garble and the header is lost. But the OTHER engine read it cleanly. Measured on 1915:
  surya alone has 450 clean standalone "CHAPTER N." headers, the 3-engine union 498, yet the
  certified floor holds only 278 distinct chapter numbers. The headers ARE in the OCR; the
  single-text parse missed them. Same pattern in 1911 (production-1910-11) and 1941.

WHAT THIS DOES -- ADDITIVE ONLY, NEVER MUTATES AN EXISTING PARSE:
  * FLOOR = the best-of current parse's confident chapter numbers (certified > chaptered_v2 >
    early_v2 > recovered), read read-only. We ONLY recover numbers NOT already in the floor.
  * For each page, scan EACH engine field for STANDALONE line-head "CHAPTER <arabic>." headers
    (the modern format). Record (chapter_number, engine, page, line_index).
  * Accept a recovered number for a page ONLY when, for a candidate header occurrence:
      (in-range) 1 <= n <= oracle_N, AND
      a REAL-ACT BODY WITNESS is present in BOTH cases (an `An act` title + an approval/enact
        marker + a minimum body length -- NOT a one-line TOC entry), AND the numeral is trusted:
      (A) >= 2 INDEPENDENT engines (surya/doctr/tess -- NOT consensus, which is their token
          majority) read the SAME clean number at a line-head position on that page, OR
      (B) exactly one INDEPENDENT engine reads it cleanly AND the body witness corroborates.
    The body witness is MANDATORY for emission in EITHER case: numeral agreement alone never
    emits an act (a two-engine TOC line is not an act). consensus_text is read only for body /
    resolution screening -- it gets NO numeral-agreement vote.
    This mirrors recover_chaptered.py's keep-gate. Its guard helpers (quoted-title exclusion,
    body-ref head cue, resolution exclusion, the line-head header predicate, approval/an-act
    detectors) are IMPORTED and reused -- recover_chaptered.py is NOT modified.

PRECISION INVARIANTS (hard -- enforced + self-checked in meta):
  * never emit a number already held by a confident floor act;
  * never emit the same number twice (intra-pass dedup);
  * never emit out of [1, oracle_N];
  * if a page's engines disagree on the number with NO >=2 majority and no single-engine
    body witness -> SKIP (do not guess) -> routed to needs_review;
  * exclude resolutions, TOC/front-matter (require a real act body), quoted titles, body
    cross-references.

OUTPUT: a NEW file production-<label>/parsed_acts_multiengine.json (NOT overwritten -- if it
  exists, writes parsed_acts_multiengine.json.new). Contains recovered_acts[], needs_review[],
  and _multiengine_meta with floor_count / recovered_count / oracle_N /
  duplicate_numbers_introduced (MUST be 0).

SCOPE (TWO eras, ONE machinery -- 2026-06-17 addition):
  * MODERN (label year >= 1880): standalone "CHAPTER <arabic>." headers, ARABIC numeral. This
    is the original, Hans-validated path -- UNCHANGED.
  * EARLY (label year < 1880): inline italic-glyph "CHAP. <ROMAN>.- An Act ..." headers. The
    1850-1879 statutes print the header and the "An Act" title on the SAME line; Tesseract
    GARBLES the CHAP glyph (CHAP->CITAP/CIAP/CLAP/CNAP/CUAR/CUAP/CRAP/Cuse/Car/...) AND
    sometimes the roman (XI->XL, VIII->VIIL), but surya and doctr usually read the ROMAN
    cleanly. The token-majority consensus inherited Tesseract's garble, which is exactly why
    these acts were lost. The roman numeral, when >= 2 INDEPENDENT engines agree on its INT
    value (or 1 engine + a body witness), is the trustworthy signal.

  The era is auto-selected from the label's leading 4-digit year (handles the "NNchapters"
  suffix). A `--era roman|arabic` override is accepted. PRECISION IS IDENTICAL in both eras:
  the SAME gates run -- >=2 independent engines OR 1 engine + body witness, a MANDATORY
  real-act body witness for EVERY emission, range gate, resolution exclusion, intra-pass
  dedup, the duplicate self-check (MUST be 0). The ONLY differences in the roman path are:
  (a) the header regex matches a glyph-tolerant CHAP token + a CLEAN roman that is converted
      to int by a STRICT canonical roman_to_int (a malformed/garbled roman like "VIIL" or
      "XLIL" is rejected -> not a candidate -- we do NOT de-garble numerals here), and
  (b) the body-witness title may sit on the header line itself (header+title share a line),
      so the head-prefix length guard is relaxed when that line is itself a roman header.

  Early-session oracle_N is known to be UNRELIABLE (sometimes inflated, sometimes -- e.g.
  1865-66 -- SMALLER than the floor max). The range ceiling is therefore generalized to
  max(oracle_N, max(floor)): for modern volumes oracle_N >= floor_max so this is a NO-OP
  (the arabic path is byte-for-byte unchanged), while for early volumes it only ever LOOSENS
  the gate (never tightens), as instructed -- precision is still carried by the cross-engine
  + body-witness gates, never by the range ceiling alone.

USAGE:  python -m ingest.recover_multiengine_headers 1915-vol1-chapters 1910-11 1941-vol1-41chapters
        python -m ingest.recover_multiengine_headers 1860 1861 1862 1863-64 1865-66
        python -m ingest.recover_multiengine_headers --era roman 1873-74
"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # pipeline/ on path
import config

ROOT = Path(config.path_for("data_root"))

# ---- reuse recover_chaptered.py guards (which itself reuses ingest_from_ocr) -- READ ONLY ----
_RC = Path(__file__).resolve().parent / "recover_chaptered.py"
_spec = importlib.util.spec_from_file_location("recover_chaptered_ro", str(_RC))
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

AN_ACT_RE = rc.AN_ACT_RE
APPROVAL_RE = rc.APPROVAL_RE
RESOLUTION_RE = rc.RESOLUTION_RE
BODYREF_HEAD_CUE = rc.BODYREF_HEAD_CUE
_quoted_before = rc._quoted_before

# consensus_text is the token-majority of the three independent engines -- it is NOT an
# independent witness. It must NEVER count toward the ">=2 engines agree" vote (CRITICAL-1):
# counting it manufactures a false "2-engine agreement" out of a single real read. The THREE
# INDEPENDENT engines below are the ONLY votes for numeral agreement. consensus_text is still
# scanned (ENGINES) for body-witness / resolution screening, never for the agreement vote.
INDEPENDENT_ENGINES = ("surya_text", "doctr_text", "tess_text")
ENGINES = INDEPENDENT_ENGINES + ("consensus_text",)

# MODERN standalone header: the line is essentially JUST "CHAPTER <arabic>." with at most a
# little leading noise and a trailing punctuation. A clean unambiguous arabic numeral is
# REQUIRED (no embedded garble glyph -- precision). A run-on tail (a sentence after the
# number) disqualifies it: that is a body line, not a standalone header.
MODERN_HEAD_RE = re.compile(
    r"^[^A-Za-z0-9]{0,3}"
    r"CHAPTER"
    r"[.\s]+"
    r"([0-9]{1,4})"           # clean arabic numeral, NO trailing garble glyph allowed
    r"\s*[.,]?\s*$")          # end of line (optional terminal . or ,)

# ---------------------------------------------------------------------------
# EARLY-ERA (1850-1879) ROMAN header path -- ADDITIVE. Reuses every gate below.
# ---------------------------------------------------------------------------
# Glyph-tolerant inline roman header. The PRINTED form is "CHAP. <ROMAN>.- An Act ...".
# Tesseract garbles the GLYPH heavily (CITAP/CIAP/CLAP/CNAP/CUAR/CUAP/CRAP/Cuse/Car/Clar/
# Cusp/...) so we are GENEROUS on the glyph: a C-leading token of up to 7 chars. We are
# STRICT on the numeral: it must be a CLEAN uppercase roman string (only I V X L C D M),
# which roman_to_int() then validates against canonical roman form. A garbled roman
# ("VIIL", "XLIL", "LXIL", "XIVII") fails roman_to_int -> NOT a candidate (we never try to
# de-garble a numeral; that is recover_lost_header's / re-OCR's job). The header and the
# "An Act" title share a line in this era, so the regex stops at the roman + terminator and
# leaves the title to the body-witness gate.
ROMAN_HEAD_RE = re.compile(
    r"^[^A-Za-z0-9]{0,4}"
    r"(C[A-Za-z]{1,6})"               # CHAP-like glyph (generous on garble; C-leading, short)
    r"\.?\s*[.\s]\s*"                 # separator (a period and/or whitespace)
    r"([IVXLCDM]{1,9})"               # CLEAN uppercase roman string (no garble glyphs)
    r"\s*[.,\-—–]")                   # terminator before the inline title

# CRITICAL-1(b): legal-prose C-words blocklist (defense-in-depth). ROMAN_HEAD_RE's glyph token
# C[A-Za-z]{1,6} happily matches Title-Case legal words (Civil/Code/Court/County/...), so a
# wrapped body line "Civil IX. An Act to amend ..." would be misread as chapter 9 with
# glyph="Civil". A real CHAP garble is short, vowel-poor, and NOT a dictionary word
# (CHAP/CITAP/CIAP/CLAP/CNAP/CUAR/CUAP/CRAP/Cuse/Car/Clar/Cuav/Cusp/...). We therefore REJECT
# any glyph token whose lowercased form IS, or STARTS WITH, a known legal prose C-word.
_LEGAL_CWORD_BLOCKLIST = (
    "civil", "code", "court", "courts", "clerk", "county", "counties",
    "case", "cases", "claim", "claims", "charter", "company", "commission",
    "commissioner", "commissioners", "convention", "certificate", "cert",
    "compromise", "comp", "common", "comm", "convict", "conv", "california",
    "chancery", "corporation", "creditor", "creditors", "contract",
)


def _is_legal_cword(glyph):
    """True when the CHAP-glyph candidate is actually a legal prose C-word (Civil/Code/...).
    Match is case-insensitive and prefix-based: the glyph IS a blocklisted word, or a
    blocklisted word is a PREFIX of the glyph (so 'County'/'Counties' is caught even though
    ROMAN_HEAD_RE may have captured extra trailing chars). A genuine CHAP garble
    (CHAP/CITAP/CLAP/CUAR/Cuse/Car/Clar/Cuav/Cusp/...) is short and vowel-poor and matches
    none of these."""
    g = (glyph or "").lower()
    for w in _LEGAL_CWORD_BLOCKLIST:
        if g == w or g.startswith(w):
            return True
    return False


# strict canonical roman validator -- rejects any non-canonical / malformed roman.
_ROMAN_CANON_RE = re.compile(r"^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_ROMAN_VAL = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s):
    """Strict roman -> int. Returns the int ONLY for a well-formed canonical roman numeral
    (e.g. CXLI -> 141). Returns None for empty / non-roman / MALFORMED romans (VIIL, XLIL,
    IIXII, LXXL, ...). We deliberately do NOT attempt to repair a garbled numeral here --
    precision: a numeral we cannot trust as clean is not a candidate."""
    if not s:
        return None
    s = s.upper()
    if not _ROMAN_CANON_RE.match(s):
        return None
    total = 0
    prev = 0
    for ch in reversed(s):
        v = _ROMAN_VAL[ch]
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    return total if total > 0 else None


def era_for_label(label):
    """ROMAN (early 1850-1879) vs ARABIC (modern 1880+) detection mode from the label.
    Auto-detect from the leading 4-digit year (handles 'NNchapters' suffix + 'volN'). A
    label with no leading year defaults to ARABIC (the original behaviour)."""
    m = re.match(r"(\d{4})", label)
    if not m:
        return "arabic"
    year = int(m.group(1))
    return "roman" if year < 1880 else "arabic"


AN_ACT_LOOKAHEAD = 8          # lines after header to find the "An Act" title (engine-local)
APPROVAL_LOOKAHEAD = 60       # lines after header to find the approval/enact footer
MIN_BODY_CHARS = 200          # a real act body is long; a TOC line is short -> excludes TOC


def floor_numbers(label):
    """Best-of current parse's CONFIDENT chapter numbers + (acts, source_file, oracle_N).
    Priority: certified > chaptered_v2 > early_v2 > recovered. Read-only."""
    d = ROOT / ("production-" + label)
    order = ("parsed_acts_certified.json", "parsed_acts_chaptered_v2.json",
             "parsed_acts_early_v2.json", "parsed_acts_recovered.json")
    src = None
    j = None
    for fn in order:
        p = d / fn
        if p.exists():
            src = fn
            j = json.loads(p.read_text(encoding="utf-8"))
            break
    if j is None:
        return set(), [], None, None
    acts = j.get("confident_acts", [])
    # MAJOR-1: the dedup FLOOR must include flagged_acts numbers too -- recover_chaptered's
    # _load_before (its "CRITICAL-B1" fix) unions confident AND flagged chapter_ints, because
    # flagged_acts (dup_number / chapter_number_suspect) DO carry a real chapter_int that this
    # pass must never re-emit. We mirror that exactly: scan confident_acts AND flagged_acts,
    # taking chapter_int_final if present else chapter_int.
    flagged = j.get("flagged_acts", [])

    def _add_nums(seq, dest):
        for a in seq:
            n = a.get("chapter_int_final")
            if not isinstance(n, int):
                n = a.get("chapter_int")
            if isinstance(n, int) and n > 0:
                dest.add(n)

    nums = set()
    _add_nums(acts, nums)        # confident floor numbers
    _add_nums(flagged, nums)     # + flagged (dup/suspect) numbers -- never re-emit these
    oracle_N = None
    for mk in ("_certify_meta", "_chaptered_meta", "_recovery_meta", "_meta"):
        if isinstance(j.get(mk), dict) and isinstance(j[mk].get("oracle_N"), int):
            oracle_N = j[mk]["oracle_N"]
            break
    return nums, acts, src, oracle_N


def page_engine_lines(pg, engine):
    return (pg.get(engine) or "").split("\n")


def scan_page_headers(pg, mode="arabic"):
    """Return {chapter_number: {engine: line_index}} for clean headers on a page, across all
    engines. A number may be read by several engines (cross-engine agreement).

    mode="arabic": MODERN standalone "CHAPTER <arabic>." headers (UNCHANGED original path).
    mode="roman" : EARLY inline "CHAP. <ROMAN>.- An Act ..." headers -- the glyph is garble-
                   tolerant, the roman must be CLEAN (roman_to_int validates canonical form);
                   a roman that fails validation is NOT recorded (we never de-garble a
                   numeral). The int VALUE is the dict key, so cross-engine agreement is on
                   the converted integer (surya 'XI'->11 and doctr 'XI'->11 agree, while a
                   tess garble 'XL'->40 lands as a different key and loses the >=2 vote)."""
    hits = {}
    for e in ENGINES:
        lines = page_engine_lines(pg, e)
        for i, ln in enumerate(lines):
            s = ln.strip()
            if mode == "roman":
                m = ROMAN_HEAD_RE.match(s)
                if not m:
                    continue
                # CRITICAL-1(b): the glyph token C[A-Za-z]{1,6} matches Title-Case legal C-words
                # (Civil/Code/Court/County/...). A wrapped body line "Civil IX. An Act ..." is NOT
                # a header -- reject any candidate whose glyph is a known legal prose word.
                if _is_legal_cword(m.group(1)):
                    continue
                n = roman_to_int(m.group(2))
                if n is None:        # malformed/garbled roman -> not a candidate
                    continue
            else:
                m = MODERN_HEAD_RE.match(s)
                if not m:
                    continue
                n = int(m.group(1))
            hits.setdefault(n, {})
            # keep the FIRST line-index this engine read the number at
            hits[n].setdefault(e, i)
    return hits


def body_witness(pg, engine, header_line_idx, chapter_num, mode="arabic"):
    """Single-engine body witness (gate B). In `engine`'s own text, starting at the header
    line, find within lookahead a genuine `An act` title (not quoted / not body-ref) AND an
    approval/enact footer, with a real (long) body. Returns (ok, title, witness_str).

    In the EARLY (mode="roman") era the printed header and the "An Act" title share ONE line
    ("CHAP. XV .- An Act to extend ..."), so the head-prefix that precedes "An act" is the
    CHAP-glyph + roman + dash. The modern head-length guard (which assumes the title is on
    its OWN line with only a short margin note before it) would wrongly reject those. So when
    the candidate title line is ITSELF a roman header, the CHAP-roman prefix is allowed."""
    lines = page_engine_lines(pg, engine)
    n = len(lines)
    # title search
    title = None
    title_idx = -1
    # CRITICAL-1(a): in the ROMAN era the documented 1850s format is COLOCATED -- the header and
    # the "An Act" title share one line ("CHAP. XV.- An Act to ..."). A real header therefore
    # carries "An Act" on the header line itself (allow +1 line only for an OCR line-split). A
    # genuine body sentence at a line-head ("Civil IX.") does NOT carry "An Act" on that same
    # line, so clamping the roman lookahead to 0-1 closes the false-positive path. The ARABIC
    # path keeps its original 8-line lookahead UNCHANGED (mode-gated).
    an_act_lookahead = 1 if mode == "roman" else AN_ACT_LOOKAHEAD
    lim = min(n, header_line_idx + 1 + an_act_lookahead)
    for j in range(header_line_idx, lim):
        seg = lines[j]
        # CRITICAL-1(a) precision guard: in roman mode the +1 line is allowed ONLY as an
        # OCR line-split of the SAME header. If that following line is itself a CHAP-roman
        # header for a DIFFERENT chapter number, it is the NEXT chapter -- do NOT borrow its
        # "An Act" title/witness (that misattributes the next act's body to this number, e.g.
        # a "CHAP. XIII.-[See volume of Amendments to the Codes.]" stub grabbing ch XIV's act).
        if mode == "roman" and j > header_line_idx:
            nm = ROMAN_HEAD_RE.match(seg.strip())
            if nm and not _is_legal_cword(nm.group(1)):
                nn = roman_to_int(nm.group(2))
                # Break if line+1 looks like a CHAP header at all: a clean DIFFERENT
                # number, OR a GARBLED roman (nn is None) -- a garbled adjacent header
                # must not let a see-reference stub borrow the next act's body
                # (Hans re-audit: garbled-adjacent-roman gap). Only a genuine OCR
                # line-split of THIS header (nn == chapter_num) is allowed to continue.
                if nn is None or nn != chapter_num:
                    break
        am = AN_ACT_RE.search(seg)
        if not am:
            continue
        if _quoted_before(seg, am):
            continue
        if BODYREF_HEAD_CUE.search(seg):
            continue
        head = seg[:am.start()].strip(" \t.,:;\"'`-")
        # ROMAN era: a "CHAP. <roman>.- " prefix on the title line is expected & legitimate.
        head_is_roman_header = mode == "roman" and bool(ROMAN_HEAD_RE.match(seg.strip()))
        if (head and len(head) > 14 and not head_is_roman_header and not re.match(
                r"^(?:Stats?\.?\s*\d{0,4}[.,]?|[A-Z][a-zA-Z]{0,9}\.?)$", head)):
            continue
        title = re.sub(r"\s+", " ", seg).strip()[:500]
        title_idx = j
        break
    if title is None:
        return False, None, None
    # approval / enact witness
    witness = None
    alim = min(n, header_line_idx + APPROVAL_LOOKAHEAD)
    body_chunk = "\n".join(lines[header_line_idx:alim])
    am2 = APPROVAL_RE.search(body_chunk)
    if am2:
        witness = body_chunk[max(0, am2.start() - 5): am2.start() + 40].strip()
    elif rc.ing.has_enact_marker(body_chunk):
        witness = "do enact"
    if witness is None:
        return False, None, None
    # min body length (exclude one-line TOC entries)
    body_len = len(re.sub(r"\s+", " ", "\n".join(lines[header_line_idx:alim])).strip())
    if body_len < MIN_BODY_CHARS:
        return False, None, None
    return True, title, witness


def is_resolution_near(pg, header_line_idx):
    """Resolution exclusion: scan a small window across ALL THREE independent engines
    (surya_text, doctr_text, tess_text) for a resolution cue (MAJOR-3). Previously only
    consensus_text + surya_text were scanned, so a resolution that one of the other
    independent engines read (and consensus garbled) slipped through."""
    for e in INDEPENDENT_ENGINES:
        lines = page_engine_lines(pg, e)
        win = "\n".join(lines[header_line_idx: header_line_idx + 8])
        if RESOLUTION_RE.search(win):
            return True
    return False


def best_excerpt(pg, engine, header_line_idx):
    lines = page_engine_lines(pg, engine)
    chunk = "\n".join(lines[header_line_idx: header_line_idx + 6])
    return re.sub(r"[ \t]+", " ", chunk).strip()[:400]


def _skipped_meta(label, reason):
    """DEFECT-B: a SKIPPED meta for a volume that could not be processed -- batch continues."""
    return {
        "label": label,
        "detector": "recover_multiengine_headers.py v1 (modern CHAPTER N. cross-engine, additive)",
        "SKIPPED": True,
        "skip_reason": reason,
        "floor_source": None,
        "floor_count": 0,
        "oracle_N": None,
        "oracle_N_source": "none",
        "recovered_count": 0,
        "range_gated_count": 0,
        "needs_review_count": 0,
        "duplicate_numbers_introduced": 0,
    }


def process_label(label, mode=None):
    # DEFECT-B: isolate the ENTIRE per-volume body in try/except. A missing/corrupt
    # page_ocr_results.json (FileNotFoundError, JSONDecodeError, etc.) on ONE volume must
    # NEVER abort the whole batch -- record a SKIPPED meta and let the caller continue.
    try:
        return _process_label_inner(label, mode=mode)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: one bad vol can't kill the run
        reason = "%s: %s" % (type(exc).__name__, str(exc)[:300])
        return [], [], _skipped_meta(label, reason)


def _process_label_inner(label, mode=None):
    d = ROOT / ("production-" + label)
    raw = json.loads((d / "ocr_consensus" / "page_ocr_results.json").read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}

    # ERA / mode: "roman" (early 1850-1879 inline CHAP. <roman>) vs "arabic" (modern path,
    # UNCHANGED). Auto from label year unless an explicit override is passed.
    if mode is None:
        mode = era_for_label(label)

    floor, floor_acts, floor_src, oracle_N = floor_numbers(label)
    # MAJOR-2: NEVER fall back to a blind 9999 -- that silently disables the range gate and
    # lets garbled page/section/year numerals (up to 9999) pass as chapter numbers.
    #   * oracle_N resolved          -> use it (oracle).
    #   * oracle_N None, floor non-empty -> use max(floor), recorded as floor_max_fallback so
    #                                       it is auditable (still a real range gate).
    #   * oracle_N None, floor empty -> REFUSE: skip the volume entirely with a loud meta note.
    oracle_N_source = "oracle"
    if oracle_N is None:
        if floor:
            oracle_N = max(floor)
            oracle_N_source = "floor_max_fallback"
        else:
            # No way to range-gate at all. Recover NOTHING from this volume; emit a loud meta.
            meta = {
                "label": label,
                "detector": "recover_multiengine_headers.py v1 (modern CHAPTER N. cross-engine, additive)",
                "SKIPPED": True,
                "skip_reason": ("oracle_N unresolved AND floor empty -- cannot range-gate; "
                                "refusing to recover (would let garble up to 9999 pass)."),
                "floor_source": floor_src,
                "floor_count": 0,
                "oracle_N": None,
                "oracle_N_source": "none",
                "recovered_count": 0,
                "needs_review_count": 0,
                "duplicate_numbers_introduced": 0,
            }
            return [], [], meta

    # RANGE CEILING (CRITICAL-2, 2026-06-17 -- PRECISION fix, reverses the prior over-loosening).
    # When oracle_N is the REAL oracle, the ceiling MUST be oracle_N -- do NOT raise it to
    # max(floor). The early-era defect is OVER-extraction (e.g. 1865-66: oracle_N=280 is CORRECT,
    # but the contaminated floor reached 463), so raising the ceiling to the floor max would
    # PROPAGATE the phantom over-count. Any recovered number > oracle_N is therefore rejected and
    # routed to needs_review with reason "above_oracle_N". Only when oracle_N is unavailable
    # (oracle_N_source == "floor_max_fallback", set above) does the ceiling fall back to
    # max(floor) -- and that path keeps its existing auditable out-of-range flagging.
    # For MODERN volumes oracle_N >= floor_max, so the arabic path's behaviour is byte-for-byte
    # unchanged. Precision is carried by the cross-engine + body-witness gates AND this ceiling.
    range_ceiling = oracle_N
    range_ceiling_source = oracle_N_source

    recovered = []
    needs_review = []
    emitted_numbers = set()        # numbers we have RECOVERED this pass (intra-pass dedup)
    range_gated_count = 0          # DEFECT-A: how many candidates the range gate dropped
    above_oracle_count = 0         # MAJOR-3: candidates rejected for n > oracle_N (over-extraction)

    for pidx in sorted(pages):
        pg = pages[pidx]
        page_1 = pg.get("page_1indexed", pidx + 1)
        hits = scan_page_headers(pg, mode=mode)
        for n in sorted(hits):
            # range gate (kills garbled page-number / citation numerals like 5828, AND -- per
            # CRITICAL-2 -- phantom over-extraction above a trusted oracle_N).
            if not (1 <= n <= range_ceiling):
                # DEFECT-A: always count the drop. Make EVERY out-of-range drop AUDITABLE by
                # routing the candidate to needs_review (it is NEVER emitted -- precision intact).
                # MAJOR-3 / CRITICAL-2: when the ceiling is the real oracle and n exceeds it, the
                # reason is "above_oracle_N" and it increments above_oracle_count; otherwise it is
                # the existing floor_max_fallback out-of-range path.
                range_gated_count += 1
                eng_read = hits[n]
                if range_ceiling_source == "oracle" and n > range_ceiling:
                    above_oracle_count += 1
                    reason = "above_oracle_N"
                else:
                    reason = "out_of_range_" + range_ceiling_source
                needs_review.append({
                    "chapter_int": n,
                    "source_page": page_1,
                    "engines_read": sorted(eng_read),
                    "reason": reason,
                    "range_ceiling": range_ceiling,
                    "range_ceiling_source": range_ceiling_source,
                    "oracle_N": oracle_N,
                    "excerpt": best_excerpt(pg, sorted(eng_read)[0], min(eng_read.values())),
                })
                continue
            # FLOOR exclusion: only recover numbers NOT already confident
            if n in floor:
                continue
            engines_read = hits[n]                 # {engine: line_idx} (ALL engines, incl. consensus)
            # CRITICAL-1: the engine-AGREEMENT vote must use ONLY the three INDEPENDENT engines.
            # consensus_text is the token-majority of those three -- counting it would fabricate
            # a false "2-engine agreement" from a single independent read. consensus may still
            # corroborate the body witness below, but it gets NO vote here.
            indep_read = {e: engines_read[e] for e in INDEPENDENT_ENGINES if e in engines_read}
            if not indep_read:
                # only consensus_text read this number at a line-head -> not an independent
                # signal at all -> never emit (consensus inherits whatever the engines read).
                continue
            # resolution exclusion (use the earliest header line idx among independent engines)
            min_idx = min(indep_read.values())
            if is_resolution_near(pg, min_idx):
                continue

            multi = len(indep_read) >= 2            # gate A numeral test: >=2 INDEPENDENT engines agree

            # CRITICAL-2: a real-act body witness is REQUIRED for EVERY emitted act -- numeral
            # agreement alone is NOT enough (a TOC line "CHAPTER 5. An act to..." read by two
            # engines must NOT become an act). body_witness() requires an `An act` title (not
            # quoted, not a body cross-ref) AND an approval/enact marker AND >= MIN_BODY_CHARS
            # of following body -- a TOC one-liner fails the length guard. We look for the body
            # witness in the independent engines first, then allow consensus_text to corroborate.
            witness = None
            title = None
            wit_engine = None
            for e in INDEPENDENT_ENGINES + ("consensus_text",):
                if e not in engines_read:
                    continue
                ok, t, w = body_witness(pg, e, engines_read[e], n, mode=mode)
                if ok:
                    witness, title, wit_engine = w, t, e
                    break

            body_ok = witness is not None
            # NUMERAL is trusted when (>=2 independent engines agree) OR (exactly one
            # independent engine reads it cleanly AND the body witness corroborates). In the
            # single-engine case the body witness IS the corroboration, so require body_ok.
            numeral_trusted = multi or (len(indep_read) == 1 and body_ok)
            # ...AND in BOTH cases a real-act body is REQUIRED before emitting.
            accept = numeral_trusted and body_ok
            if not accept:
                # detected but not safely numbered/witnessed -> needs_review, NEVER emitted
                if not body_ok:
                    reason = ("no real-act body witness (no An-act title / no approval-enact "
                              "marker / body shorter than %d chars -- likely TOC or stub)"
                              % MIN_BODY_CHARS)
                else:
                    reason = "single independent engine read with no corroborating body witness"
                needs_review.append({
                    "chapter_int": n,
                    "source_page": page_1,
                    "engines_read": sorted(engines_read),
                    "independent_engines_read": sorted(indep_read),
                    "multi_engine_agreement": multi,
                    "body_witness_found": body_ok,
                    "reason": reason,
                    "excerpt": best_excerpt(pg, sorted(indep_read)[0], min_idx),
                })
                continue

            # intra-pass dedup: the SAME number must never be emitted twice. If a later page
            # also yields this number, the first wins; the second is routed to needs_review.
            if n in emitted_numbers:
                needs_review.append({
                    "chapter_int": n,
                    "source_page": page_1,
                    "engines_read": sorted(engines_read),
                    "independent_engines_read": sorted(indep_read),
                    "reason": "duplicate of an already-recovered number (kept first occurrence)",
                    "excerpt": best_excerpt(pg, sorted(indep_read)[0], min_idx),
                })
                continue

            # choose a display engine + title/excerpt: prefer the witness engine, else an
            # independent engine that read the header.
            disp_engine = wit_engine or next(
                (e for e in INDEPENDENT_ENGINES if e in indep_read),
                sorted(indep_read)[0])
            disp_idx = engines_read[disp_engine]
            if title is None:
                _ok, title, _w = body_witness(pg, disp_engine, disp_idx, n, mode=mode)
            # MINOR-1: provenance must truthfully record HOW the act was accepted -- which
            # INDEPENDENT engines agreed on the numeral, whether consensus also read it, and
            # which engine supplied the corroborating body witness.
            rec = {
                "chapter": str(n),
                "chapter_int": n,
                "source_page": page_1,
                "engines_read": sorted(engines_read),
                "independent_engines_agreed": sorted(indep_read),
                "n_independent_agreed": len(indep_read),
                "consensus_also_read": "consensus_text" in engines_read,
                "agreement": "multi_engine" if multi else "single_engine_body_witness",
                "body_witness_engine": wit_engine,
                "body_witness_found": True,
                "witness": witness,
                "title": title or "",
                "text_excerpt": best_excerpt(pg, disp_engine, disp_idx),
                "era_mode": mode,
                "origin": "multiengine_roman_v1" if mode == "roman" else "multiengine_v1",
            }
            recovered.append(rec)
            emitted_numbers.add(n)

    # ---- self-checked precision invariants ----
    rec_nums = [r["chapter_int"] for r in recovered]
    dup_in_pass = len(rec_nums) - len(set(rec_nums))
    dup_vs_floor = len(set(rec_nums) & floor)
    out_of_range = sum(1 for x in rec_nums if not (1 <= x <= range_ceiling))
    duplicate_numbers_introduced = dup_in_pass + dup_vs_floor + out_of_range

    after = len(floor) + len(set(rec_nums))
    meta = {
        "label": label,
        "detector": ("recover_multiengine_headers.py v2 (cross-engine, additive; "
                     "arabic MODERN + roman EARLY paths)"),
        "era_mode": mode,                       # "roman" (1850-1879) | "arabic" (1880+)
        "scope": ("EARLY inline 'CHAP. <roman>.- An Act' (roman path)" if mode == "roman"
                  else "MODERN standalone 'CHAPTER <arabic>.' (arabic path, unchanged)"),
        "floor_source": floor_src,
        "floor_count": len(floor),
        "oracle_N": oracle_N,
        "oracle_N_source": oracle_N_source,    # "oracle" | "floor_max_fallback" (MAJOR-2)
        "range_ceiling": range_ceiling,        # = oracle_N when oracle resolved; max(floor) only via floor_max_fallback
        "range_ceiling_source": range_ceiling_source,
        "recovered_count": len(recovered),
        "recovered_multi_engine": sum(1 for r in recovered if r["agreement"] == "multi_engine"),
        "recovered_single_witness": sum(1 for r in recovered if r["agreement"] == "single_engine_body_witness"),
        "range_gated_count": range_gated_count,   # DEFECT-A: candidates dropped by the range gate
        "above_oracle_count": above_oracle_count,  # MAJOR-3: dropped for n > trusted oracle_N (over-extraction)
        "needs_review_count": len(needs_review),
        "after_distinct_floor_plus_recovered": after,
        "implied_completeness_before": round(len(floor) / oracle_N, 4) if oracle_N else None,
        "implied_completeness_after": round(after / oracle_N, 4) if oracle_N else None,
        "missing_before": (oracle_N - len(floor)) if oracle_N else None,
        "fraction_of_missing_recovered": (
            round(len(set(rec_nums)) / (oracle_N - len(floor)), 4)
            if oracle_N and (oracle_N - len(floor)) > 0 else None),
        "duplicate_numbers_introduced": duplicate_numbers_introduced,   # MUST be 0
        "_invariant_breakdown": {
            "dup_within_pass": dup_in_pass,
            "dup_vs_floor": dup_vs_floor,
            "out_of_range": out_of_range,
            "above_oracle_count": above_oracle_count,   # MAJOR-3: n > oracle_N rejects (over-extraction drop)
        },
    }
    return recovered, needs_review, meta


def write_label(label, mode=None):
    recovered, needs_review, meta = process_label(label, mode=mode)
    d = ROOT / ("production-" + label)
    out = d / "parsed_acts_multiengine.json"
    suffix = ""
    if out.exists():
        out = d / "parsed_acts_multiengine.json.new"
        suffix = " (existing file present -> wrote .new)"
    out.write_text(json.dumps({
        "recovered_acts": recovered,
        "needs_review": needs_review,
        "_multiengine_meta": meta,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta, out, suffix


def main():
    args = sys.argv[1:]
    # optional --era roman|arabic override (else auto per-label from year). Applies to ALL
    # labels in the call; omit it to let each label auto-select its era.
    mode = None
    if "--era" in args:
        i = args.index("--era")
        try:
            mode = args[i + 1]
        except IndexError:
            raise SystemExit("--era requires a value: roman | arabic")
        if mode not in ("roman", "arabic"):
            raise SystemExit("--era must be 'roman' or 'arabic'")
        del args[i:i + 2]
    if not args:
        raise SystemExit("usage: python -m ingest.recover_multiengine_headers "
                         "[--era roman|arabic] <label> ...")
    for label in args:
        # DEFECT-B backstop: isolate each label at the driver level too -- even a failure in
        # write_label (e.g. an unwritable output dir) must not abort the rest of the batch.
        try:
            meta, out, suffix = write_label(label, mode=mode)
        except Exception as exc:  # noqa: BLE001
            print(f"{label}: SKIPPED (write_label error) -- "
                  f"{type(exc).__name__}: {str(exc)[:200]}")
            continue
        if meta.get("SKIPPED"):
            print(f"{label}: SKIPPED -- {meta.get('skip_reason')} -> {out.name}{suffix}")
            continue
        print(f"{label} [{meta.get('era_mode')}]: floor={meta['floor_count']} "
              f"(src={meta['floor_source']}) +recovered={meta['recovered_count']} "
              f"(multi={meta['recovered_multi_engine']} "
              f"single_witness={meta['recovered_single_witness']}) "
              f"-> after={meta['after_distinct_floor_plus_recovered']} / N={meta['oracle_N']} "
              f"(ceiling={meta.get('range_ceiling')}/{meta.get('range_ceiling_source')}) "
              f"| completeness {meta['implied_completeness_before']}->{meta['implied_completeness_after']} "
              f"| dup_introduced={meta['duplicate_numbers_introduced']} "
              f"| range_gated={meta.get('range_gated_count')} "
              f"| needs_review={meta['needs_review_count']} "
              f"-> {out.name}{suffix}")


if __name__ == "__main__":
    main()
