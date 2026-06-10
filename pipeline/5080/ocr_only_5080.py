"""
ocr_only_5080.py -- OCR-only stage for the RTX 5080 (no DB).
==============================================================
Twin of ocr_only_5090.py, but with the PINNED + OFFLINE docTR load that the
5080 requires (bare ocr_predictor(pretrained=True) hangs on the 5080; the
pinned fast_base+crnn_vgg16_bn load with orientation classifiers disabled and
HF offline env set BEFORE any torch/doctr import loads straight from local
~/.cache/doctr -- proven by doctr_warmup_5080.py).

Runs stages 0-4 (SHA256, render, v2-grayscale preprocess, body classification,
3-engine Surya+docTR+Tesseract consensus) and writes, under 5080-local paths:

    production-<label>/sha256.txt
    production-<label>/page_classification.json
    production-<label>/ocr_consensus/page_ocr_results.json

NO database access. The queue_worker_5080.py wrapper pushes these three
outputs + an OCR_COMPLETE.marker back to the 5090, where the existing
ingest_watcher.py loop picks them up unchanged (identical producer contract).

Idempotent + resumable: render/preprocess skip existing PNGs; OCR resumes from
the checkpointed page_ocr_results.json. Same per-page GPU hygiene as the fix.

Usage:
    python ocr_only_5080.py <volume_pdf_path> <session_label>
"""

import sys
import os

# ---------------------------------------------------------------------------
# docTR OFFLINE LOAD FIX -- must run BEFORE any torch/doctr/huggingface import.
# (Identical to production_pipeline.py's fix; this is what makes docTR load on
# the 5080 instead of hanging on a HuggingFace Hub round-trip.)
# ---------------------------------------------------------------------------
os.environ.setdefault("DOCTR_CACHE_DIR",
                      os.path.join(os.path.expanduser("~"), ".cache", "doctr"))
os.environ["HF_HUB_OFFLINE"]           = "1"
os.environ["TRANSFORMERS_OFFLINE"]     = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["USE_TORCH"]                = "1"
os.environ["DOCTR_MULTIPROCESSING_DISABLE"] = "TRUE"

# --- VRAM-RAMP FIX (leak diagnosis 2026-06-08) -------------------------------
# Surya batch=None auto-sizes huge, per-page-VARIABLE batches -> CUDA allocator
# fragmentation -> reserved VRAM ratchets up across a volume (the "leak") and
# TDR-crashes multi-worker runs. A FIXED batch keeps it flat (proven: 60 OCRs of
# one page = +0 MB growth at batch 32/128). Must precede any surya/torch import.
os.environ.setdefault("RECOGNITION_BATCH_SIZE", "128")
os.environ.setdefault("DETECTOR_BATCH_SIZE", "12")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import re
import json
import time
import hashlib
import datetime
import gc
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
SCRATCH_ROOT = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch")
LOG_FILE     = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch\ocr-5080-run.log")
TESS_PATH    = r"C:\Users\PatrickKolasinski\AppData\Local\Tesseract-OCR\tesseract.exe"
PRODUCTION_DPI = 300

if len(sys.argv) < 3:
    print("Usage: python ocr_only_5080.py <volume_pdf_path> <session_label>")
    sys.exit(1)

PDF_PATH      = Path(sys.argv[1])
SESSION_LABEL = sys.argv[2].strip()

# --stage gate (parity with ocr_only_5090.py). The 5080 is normally invoked with the
# legacy 2-arg form (no --stage) => "all". This MUST be defined: the born-digital clean
# text-layer branch references STAGE (`if STAGE == "prep"`), so a missing definition
# NameError-crashes every 2000+ volume that has a usable text layer.
STAGE = "all"
if "--stage" in sys.argv:
    _si = sys.argv.index("--stage")
    if _si + 1 < len(sys.argv):
        STAGE = sys.argv[_si + 1].strip().lower()
if STAGE not in ("prep", "ocr", "all"):
    print(f"ERROR: --stage must be prep|ocr|all, got {STAGE!r}")
    sys.exit(1)

if not PDF_PATH.exists():
    print(f"ERROR: PDF not found: {PDF_PATH}")
    sys.exit(1)

