"""
surya_page_shapes.py -- categorize EVERY page of the corpus by visual SHAPE with Surya's layout model,
PERSISTING every rendered page image (so we never lose the renders again), multi-threaded, and shardable
across processes/boxes (5080 + 5090).

Pipeline per volume: R render threads (PyMuPDF, thread-local doc handles) render each page, SAVE the PNG to
the render-root (resumable -- skip if it already exists), and feed a bounded queue; the main thread batches
images through Surya LayoutPredictor (GPU) and assigns each page ONE dominant shape + a coarse class. Because
it reads page SHAPE (not OCR tokens) it works on heavily-garbled scans.

Cross-box / multi-track: run the SAME command on each box/process with a distinct --shard i --nshards N.
Sharding is at the VOLUME level (each worker owns whole PDFs -> clean render output, no mid-PDF coordination).

Modes (run with the surya venv python; cwd anywhere):
  --labels                                   # print Surya shape vocabulary + check fitz, exit
  <pdf-or-dir> --out-dir D --render-root R    # classify; per-volume TSV in D, PNGs in R/<vol>/<pidx>.png
    [--shard i --nshards N] [--render-threads 6] [--batch 8] [--zoom 1.6] [--maxpages 0] [--reuse]
    [--bench]                                # measure peak VRAM (torch) + RAM + pg/s on the slice, then exit

Example (two boxes, 2 shards):
  5090:  ... surya_page_shapes.py <archive_dir> --out-dir <shapes> --render-root <renders> --shard 0 --nshards 2 --render-threads 8
  5080:  ... surya_page_shapes.py <archive_dir> --out-dir <shapes> --render-root <renders> --shard 1 --nshards 2 --render-threads 4
"""
import argparse, os, sys, time, glob, threading, queue
from collections import Counter, defaultdict

COARSE = {
    "Text": "BODY", "Title": "BODY", "TextInlineMath": "BODY",
    "TableOfContents": "INDEX_TOC",
    "Table": "TABLE_ROSTER", "Form": "TABLE_ROSTER", "ListItem": "TABLE_ROSTER",
    "SectionHeader": "DIVIDER_TITLE", "Caption": "DIVIDER_TITLE",
    "Picture": "PICTURE", "Figure": "PICTURE",
    "PageHeader": "MARGIN", "PageFooter": "MARGIN", "Footnote": "MARGIN", "Formula": "MARGIN",
}

_tl = threading.local()
def _doc(pdf):
    import fitz
    if getattr(_tl, "pdf", None) != pdf:
        _tl.doc = fitz.open(pdf); _tl.pdf = pdf
    return _tl.doc

def _vol_id(pdf):
    return os.path.splitext(os.path.basename(pdf))[0]

def _render(pdf, pidx, render_dir, zoom, reuse):
    """render+persist one page; return (pidx, PIL.Image). reuse: load existing PNG instead of re-rendering."""
    import fitz
    from PIL import Image
    png = os.path.join(render_dir, f"{pidx:04d}.png")
    if reuse and os.path.exists(png):
        return pidx, Image.open(png).convert("RGB")
    pix = _doc(pdf)[pidx].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    os.makedirs(render_dir, exist_ok=True)
    pix.save(png)                                   # PERSIST the render (durable, not lost this time)
    return pidx, Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

def _dominant(res):
    area = defaultdict(float)
    for b in res.bboxes:
        x1, y1, x2, y2 = b.bbox
        area[b.label] += max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if not area:
        return "Empty", 0.0
    total = sum(area.values()) or 1.0
    lab, a = max(area.items(), key=lambda kv: kv[1])
    return lab, round(a / total, 3)

def _classify_volume(pdf, out_dir, render_root, predictor, a):
    vol = _vol_id(pdf)
    render_dir = os.path.join(render_root, vol)
    import fitz
    doc = fitz.open(pdf)
    npages = doc.page_count if a.maxpages <= 0 else min(a.maxpages, doc.page_count)
    doc.close()

    idxq = queue.Queue()
    for j in range(npages):
        idxq.put(j)
    resq = queue.Queue(maxsize=a.batch * 3)          # bound RAM: producers block when consumer is behind
    SENT = object()

    def worker():
        while True:
            try:
                j = idxq.get_nowait()
            except queue.Empty:
                break
            try:
                resq.put(_render(pdf, j, render_dir, a.zoom, a.reuse))
            except Exception as e:
                resq.put((j, e))
        resq.put(SENT)

    nthreads = max(1, a.render_threads)
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(nthreads)]
    for t in threads:
        t.start()

    rows = []; coarse = Counter(); labels = Counter(); errs = 0
    done = 0; finished = 0; buf = []
    t0 = time.time()

    def flush():
        nonlocal buf
        if not buf:
            return
        imgs = [im for _, im in buf]
        results = predictor(imgs)
        for (pidx, _), res in zip(buf, results):
            lab, conf = _dominant(res)
            cls = COARSE.get(lab, "OTHER")
            coarse[cls] += 1; labels[lab] += 1
            rows.append((pidx, cls, lab, conf))
        buf = []

    while finished < nthreads:
        item = resq.get()
        if item is SENT:
            finished += 1; continue
        pidx, payload = item
        if isinstance(payload, Exception):
            errs += 1; continue
        buf.append((pidx, payload)); done += 1
        if len(buf) >= a.batch:
            flush()
        if done % 200 == 0:
            el = time.time() - t0
            print(f"  [{vol}] {done}/{npages}  ({el:.0f}s, {done/max(el,1e-9):.1f} pg/s)", flush=True)
    flush()

    rows.sort()
    os.makedirs(out_dir, exist_ok=True)
    out_tsv = os.path.join(out_dir, f"{vol}.shapes.tsv")
    with open(out_tsv, "w", encoding="utf-8") as f:
        f.write("pidx\tclass\tdominant_label\tconf\n")
        for pidx, cls, lab, conf in rows:
            f.write(f"{pidx}\t{cls}\t{lab}\t{conf}\n")
    el = time.time() - t0
    print(f"[{vol}] {npages} pages in {el:.0f}s ({npages/max(el,1e-9):.1f} pg/s), errs={errs} -> {out_tsv}")
    print(f"[{vol}] coarse:", dict(coarse.most_common()), " labels:", dict(labels.most_common()))
    return npages, el, coarse

