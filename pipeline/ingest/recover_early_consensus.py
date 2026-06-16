"""recover_early_consensus.py -- SURYA-PREFERRED chapter-header recovery for the
early italic-typeface session-law volumes (1850-1866), fixing a CONSENSUS BUG.

ROOT CAUSE (see docs/30_SYSTEM_DESIGN/CHAPTER_COMPLETENESS_FINDINGS.md
"ROOT-CAUSE UPDATE 2026-06-16"):
  In the early volumes the per-act "CHAP." headers are printed in an ITALIC /
  display typeface. TESSERACT misreads the glyph (Chap.->Cuap./Crap./Cnap...),
  while SURYA and DocTR read it correctly. The token-majority CONSENSUS
  (pipeline/ocr/consensus.py) then picked Tesseract's garble over the two
  CORRECT engines on those header lines, so the CHAP headers VANISHED from the
  consensus_text. The scans are clean; the headers are legible; the CORRECT
  headers already live in the `surya_text` (and `doctr_text`) per-page fields of
  the existing OCR JSON. This is a CONSENSUS bug, not OCR loss -- no re-scan/
  re-OCR needed.

WHAT THIS MODULE DOES (precision-first, READ-ONLY w.r.t. DB + every existing file):
  1. Loads production-<label>/ocr_consensus/page_ocr_results.json, which carries
     per-page `tess_text` / `doctr_text` / `surya_text` (the per-engine reads)
     PLUS the merged `consensus_text` (confirmed field names from
     pipeline/ocr/consensus.py:consensus_from_page_record).
  2. Builds a CORRECTED per-page line stream: starts from `consensus_text`, and
     for any line that is a GARBLED-or-missing header in consensus but reads as a
     CLEAR "CHAP <numeral> -- An Act" header in SURYA (preferred) or DocTR,
     SUBSTITUTES the engine line. We patch ONLY header lines; all body text stays
     consensus. We NEVER trust Tesseract on a header line and NEVER fabricate a
     header an engine did not clearly read.
  3. Runs the proven recover_early header-form detector (imported verbatim:
     same FORMA triad, same SANITY enacting-clause/[Approved] gate, same
     positional numbering) over the CORRECTED stream.
  4. Writes the NEW file production-<label>/parsed_acts_early_v2.json -- NEVER
     touches parsed_acts*.json, parsed_acts_early.json, parsed_acts_recovered.json,
     or page_ocr_results.json. No Postgres writes.

PRECISION: a header line is corrected ONLY when Surya OR DocTR matches the
recover_early JOINED triad (loose C-glyph + REAL numeral + em-dash + "An Act",
quoted-title rejected) -- the exact same high-precision predicate the early
detector already uses for ERA-1. So a substituted line is, by construction, a
real act-start header in the engine that read it. Tesseract's read of that line
is discarded.

USAGE
  python -m ingest.recover_early_consensus --census 1850 1851 ... 1865-66   # affected-set table
  python -m ingest.recover_early_consensus 1861 1862 1863-64                # detect + write v2
  python -m ingest.recover_early_consensus --score 1861 1862 1863-64        # detect + score BEFORE/AFTER vs oracle
  python -m ingest.recover_early_consensus --all                            # all early sessions, write + score

Default ENV: PATOLEX_LOCATION_ROOT=C:\\Users\\patolex\\PatoLex-scratch,
             PYTHONPATH=C:\\github\\PatoLex\\pipeline
"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # pipeline/ on path
import config

ROOT = Path(config.path_for("data_root"))

# ---- import recover_early (the proven detector + regexes + oracle) ----------
_RE = Path(__file__).resolve().parent / "recover_early.py"
_spec = importlib.util.spec_from_file_location("recover_early_ro", str(_RE))
re_early = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(re_early)

# the production parser predicates (header_starts_act) used by recover_early's
# split-form baseline -- reused through re_early; nothing new needed here.

# Early sessions we hold OCR for (1850-1866 individual + biennials).
EARLY_LABELS = [
    "1850", "1851", "1852", "1853", "1854", "1855", "1856", "1857", "1858",
    "1859", "1860", "1861", "1862", "1863", "1863-64", "1865-66",
]


# ---------------------------------------------------------------------------
# OCR JSON access -- confirmed fields: consensus_text / tess_text / doctr_text /
# surya_text per page (see pipeline/ocr/consensus.py:consensus_from_page_record).
# ---------------------------------------------------------------------------
def _ocr_path(label: str) -> Path:
    return ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"


def load_pages(label: str) -> dict:
    """Return {page_index:int -> page_record:dict} sorted-able by key."""
    raw = json.loads(_ocr_path(label).read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def _engine_lines(page: dict, field: str) -> list[str]:
    return (page.get(field) or "").split("\n")


# ---------------------------------------------------------------------------
# Header detection on a single line -- reuse recover_early's EXACT joined triad.
# Returns the numeral token if `line` is a clear CHAP+numeral+dash+"An Act"
# header in this engine, else None. (We deliberately use the same FORMA + AN_ACT
# + quoted-title logic recover_early uses, so a "clear header" here == a real
# ERA-1 act-start header there.)
# ---------------------------------------------------------------------------
def header_numeral(line: str) -> str | None:
    s = line.strip()
    ma = re_early.FORMA.match(s)
    if not (ma and re_early.numeral_ok(ma.group(2))):
        return None
    title = ma.group(3)
    am = re_early.AN_ACT_STRICT.search(title) or re_early.AN_ACT_FUZZY.search(title)
    if am and not re_early._quoted_before(title, am):
        return ma.group(2)
    return None


# ---------------------------------------------------------------------------
# CHAP-glyph census (DO step 1): count clear CHAP-headers per engine field.
# A volume is AFFECTED when SURYA has many and CONSENSUS has ~0.
# ---------------------------------------------------------------------------
def census(label: str) -> dict:
    pages = load_pages(label)
    counts = {"surya_text": 0, "doctr_text": 0, "tess_text": 0, "consensus_text": 0}
    for pidx in sorted(pages):
        page = pages[pidx]
        for field in counts:
            for ln in _engine_lines(page, field):
                if header_numeral(ln) is not None:
                    counts[field] += 1
    counts["label"] = label
    return counts


# ---------------------------------------------------------------------------
# Build the CORRECTED line stream (DO step 2) -- COUNT-STABLE, SUBSTITUTION-FIRST.
#
# What the census revealed (see run-log + CHAPTER_COMPLETENESS_FINDINGS update):
#   The consensus_text ALREADY carries the early CHAP headers -- but with the
#   GLYPH garbled by Tesseract (Cuap/Crap/Caar...). The loose-glyph triad in
#   recover_early therefore already DETECTS them on consensus. What consensus
#   loses vs Surya is (a) the CLEAN glyph spelling and, occasionally, (b) a
#   header Tesseract garbled so badly the numeral/dash/An-Act tail broke too.
#
# So the correction is TWO precise, count-stable operations per page, NOT a
# blanket append (the naive append duplicated every garbled-glyph header against
# its clean Surya twin -> the 1865-66 442->595 blow-up):
#
#   (1) SUBSTITUTE IN PLACE: for each CONSENSUS header line, find the
#       positionally-corresponding SURYA (then DocTR) header on the same page
#       (matched by order among that page's headers) and replace the consensus
#       header line with the engine's clean reading -> clean glyph + clean
#       numeral for display. Count is unchanged (1 consensus header -> 1 line).
#
#   (2) BACKFILL ONLY THE SHORTFALL: if SURYA saw MORE headers on the page than
#       consensus did (n_eng > n_cons), add exactly (n_eng - n_cons) engine
#       headers that have NO positional consensus match -- the genuinely-dropped
#       ones -- inserted in reading order. We add at most the shortfall, never a
#       header that already has a consensus twin, so no duplication.
#
# Returns ([(page_index, line_text, source), ...], n_substituted, n_backfilled).
# ---------------------------------------------------------------------------
def _page_engine_headers(page):
    """Ordered list of (line_text, numeral, engine) clear headers for the page,
    SURYA preferred then DocTR backfill (DocTR header added only if no Surya
    header reads the same numeral on the page)."""
    surya = []
    for ln in _engine_lines(page, "surya_text"):
        num = header_numeral(ln)
        if num is not None:
            surya.append((ln.strip(), num, "surya"))
    surya_nums = {re_early.parse_chapter_numeral(n) for _, n, _ in surya}
    doctr = []
    for ln in _engine_lines(page, "doctr_text"):
        num = header_numeral(ln)
        if num is not None:
            v = re_early.parse_chapter_numeral(num)
            if v not in surya_nums:        # only DocTR headers Surya missed
                doctr.append((ln.strip(), num, "doctr"))
    return surya + doctr


def corrected_lines(label: str):
    pages = load_pages(label)
    out = []
    n_sub = 0
    n_backfill = 0
    for pidx in sorted(pages):
        page = pages[pidx]
        cons_lines = _engine_lines(page, "consensus_text")
        eng_hdrs = _page_engine_headers(page)        # ordered clean headers

        # indices of consensus header lines (in page order)
        cons_hdr_idx = [i for i, ln in enumerate(cons_lines)
                        if header_numeral(ln) is not None]

        # (1) SUBSTITUTE each consensus header with the positionally-matched
        #     clean engine header (by order among the page's headers).
        used_eng = set()
        for rank, ci in enumerate(cons_hdr_idx):
            if rank < len(eng_hdrs):
                clean_line, _num, _eng = eng_hdrs[rank]
                cons_lines[ci] = clean_line
                used_eng.add(rank)
                n_sub += 1
            # if consensus has MORE headers than the engines saw, leave the
            # consensus header as-is (rare; engine under-read this page).

        # emit (possibly-substituted) consensus lines in order
        for ln in cons_lines:
            out.append((pidx, ln, "consensus/clean"))

        # (2) BACKFILL the shortfall: engine headers with no consensus twin
        #     (ranks beyond the number of consensus headers on this page).
        for rank in range(len(cons_hdr_idx), len(eng_hdrs)):
            clean_line, _num, eng = eng_hdrs[rank]
            out.append((pidx, clean_line, eng + "/backfill"))
            n_backfill += 1
    return out, n_sub, n_backfill


# ---------------------------------------------------------------------------
# Detect acts over the CORRECTED stream by reusing recover_early.detect_starts /
# build_act / SANITY gate logic verbatim. We feed corrected lines as the
# [(page_index, line_text)] list recover_early expects.
# ---------------------------------------------------------------------------
def process_session(label: str):
    corr, n_sub, n_backfill = corrected_lines(label)
    patched = n_sub + n_backfill
    lines = [(p, t) for (p, t, _src) in corr]
    starts = re_early.detect_starts(lines)
    acts = []
    for k, (si, tok, form) in enumerate(starts):
        ei = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        rec = re_early.build_act(lines, si, ei, tok, form, label, k)
        # SAME SANITY gate as recover_early: real body span + corroborating marker.
        if len(rec["text"]) < re_early.SANITY_MIN_TEXT:
            continue
        if not (rec["has_enact"] or rec["has_approved"]):
            continue
        rec["origin"] = "early_consensus_v2"
        acts.append(rec)
    for k, a in enumerate(acts):
        a["in_act_order"] = k
    n_a = sum(1 for a in acts if a["form"] == "A")
    n_b = sum(1 for a in acts if a["form"] == "B")
    out_path = ROOT / ("production-" + label) / "parsed_acts_early_v2.json"
    out_path.write_text(json.dumps({
        "confident_acts": [],
        "flagged_acts": acts,
        "_early_meta": {
            "label": label,
            "detector": "recover_early_consensus.py surya-header-corrected v2",
            "raw_starts": len(starts),
            "acts_kept": len(acts),
            "form_a_joined": n_a,
            "form_b_split": n_b,
            "header_lines_substituted_clean": n_sub,
            "header_lines_backfilled": n_backfill,
            "min_gap": re_early.MIN_GAP,
        },
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(acts), len(starts), patched, out_path


# ---------------------------------------------------------------------------
# BEFORE baseline = what the current CONSENSUS-only recover_early keeps (its own
# process is consensus-only). We reuse recover_early.process_session's logic but
# WITHOUT writing -- by re-detecting over consensus lines directly.
# ---------------------------------------------------------------------------
def baseline_consensus_count(label: str) -> int:
    """Acts kept by the EXISTING consensus-only recover_early detector (the BEFORE
    number for the AFTER-recovery comparison). Read-only re-walk over
    consensus_text, no file written."""
    lines = re_early.load_lines(label)   # reads consensus_text per page
    starts = re_early.detect_starts(lines)
    n = 0
    for k, (si, tok, form) in enumerate(starts):
        ei = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        rec = re_early.build_act(lines, si, ei, tok, form, label, k)
        if len(rec["text"]) < re_early.SANITY_MIN_TEXT:
            continue
        if not (rec["has_enact"] or rec["has_approved"]):
            continue
        n += 1
    return n


def main():
    args = sys.argv[1:]
    do_census = "--census" in args
    do_score = "--score" in args
    do_all = "--all" in args
    for f in ("--census", "--score", "--all"):
        if f in args:
            args.remove(f)
    labels = EARLY_LABELS if do_all else args
    if not labels:
        raise SystemExit(
            "usage: python -m ingest.recover_early_consensus "
            "[--census|--score|--all] <label> [label...]")

    if do_census:
        print(f"{'label':<10}{'surya':>8}{'doctr':>8}{'tess':>8}{'consensus':>11}"
              f"{'affected?':>11}")
        for label in labels:
            try:
                c = census(label)
            except FileNotFoundError:
                print(f"{label:<10}{'(no OCR json)':>46}")
                continue
            affected = "YES" if (c["surya_text"] >= 20 and
                                 c["consensus_text"] <= 0.25 * c["surya_text"]) else "no"
            print(f"{label:<10}{c['surya_text']:>8}{c['doctr_text']:>8}"
                  f"{c['tess_text']:>8}{c['consensus_text']:>11}{affected:>11}")
        return

    hdr = (f"{'label':<10}{'before':>8}{'after':>8}{'oracle':>8}{'b%':>6}{'a%':>6}"
           f"{'A':>6}{'B':>6}{'patched':>9}") if do_score else \
          (f"{'label':<10}{'detected':>9}{'kept':>7}{'patched':>9}{'oracle':>8}{'compl%':>8}")
    print(hdr)
    for label in labels:
        try:
            kept, raw_starts, patched, out_path = process_session(label)
        except FileNotFoundError:
            print(f"{label:<10}  (no OCR json -- skipped)")
            continue
        N = re_early._ORACLE.get(label, 0)
        apct = (100.0 * kept / N) if N else 0.0
        if do_score:
            before = baseline_consensus_count(label)
            bpct = (100.0 * before / N) if N else 0.0
            n_a = sum(1 for _ in ())  # placeholder; read from file meta
            meta = json.loads(out_path.read_text(encoding="utf-8")).get("_early_meta", {})
            print(f"{label:<10}{before:>8}{kept:>8}{N:>8}{bpct:>5.0f}%{apct:>5.0f}%"
                  f"{meta.get('form_a_joined', 0):>6}{meta.get('form_b_split', 0):>6}"
                  f"{patched:>9}")
        else:
            print(f"{label:<10}{raw_starts:>9}{kept:>7}{patched:>9}{N:>8}{apct:>7.0f}%")
    if do_score:
        print("\n(scored vs docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv; "
              "BEFORE = consensus-only recover_early, AFTER = surya-header-corrected; "
              "1865-66 oracle=280 CONFIRMED correct -- AFTER should drop toward 280)")


if __name__ == "__main__":
    main()
