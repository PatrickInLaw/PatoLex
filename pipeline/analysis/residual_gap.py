"""residual_gap.py -- characterize the chapters STILL missing after recovery: are they
scattered singletons (isolated detection misses) or long consecutive runs (a missing
page range / data gap)? Usage: python -m analysis.residual_gap --true N <label> ..."""
import sys, json
from pathlib import Path
import config
ROOT = Path(config.path_for("data_root"))

def main():
    args = sys.argv[1:]
    true_total = None
    if "--true" in args:
        k = args.index("--true"); true_total = int(args[k+1]); del args[k:k+2]
    present = set()
    for label in args:
        d = json.loads((ROOT / ("production-" + label) / "parsed_acts_recovered.json").read_text(encoding="utf-8"))
        for a in d["confident_acts"]:
            present.add(a["chapter_int"])
    miss = [n for n in range(1, true_total + 1) if n not in present]
    print("missing count:", len(miss))
    print("missing (first 60):", miss[:60])
    runs = []
    if miss:
        s = p = miss[0]
        for n in miss[1:]:
            if n == p + 1:
                p = n
            else:
                runs.append((s, p)); s = p = n
        runs.append((s, p))
    singles = sum(1 for a, b in runs if a == b)
    long = [r for r in runs if r[1] - r[0] >= 3]
    print(f"total runs: {len(runs)}  singletons: {singles}  runs of >=4 consecutive: {len(long)}")
    print("long runs (>=4 consec):", long[:25])

if __name__ == "__main__":
    main()