SCRATCH       = SCRATCH_ROOT / f"production-{SESSION_LABEL}"
PAGES_DIR     = SCRATCH / "pages_raw"
PREP_GRAY_DIR = SCRATCH / "pages_prep_gray"
OCR_OUT_DIR   = SCRATCH / "ocr_consensus"
for d in [SCRATCH, PAGES_DIR, PREP_GRAY_DIR, OCR_OUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def log(phase, description, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    entry = f"[{ts}] [{SESSION_LABEL}] {phase} | {description} | {status}\n"
    with open(str(LOG_FILE), "a", encoding="utf-8") as f:
        f.write(entry)
    print(entry.strip(), flush=True)


log("OCR5080", f"=== START OCR-ONLY: {PDF_PATH.name} session={SESSION_LABEL} ===", "OK")

# ---------------------------------------------------------------------------
# STAGE 0: SHA256
# ---------------------------------------------------------------------------
h = hashlib.sha256()
with open(str(PDF_PATH), "rb") as f:
    for chunk in iter(lambda: f.read(65536), b""):
        h.update(chunk)
computed_sha = h.hexdigest()
(SCRATCH / "sha256.txt").write_text(computed_sha, encoding="utf-8")
log("STAGE0", f"SHA256={computed_sha}", "OK")

import fitz
doc = fitz.open(str(PDF_PATH))
total_pages = doc.page_count
log("STAGE0", f"PDF opened: {total_pages} pages", "OK")

# ---------------------------------------------------------------------------
# STAGE 0.5: Digital-native probe â€” PDF with native text layer skips render/OCR.
# See ocr_only_5090.py STAGE 0.5 comment block for full design rationale.
# Keep this block in sync with ocr_only_5090.py and pipeline/sql/ocr_only_sql.py.
# ---------------------------------------------------------------------------
_probe_n = min(20, total_pages)
_probe_idx = [int(total_pages * i / _probe_n) for i in range(_probe_n)]
_image_pages = sum(1 for i in _probe_idx if len(doc[i].get_images()) > 0)
_avg_chars = sum(len(doc[i].get_text("text").strip()) for i in _probe_idx) / max(_probe_n, 1)
# Year-based cutoff: 1997-1999 Chief Clerk PDFs have broken CMap fonts that
# produce printable mojibake (ctrl_ratio ~0.0, not caught by the quality check).
# Born-digital extraction is only valid for 2000+. See MODERN_STATUTE_FORMAT doc.
_vol_year_m = re.match(r'(\d{4})', PDF_PATH.stem)
_vol_year = int(_vol_year_m.group(1)) if _vol_year_m else 9999
DIGITAL_NATIVE = (_image_pages / max(_probe_n, 1)) < 0.2 and _avg_chars >= 200 and _vol_year >= 2000
log("STAGE0-PROBE",
    f"image_pages={_image_pages}/{_probe_n} avg_chars={_avg_chars:.0f} vol_year={_vol_year} DIGITAL_NATIVE={DIGITAL_NATIVE}",
    "OK")

if DIGITAL_NATIVE:
    log("BORN-DIGITAL", "PDF has native text layer -- skipping render/preprocess/OCR", "OK")
    _body_pgs, _empty_pgs, _page_texts = [], [], {}
    for _pidx in range(total_pages):
        _txt = doc[_pidx].get_text("text")
        _page_texts[_pidx] = _txt
        (_body_pgs if len(_txt.strip()) >= 50 else _empty_pgs).append(_pidx)

    # --- BLOCKER 1 FIX: Font-corruption quality check ---
    # After extracting text layer, sample first few body pages and check for
    # control characters (indicator of corrupt/garbled text layer like PSOwstdutch).
    # If >20% are control chars, text layer is unusable -- fall back to OCR path.
    _sample_pages = list(_body_pgs)[:min(5, len(_body_pgs))]
    _sample_text = "".join(_page_texts[p] for p in _sample_pages)
    _ctrl_chars = sum(1 for c in _sample_text if ord(c) < 32 and c not in '\n\t\r')
    _ctrl_ratio = _ctrl_chars / max(len(_sample_text), 1)
    if _ctrl_ratio > 0.20:
        log("BORN-DIGITAL", f"Text layer corrupt (ctrl_ratio={_ctrl_ratio:.2f}) -- falling back to OCR path", "WARN")
        DIGITAL_NATIVE = False
        doc.close()
        # Re-open doc and continue to normal render/OCR flow below
        doc = fitz.open(str(PDF_PATH))
    else:
        # Text layer is clean, proceed with born-digital path
        _cls_tmp = (SCRATCH / "page_classification.json").with_suffix(".json.tmp")
        _cls_tmp.write_text(json.dumps({
            "body_start_idx": _body_pgs[0] if _body_pgs else 0,
            "total_pages": total_pages,
            "front_matter": [],
            "body": [p + 1 for p in _body_pgs],
            "index": [],
            "empty": [p + 1 for p in _empty_pgs],
            "median_body_density": 1.0,
            "born_digital": True,
        }, indent=2), encoding="utf-8")
        _cls_tmp.replace(SCRATCH / "page_classification.json")
        doc.close()
        log("BORN-DIGITAL", f"body={len(_body_pgs)} empty={len(_empty_pgs)} classified", "OK")
        if STAGE == "prep":
            log("PREP-DONE", "Born-digital prep complete -- exiting before OCR", "OK")
            sys.exit(0)
        _t0 = time.time()
        _bd_results = {
            _pidx: {
                "page_1indexed": _pidx + 1,
                "tess_text": "", "doctr_text": "", "surya_text": "",
                "consensus_text": _page_texts[_pidx],
                "agreement_ratio": 1.0,
                "high_confidence": True,
                "engines_used": "pdf_text_extract",
                "seconds": 0.0,
                "img_path": "",
            }
            for _pidx in _body_pgs
        }
        (OCR_OUT_DIR / "page_ocr_results.json").write_text(
            json.dumps(_bd_results, indent=2), encoding="utf-8"
        )
        log("BORN-DIGITAL",
            f"body={len(_body_pgs)} empty={len(_empty_pgs)} wrote {len(_bd_results)} page records "
            f"in {time.time() - _t0:.1f}s", "OK")
        sys.exit(0)

# ---------------------------------------------------------------------------
# STAGE 1: Render at 300 DPI (grayscale)
# ---------------------------------------------------------------------------
# Prep-already-on-disk fast path: if every page is already preprocessed in
# pages_prep_gray (rendered on another box and synced here, or a resumed run),
# skip render+preprocess entirely. STAGE 3/4 read pages_prep_gray directly, and
# pages_raw is only an input to STAGE 2, so it is never needed once prep is done.
PREP_COMPLETE = len(list(PREP_GRAY_DIR.glob("page_*.png"))) >= total_pages
if PREP_COMPLETE:
    log("STAGE1-2-SKIP",
        f"pages_prep_gray already complete ({total_pages} pages) -- skipping render+preprocess", "OK")
log("STAGE1-RENDER", f"Rendering {total_pages} pages at {PRODUCTION_DPI} DPI", "OK")
t_render = time.time()
for pidx in range(total_pages):
    out_path = PAGES_DIR / f"page_{pidx:04d}.png"
    if PREP_COMPLETE or out_path.exists():
        continue
    page = doc[pidx]
    mat = fitz.Matrix(PRODUCTION_DPI / 72.0, PRODUCTION_DPI / 72.0)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    img_rgb = cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)
    cv2.imwrite(str(out_path), img_rgb)
    if pidx % 100 == 0:
        log("STAGE1-RENDER", f"page {pidx+1}/{total_pages}", "OK")
render_wall = time.time() - t_render
log("STAGE1-RENDER", f"Render done in {render_wall:.1f}s ({render_wall/total_pages:.2f}s/page)", "OK")

# ---------------------------------------------------------------------------
# STAGE 2: v2-grayscale preprocess (identical to ocr_only_5090.py)
# ---------------------------------------------------------------------------
def deskew(gray):
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    best_angle, best_score = 0.0, -1.0
    hh, ww = binary.shape
    for angle_tenth in range(-50, 51):
        angle = angle_tenth / 10.0
        M = cv2.getRotationMatrix2D((ww / 2, hh / 2), angle, 1.0)
        rotated = cv2.warpAffine(binary, M, (ww, hh), flags=cv2.INTER_NEAREST,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        score = float(np.var(rotated.sum(axis=1).astype(np.float64)))
        if score > best_score:
            best_score, best_angle = score, angle
    if abs(best_angle) < 0.15:
        return gray, 0.0
    M = cv2.getRotationMatrix2D((ww / 2, hh / 2), best_angle, 1.0)
    return cv2.warpAffine(gray, M, (ww, hh), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE), best_angle

def binarize_sauvola(gray):
    w_size = max(15, (gray.shape[1] // 15) | 1)
    k, R = 0.2, 128.0
    gray_f = gray.astype(np.float64)
    p = w_size // 2
    g_pad = np.pad(gray_f, p, mode="reflect")
    i_pad  = cv2.integral(g_pad)
    i2_pad = cv2.integral(g_pad ** 2)
    N = w_size * w_size
    hh, ww = gray.shape
    r1, r2, c1, c2 = p, p + hh, p, p + ww
    s  = (i_pad[r1-p:r2-p, c1-p:c2-p] - i_pad[r1-p:r2-p, c1+p+1:c2+p+1]
        - i_pad[r1+p+1:r2+p+1, c1-p:c2-p] + i_pad[r1+p+1:r2+p+1, c1+p+1:c2+p+1])
    s2 = (i2_pad[r1-p:r2-p, c1-p:c2-p] - i2_pad[r1-p:r2-p, c1+p+1:c2+p+1]
        - i2_pad[r1+p+1:r2+p+1, c1-p:c2-p] + i2_pad[r1+p+1:r2+p+1, c1+p+1:c2+p+1])
    mean = s / N
    std  = np.sqrt(np.maximum(0, s2 / N - mean**2))
    threshold = mean * (1.0 + k * (std / R - 1.0))
    return np.where(gray_f >= threshold, 255, 0).astype(np.uint8)

def find_margin_and_crop(binary, gray):
    hh, ww = binary.shape
    ink = (binary < 128).astype(np.uint8)
    col_proj = ink.sum(axis=0).astype(np.float64)
    min_mf, max_mf = 0.06, 0.28
    left_bound = int(min_mf * ww)
    max_margin = int(max_mf * ww)
    SPARSITY_GUARD = 0.55

    def smooth_norm(proj, ks):
        kk = np.ones(ks) / float(ks)
        ss = np.convolve(proj, kk, mode="same")
        mx = ss.max()
        return ss / mx if mx > 1 else ss

    def find_gutters(cn, thresh, min_w):
        mask = cn < thresh
        gutters, in_g, gs = [], False, 0
        for x in range(len(mask)):
            if mask[x] and not in_g:
                in_g, gs = True, x
            elif not mask[x] and in_g:
                in_g = False
                if x - gs >= min_w:
                    gutters.append((gs, x - 1))
        if in_g and len(mask) - gs >= min_w:
            gutters.append((gs, len(mask) - 1))
        return gutters

    def get_cands(gutters):
        lc = [(gs, ge) for gs, ge in gutters if left_bound <= ge <= max_margin and gs >= left_bound]
        rc = [(gs, ge) for gs, ge in gutters if (ww - max_margin) <= gs <= (ww - left_bound)]
        return lc, rc

    def widest(cands):
        return max(cands, key=lambda t: t[1] - t[0]) if cands else None

    for kernel, thresh, min_w in [(5, 0.05, 10), (5, 0.15, 8), (15, 0.15, 5)]:
        n = smooth_norm(col_proj, kernel)
        gutters = find_gutters(n, thresh, min_w)
        lc, rc = get_cands(gutters)
        bl, br = widest(lc), widest(rc)
        chosen, side = None, None
        if bl and br:
            sl = float(n[:bl[0]].mean()) if bl[0] > 0 else 1.0
            sr = float(n[br[1]:].mean()) if br[1] < len(n) else 1.0
            chosen, side = (br, "right") if sl >= sr - 0.05 else (bl, "left")
        elif bl and float(n[:bl[0]].mean()) < SPARSITY_GUARD:
            chosen, side = bl, "left"
        elif br and float(n[br[1]:].mean()) < SPARSITY_GUARD:
            chosen, side = br, "right"
        if chosen:
            gs, ge = chosen
            return gray[:, ge+1:] if side == "left" else gray[:, :gs]
    return gray

def strip_headers_footers(gray, top_frac=0.12, bot_frac=0.10, min_gap=8):
    hh, ww = gray.shape
    ink = (gray < 128).astype(np.uint8)
    rp = ink.sum(axis=1).astype(np.float64)
    rs = np.convolve(rp, np.ones(3) / 3.0, mode="same")
    mx = rs.max()
    if mx < 1:
        return gray
    rn = rs / mx
    low = rn < 0.05
    tl, bl = int(top_frac * hh), int((1 - bot_frac) * hh)
    top_crop, in_g, gs = 0, False, 0
    for y in range(tl):
        if low[y] and not in_g:
            in_g, gs = True, y
        elif not low[y] and in_g:
            in_g = False
            if y - gs >= min_gap:
                top_crop = y
    bot_crop, in_g, gs = hh, False, 0
    for y in range(bl, hh):
        if low[y] and not in_g:
            in_g, gs = True, y
        elif not low[y] and in_g:
            in_g = False
    if in_g and hh - gs >= min_gap:
        bot_crop = gs
    return gray[min(top_crop, tl):max(bot_crop, bl), :]

def despeckle(gray):
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    opened = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)
    return cv2.fastNlMeansDenoising(opened, h=8, templateWindowSize=7, searchWindowSize=21)

def preprocess_page(img_path, out_gray_path):
    orig = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
    if orig is None:
        return False
    gray = cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY)
    gray_d, _ = deskew(gray)
    binary = binarize_sauvola(gray_d)
    gray_c = find_margin_and_crop(binary, gray_d)
    gray_s = strip_headers_footers(gray_c)
    gray_f = despeckle(gray_s)
    cv2.imwrite(str(out_gray_path), cv2.cvtColor(gray_f, cv2.COLOR_GRAY2BGR))
    return True

log("STAGE2-PREPROCESS", f"Preprocessing {total_pages} pages (v2 grayscale)", "OK")
t_prep = time.time()
prep_ok = prep_fail = 0
for pidx in range(total_pages):
    in_p  = PAGES_DIR / f"page_{pidx:04d}.png"
    out_p = PREP_GRAY_DIR / f"page_{pidx:04d}.png"
    if out_p.exists():
        prep_ok += 1
        continue
    ok = preprocess_page(in_p, out_p)
    prep_ok += ok
    prep_fail += not ok
    if pidx % 100 == 0:
        log("STAGE2-PREPROCESS", f"page {pidx+1}/{total_pages} ok={prep_ok} fail={prep_fail}", "OK")
prep_wall = time.time() - t_prep
log("STAGE2-PREPROCESS", f"Preprocess done: {prep_ok} OK / {prep_fail} FAIL in {prep_wall:.1f}s",
    "OK" if prep_fail == 0 else "WARN")

# ---------------------------------------------------------------------------
# STAGE 3: Body classification (identical logic)
# ---------------------------------------------------------------------------
def ink_density(img_path):
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0
    return float((img < 128).sum()) / (img.shape[0] * img.shape[1])

def detect_body_start(total_pages, prep_dir):
    # SHORT-VOLUME FAST PATH: extraordinary-session volumes (e.g. 1926/1928 extra
    # sessions) can be as few as 4-6 pages. The density-scan approach needs at
    # least ~10 pages in the mid-range window to produce a meaningful signal; on
    # tiny volumes it yields an empty mid-list and falls through to the hardcoded
    # fallback of 30, which exceeds total_pages and produces an empty body list.
    # Fix: for volumes with <=12 pages, treat every page as body (body_start=0).
    # This is correct because a tiny special-session volume has no separable front
    # matter worth skipping -- the proclamation/chapter pages ARE the substance.
    # Normal volumes (hundreds of pages) are never affected by this threshold.
    SHORT_VOLUME_THRESHOLD = 12
    if total_pages <= SHORT_VOLUME_THRESHOLD:
        log("STAGE3-CLASSIFY",
            f"Short volume detected ({total_pages} pages <= {SHORT_VOLUME_THRESHOLD}) "
            f"-- treating all pages as body (body_start=0)", "WARN")
        return 0

    densities = []
    for pidx in range(min(80, total_pages)):
        p = prep_dir / f"page_{pidx:04d}.png"
        densities.append(ink_density(p) if p.exists() else 0.0)
    mid = [densities[i] for i in range(min(10, len(densities)), min(40, len(densities)))
           if densities[i] > 0.005]
    if not mid:
        # Fallback: no usable density signal. Clamp to avoid exceeding page count.
        fallback = min(30, max(0, total_pages - 1))
        log("STAGE3-CLASSIFY",
            f"No mid-range density signal (mid empty) -- using clamped fallback body_start={fallback} "
            f"(total_pages={total_pages})", "WARN")
        return fallback
    med_d = float(np.median(mid))
    threshold = med_d * 0.30
    consecutive = 0
    for pidx in range(total_pages):
        d = densities[pidx] if pidx < len(densities) else 0.05
        if d >= threshold:
            consecutive += 1
            if consecutive >= 4:
                return max(0, pidx - 3)
        else:
            consecutive = 0
    return 0

log("STAGE3-CLASSIFY", "Detecting body start", "OK")
BODY_START_IDX = detect_body_start(total_pages, PREP_GRAY_DIR)
log("STAGE3-CLASSIFY", f"Body start at 0-indexed page {BODY_START_IDX} (PDF page {BODY_START_IDX+1})", "OK")

FRONT_MATTER_RANGE = list(range(0, BODY_START_IDX))
body_candidates = list(range(BODY_START_IDX, total_pages))
ref_densities = []
for pidx in range(BODY_START_IDX, min(BODY_START_IDX + 40, total_pages)):
    p = PREP_GRAY_DIR / f"page_{pidx:04d}.png"
    if p.exists():
        ref_densities.append(ink_density(p))
median_density = float(np.median(ref_densities)) if ref_densities else 0.05
LOW_DENSITY_THRESHOLD = median_density * 0.25

body_pages, index_pages, empty_pages = [], [], []
for pidx in body_candidates:
    p = PREP_GRAY_DIR / f"page_{pidx:04d}.png"
    if not p.exists():
        empty_pages.append(pidx)
        continue
    d = ink_density(p)
    if d < 0.003:
        empty_pages.append(pidx)
    elif d < LOW_DENSITY_THRESHOLD and pidx > total_pages - 80:
        index_pages.append(pidx)
    else:
        body_pages.append(pidx)

log("STAGE3-CLASSIFY", f"body={len(body_pages)} front_matter={len(FRONT_MATTER_RANGE)} "
    f"index={len(index_pages)} empty={len(empty_pages)}", "OK")
(SCRATCH / "page_classification.json").write_text(json.dumps({
    "body_start_idx": BODY_START_IDX,
    "front_matter": [p+1 for p in FRONT_MATTER_RANGE],
    "body": [p+1 for p in body_pages],
    "index": [p+1 for p in index_pages],
    "empty": [p+1 for p in empty_pages],
    "median_body_density": median_density,
}, indent=2), encoding="utf-8")

# ---------------------------------------------------------------------------
# STAGE 4: OCR -- Surya + docTR + Tesseract consensus
#          (docTR loaded with the PINNED + OFFLINE fix for the 5080)
# ---------------------------------------------------------------------------
log("STAGE4-OCR", "Loading docTR model (GPU, pinned fast_base+crnn, orientation off)", "OK")
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
import torch

try:
    doctr_model = ocr_predictor(
        det_arch="fast_base",
        reco_arch="crnn_vgg16_bn",
        pretrained=True,
        assume_straight_pages=True,
        disable_page_orientation=True,
        disable_crop_orientation=True,
    )
except TypeError:
    doctr_model = ocr_predictor(det_arch="fast_base", reco_arch="crnn_vgg16_bn", pretrained=True)
if torch.cuda.is_available():
    doctr_model = doctr_model.cuda()
    log("STAGE4-OCR", f"docTR on GPU: {torch.cuda.get_device_name(0)}", "OK")
    torch.cuda.reset_peak_memory_stats()
else:
    log("STAGE4-OCR", "docTR on CPU (no GPU) -- ABORT, 5080 GPU expected", "FAIL")
    sys.exit(2)

import pytesseract
pytesseract.pytesseract.tesseract_cmd = TESS_PATH

SURYA_AVAILABLE = False
surya_rec = surya_det = None
try:
    from surya.detection import DetectionPredictor
    from surya.recognition import RecognitionPredictor
    surya_det = DetectionPredictor()
    surya_rec = RecognitionPredictor()
    SURYA_AVAILABLE = True
    log("STAGE4-OCR", "Surya loaded OK", "OK")
except Exception as e:
    log("STAGE4-OCR", f"Surya unavailable: {e} -- fallback docTR+Tess", "WARN")

def run_doctr(img_path):
    docu = DocumentFile.from_images(str(img_path))
    with torch.inference_mode():
        result = doctr_model(docu)
    lines = []
    for page in result.pages:
        for block in page.blocks:
            for line in block.lines:
                lines.append(" ".join(w.value for w in line.words))
    text = "\n".join(lines)
    del result, docu
    return text

def run_tesseract(img_path):
    from PIL import Image as PILImage
    img = PILImage.open(str(img_path)).convert("L")
    return pytesseract.image_to_string(img, lang="eng", config="--oem 1 --psm 6")

def run_surya(img_path):
    from PIL import Image as PILImage
    img = PILImage.open(str(img_path)).convert("RGB")
    with torch.inference_mode():
        results = surya_rec([img], langs=[["en"]], det_predictor=surya_det)
    lines = []
    for page_result in results:
        for line in page_result.text_lines:
            lines.append(line.text)
    text = "\n".join(lines)
    del results
    img.close()
    del img
    return text

def tokenize(text):
    return re.findall(r'\S+', text.lower())

def three_engine_consensus(surya_text, doctr_text, tess_text, surya_ok):
    if surya_ok:
        surya_words = set(tokenize(surya_text))
        doctr_words = set(tokenize(doctr_text))
        tess_words  = set(tokenize(tess_text))
        all_words = surya_words | doctr_words | tess_words
        if not all_words:
            return tess_text.strip(), 0.0, False, "surya+doctr+tess"
        agree_2of3 = set()
        for w in all_words:
            votes = (w in surya_words) + (w in doctr_words) + (w in tess_words)
            if votes >= 2:
                agree_2of3.add(w)
        ratio = len(agree_2of3) / len(all_words) if all_words else 0.0
        return tess_text.strip(), round(ratio, 4), ratio > 0.65, "surya+doctr+tess"
    else:
        tess_w = set(tokenize(tess_text))
        doctr_w = set(tokenize(doctr_text))
        union = tess_w | doctr_w
        if not union:
            return tess_text.strip(), 0.0, False, "doctr+tess"
        common = tess_w & doctr_w
        ratio = len(common) / len(union)
        return tess_text.strip(), round(ratio, 4), ratio > 0.70, "doctr+tess"

log("STAGE4-OCR", f"Starting OCR on {len(body_pages)} body pages (Surya={SURYA_AVAILABLE})", "OK")
t_ocr = time.time()
page_ocr_results = {}
ocr_timings = []
high_conf_count = low_conf_count = 0

existing_ocr_path = OCR_OUT_DIR / "page_ocr_results.json"
if existing_ocr_path.exists():
    try:
        existing = json.loads(existing_ocr_path.read_text(encoding="utf-8"))
        page_ocr_results = {int(k): v for k, v in existing.items()}
        log("STAGE4-OCR", f"Resuming: {len(page_ocr_results)} pages already OCR'd", "OK")
    except Exception:
        pass

for i, pidx in enumerate(body_pages):
    if pidx in page_ocr_results:
        if page_ocr_results[pidx].get("high_confidence"):
            high_conf_count += 1
        else:
            low_conf_count += 1
        continue

    gray_path = PREP_GRAY_DIR / f"page_{pidx:04d}.png"
    if not gray_path.exists():
        log("STAGE4-OCR", f"page {pidx+1}: preprocessed image missing", "WARN")
        continue

    t0 = time.time()
    try:
        tess_text = run_tesseract(gray_path)
    except Exception as e:
        log("STAGE4-OCR", f"page {pidx+1}: Tesseract FAIL: {e}", "FAIL")
        tess_text = ""
    try:
        doctr_text = run_doctr(gray_path)
    except Exception as e:
        log("STAGE4-OCR", f"page {pidx+1}: docTR FAIL: {e}", "WARN")
        doctr_text = ""
    surya_text = ""
    surya_page_ok = False
    if SURYA_AVAILABLE:
        try:
            surya_text = run_surya(gray_path)
            surya_page_ok = True
        except Exception as e:
            log("STAGE4-OCR", f"page {pidx+1}: Surya FAIL (docTR+Tess): {e}", "WARN")

    consensus_text, agreement_ratio, high_conf, engines = three_engine_consensus(
        surya_text, doctr_text, tess_text, surya_page_ok)
    elapsed = time.time() - t0
    ocr_timings.append(elapsed)

    page_ocr_results[pidx] = {
        "page_1indexed": pidx + 1,
        "tess_text": tess_text,
        "doctr_text": doctr_text,
        "surya_text": surya_text,
        "consensus_text": consensus_text,
        "agreement_ratio": agreement_ratio,
        "high_confidence": high_conf,
        "engines_used": engines,
        "seconds": round(elapsed, 2),
        "img_path": str(gray_path),
    }
    if high_conf:
        high_conf_count += 1
    else:
        low_conf_count += 1

    if i % 20 == 0:
        peak_mb = torch.cuda.max_memory_reserved() / 1048576 if torch.cuda.is_available() else 0
        log("STAGE4-OCR", f"page {pidx+1} ({i+1}/{len(body_pages)}): {engines} "
            f"agree={agreement_ratio:.2f} hi={high_conf} {elapsed:.1f}s peakVRAM={peak_mb:.0f}MB", "OK")

    # Per-page GPU memory hygiene
    del tess_text, doctr_text, surya_text, consensus_text
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    if (i + 1) % 20 == 0:
        gc.collect()
    if (i + 1) % 25 == 0:
        existing_ocr_path.write_text(json.dumps(page_ocr_results, indent=2), encoding="utf-8")

ocr_wall = time.time() - t_ocr
mean_ocr_sec = float(np.mean(ocr_timings)) if ocr_timings else 0.0
pages_per_min = 60.0 / mean_ocr_sec if mean_ocr_sec > 0 else 0
peak_alloc_mb = torch.cuda.max_memory_allocated() / 1048576 if torch.cuda.is_available() else 0
peak_resv_mb  = torch.cuda.max_memory_reserved() / 1048576 if torch.cuda.is_available() else 0

ratios = [v["agreement_ratio"] for v in page_ocr_results.values()]
conf_dist = {
    "high_>=0.65": sum(1 for r in ratios if r >= 0.65),
    "medium_0.50_0.65": sum(1 for r in ratios if 0.50 <= r < 0.65),
    "low_<0.50": sum(1 for r in ratios if r < 0.50),
    "mean_agreement": round(float(np.mean(ratios)), 4) if ratios else 0.0,
    "median_agreement": round(float(np.median(ratios)), 4) if ratios else 0.0,
}
existing_ocr_path.write_text(json.dumps(page_ocr_results, indent=2), encoding="utf-8")

log("STAGE4-OCR", f"OCR done: {len(body_pages)} body pages in {ocr_wall:.1f}s "
    f"({mean_ocr_sec:.2f}s/page, {pages_per_min:.1f} p/min) hi={high_conf_count} lo={low_conf_count}", "OK")
log("STAGE4-OCR", f"Confidence dist: {conf_dist}", "OK")
log("OCR5080", f"PEAK VRAM: allocated={peak_alloc_mb:.0f}MB reserved={peak_resv_mb:.0f}MB "
    f"(GPU {torch.cuda.get_device_name(0)})", "OK")
log("OCR5080", f"=== OCR-ONLY COMPLETE: {SESSION_LABEL} | sha={computed_sha} | "
    f"body={len(body_pages)} total={total_pages} | output={existing_ocr_path} ===", "OK")

# Self-documenting per-volume throughput summary (parsed by benchmark_throughput.py).
# ocr_wall is the OCR-loop time (sum of per-page seconds); EXCLUDES render+preprocess.
_vol_ppm = (len(body_pages) / (ocr_wall / 60.0)) if ocr_wall > 0 else 0.0
log("VOLUME", f"{SESSION_LABEL} | {len(body_pages)} pages | {ocr_wall:.0f}s | "
    f"{_vol_ppm:.1f} pages/min | card=5080 workers=1", "OK")

print(f"\n=== {SESSION_LABEL} OCR-ONLY COMPLETE (5080) ===")
print(f"Pages: {total_pages} total | {len(body_pages)} body OCR'd")
print(f"Surya: {SURYA_AVAILABLE} | mean agreement: {conf_dist['mean_agreement']}")
print(f"PEAK VRAM: allocated={peak_alloc_mb:.0f}MB reserved={peak_resv_mb:.0f}MB")
print(f"Throughput: {pages_per_min:.1f} pages/min")
print(f"Output: {existing_ocr_path}")
print(f"SHA256: {computed_sha}")
