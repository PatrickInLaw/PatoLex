"""Dump context around given (label, chapter) header occurrences. READ-ONLY."""
import sys, re, json
from pathlib import Path
import config
ROOT = Path(config.path_for("data_root"))
ANY = re.compile(r"\bCHAP(?:TER|T\.?|\.)?\s*([0-9]{1,4})\b", re.I)

def load_lines(label):
    p = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    lines = []
    for pidx in sorted(pages.keys()):
        for k, line in enumerate(pages[pidx].get("consensus_text", "").split("\n")):
            lines.append((pidx, line, k))
    return lines

def main():
    label = sys.argv[1]
    targets = [int(x) for x in sys.argv[2:]]
    lines = load_lines(label)
    for n in targets:
        # find page-top-ish header occurrence
        hit = None
        for i, (p, t, k) in enumerate(lines):
            m = re.match(r"^\s*[^A-Za-z0-9]{0,4}CHAP(?:TER|T\.?|\.)?\s*"+str(n)+r"\b", t, re.I)
            if m:
                hit = i; break
        print("==== CH", n, "====")
        if hit is None:
            print("  (no page-top header found)")
            continue
        lo, hi = max(0, hit-2), min(len(lines), hit+10)
        for j in range(lo, hi):
            p, t, k = lines[j]
            mark = ">>" if j == hit else "  "
            print(f"{mark} p{p+1} l{k:>3}: {t}")

if __name__ == "__main__":
    main()
