"""inspect_nochap.py -- for 'An Act' starts with no CHAPTER header in prior 3 lines,
look FURTHER UP (prior 8 lines) for a chapter header, and report position-on-page,
to separate real act-starts (header just out of the 3-line window, or page-top) from
mid-body title references (no header, deep inside a page).

Usage: python -m analysis.inspect_nochap <label> [<label> ...]
"""
import sys, re, json
from collections import Counter
from pathlib import Path
import importlib.util
import config

_ING = Path(__file__).resolve().parent.parent / "ingest" / "ingest_from_ocr.py"
_spec = importlib.util.spec_from_file_location("ingest_from_ocr", str(_ING))
ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ing)
ROOT = Path(config.path_for("data_root"))

# loose chapter header probe for "is there a header further up"
CHAPHEADER = re.compile(r"^[^A-Za-z0-9]{0,6}(c[hilou][\w]{0,2}p|cilap|ohap|ghap)\w{0,4}\.?\s*[ivxlcdm0-9]", re.I)
ENACT = ing.ENACT_MARKER_RE


def main():
    labels = sys.argv[1:]
    cnt = Counter()
    deep_examples = []
    for label in labels:
        ocr_path = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
        raw = json.loads(ocr_path.read_text(encoding="utf-8"))
        pages = {int(k): v for k, v in raw.items()}
        # build line list, recording per-page line index
        lines = []
        page_line_no = {}
        per_page_count = Counter()
        for pidx in sorted(pages.keys()):
            txt = pages[pidx].get("consensus_text", "").split("\n")
            for k, line in enumerate(txt):
                lines.append((pidx, line, k, len(txt)))
        for i, (pidx, line, kpos, plen) in enumerate(lines):
            if not ing.AN_ACT_RE.search(line):
                continue
            if any(ing.HEADER_RE.match(lines[j][1].strip()) for j in range(max(0, i-3), i)):
                continue
            # look up to 8 lines above for a loose chapter header
            hdr_within_8 = None
            for j in range(i-1, max(-1, i-9), -1):
                if CHAPHEADER.match(lines[j][1].strip()):
                    hdr_within_8 = j
                    break
            # does an enact marker appear within next 8 lines? (signal: real act)
            has_enact = any(ENACT.search(lines[j][1]) for j in range(i, min(len(lines), i+8)))
            top_of_page = kpos <= 2
            if hdr_within_8 is not None:
                cnt["header_4to8_above"] += 1
            elif top_of_page:
                cnt["page_top_no_header"] += 1
            elif has_enact:
                cnt["midpage_but_has_enact"] += 1
            else:
                cnt["midpage_no_enact_likely_bodyref"] += 1
                if len(deep_examples) < 15:
                    deep_examples.append((pidx+1, kpos, line.strip()[:70]))
    print("An-Act-no-header-in-3 breakdown (extended look):")
    for k, v in cnt.most_common():
        print(f"  {k:<34} {v}")
    print("\n  likely-body-ref examples (midpage, no enact marker nearby):")
    for pg, kpos, txt in deep_examples:
        print(f"    p{pg} linepos={kpos}: {repr(txt)}")


if __name__ == "__main__":
    main()
