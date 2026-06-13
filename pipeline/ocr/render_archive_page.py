"""Render one page of an archive source PDF to PNG (for visual inspection of OCR-garbled pages).
Usage: python render_archive_page.py <pdf> <0-based-page-idx> <out.png> [zoom]"""
import sys, fitz
pdf, idx, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
zoom = float(sys.argv[4]) if len(sys.argv) > 4 else 2.2
doc = fitz.open(pdf)
pix = doc[idx].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
pix.save(out)
print(f"rendered {pdf} page idx {idx} (of {doc.page_count}) -> {out} {pix.width}x{pix.height}")
