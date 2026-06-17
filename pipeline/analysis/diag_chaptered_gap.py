"""diag_chaptered_gap.py -- STEP 1 diagnostic for the chaptered-era (1880-1999)
detection gap. READ-ONLY. Writes ONE JSON report per session to the data root
(diag_chaptered_<label>.json) -- never touches parsed_acts*.json or the DB.

For a session whose authoritative chapter total is N, it:
  1. Re-runs the EXACT production header walk (ingest_from_ocr.header_starts_act)
     to get the chapter numbers production actually KEEPS (flush_act criteria).
  2. Computes the set of chapter numbers in [1,N] that production MISSED.
  3. For a sample of missed chapters, locates where "CHAPTER <n>" physically
     sits in the OCR text (anchored arabic header line) and categorizes WHY the
     production parser failed to start an act there. Failure modes:
       - no_header_found        : no anchored 'CHAPTER <n>' header line anywhere
                                  (true OCR loss or garbled numeral) -> not this gap
       - header_re_no_match     : a 'CHAPTER <n>' arabic line exists but the
                                  production HEADER_RE does not match it (shares a
                                  line / trailing text / leading junk)
       - an_act_outside_window  : HEADER_RE matches but 'An Act' is NOT within the
                                  4-nonempty-line lookahead (intervening matter:
                                  bill cite, blank gap, long title)
       - flush_dropped          : header_starts_act fires but flush_act drops the
                                  act (no enact marker / <60 chars / Approved hdr)
       - other                  : header matched + An Act in window + would-keep,
                                  yet the number isn't in our kept set (dedup/
                                  collision / numeral misparse)

Usage (on the 5090, where the OCR lives):
  python -m analysis.diag_chaptered_gap <N> <label> [<label> ...] [--sample K]
    <N>     authoritative chapter total for the session (oracle)
    labels  one or more physical volume labels of the SAME session
"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # pipeline/ on path
import config

ROOT = Path(config.path_for("data_root"))

_ING = Path(__file__).resolve().parents[1] / "ingest" / "ingest_from_ocr.py"
_spec = importlib.util.spec_from_file_location("ingest_from_ocr_ro", str(_ING))
ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ing)

# anchored arabic chapter header (the header line printed for an act). We accept a
# small amount of leading junk and OPTIONAL trailing text, so we can detect BOTH
# clean headers and headers that share a line / have trailing matter.
CHAP_ARABIC_ANY = re.compile(r"CHAP(?:TER|T\.?|\.)?\s*([0-9]{1,4})\b", re.I)


def load_lines(label):
    ocr_path = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(ocr_path.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    lines = []  # (page_index, text, line_pos_within_page)
    for pidx in sorted(pages):
        txt = pages[pidx].get("consensus_text", "").split("\n")
        for k, line in enumerate(txt):
            lines.append((pidx, line, k))
    return lines


def production_kept_numbers(lines):
    """Replicate parse_volume + flush_act keep-criteria; return:
       kept_nums:set[int], fired_idx:list[int] (header_starts_act fires),
       fired_tok:dict[idx->token]."""
    plain = [(p, t) for (p, t, k) in lines]
    fired_idx = []
    fired_tok = {}
    for i in range(len(plain)):
        ok, tok = ing.header_starts_act(plain, i)
        if ok:
            fired_idx.append(i)
            fired_tok[i] = tok
    kept = set()
    for k, si in enumerate(fired_idx):
        ei = fired_idx[k + 1] if k + 1 < len(fired_idx) else len(plain)
        buf = [plain[j][1] for j in range(si, ei)]
        full = "\n".join(buf).strip()
        if len(full) < 60:
            continue
        header_line = re.sub(r"\s+", " ", buf[0]).strip() if buf else ""
        if re.search(r"\b(?:Approved|Passed)\b", header_line, re.I):
            continue
        if not ing.has_enact_marker(full):
            continue
        ci = ing.parse_chapter_number(fired_tok[si])
        if ci > 0:
            kept.add(ci)
    return kept, fired_idx, fired_tok


def _next_nonempty_join(lines, i, k=4):
    return ing._next_nonempty([(p, t) for (p, t, _k) in lines], i, k)


def classify_missing(lines, n):
    """For missing chapter number n, find a plausible header location and classify.
    Returns dict with mode + evidence."""
    fired_set = None  # filled by caller for 'other' detection
    hits = []  # (line_index) where an anchored arabic 'CHAPTER n' appears
    for i, (pidx, line, kpos) in enumerate(lines):
        s = line.strip()
        for m in CHAP_ARABIC_ANY.finditer(s):
            if int(m.group(1)) == n:
                # require the CHAPTER token to be at/near the start of the line OR
                # the only chapter ref -- record position of match within line
                hits.append((i, m.start(), s))
                break
    if not hits:
        return {"chapter": n, "mode": "no_header_found", "evidence": ""}

    # pick the most header-like hit: prefer one where CHAPTER is at line start
    hits.sort(key=lambda h: h[1])  # smallest start offset first
    for (i, off, s) in hits:
        pidx, line, kpos = lines[i]
        plain = [(p, t) for (p, t, _k) in lines]
        hdr_match = bool(ing.HEADER_RE.match(line.strip()))
        # window check (production uses header_starts_act = HEADER_RE + AnAct in 4)
        starts, tok = ing.header_starts_act(plain, i)
        window = " ".join([line.strip()] + _next_nonempty_join(lines, i, 4))
        an_in_window = bool(ing.AN_ACT_RE.search(window))
        # broader: is there an "An Act" within, say, 12 non-empty lines?
        wider = " ".join([line.strip()] + _next_nonempty_join(lines, i, 12))
        an_in_wider = bool(ing.AN_ACT_RE.search(wider))

        if not hdr_match:
            # arabic CHAPTER n line exists but production HEADER_RE rejects it
            return {"chapter": n, "mode": "header_re_no_match",
                    "evidence": s[:160], "page": pidx + 1, "line_pos": kpos,
                    "an_within_12": an_in_wider}
        if hdr_match and not an_in_window:
            mode = ("an_act_outside_window" if an_in_wider
                    else "an_act_not_near")
            nxt = _next_nonempty_join(lines, i, 8)
            return {"chapter": n, "mode": mode, "evidence": s[:120],
                    "page": pidx + 1, "line_pos": kpos,
                    "next_lines": [x[:80] for x in nxt[:6]],
                    "an_within_12": an_in_wider}
        if starts:
            # header_starts_act WOULD fire here -> flush_act must have dropped it,
            # or numeral misparsed, or a dedup/collision in the kept set.
            ei = None
            plainlines = plain
            # find next fire after i to bound the buffer
            j = i + 1
            while j < len(plainlines):
                ok2, _ = ing.header_starts_act(plainlines, j)
                if ok2:
                    ei = j
                    break
                j += 1
            if ei is None:
                ei = len(plainlines)
            buf = [plainlines[k2][1] for k2 in range(i, ei)]
            full = "\n".join(buf).strip()
            reasons = []
            if len(full) < 60:
                reasons.append("text<60")
            hl = re.sub(r"\s+", " ", buf[0]).strip() if buf else ""
            if re.search(r"\b(?:Approved|Passed)\b", hl, re.I):
                reasons.append("approved_header")
            if not ing.has_enact_marker(full):
                reasons.append("no_enact_marker")
            ci = ing.parse_chapter_number(tok)
            if ci != n:
                reasons.append(f"numeral_parsed_as_{ci}")
            mode = "flush_dropped" if reasons else "other_fires_but_missing"
            return {"chapter": n, "mode": mode, "evidence": s[:120],
                    "page": pidx + 1, "line_pos": kpos, "reasons": reasons,
                    "token": tok}
    # none of the hits were header-like enough
    i, off, s = hits[0]
    return {"chapter": n, "mode": "header_re_no_match", "evidence": s[:160],
            "page": lines[i][0] + 1, "line_pos": lines[i][2]}


def main():
    args = sys.argv[1:]
    sample = 24
    if "--sample" in args:
        k = args.index("--sample")
        sample = int(args[k + 1])
        del args[k:k + 2]
    N = int(args[0])
    labels = args[1:]
    if not labels:
        raise SystemExit("usage: diag_chaptered_gap.py <N> <label> [label...] [--sample K]")

    # merge all volumes into one page-ordered stream
    all_lines = []
    for label in labels:
        all_lines.extend(load_lines(label))

    kept, fired_idx, fired_tok = production_kept_numbers(all_lines)
    kept_in_range = {c for c in kept if 1 <= c <= N}
    missing = [n for n in range(1, N + 1) if n not in kept_in_range]

    # sample missing chapters evenly across [1,N]
    if len(missing) > sample:
        step = len(missing) / sample
        sampled = [missing[int(i * step)] for i in range(sample)]
    else:
        sampled = missing

    classifications = [classify_missing(all_lines, n) for n in sampled]
    from collections import Counter
    mode_counts = Counter(c["mode"] for c in classifications)

    report = {
        "labels": labels,
        "oracle_N": N,
        "production_kept_in_range": len(kept_in_range),
        "production_missing": len(missing),
        "completeness_pct": round(100.0 * len(kept_in_range) / N, 1),
        "sample_size": len(sampled),
        "mode_counts": dict(mode_counts),
        "classifications": classifications,
    }
    out = ROOT / ("diag_chaptered_" + labels[0] + ".json")
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"labels": labels, "oracle_N": N,
                      "kept": len(kept_in_range), "missing": len(missing),
                      "completeness_pct": report["completeness_pct"],
                      "mode_counts": dict(mode_counts),
                      "out": str(out)}, indent=2))


if __name__ == "__main__":
    main()
