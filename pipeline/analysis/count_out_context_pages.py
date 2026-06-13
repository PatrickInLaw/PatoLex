"""Sum page counts across the 205 processed cascade volumes (out_context/*.json page keys) = the render
denominator for the page-shape job. Run:  python count_out_context_pages.py <out_context_dir>"""
import sys, os, glob, json
from collections import Counter
d = sys.argv[1]
files = sorted(glob.glob(os.path.join(d, "*.json")))
total = 0; dec = Counter()
for fp in files:
    try:
        pages = len(json.load(open(fp, encoding="utf-8", errors="replace")))
    except Exception as e:
        print("ERR", os.path.basename(fp), e); continue
    total += pages
    yr = os.path.basename(fp)[len("production-"):][:4] if os.path.basename(fp).startswith("production-") else "????"
    dec[(yr[:3] + "0s") if yr.isdigit() else "????"] += pages
print(f"VOLUMES: {len(files)}   TOTAL PAGES (cascade content pages): {total:,}")
for k in sorted(dec):
    print(f"  {k}: {dec[k]:,}")
