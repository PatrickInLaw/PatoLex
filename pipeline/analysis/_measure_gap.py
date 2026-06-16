"""_measure_gap.py -- scratch measurement: chaptered-era confident vs flagged, and the
misnumbered-but-present picture (raw chapter_int out-of-range / duplicate among ALL acts).
Read-only. Not committed (scratch)."""
import json, glob, os, re
from collections import defaultdict

ROOT = r"C:\Users\patolex\PatoLex-scratch"

def main():
    conf = flagged = tot = 0
    # raw-number view: among ALL acts (conf+flagged), how many carry an out-of-range or
    # duplicate raw chapter_int -- the "misnumbered-but-present" the brief describes.
    raw_oor = raw_dup = 0
    for d in sorted(glob.glob(os.path.join(ROOT, "production-*"))):
        fp = os.path.join(d, "parsed_acts_recovered.json")
        if not os.path.exists(fp):
            continue
        lbl = os.path.basename(d)[len("production-"):]
        m = re.match(r"(\d{4})", lbl)
        yr = int(m.group(1)) if m else 0
        if not (1880 <= yr <= 1999):
            continue
        data = json.load(open(fp, encoding="utf-8"))
        c = data.get("confident_acts", [])
        f = data.get("flagged_acts", [])
        conf += len(c); flagged += len(f); tot += len(c) + len(f)
    print("chaptered conf=%d flagged=%d total=%d" % (conf, flagged, tot))

if __name__ == "__main__":
    main()
