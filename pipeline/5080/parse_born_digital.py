"""
parse_born_digital.py -- Modern (born-digital, ~1997-2008+) CA Statutes parser.
=============================================================================
The chaptered statutes in the born-digital Statutes-of-<year> volumes have a
clean text layer (PyMuPDF `get_text()`), so no OCR is needed. This parser
extracts each `CHAPTER N` block into the SAME parsed-act record shape that
ingest_from_ocr.py's flush_act() produces, so the canonical ingest
(ingest_clean.py) can consume it unchanged.

Format spec: docs/80_PROJECT_HISTORY/MODERN_STATUTE_FORMAT_2026-06-02.md

Reuses the date/marker logic from ingest_from_ocr.py (APPROVED_MODERN_RE etc.)
so the 1900+ date-cliff fix lives in exactly one place.

PROTOTYPE STATUS (2026-06-02): validated on 2008_Vol1.pdf -> 227 chapters,
all confident, continuous 1..227, every block has a parsed iso_date. This
does NOT yet do the multi-volume year roll-up; see TODO below.

Usage (offline characterization only -- does NOT write to the DB):
    python parse_born_digital.py <path-to-volume.pdf>
"""

import sys
import re
import json
import importlib.util
from pathlib import Path

import fitz  # PyMuPDF

# Import the shared parser helpers (date regexes, markers, chapter-num parse).
# The source module has no __main__ guard and its MAIN block performs DB
# ingest, so we force the argv<2 usage-exit branch and swallow the SystemExit;
# all function/regex definitions precede that branch and are bound normally.
_MOD = Path(__file__).with_name("ingest_from_ocr.py")
_spec = importlib.util.spec_from_file_location("ingest_from_ocr_helpers", _MOD)
_helpers = importlib.util.module_from_spec(_spec)
_saved_argv = sys.argv
sys.argv = ["ingest_from_ocr.py"]
try:
    _spec.loader.exec_module(_helpers)
except SystemExit:
    pass
finally:
    sys.argv = _saved_argv

AN_ACT_RE = _helpers.AN_ACT_RE
ENACT_MARKER_RE = _helpers.ENACT_MARKER_RE
parse_act_date = _helpers.parse_act_date

CHAP_HDR_RE = re.compile(r"^\s*CHAPTER\s+(\d+)\s*$")


def parse_born_digital_volume(pdf_path):
    """Extract chaptered statutes from one born-digital Statutes volume.

    TOMBSTONED (SERIOUS-2 fix, cc006): this prototype calls parse_act_date()
    from ingest_from_ocr.py WITHOUT a volume_year argument, bypassing the
    Cluster-B date-poisoning fix.

    Use parse_born_digital_prod.py (via batch_ingest_born_digital.py) for
    all production born-digital parsing.  That script is self-contained and
    always passes volume_year to parse_act_date().
    """
    raise NotImplementedError(
        "parse_born_digital.py is a retired prototype; use parse_born_digital_prod.py"
    )

    # --- original code below (unreachable; preserved for reference) ---
    doc = fitz.open(pdf_path)
    lines = []
    for pi in range(doc.page_count):
        for ln in doc[pi].get_text().split("\n"):
            lines.append((pi, ln))

    starts = [i for i, (pi, ln) in enumerate(lines) if CHAP_HDR_RE.match(ln)]
    acts = []
    for k, si in enumerate(starts):
        ei = starts[k + 1] if k + 1 < len(starts) else len(lines)
        chap_num = int(CHAP_HDR_RE.match(lines[si][1]).group(1))
        start_page = lines[si][0]
        block_lines = [ln for (pi, ln) in lines[si:ei]]
        full = "\n".join(block_lines).strip()

        # Title: the "An act ..." run, from the first An-act line up to the
        # "[Approved" bracket / enact clause / 6 lines, whichever comes first.
        title = ""
        for j, ln in enumerate(block_lines):
            if AN_ACT_RE.search(ln):
                tparts = [ln]
                for nxt in block_lines[j + 1:j + 6]:
                    if nxt.lstrip().startswith("[") or ENACT_MARKER_RE.search(nxt):
                        break
                    tparts.append(nxt)
                title = re.sub(r"\s+", " ", " ".join(tparts)).strip()[:500]
                break

        iso_date, approved_str = parse_act_date(full)
        confident = (
            chap_num > 0
            and bool(AN_ACT_RE.search(full))
            and bool(ENACT_MARKER_RE.search(full))
            and iso_date is not None
            and len(full) >= 100
        )
        acts.append({
            "chapter": str(chap_num),
            "chapter_int": chap_num,
            "chapter_raw": str(chap_num),
            "title": title,
            "approved_date": approved_str,
            "iso_date": iso_date,
            "text": re.sub(r"[ \t]+", " ", full)[:6000],
            "source_page": start_page + 1,
            "confident": confident,
        })
    return acts


# ---------------------------------------------------------------------------
# TODO -- needed before this is production-ready for the full modern era:
#
# 1. MULTI-VOLUME YEAR ROLL-UP (1915+): a year spans Vol1..VolN with chapter
#    numbers continuous across volumes. Add a parse_born_digital_year() that
#    concatenates the volumes in order, parses each, and emits one chapter
#    stream per year. Must dedupe the "[ Ch. N ]" running-head/footer tokens
#    (they are NOT chapter headers).
#
# 2. OCR-FUZZ-TOLERANT VARIANT (1915-1996, image-only): those years need OCR
#    first; then the CHAPTER/Approved/enact regexes need the same OCR-fuzzy
#    treatment the pre-1900 parser uses (CHAPTER<->CIIAPTER, Approved<->Approvod,
#    ligature/fi normalization, digit confusions in chapter numbers). Cannot be
#    finalized until real 1915-1996 OCR consensus text exists to profile the
#    actual error modes.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse_born_digital.py <path-to-volume.pdf>")
        sys.exit(1)
    acts = parse_born_digital_volume(sys.argv[1])
    conf = [a for a in acts if a["confident"]]
    print("chapters=%d confident=%d range=%s..%s" % (
        len(acts), len(conf),
        min((a["chapter_int"] for a in acts), default=0),
        max((a["chapter_int"] for a in acts), default=0)))
