"""vol_ranges.py -- show the chapter-number range each physical volume actually covers
(from baseline confident acts), so session-level renumbering knows the volume boundaries.
Usage: python -m analysis.vol_ranges <label> [<label> ...]"""
import sys, json
from pathlib import Path
import config
ROOT = Path(config.path_for("data_root"))

def main():
    for label in sys.argv[1:]:
        p = ROOT / ("production-" + label) / "parsed_acts_fixed.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        ch = sorted(a["chapter_int"] for a in d["confident_acts"]
                    if 1 <= a.get("chapter_int", 0) <= 2300)
        # show 10th and 90th percentile to ignore outliers
        if not ch:
            print(label, "no chapters"); continue
        lo = ch[len(ch)//20]; hi = ch[-len(ch)//20 - 1]
        print(f"{label}: n={len(ch)} min={ch[0]} p5={lo} p95={hi} max={ch[-1]}")

if __name__ == "__main__":
    main()
