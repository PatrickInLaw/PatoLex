"""Reusable: render a PDF page range to PNGs for inspection (PyMuPDF; pdftoppm is absent).
Usage: python _render_pdf.py <pdf_path> <first> <last> <out_dir> [dpi]"""
import fitz, os, sys
pdf, first, last, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
dpi = int(sys.argv[5]) if len(sys.argv) > 5 else 160
os.makedirs(out, exist_ok=True)
doc = fitz.open(pdf)
n = doc.page_count
print(f"{os.path.basename(pdf)}: {n} pages")
stem = os.path.splitext(os.path.basename(pdf))[0]
for i in range(max(0, first-1), min(n, last)):
    doc[i].get_pixmap(dpi=dpi).save(os.path.join(out, f"{stem}_p{i+1}.png"))
print(f"rendered pages {first}..{min(n,last)} -> {out}")
