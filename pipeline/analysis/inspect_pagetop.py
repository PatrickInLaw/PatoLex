"""inspect_pagetop.py -- for 'An Act' starts at the TOP of a page with no header in
prior 3 lines, dump the tail of the PREVIOUS page + the page-top lines, to see whether
the CHAPTER header is (a) at the bottom of the prior page, (b) OCR-garbled on this page,
or (c) genuinely absent. Read-only.

Usage: python -m analysis.inspect_pagetop <label> [--n 15]
"""
import sys, re, json
from pathlib import Path
import importlib.util
import config

_ING = Path(__file__).resolve().parent.parent / "ingest" / "ingest_from_ocr.py"
_spec = importlib.util.spec_from_file_location("ingest_from_ocr", str(_ING))
ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ing)
ROOT = Path(config.path_for("data_root"))


def main():
    label = sys.argv[1]
    n = int(sys.argv[sys.argv.index("--n")+1]) if "--n" in sys.argv else 15
    ocr_path = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(ocr_path.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    page_texts = {p: pages[p].get("consensus_text", "").split("\n") for p in pages}
    lines = []
    for pidx in sorted(pages.keys()):
        for k, line in enumerate(page_texts[pidx]):
            lines.append((pidx, line, k))
    shown = 0
    for i, (pidx, line, kpos) in enumerate(lines):
        if not ing.AN_ACT_RE.search(line):
            continue
        if kpos > 2:
            continue
        if any(ing.HEADER_RE.match(lines[j][1].strip()) for j in range(max(0, i-3), i)):
            continue
        shown += 1
        if shown > n:
            break
        print(f"\n========= page {pidx+1}, An Act at linepos {kpos} =========")
        prev = page_texts.get(pidx-1)
        if prev:
            print("  --- tail of prev page", pidx, "---")
            for s in prev[-5:]:
                print(f"      {repr(s.strip()[:80])}")
        print("  --- top of page", pidx+1, "---")
        for s in page_texts[pidx][:5]:
            print(f"      {repr(s.strip()[:80])}")


if __name__ == "__main__":
    main()
