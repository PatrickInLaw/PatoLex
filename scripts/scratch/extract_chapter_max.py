"""Download SoS 'Chapters by number' PDFs (2009-2024) and report the highest chapter number per year.

The PDFs list chaptered bills; each row begins with the chapter number. We extract all
integers that appear as leading 'Chapter N' / 'N AB ...' tokens and take the max per year.
Output: TSV rows to stdout-equivalent file.
"""
import io
import re
import sys
import urllib.request

try:
    import fitz  # PyMuPDF
except Exception as e:  # pragma: no cover
    print("NO_PYMUPDF", e)
    sys.exit(2)

YEARS = list(range(2009, 2025))
URL = "https://admin.cdn.sos.ca.gov/bill-chapters/{y}/chapter-number.pdf"
OUT = r"C:/Users/PatrickKolasinski/Documents/GitHub/PatoLex/scripts/scratch/chapter_max_2009_2024.tsv"

rows = []
for y in YEARS:
    url = URL.format(y=y)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=60).read()
    except Exception as e:
        rows.append((y, None, url, f"download_fail:{e}"))
        continue
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
    except Exception as e:
        rows.append((y, None, url, f"parse_fail:{e}"))
        continue
    # Chapter rows typically look like: "Chapter 1" then bill, or a line "1  AB 123".
    # Strategy: find numbers that are followed (same or next token) by a bill id AB/SB/ACA/SCA.
    nums = []
    # Pattern A: "Chapter\s+N"
    for m in re.finditer(r"Chapter\s+(\d{1,4})", text):
        nums.append(int(m.group(1)))
    # Pattern B: line-leading "N  AB/SB ..." (chapter-number column tables)
    for m in re.finditer(r"(?m)^\s*(\d{1,4})\s+(?:AB|SB|ACA|SCA|ACR|SCR)\b", text):
        nums.append(int(m.group(1)))
    if not nums:
        # fallback: any standalone 1-4 digit number near a bill id within 12 chars
        for m in re.finditer(r"(\d{1,4})\D{0,12}(?:AB|SB)\s*\d", text):
            nums.append(int(m.group(1)))
    if nums:
        rows.append((y, max(nums), url, f"high(n={len(nums)})"))
    else:
        rows.append((y, None, url, "no_numbers_found"))

with open(OUT, "w", encoding="utf-8") as f:
    for y, mx, url, note in rows:
        f.write(f"{y}\t{mx if mx is not None else ''}\t{url}\t{note}\n")

# Also write a human-readable copy
print("DONE -> " + OUT)
for r in rows:
    print(r)
