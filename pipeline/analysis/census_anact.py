"""census_anact.py -- READ-ONLY. Census of candidate act-START signals in a
chaptered-era volume, to quantify WHERE the recoverable acts are.

Counts, across the whole volume:
  A) HEADER_RE header lines (production's start signal)
  B) lines that look like a chapter header by a TOLERANT arabic/roman rule but
     are NOT matched by HEADER_RE
  C) "An act"-opening lines matched by production AN_ACT_RE
  D) "An act"-opening lines matched only by a TOLERANT an-act rule (garbled:
     'ain act','Aniact','An aet','An net', etc.) -- the suspected real miss
  E) of (C)+(D), how many sit within +/-3 lines of a tolerant chapter header AND
     have an enacting clause within 25 lines below (a strong real-act signal)

This tells us how many acts are present-in-text but lost because either the
header numeral garbled OR the 'An act' garbled past AN_ACT_RE.

Usage: python census_anact.py <label> [<label> ...]
"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import importlib.util
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
ROOT = Path(config.path_for("data_root"))
_ING = Path(__file__).resolve().parents[1] / "ingest" / "ingest_from_ocr.py"
_spec = importlib.util.spec_from_file_location("ing_ro", str(_ING))
ing = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ing)

# tolerant chapter header: a 'CHAP...' word at line start + an optional numeral.
TOL_HDR = re.compile(r"^[^A-Za-z0-9]{0,4}CHAP(?:TER|T|\.)?\b", re.I)
# tolerant 'An act' opener: An/Aniact/ain/An aet/An net/An ait, at/near line start
TOL_ANACT = re.compile(
    r"^[\s.,;:'\"\[\(]{0,4}"
    r"(?:A[nui]{1,2}|ain)\s*"          # An / Au / Ani / ain (incl. 'Aniact' = Ani+act)
    r"[. ]?a[ceon][tilr]\b",           # act / aet / aci / acl / aor ...
    re.I)
# enacting clause, tolerant
ENACT_TOL = re.compile(
    r"[Pp]e[oe]ple\s+of\s+the\s+[Ss]tate\s+of\s+Calif"
    r"|do\s+enact\s+as\s+follow", re.I)


def load_lines(label):
    p = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    out = []
    for pidx in sorted(pages):
        for k, ln in enumerate(pages[pidx].get("consensus_text", "").split("\n")):
            out.append((pidx, ln, k))
    return out


def main():
    labels = sys.argv[1:]
    all_lines = []
    for lb in labels:
        all_lines.extend(load_lines(lb))
    plain = [(p, t) for (p, t, k) in all_lines]
    n = len(all_lines)

    header_re = [i for i in range(n) if ing.HEADER_RE.match(plain[i][1].strip())]
    an_strict = [i for i in range(n) if ing.AN_ACT_RE.search(plain[i][1])]
    an_tol_only = [i for i in range(n)
                   if TOL_ANACT.match(all_lines[i][1].strip())
                   and not ing.AN_ACT_RE.search(all_lines[i][1])]

    def enact_below(i, k=25):
        for j in range(i, min(n, i + k)):
            if ENACT_TOL.search(all_lines[j][1]):
                return True
        return False

    def tol_hdr_above(i, k=4):
        for j in range(max(0, i - k), i + 1):
            if TOL_HDR.match(all_lines[j][1].strip()):
                return True
        return False

    # production-found act openers: an 'An act' (strict) within 4 nonempty below a HEADER_RE
    prod_acts = 0
    for i in header_re:
        window = " ".join([plain[i][1].strip()] +
                          ing._next_nonempty(plain, i, 4))
        if ing.AN_ACT_RE.search(window):
            prod_acts += 1

    # candidate REAL misses: a tolerant-only 'An act' that has a chapter header just
    # above AND an enacting clause below -- present-in-text act lost to garble.
    garbled_anact_real = [i for i in an_tol_only
                          if tol_hdr_above(i, 4) and enact_below(i, 25)]
    # also: strict 'An act' with a header above but production didn't fire (because
    # HEADER_RE failed on the header line) -- header-side garble
    strict_anact_hdr_above_enact = [
        i for i in an_strict
        if tol_hdr_above(i, 4) and enact_below(i, 25)]

    report = {
        "labels": labels,
        "total_lines": n,
        "HEADER_RE_lines": len(header_re),
        "AN_ACT_strict_lines": len(an_strict),
        "AN_ACT_tolerant_only_lines": len(an_tol_only),
        "production_header+anact_pairs": prod_acts,
        "garbled_anact_with_hdr_and_enact": len(garbled_anact_real),
        "strict_anact_with_hdr_and_enact": len(strict_anact_hdr_above_enact),
        "samples_garbled_anact": [
            (all_lines[i][0] + 1, all_lines[i][2], all_lines[i][1].strip()[:90])
            for i in garbled_anact_real[:25]],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