def _labels_mode():
    try:
        import fitz
        print("fitz (PyMuPDF):", (fitz.__doc__ or "OK").splitlines()[0])
    except Exception as e:
        print("fitz IMPORT FAILED:", e)
    from surya.layout import LayoutPredictor
    LayoutPredictor()
    print("Surya layout loaded. Empirical label set (from predictions): "
          "Text, Title, SectionHeader, TableOfContents, Table, ListItem, Form, Picture, Caption, "
          "PageHeader, PageFooter, Footnote, Formula, TextInlineMath")

def main():
    if "--labels" in sys.argv:
        _labels_mode(); return
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="a source PDF or a directory of PDFs")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--render-root", required=True)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--render-threads", type=int, default=6)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--zoom", type=float, default=1.6)
    ap.add_argument("--maxpages", type=int, default=0)
    ap.add_argument("--reuse", action="store_true", help="load existing PNG instead of re-rendering")
    ap.add_argument("--bench", action="store_true", help="measure VRAM/RAM/throughput on the slice, then report")
    ap.add_argument("--vram-frac", type=float, default=0.22,
                    help="HARD cap: max fraction of total GPU memory this process may allocate (torch caching "
                         "allocator). A track that exceeds it OOMs ITSELF (catchable) instead of spiking the "
                         "whole GPU. Stacking rule: (#tracks_on_this_gpu) * vram-frac must stay <= ~0.80.")
    a = ap.parse_args()

    if os.path.isdir(a.input):
        pdfs = sorted(glob.glob(os.path.join(a.input, "*.pdf")) + glob.glob(os.path.join(a.input, "*.PDF")))
    else:
        pdfs = [a.input]
    mine = [p for i, p in enumerate(pdfs) if i % a.nshards == a.shard]
    print(f"shard {a.shard}/{a.nshards}: {len(mine)} of {len(pdfs)} volumes "
          f"(render-threads={a.render_threads}, batch={a.batch}, zoom={a.zoom})", flush=True)

    import torch
    torch.backends.cudnn.benchmark = False   # avoid the large transient cuDNN-workspace VRAM spike when
                                             # stacking multiple tracks on one GPU (keeps footprint ~steady)
    if a.vram_frac and a.vram_frac > 0 and torch.cuda.is_available():
        torch.cuda.set_per_process_memory_fraction(a.vram_frac, 0)   # HARD ceiling -- OOM self, never the GPU
        total_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"VRAM HARD CAP: {a.vram_frac:.2f} of {total_gb:.1f}GB = {a.vram_frac*total_gb:.1f}GB max for this "
              f"track (plus ~1-2GB CUDA context). Keep #tracks*frac <= ~0.80.", flush=True)
    from surya.layout import LayoutPredictor
    try:
        import psutil; proc = psutil.Process()
    except Exception:
        proc = None

    predictor = LayoutPredictor()
    torch.cuda.reset_peak_memory_stats()
    ram_peak = [0]
    stop = threading.Event()
    def ram_sampler():
        while not stop.is_set():
            if proc:
                ram_peak[0] = max(ram_peak[0], proc.memory_info().rss)
            time.sleep(0.5)
    st = threading.Thread(target=ram_sampler, daemon=True); st.start()

    tot_pages = 0; tot_time = 0.0; agg = Counter()
    T0 = time.time()
    for pdf in mine:
        np_, el, coarse = _classify_volume(pdf, a.out_dir, a.render_root, predictor, a)
        tot_pages += np_; tot_time += el; agg.update(coarse)
        if a.bench:
            break
    wall = time.time() - T0
    stop.set()

    vram_alloc = torch.cuda.max_memory_allocated() / 1e9
    vram_resv  = torch.cuda.max_memory_reserved() / 1e9
    print("\n==== RESOURCE / THROUGHPUT ====")
    print(f"pages: {tot_pages}  wall: {wall:.0f}s  throughput: {tot_pages/max(wall,1e-9):.1f} pg/s")
    print(f"VRAM peak: allocated {vram_alloc:.2f} GB / reserved {vram_resv:.2f} GB")
    print(f"RAM  peak (this proc RSS): {ram_peak[0]/1e9:.2f} GB" if proc else "RAM peak: psutil N/A (sample externally)")
    print("aggregate coarse classes:", dict(agg.most_common()))

if __name__ == "__main__":
    main()
