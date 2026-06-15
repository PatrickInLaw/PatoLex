"""inspect_missing.py -- show the raw OCR text around 'An Act' starts whose CHAPTER
header the production HEADER_RE did NOT match, plus the headers it DID match that look
garbled. Read-only; for eyeballing what the missed headers actually look like.

Usage: python -m analysis.inspect_missing <label> [--n 25]
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
    n = 25
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    ocr_path = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(ocr_path.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    lines = []
    for pidx in sorted(pages.keys()):
        for line in pages[pidx].get("consensus_text", "").split("\n"):
            lines.append((pidx, line))

    shown = 0
    print(f"=== '{label}': 'An Act' lines whose header was NOT matched by HEADER_RE (prev 3 lines) ===")
    for i, (pidx, line) in enumerate(lines):
        if ing.AN_ACT_RE.search(line):
            # was a header matched in prev 3?
            had = any(ing.HEADER_RE.match(lines[j][1].strip()) for j in range(max(0, i-3), i))
            if had:
                continue
            shown += 1
            if shown > n:
                break
            print(f"\n--- page {pidx+1}  (line idx {i}) ---")
            for j in range(max(0, i-4), min(len(lines), i+2)):
                mark = ">>" if j == i else "  "
                print(f"  {mark} [{lines[j][0]+1}] {repr(lines[j][1].strip()[:90])}")


if __name__ == "__main__":
    main()
