"""Spot-check renderer for the transition-shortfall investigation (2026-06-22).
Renders a source PDF page (PyMuPDF, CPU) to PNG and dumps its extracted text layer so we can see
whether a 'missing' chapter header is actually PRINTED there. NO GPU OCR.

source_page in the parse is 1-indexed over the rendered page set, which == PDF page index+? We resolve
the offset empirically per dir by matching a KNOWN present chapter's source_page to the PDF page whose
text contains that 'CHAPTER <n>' header.

Usage:
  python _spot_render.py pageinfo <pdf>                      -> page count
  python _spot_render.py text <pdf> <pdf_page_1idx>          -> text-layer dump of that PDF page
  python _spot_render.py findoffset <pdf> <known_src_page> <known_chap>  -> locate matching PDF page
  python _spot_render.py render <pdf> <pdf_page_1idx> <out.png>
"""
import sys, re, fitz

def main():
    cmd = sys.argv[1]
    pdf = sys.argv[2]
    d = fitz.open(pdf)
    if cmd == "pageinfo":
        print("pages", d.page_count)
        return
    if cmd == "text":
        p = int(sys.argv[3]) - 1
        t = d[p].get_text()
        print(f"--- PDF page {p+1} (0idx {p}) textlen={len(t)} ---")
        print(t[:2500])
        return
    if cmd == "findoffset":
        known_src = int(sys.argv[3]); known_chap = int(sys.argv[4])
        pat = re.compile(r"CHAPTER\s+0*%d\b" % known_chap, re.IGNORECASE)
        hits = []
        for i in range(d.page_count):
            if pat.search(d[i].get_text()):
                hits.append(i + 1)  # 1-indexed PDF page
        print(f"known src_page={known_src} chap={known_chap}: matched PDF pages(1idx)={hits}")
        if hits:
            print(f"  candidate offset(s) pdf1idx - src = {[h - known_src for h in hits]}")
        return
    if cmd == "render":
        p = int(sys.argv[3]) - 1
        out = sys.argv[4]
        pix = d[p].get_pixmap(matrix=fitz.Matrix(2, 2))
        pix.save(out)
        print("wrote", out, pix.width, "x", pix.height)
        return

if __name__ == "__main__":
    main()
