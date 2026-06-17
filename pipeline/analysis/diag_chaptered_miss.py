"""diag_chaptered_miss.py -- READ-ONLY diagnostic. Why does the production parser
miss chaptered-era acts whose 'CHAPTER <n>' header IS in the OCR?

Reproduces the production header_starts_act walk, lists chapter numbers in [1,N]
that are missing from parsed_acts_recovered.json, locates each missing
'CHAPTER <n>' header in consensus_text, inspects surrounding lines, and
categorizes the failure mode. Prints a JSON summary. Writes nothing but stdout.

Run on 5090:  python -m analysis.diag_chaptered_miss 1931-vol1-chapters 1933-vol1-chapters
"""
import sys, re, json
from pathlib import Path
import importlib.util
import config

_here = Path(__file__).resolve().parent
_cands = [_here / "ingest" / "ingest_from_ocr.py",
          _here.parent / "ingest" / "ingest_from_ocr.py",
          _here / "ingest_from_ocr.py"]
_ING = next(p for p in _cands if p.exists())
_spec = importlib.util.spec_from_file_location("ingest_from_ocr", str(_ING))
ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ing)

ROOT = Path(config.path_for("data_root"))

# A literal printed "CHAPTER <arabic n>" header line (what the oracle counts).
# Anchored loosely: allow leading junk, then CHAP-ish word, then an ARABIC number.
CHAP_LINE_RE = re.compile(r"^\s*[^A-Za-z0-9]{0,4}CHAP(?:TER|T\.?|\.)?\s*([0-9]{1,4})\b", re.I)
# Also a looser one that the oracle (OCR runs to chapter N) would catch incl. fuzzy
ANY_CHAP_NUM_RE = re.compile(r"\bCHAP(?:TER|T\.?|\.)?\s*([0-9]{1,4})\b", re.I)


def load_lines(label):
    p = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    lines = []  # (page_idx, text, line_pos_within_page)
    for pidx in sorted(pages.keys()):
        txt = pages[pidx].get("consensus_text", "").split("\n")
        for k, line in enumerate(txt):
            lines.append((pidx, line, k))
    return lines


def parsed_chapters(label):
    p = ROOT / ("production-" + label) / "parsed_acts_recovered.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    nums = set()
    for bucket in ("confident_acts", "flagged_acts"):
        for a in data.get(bucket, []):
            ci = a.get("chapter_int_final", a.get("chapter_int", 0)) or 0
            if ci > 0:
                nums.add(int(ci))
    return nums


def find_chapter_header_lines(lines):
    """Map chapter_number -> list of line indices where a 'CHAPTER n' header (page-top
    anchored arabic) appears. Returns dict num->[idx,...]."""
    hdrs = {}
    for i, (p, t, k) in enumerate(lines):
        m = CHAP_LINE_RE.match(t)
        if m:
            n = int(m.group(1))
            hdrs.setdefault(n, []).append(i)
    return hdrs


def find_any_chapter_num(lines, n):
    """Any line mentioning 'CHAPTER n' (mid-line ok) -- for locating headers the
    strict page-top regex missed."""
    out = []
    for i, (p, t, k) in enumerate(lines):
        for m in ANY_CHAP_NUM_RE.finditer(t):
            if int(m.group(1)) == n:
                out.append(i)
                break
    return out


