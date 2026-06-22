"""Render a source PDF page (PyMuPDF CPU) and run a LIGHT Tesseract read to confirm whether a
'missing' chapter header is printed on it. NO GPU. Calls the tesseract binary directly.

source_page p (parse) -> PDF page: the parse renders 1 image per PDF page, 1-indexed == PDF 1-indexed
(offset auto-checked by also reading neighbor present chapters). We just render the candidate PDF pages.

Usage: python _spot_ocr.py <pdf> <pdf_page_1idx> [<pdf_page_1idx> ...]
Prints, per page, the first ~600 chars of Tesseract text and every 'CHAPTER <n>' it finds.
"""
import sys, re, subprocess, tempfile, os, fitz

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def ocr_page(d, p1):
    page = d[p1 - 1]
    pix = page.get_pixmap(matrix=fitz.Matrix(2.2, 2.2))
    tmp = os.path.join(tempfile.gettempdir(), f"_spot_{p1}.png")
    pix.save(tmp)
    base = tmp[:-4]
    subprocess.run([TESS, tmp, base, "--psm", "6"], capture_output=True)
    txt = ""
    if os.path.exists(base + ".txt"):
        txt = open(base + ".txt", encoding="utf-8", errors="ignore").read()
    return txt

def main():
    pdf = sys.argv[1]
    pages = [int(x) for x in sys.argv[2:]]
    d = fitz.open(pdf)
    for p1 in pages:
        txt = ocr_page(d, p1)
        chaps = re.findall(r"CHAP(?:TER|\.)\s*[.,]?\s*0*(\d+)", txt, re.IGNORECASE)
        print(f"=== PDF page {p1} === CHAPTER tokens found: {chaps}")
        print(txt[:600].replace("\n", " | "))
        print()

if __name__ == "__main__":
    main()
