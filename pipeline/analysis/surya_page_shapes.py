"""
surya_page_shapes.py -- categorize EVERY page of a volume by its visual SHAPE using Surya's layout model.

Renders each source-PDF page (PyMuPDF) and runs Surya 0.13 LayoutPredictor, then assigns the page ONE
dominant shape (area-weighted top region label) plus a coarse class. This is the structural page-type map
(a real replacement for the ink-density page_classification.json) -- and unlike token heuristics it reads
page SHAPE, so it works on heavily-garbled scans.

Modes (run with the surya venv python):
  ... surya_page_shapes.py --labels                         # print Surya's shape vocabulary + check fitz
  ... surya_page_shapes.py <source.pdf> <out.tsv> [maxpages] [zoom] [batch]

Coarse class mapping (dominant Surya label -> class):
  Text/Title                              -> BODY
  TableOfContents                          -> INDEX_TOC
  Table/Form/ListItem                      -> TABLE_ROSTER
  SectionHeader/Caption                    -> DIVIDER_TITLE
  Picture/Figure                           -> PICTURE
  (none / empty)                           -> EMPTY
"""
import os, sys, time
from collections import Counter, defaultdict

COARSE = {
    "Text": "BODY", "Title": "BODY",
    "TableOfContents": "INDEX_TOC",
    "Table": "TABLE_ROSTER", "Form": "TABLE_ROSTER", "ListItem": "TABLE_ROSTER",
    "SectionHeader": "DIVIDER_TITLE", "Caption": "DIVIDER_TITLE",
    "Picture": "PICTURE", "Figure": "PICTURE",
    "PageHeader": "MARGIN", "PageFooter": "MARGIN", "Footnote": "MARGIN",
}

def _labels_mode():
    try:
        import fitz
        print("fitz (PyMuPDF):", fitz.__doc__.splitlines()[0] if fitz.__doc__ else "OK")
    except Exception as e:
        print("fitz IMPORT FAILED:", e)
    from surya.layout import LayoutPredictor
    p = LayoutPredictor()
    id2label = getattr(getattr(p, "model", None), "config", None)
    labels = getattr(id2label, "id2label", None) if id2label else None
    print("Surya layout label vocabulary:", labels)

def _dominant(layout_result):
    area = defaultdict(float)
    for b in layout_result.bboxes:
        x1, y1, x2, y2 = b.bbox
        area[b.label] += max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if not area:
        return "Empty", 0.0, {}
    total = sum(area.values()) or 1.0
    lab, a = max(area.items(), key=lambda kv: kv[1])
    dist = {k: round(v / total, 3) for k, v in sorted(area.items(), key=lambda kv: -kv[1])[:4]}
    return lab, round(a / total, 3), dist

def main():
    if sys.argv[1] == "--labels":
        _labels_mode(); return
    import fitz
    from PIL import Image
    from surya.layout import LayoutPredictor

    pdf   = sys.argv[1]
    out   = sys.argv[2]
    maxp  = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    zoom  = float(sys.argv[4]) if len(sys.argv) > 4 else 1.6
    batch = int(sys.argv[5]) if len(sys.argv) > 5 else 8

    predictor = LayoutPredictor()
    doc = fitz.open(pdf)
    npages = doc.page_count if maxp <= 0 else min(maxp, doc.page_count)
    print(f"{os.path.basename(pdf)}: {npages} pages, zoom={zoom}, batch={batch}", flush=True)
    t0 = time.time()
    rows = []; coarse_hist = Counter(); label_hist = Counter()
    mat = fitz.Matrix(zoom, zoom)
    i = 0
    while i < npages:
        imgs = []; idxs = []
        for j in range(i, min(i + batch, npages)):
            pix = doc[j].get_pixmap(matrix=mat)
            imgs.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
            idxs.append(j)
        results = predictor(imgs)
        for pidx, res in zip(idxs, results):
            lab, conf, dist = _dominant(res)
            cls = COARSE.get(lab, "OTHER")
            coarse_hist[cls] += 1; label_hist[lab] += 1
            rows.append((pidx, cls, lab, conf, dist))
        i += batch
        if i % 80 == 0 or i >= npages:
            el = time.time() - t0
            print(f"  {min(i,npages)}/{npages}  ({el:.0f}s, {min(i,npages)/max(el,1e-9):.1f} pg/s)", flush=True)

    with open(out, "w", encoding="utf-8") as f:
        f.write("pidx\tclass\tdominant_label\tconf\tdist\n")
        for pidx, cls, lab, conf, dist in rows:
            f.write(f"{pidx}\t{cls}\t{lab}\t{conf}\t{dist}\n")
    el = time.time() - t0
    print(f"\ndone {npages} pages in {el:.0f}s ({npages/max(el,1e-9):.1f} pg/s) -> {out}")
    print("coarse class histogram:", dict(coarse_hist.most_common()))
    print("dominant label histogram:", dict(label_hist.most_common()))

if __name__ == "__main__":
    main()
