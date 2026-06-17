"""diag_missed_starts.py -- READ-ONLY. Enumerate the REAL act-starts the
production parser missed, and bucket each by the precise failure mode, so STEP 1
has hard counts (not a sample).

A "real act-start" line i is one where:
  * line i opens with 'An act' (strict OR a small tolerant garble set), AND
  * an enacting clause appears within ENACT_K lines below, AND
  * a tolerant chapter-header line ('CHAP...') appears within HDR_K lines above
    (so it is an act header context, not a body 'an act' citation), AND
  * the 'An act' is NOT a quoted citation (no opening quote right before it).

For each such start, did PRODUCTION fire header_starts_act at the header above it?
If yes -> production got it (not a miss). If no -> bucket WHY:
  M1 header_garbled_numeral : header line present, glyph ok, but numeral not in
                              HEADER_RE's token class (roman/garble) -> HEADER_RE fails
  M2 header_trailing_text   : HEADER_RE fails because the header shares its line with
                              trailing text / punctuation past the '$' anchor
  M3 anact_past_window      : HEADER_RE matches the header but 'An act' is beyond the
                              4-nonempty-line lookahead
  M4 anact_garbled          : the 'An act' line is tolerant-only (AN_ACT_RE misses it)
  M5 header_missing         : no chapter header line at all within HDR_K above
  M6 other

Usage: python diag_missed_starts.py <label> [<label> ...]
"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
from collections import Counter
import importlib.util
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
ROOT = Path(config.path_for("data_root"))
_ING = Path(__file__).resolve().parents[1] / "ingest" / "ingest_from_ocr.py"
_spec = importlib.util.spec_from_file_location("ing_ro", str(_ING))
ing = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ing)

ENACT_K = 25
HDR_K = 5

TOL_HDR = re.compile(r"^[^A-Za-z0-9]{0,4}(CHAP(?:TER|T|\.)?)\b", re.I)
# header that has a numeral after the glyph (arabic OR roman-ish)
TOL_HDR_NUM = re.compile(
    r"^[^A-Za-z0-9]{0,4}CHAP(?:TER|T|\.)?\.?\s*"
    r"([IVXLCDMivxlcdm0-9JjTtYyLl!|]{1,9})\b", re.I)
TOL_ANACT = re.compile(
    r"^[\s.,;:'\"\[\(]{0,4}(?:A[nui]{1,2}|ain)\s*[. ]?a[ceon][tilr]\b", re.I)
ENACT_TOL = re.compile(
    r"[Pp]e[oe]ple\s+of\s+the\s+[Ss]tate\s+of\s+Calif|do\s+enact\s+as\s+follow", re.I)
_OPEN_QUOTES = "\"'“‘„‚«‹`’”›»"


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

    def enact_below(i, k=ENACT_K):
        for j in range(i, min(n, i + k)):
            if ENACT_TOL.search(all_lines[j][1]):
                return True
        return False

    def find_hdr_above(i, k=HDR_K):
        """return (hdr_idx, hdr_line) of the closest tolerant chapter header above, or (None,None)"""
        for j in range(i, max(-1, i - k - 1), -1):
            if TOL_HDR.match(all_lines[j][1].strip()):
                return j, all_lines[j][1].strip()
        return None, None

    def production_fires_at(j):
        ok, tok = ing.header_starts_act(plain, j)
        return ok

    def anact_strict(i):
        return bool(ing.AN_ACT_RE.search(all_lines[i][1]))

    def quoted(i):
        s = all_lines[i][1]
        m = ing.AN_ACT_RE.search(s) or TOL_ANACT.match(s.strip())
        if not m:
            return False
        head = s[:m.start()].rstrip(" \t") if hasattr(m, "start") else ""
        return bool(head) and head[-1] in _OPEN_QUOTES

    starts = []          # (i, hdr_idx) real act-starts
    for i in range(n):
        s = all_lines[i][1]
        is_an = ing.AN_ACT_RE.search(s) or TOL_ANACT.match(s.strip())
        if not is_an:
            continue
        # opener must begin the line (not a mid-sentence citation)
        m = ing.AN_ACT_RE.search(s) or TOL_ANACT.match(s.strip())
        head = s[:m.start()].strip(" \t.,:;\"'`-[(") if m else "x"
        if head:
            continue
        if quoted(i):
            continue
        if not enact_below(i):
            continue
        hdr_idx, hdr_line = find_hdr_above(i)
        if hdr_idx is None:
            starts.append((i, None, "M5_header_missing"))
            continue
        starts.append((i, hdr_idx, None))

    # now bucket
    modes = Counter()
    missed = []
    prod_got = 0
    for (i, hdr_idx, premode) in starts:
        if premode == "M5_header_missing":
            # only a miss if production didn't already fire somewhere at i-ish
            if not anact_strict(i) or not any(production_fires_at(j) for j in range(max(0, i - 5), i + 1)):
                modes["M5_header_missing"] += 1
                missed.append((i, "M5_header_missing"))
            continue
        # did production fire at the header above (within HDR_K)?
        fired = any(production_fires_at(j) for j in range(hdr_idx, min(n, hdr_idx + 1)))
        # production scans the whole vol; it fires at hdr_idx if HEADER_RE matches AND
        # AnAct within 4 nonempty. Check hdr_idx specifically.
        fired = production_fires_at(hdr_idx)
        if fired:
            prod_got += 1
            continue
        # MISS -- why?
        hdr_line = all_lines[hdr_idx][1].strip()
        header_re_ok = bool(ing.HEADER_RE.match(hdr_line))
        if not anact_strict(i):
            mode = "M4_anact_garbled"
        elif not header_re_ok:
            mnum = TOL_HDR_NUM.match(hdr_line)
            if mnum and not re.fullmatch(r"[0-9]{1,4}", mnum.group(1)):
                mode = "M1_header_garbled_numeral"
            elif mnum is None:
                # glyph but no numeral captured -> numeral garble too
                mode = "M1_header_garbled_numeral"
            else:
                mode = "M2_header_trailing_text"
        else:
            # HEADER_RE matches header, strict An act, but production didn't fire ->
            # An act beyond the 4-line window
            mode = "M3_anact_past_window"
        modes[mode] += 1
        missed.append((i, mode))

    report = {
        "labels": labels,
        "real_act_starts_detected": len(starts),
        "production_got": prod_got,
        "total_missed": sum(modes.values()),
        "mode_counts": dict(modes),
        "sample_missed": [
            {"page": all_lines[i][0] + 1, "line": all_lines[i][2],
             "mode": mode, "anact": all_lines[i][1].strip()[:80],
             "hdr_above": (lambda hi: all_lines[hi][1].strip()[:50] if hi is not None else "")(
                 next((h for (ii, h, pm) in starts if ii == i), None))}
            for (i, mode) in missed[:30]],
    }
    out = ROOT / ("diag_missed_" + labels[0] + ".json")
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in
                      ("labels", "real_act_starts_detected", "production_got",
                       "total_missed", "mode_counts")}, indent=2))
    print("out:", out)


if __name__ == "__main__":
    main()