def classify(lines, idx, plain):
    """Classify why production header_starts_act did NOT fire at this CHAPTER header
    line (or why the act wasn't extracted). Returns (mode, detail)."""
    p, t, k = lines[idx]
    reasons = []

    # Does HEADER_RE even match this line (production requires ^ match)?
    hdr_match = ing.HEADER_RE.match(t.strip())

    # Is "CHAPTER n" sharing the line with other text (so ^...$ header regex fails)?
    # HEADER_RE requires the line to END after the numeral (+optional dash tail).
    shares_line = False
    if ANY_CHAP_NUM_RE.search(t):
        # strip the leading chapter token; is there substantial trailing text?
        tail = ANY_CHAP_NUM_RE.sub("", t, count=1).strip(" .,;:-")
        if len(tail) > 3 and not re.match(r"^[" + ing._DASH + r"]", tail):
            shares_line = True

    # Where does "An Act" appear relative to the header? Production needs it within
    # the next 4 NON-EMPTY lines.
    nn = ing._next_nonempty(plain, idx, 4)
    window = " ".join([plain[idx][1]] + nn)
    an_in_window = bool(ing.AN_ACT_RE.search(window))

    # how many lines down is the first "An Act"? (scan up to 14)
    an_dist = None
    an_blank_before = 0
    seen_nonblank = 0
    for d in range(1, 15):
        j = idx + d
        if j >= len(plain):
            break
        s = plain[j][1].strip()
        if ing.AN_ACT_RE.search(plain[j][1]):
            an_dist = d
            break
    # count non-empty lines between header and An Act
    an_nonempty_dist = None
    if an_dist is not None:
        cnt = 0
        for d in range(1, an_dist + 1):
            if plain[idx + d][1].strip():
                cnt += 1
        an_nonempty_dist = cnt

    # page-top? production header_starts_act doesn't require page-top, but recovered_starts does
    page_top = k <= 2

    # Is the numeral garbled (non-arabic / would parse wrong)?
    garbled_num = False
    if hdr_match:
        tok = hdr_match.group(1)
        if ing.parse_chapter_number(tok) == 0:
            garbled_num = True

    # ---- decide primary mode ----
    if shares_line:
        mode = "shares_line"          # 'CHAPTER N' on a line with other text -> HEADER_RE ^...$ fails
    elif not hdr_match:
        mode = "header_re_no_match"   # the CHAPTER line doesn't satisfy HEADER_RE at all
    elif garbled_num:
        mode = "garbled_numeral"
    elif an_in_window is False and an_dist is None:
        mode = "no_an_act_nearby"     # no An Act within 14 lines at all
    elif an_in_window is False and an_nonempty_dist is not None and an_nonempty_dist > 4:
        mode = "an_act_beyond_4line_lookahead"  # An Act exists but >4 non-empty lines down
    elif an_in_window is True:
        # header_starts_act WOULD fire here -> act likely dropped downstream
        # (flush_act gate: no enact marker, header has Approved/Passed, <60 chars,
        #  or it WAS parsed but renumber demoted/dropped it)
        mode = "fires_but_dropped_downstream"
    else:
        mode = "other"

    detail = {
        "page": p + 1, "line_pos": k, "page_top": page_top,
        "hdr_re_match": bool(hdr_match),
        "shares_line": shares_line, "garbled_num": garbled_num,
        "an_in_4line_window": an_in_window,
        "an_first_dist_lines": an_dist,
        "an_nonempty_dist": an_nonempty_dist,
    }
    return mode, detail


def context(lines, idx, before=2, after=6):
    lo = max(0, idx - before)
    hi = min(len(lines), idx + after + 1)
    out = []
    for j in range(lo, hi):
        p, t, k = lines[j]
        mark = ">>" if j == idx else "  "
        out.append(f"{mark} p{p+1} l{k:>3}: {t}")
    return out


def diagnose(label, sample_target=20):
    lines = load_lines(label)
    plain = [(p, t) for (p, t, k) in lines]
    parsed = parsed_chapters(label)

    # oracle N: the max chapter number that appears anywhere as 'CHAPTER n'
    all_nums = set()
    for i, (p, t, k) in enumerate(lines):
        for m in ANY_CHAP_NUM_RE.finditer(t):
            v = int(m.group(1))
            if 1 <= v <= 3000:
                all_nums.add(v)
    oracle_n = max(all_nums) if all_nums else 0

    hdr_lines = find_chapter_header_lines(lines)

    if parsed is None:
        return {"label": label, "error": "no parsed_acts_recovered.json"}

    missing = sorted(n for n in range(1, oracle_n + 1)
                     if n not in parsed and n in all_nums)

    # build samples + categorize ALL missing (count), sample for verbatim
    mode_counts = {}
    samples = []
    examples = []
    for n in missing:
        # find the header line for this chapter: prefer strict page-top match, else any
        idxs = hdr_lines.get(n) or find_any_chapter_num(lines, n)
        if not idxs:
            mode_counts["no_header_found"] = mode_counts.get("no_header_found", 0) + 1
            continue
        # pick the first occurrence (act-start position)
        idx = idxs[0]
        mode, detail = classify(lines, idx, plain)
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        if len(samples) < sample_target:
            samples.append({"chapter": n, "mode": mode, "detail": detail})
        # collect up to a couple verbatim examples per mode
        if sum(1 for e in examples if e["mode"] == mode) < 1:
            examples.append({"chapter": n, "mode": mode,
                             "context": context(lines, idx)})

    return {
        "label": label,
        "oracle_n": oracle_n,
        "parsed_distinct": len(parsed),
        "missing_count": len(missing),
        "missing_sample": missing[:40],
        "mode_counts": mode_counts,
        "samples": samples,
        "examples": examples,
    }


def main():
    labels = sys.argv[1:] or ["1931-vol1-chapters", "1933-vol1-chapters"]
    result = {}
    for lab in labels:
        result[lab] = diagnose(lab)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
