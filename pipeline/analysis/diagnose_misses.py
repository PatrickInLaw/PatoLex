"""diagnose_misses.py -- WHY does the act parser miss ~18% of chapters in noisy OCR?

Read-only diagnostic. Does NOT touch the DB and does NOT modify any parsed file.
For each calibration volume it:
  1. loads the existing parsed_acts_fixed.json (confident + flagged) -> the chapters the
     CURRENT parser found, with their source_page.
  2. re-walks the raw OCR (ocr_consensus/page_ocr_results.json) line by line and counts,
     at each gate of the real parser, how many candidate chapter headers survive:
        G0  lines matching HEADER_RE                       (header regex hit)
        G1  ... AND "An Act" within next 4 lines           (header_starts_act == True)
        G2  ... AND enact-marker present in the act buffer  (flush_act keeps it)
        G3  ... AND is_confident_act  (An Act + date + len) (lands in confident_acts)
  3. characterizes the misses against the expected 1..TRUE sequence:
        (a) header-not-matched   : a "CHAPTER"-ish line the regex missed
        (b) merged               : a gap where two consecutive found chapters skip >1
        (c) misread-number       : header found but chapter_int wrong/0
        (d) split/garbled header : "An Act" present but no nearby header line

Usage (env already set by caller):
  python -m analysis.diagnose_misses 1957-vol1-57chapters 1957-vol2-57chapters --true 2424
  python -m analysis.diagnose_misses <label> [<label> ...] [--true N]
"""
import sys, os, re, json
from pathlib import Path

import config
import importlib.util

# import the real parser module so we test the EXACT regexes/gates in production
_ING = Path(__file__).resolve().parent.parent / "ingest" / "ingest_from_ocr.py"
_spec = importlib.util.spec_from_file_location("ingest_from_ocr", str(_ING))
ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ing)

ROOT = Path(config.path_for("data_root"))

# A looser "this line mentions a chapter heading" probe used ONLY for diagnosis,
# to find headers the production HEADER_RE missed. Intentionally permissive.
LOOSE_CHAP = re.compile(r"^[^A-Za-z0-9]{0,4}(c[hnu].{0,6}?|chap\w*)\b", re.I)
ANY_AN_ACT = ing.AN_ACT_RE


def load_lines(label):
    ocr_path = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(ocr_path.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    lines = []
    for pidx in sorted(pages.keys()):
        for line in pages[pidx].get("consensus_text", "").split("\n"):
            lines.append((pidx, line))
    return lines, pages


def gate_counts(label):
    lines, pages = load_lines(label)
    volume_year = int(re.match(r"(\d{4})", label).group(1))
    g0 = g1 = g2 = 0
    g0_lines = []        # (pidx, line, token) for HEADER_RE hits
    an_act_no_header = 0 # "An Act" lines with no HEADER_RE within prior 3 lines
    for i, (pidx, line) in enumerate(lines):
        ln = line.strip()
        m = ing.HEADER_RE.match(ln)
        if m:
            g0 += 1
            is_hdr, token = ing.header_starts_act(lines, i)
            if is_hdr:
                g1 += 1
                g0_lines.append((pidx, ln, token, True))
            else:
                g0_lines.append((pidx, ln, m.group(1), False))
    # count "An Act" lines that have NO header regex hit in the 3 preceding lines
    for i, (pidx, line) in enumerate(lines):
        if ANY_AN_ACT.search(line):
            had_hdr = False
            for j in range(max(0, i - 3), i):
                if ing.HEADER_RE.match(lines[j][1].strip()):
                    had_hdr = True
                    break
            if not had_hdr:
                an_act_no_header += 1
    return {
        "label": label, "volume_year": volume_year,
        "n_lines": len(lines), "n_pages": len(pages),
        "G0_header_regex_hits": g0,
        "G1_header_plus_anact": g1,
        "an_act_no_header_nearby": an_act_no_header,
        "header_hits": g0_lines,
    }


def found_chapters(label):
    p = ROOT / ("production-" + label) / "parsed_acts_fixed.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    conf = d.get("confident_acts", [])
    flag = d.get("flagged_acts", [])
    return conf, flag


def main():
    args = [a for a in sys.argv[1:]]
    true_total = None
    if "--true" in args:
        k = args.index("--true")
        true_total = int(args[k + 1])
        del args[k:k + 2]
    labels = args

    all_conf, all_flag = [], []
    print("=" * 78)
    for label in labels:
        gc = gate_counts(label)
        conf, flag = found_chapters(label)
        all_conf += conf
        all_flag += flag
        conf_chaps = sorted(a["chapter_int"] for a in conf if a.get("chapter_int", 0) > 0)
        zero_conf = sum(1 for a in conf if a.get("chapter_int", 0) == 0)
        flag_chaps = sorted(a["chapter_int"] for a in flag if a.get("chapter_int", 0) > 0)
        print(f"\nVOLUME {label}  (year {gc['volume_year']})")
        print(f"  pages={gc['n_pages']}  lines={gc['n_lines']}")
        print(f"  GATE G0 HEADER_RE line hits ............ {gc['G0_header_regex_hits']}")
        print(f"  GATE G1 + 'An Act' in next 4 (=header_starts_act) {gc['G1_header_plus_anact']}")
        print(f"  'An Act' lines with NO header within prior 3 lines {gc['an_act_no_header_nearby']}")
        print(f"  CONFIDENT acts (in parsed file) ........ {len(conf)}  (chap_int>0: {len(conf_chaps)}, chap_int==0: {zero_conf})")
        print(f"  FLAGGED acts (in parsed file) .......... {len(flag)}  (chap_int>0: {len(flag_chaps)})")
        if conf_chaps:
            print(f"  confident chapter range: {conf_chaps[0]}..{conf_chaps[-1]}  distinct={len(set(conf_chaps))}")

    # Combine confident chapters across the listed volumes (a session)
    conf_all = sorted(set(a["chapter_int"] for a in all_conf if a.get("chapter_int", 0) > 0))
    flag_all = sorted(set(a["chapter_int"] for a in all_flag if a.get("chapter_int", 0) > 0))
    print("\n" + "=" * 78)
    print("SESSION-LEVEL (confident across all listed volumes)")
    if conf_all:
        cmax = conf_all[-1]
        present = set(conf_all)
        target = true_total or cmax
        missing = [n for n in range(1, target + 1) if n not in present]
        print(f"  distinct confident chapters = {len(conf_all)}  min={conf_all[0]} max={cmax}")
        print(f"  target (true total) = {target}")
        print(f"  MISSING from 1..{target}: {len(missing)}")
        # how many of the missing are recoverable from FLAGGED acts (present but not confident)?
        flag_set = set(flag_all)
        miss_in_flag = [n for n in missing if n in flag_set]
        print(f"    of those, present in FLAGGED (parser saw header, low conf) = {len(miss_in_flag)}")
        print(f"    truly absent (not confident, not flagged) = {len(missing) - len(miss_in_flag)}")
        # gap-run analysis -> merged-act candidates (consecutive found chapters skipping >1)
        gaps = []
        for a, b in zip(conf_all, conf_all[1:]):
            if b - a > 1:
                gaps.append((a, b, b - a - 1))
        big = [g for g in gaps if g[2] >= 1]
        print(f"  internal gaps (consecutive confident chapters skipping >=1): {len(big)} runs, {sum(g[2] for g in big)} missing nums")
        sample = big[:15]
        for a, b, n in sample:
            print(f"    gap {a} -> {b}  ({n} missing)")


if __name__ == "__main__":
    main()
