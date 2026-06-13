"""Sum page counts over a directory of source PDFs (for render/throughput estimates).
Run:  python count_corpus_pages.py <pdf_dir>"""
import sys, os, glob, fitz
from collections import Counter
d = sys.argv[1]
pdfs = sorted(glob.glob(os.path.join(d, "*.pdf")) + glob.glob(os.path.join(d, "*.PDF")))
total = 0; dec = Counter()
for p in pdfs:
    try:
        n = fitz.open(p).page_count
    except Exception as e:
        print("ERR", os.path.basename(p), e); continue
    total += n
    name = os.path.basename(p)
    yr = name[:4]
    decade = (yr[:3] + "0s") if yr.isdigit() else "????"
    dec[decade] += n
print(f"PDFs: {len(pdfs)}   TOTAL PAGES: {total:,}")
for k in sorted(dec):
    print(f"  {k}: {dec[k]:,}")
