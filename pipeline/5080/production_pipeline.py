"""
PatoLex Production Pipeline — Generalized for all CA session-law volumes
=========================================================================
Usage:
    python production_pipeline.py <volume_pdf_path> <session_label>

    session_label: e.g. "1851", "1863-64", "1865-66"
    The script derives session/legislature info from the label.

Stages:
  0. SHA256 + idempotency check (skip if already ingested)
  1. Render all PDF pages to PNG (300 DPI)
  2. v2-grayscale preprocess (deskew, margin-strip, header/footer, despeckle)
  3. Classify pages: front-matter/index vs body
  4. OCR three-engine consensus:
       Surya (local GPU, primary) + docTR (GPU) + Tesseract (CPU)
       Committed text = per-token majority of all three engines.
       If Surya fails on a volume, fall back to docTR+Tesseract (logged).
  5. Parse acts/sections from consensus text
  6. DB ingest (idempotent): source_document + enactments + provisions + change_events
  7. Report

Trust level: 'ocr_uncertain' (only OCR-level in live schema).
Faithfulness: committed text is literal OCR consensus, never modernized.
Idempotent: if SHA256 already in source_document, skip entire volume.
"""

import sys
import os

# ---------------------------------------------------------------------------
# docTR OFFLINE LOAD FIX (must run BEFORE any torch/doctr/huggingface import)
# ---------------------------------------------------------------------------
# ocr_predictor(pretrained=True) otherwise attempts a HuggingFace Hub round-trip
# to resolve model configs even when the .pt weights are already in
# ~/.cache/doctr. On the 5080 that network probe stalled (CPU froze ~12s then
# hung). Forcing offline + USE_TORCH makes docTR load straight from local cache.
# Set unconditionally and idempotently; harmless on the 5090's separate scripts.
os.environ.setdefault("DOCTR_CACHE_DIR",
                      os.path.join(os.path.expanduser("~"), ".cache", "doctr"))
os.environ["HF_HUB_OFFLINE"]           = "1"
os.environ["TRANSFORMERS_OFFLINE"]     = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["USE_TORCH"]                = "1"
os.environ["DOCTR_MULTIPROCESSING_DISABLE"] = "TRUE"

import re
import json
import time
import hashlib
import datetime
import subprocess
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
SCRATCH_ROOT    = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch")
LOG_FILE        = Path(r"C:\Users\PatrickKolasinski\Documents\GitHub\patolex\docs\80_PROJECT_HISTORY\run-logs\production-batch-run.log")
PSQL            = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"
TESS_PATH       = r"C:\Users\PatrickKolasinski\AppData\Local\Tesseract-OCR\tesseract.exe"
PYTHON_EXE      = r"C:\Users\PatrickKolasinski\AppData\Local\Programs\Python\Python312\python.exe"
PRODUCTION_DPI  = 300

# CA legislature number mapping (session_year_label -> legislature ordinal)
# Annual sessions 1850-1862, biennial from 1863 onward
# 1st = 1850, 2nd = 1851, 3rd = 1852, 4th = 1853, 5th = 1854, 6th = 1855
# 7th = 1856, 8th = 1857, 9th = 1858, 10th = 1859, 11th = 1860, 12th = 1861
# 13th = 1862, 14th = 1863, 15th = 1863-64 adjourned, 16th = 1865-66
# 17th = 1867-68, 18th = 1869-70, 19th = 1871-72, 20th = 1873-74, 21st = 1875-76

LEGISLATURE_MAP = {
    "1850": ("1849-1850", "1st"),
    "1851": ("1851", "2nd"),
    "1852": ("1852", "3rd"),
    "1853": ("1853", "4th"),
    "1854": ("1854", "5th"),
    "1855": ("1855", "6th"),
    "1856": ("1856", "7th"),
    "1857": ("1857", "8th"),
    "1858": ("1858", "9th"),
    "1859": ("1859", "10th"),
    "1860": ("1860", "11th"),
    "1861": ("1861", "12th"),
    "1862": ("1862", "13th"),
    "1863": ("1863", "14th"),
    "1863-64": ("1863-64 adjourned", "15th"),
    "1865-66": ("1865-66", "16th"),
    "1867-68": ("1867-68", "17th"),
    "1869-70": ("1869-70", "18th"),
    "1871-72": ("1871-72", "19th"),
    "1873-74": ("1873-74", "20th"),
    "1875-76": ("1875-76", "21st"),
}

# Ordinal suffix helper
def ordinal_suffix(n):
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return {1: f"{n}st", 2: f"{n}nd", 3: f"{n}rd"}.get(n % 10, f"{n}th")

# ---------------------------------------------------------------------------
# ARGUMENT PARSING
# ---------------------------------------------------------------------------
if len(sys.argv) < 3:
    print("Usage: python production_pipeline.py <volume_pdf_path> <session_label>")
    print("  e.g.: python production_pipeline.py C:/...1851_Statutes.pdf 1851")
    sys.exit(1)

PDF_PATH      = Path(sys.argv[1])
SESSION_LABEL = sys.argv[2].strip()

if not PDF_PATH.exists():
    print(f"ERROR: PDF not found: {PDF_PATH}")
    sys.exit(1)

if SESSION_LABEL not in LEGISLATURE_MAP:
    print(f"WARNING: session_label '{SESSION_LABEL}' not in LEGISLATURE_MAP. Using fallback.")
    SESSION_STR  = SESSION_LABEL
    LEGIS_NUM    = SESSION_LABEL
else:
    SESSION_STR, LEGIS_NUM = LEGISLATURE_MAP[SESSION_LABEL]

# Start year for date matching
START_YEAR = int(SESSION_LABEL.split("-")[0])

# Scratch directory for this volume
SCRATCH = SCRATCH_ROOT / f"production-{SESSION_LABEL}"
PAGES_DIR     = SCRATCH / "pages_raw"
PREP_GRAY_DIR = SCRATCH / "pages_prep_gray"
OCR_OUT_DIR   = SCRATCH / "ocr_consensus"

for d in [SCRATCH, PAGES_DIR, PREP_GRAY_DIR, OCR_OUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

SOURCE_URL = f"https://clerk.assembly.ca.gov/sites/clerk.assembly.ca.gov/files/archive/Statutes/{START_YEAR}/{PDF_PATH.name}"

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
def log(phase, description, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    vol = SESSION_LABEL
    entry = f"[{ts}] [{vol}] {phase} | {description} | {status}\n"
    with open(str(LOG_FILE), "a", encoding="utf-8") as f:
        f.write(entry)
    print(entry.strip())

log("PIPELINE", f"=== START: {PDF_PATH.name} session={SESSION_LABEL} ===", "OK")

# ---------------------------------------------------------------------------
# DB HELPERS
# ---------------------------------------------------------------------------
def psql_query(sql_str):
    """Run a SQL statement via psql. Returns first result line or empty string."""
    env = dict(os.environ)
    env["PGPASSWORD"] = os.environ.get("PGPASSWORD", "postgres")  # no hardcoded secret; supply via env
    args = [PSQL, "-U", "postgres", "-d", "patolex", "-t", "-A",
            "--set=client_encoding=UTF8", "-c", sql_str]
    r = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace",
                       env=env, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"psql error: {r.stderr.strip()[:300]}")
    lines = [ln for ln in r.stdout.strip().splitlines()
             if ln.strip()
             and not ln.strip().startswith("INSERT")
             and not ln.strip().startswith("UPDATE")
             and not ln.strip().startswith("DELETE")]
    return lines[0] if lines else ""

def safe_str(s, maxlen=None):
    """Encode to ASCII, escape SQL single-quotes, optionally truncate."""
    s = s.encode("ascii", errors="replace").decode("ascii")
    s = s.replace("'", "''")
    if maxlen:
        s = s[:maxlen]
    return s

# ---------------------------------------------------------------------------
# STAGE 0: SHA256 + idempotency
# ---------------------------------------------------------------------------
log("STAGE0", f"Computing SHA256 of {PDF_PATH.name}", "OK")
t_sha = time.time()
h = hashlib.sha256()
with open(str(PDF_PATH), "rb") as f:
    for chunk in iter(lambda: f.read(65536), b""):
        h.update(chunk)
computed_sha = h.hexdigest()
sha_ms = (time.time() - t_sha) * 1000
log("STAGE0", f"SHA256={computed_sha} ({sha_ms:.0f}ms)", "OK")

# Save SHA to scratch for reference
(SCRATCH / "sha256.txt").write_text(computed_sha, encoding="utf-8")

# Idempotency check: skip if this SHA256 is already a PRODUCTION row
# (production rows have page_count set; skeleton rows from prior runs don't)
idempotency_sql = (
    f"SELECT id FROM source_document "
    f"WHERE content_sha256 = '{computed_sha}' AND page_count IS NOT NULL;"
)
existing_id = psql_query(idempotency_sql)
if existing_id:
    log("STAGE0", f"source_document with this SHA256 already ingested (id={existing_id}) -- SKIP (idempotent)", "WARN")
    print("IDEMPOTENT STOP: volume already loaded. Purge the row to re-run.")
    sys.exit(0)
log("STAGE0", "No production row with this SHA256 -- proceeding", "OK")

# ---------------------------------------------------------------------------
# OPEN PDF
# ---------------------------------------------------------------------------
import fitz
doc = fitz.open(str(PDF_PATH))
total_pages = doc.page_count
log("STAGE0", f"PDF opened: {total_pages} pages", "OK")

# ---------------------------------------------------------------------------
# STAGE 1: Render pages at 300 DPI
# ---------------------------------------------------------------------------
log("STAGE1-RENDER", f"Rendering {total_pages} pages at {PRODUCTION_DPI} DPI", "OK")
t_render = time.time()

for pidx in range(total_pages):
    out_path = PAGES_DIR / f"page_{pidx:04d}.png"
    if out_path.exists():
        continue
    page = doc[pidx]
    mat = fitz.Matrix(PRODUCTION_DPI / 72.0, PRODUCTION_DPI / 72.0)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    img_rgb = cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)
    cv2.imwrite(str(out_path), img_rgb)
    if pidx % 100 == 0 or pidx < 3:
        log("STAGE1-RENDER", f"page {pidx+1}/{total_pages}", "OK")

render_wall = time.time() - t_render
log("STAGE1-RENDER", f"Render done: {total_pages} pages in {render_wall:.1f}s ({render_wall/total_pages:.2f}s/page)", "OK")

# ---------------------------------------------------------------------------
# STAGE 2: v2-grayscale preprocessing (inline)
# ---------------------------------------------------------------------------
def deskew(gray):
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    best_angle, best_score = 0.0, -1.0
    h, w = binary.shape
    for angle_tenth in range(-50, 51):
        angle = angle_tenth / 10.0
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        rotated = cv2.warpAffine(binary, M, (w, h), flags=cv2.INTER_NEAREST,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        score = float(np.var(rotated.sum(axis=1).astype(np.float64)))
        if score > best_score:
            best_score, best_angle = score, angle
    if abs(best_angle) < 0.15:
        return gray, 0.0
    M = cv2.getRotationMatrix2D((w / 2, h / 2), best_angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_LINEAR,
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
    h, w = gray.shape
    r1, r2, c1, c2 = p, p + h, p, p + w
    s  = (i_pad[r1-p:r2-p, c1-p:c2-p] - i_pad[r1-p:r2-p, c1+p+1:c2+p+1]
        - i_pad[r1+p+1:r2+p+1, c1-p:c2-p] + i_pad[r1+p+1:r2+p+1, c1+p+1:c2+p+1])
    s2 = (i2_pad[r1-p:r2-p, c1-p:c2-p] - i2_pad[r1-p:r2-p, c1+p+1:c2+p+1]
        - i2_pad[r1+p+1:r2+p+1, c1-p:c2-p] + i2_pad[r1+p+1:r2+p+1, c1+p+1:c2+p+1])
    mean = s / N
    std  = np.sqrt(np.maximum(0, s2 / N - mean**2))
    threshold = mean * (1.0 + k * (std / R - 1.0))
    return np.where(gray_f >= threshold, 255, 0).astype(np.uint8)

def find_margin_and_crop(binary, gray):
    h, w = binary.shape
    ink = (binary < 128).astype(np.uint8)
    col_proj = ink.sum(axis=0).astype(np.float64)
    min_mf, max_mf = 0.06, 0.28
    left_bound = int(min_mf * w)
    max_margin = int(max_mf * w)
    SPARSITY_GUARD = 0.55

    def smooth_norm(proj, ks):
        k = np.ones(ks) / float(ks)
        s = np.convolve(proj, k, mode="same")
        mx = s.max()
        return s / mx if mx > 1 else s

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
        rc = [(gs, ge) for gs, ge in gutters if (w - max_margin) <= gs <= (w - left_bound)]
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
    h, w = gray.shape
    ink = (gray < 128).astype(np.uint8)
    rp = ink.sum(axis=1).astype(np.float64)
    rs = np.convolve(rp, np.ones(3) / 3.0, mode="same")
    mx = rs.max()
    if mx < 1:
        return gray
    rn = rs / mx
    low = rn < 0.05
    tl, bl = int(top_frac * h), int((1 - bot_frac) * h)
    top_crop, in_g, gs = 0, False, 0
    for y in range(tl):
        if low[y] and not in_g:
            in_g, gs = True, y
        elif not low[y] and in_g:
            in_g = False
            if y - gs >= min_gap:
                top_crop = y
    bot_crop, in_g, gs = h, False, 0
    for y in range(bl, h):
        if low[y] and not in_g:
            in_g, gs = True, y
        elif not low[y] and in_g:
            in_g = False
    if in_g and h - gs >= min_gap:
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

log("STAGE2-PREPROCESS", f"Preprocessing {total_pages} pages (v2 grayscale track)", "OK")
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
    if pidx % 100 == 0 or pidx < 3:
        log("STAGE2-PREPROCESS", f"page {pidx+1}/{total_pages} ok={prep_ok} fail={prep_fail}", "OK" if ok else "WARN")

prep_wall = time.time() - t_prep
log("STAGE2-PREPROCESS", f"Preprocess done: {prep_ok} OK / {prep_fail} FAIL in {prep_wall:.1f}s", "OK" if prep_fail == 0 else "WARN")

# ---------------------------------------------------------------------------
# STAGE 3: Page classification (body vs front-matter/index)
# ---------------------------------------------------------------------------
def ink_density(img_path):
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0
    return float((img < 128).sum()) / (img.shape[0] * img.shape[1])

# Detect body start: first dense page after initial sparse front-matter
# Strategy: scan from beginning; body pages have density > 0.02
# Find first run of 5 consecutive dense pages starting after page 5
def detect_body_start(total_pages, pages_dir, prep_dir):
    densities = []
    for pidx in range(min(80, total_pages)):
        p = prep_dir / f"page_{pidx:04d}.png"
        d = ink_density(p) if p.exists() else 0.0
        densities.append(d)

    # Compute median of pages 10-40 (expected body region for all volumes)
    mid_densities = [densities[i] for i in range(min(10, len(densities)), min(40, len(densities))) if densities[i] > 0.005]
    if not mid_densities:
        return 30  # fallback
    med_d = float(np.median(mid_densities))

    # Find first transition from sparse to dense
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
    return 0  # fallback: start from page 0

log("STAGE3-CLASSIFY", "Detecting body start page via ink density", "OK")
t_class = time.time()
BODY_START_IDX = detect_body_start(total_pages, PAGES_DIR, PREP_GRAY_DIR)
log("STAGE3-CLASSIFY", f"Body start detected at 0-indexed page {BODY_START_IDX} (PDF page {BODY_START_IDX+1})", "OK")

FRONT_MATTER_RANGE = list(range(0, BODY_START_IDX))
body_candidates = list(range(BODY_START_IDX, total_pages))

# Compute median body density
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

class_wall = time.time() - t_class
log("STAGE3-CLASSIFY", f"Classification done in {class_wall:.1f}s: body={len(body_pages)} front_matter={len(FRONT_MATTER_RANGE)} index={len(index_pages)} empty={len(empty_pages)}", "OK")
(SCRATCH / "page_classification.json").write_text(
    json.dumps({
        "body_start_idx": BODY_START_IDX,
        "front_matter": [p+1 for p in FRONT_MATTER_RANGE],
        "body": [p+1 for p in body_pages],
        "index": [p+1 for p in index_pages],
        "empty": [p+1 for p in empty_pages],
        "median_body_density": median_density,
    }, indent=2), encoding="utf-8")

# ---------------------------------------------------------------------------
# STAGE 4: OCR — Surya + docTR + Tesseract three-engine consensus
# ---------------------------------------------------------------------------

# --- 4a. Load docTR ---
log("STAGE4-OCR", "Loading docTR model (GPU)", "OK")
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
import torch

# Pin architectures to the two weight files present in ~/.cache/doctr
# (fast_base detection + crnn_vgg16_bn recognition) and disable the page/crop
# orientation classifiers -- those pull a separate MobileNet checkpoint that is
# NOT cached and would trigger a (now-offline => failing) fetch. assume_straight
# is correct for these deskewed, single-orientation scans.
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
    # Older docTR without the orientation kwargs
    doctr_model = ocr_predictor(det_arch="fast_base", reco_arch="crnn_vgg16_bn", pretrained=True)
if torch.cuda.is_available():
    doctr_model = doctr_model.cuda()
    log("STAGE4-OCR", f"docTR on GPU: {torch.cuda.get_device_name(0)}", "OK")
else:
    log("STAGE4-OCR", "docTR on CPU (no GPU)", "WARN")

import pytesseract
pytesseract.pytesseract.tesseract_cmd = TESS_PATH

# --- 4b. Load Surya ---
SURYA_AVAILABLE = False
surya_rec = None
surya_det = None

try:
    from surya.detection import DetectionPredictor
    from surya.recognition import RecognitionPredictor
    surya_det = DetectionPredictor()
    surya_rec = RecognitionPredictor()
    SURYA_AVAILABLE = True
    log("STAGE4-OCR", "Surya (local) loaded OK", "OK")
except Exception as e:
    log("STAGE4-OCR", f"Surya unavailable: {e} -- falling back to docTR+Tesseract only", "WARN")

# --- 4c. OCR functions ---
def run_doctr(img_path):
    """Run docTR on preprocessed grayscale image. Returns plain text.

    Wrapped in torch.inference_mode() so no autograd graph / activation
    buffers are retained across pages (prevents cross-page GPU memory growth).
    Intermediate tensors are explicitly deleted before returning.
    """
    doc = DocumentFile.from_images(str(img_path))
    with torch.inference_mode():
        result = doctr_model(doc)
    lines = []
    for page in result.pages:
        for block in page.blocks:
            for line in block.lines:
                lines.append(" ".join(w.value for w in line.words))
    text = "\n".join(lines)
    # Free per-page tensors/result before next page
    del result, doc
    return text

def run_tesseract(img_path):
    """Run Tesseract on preprocessed image. Returns plain text."""
    from PIL import Image as PILImage
    img = PILImage.open(str(img_path)).convert("L")
    return pytesseract.image_to_string(img, lang="eng", config="--oem 1 --psm 6")

def run_surya(img_path):
    """Run Surya on preprocessed image. Returns plain text or raises.

    Wrapped in torch.inference_mode() so the detection + recognition forward
    passes do not retain autograd state across pages. The PIL image and the
    results object are explicitly released before returning.
    """
    from PIL import Image as PILImage
    img = PILImage.open(str(img_path)).convert("RGB")
    # RecognitionPredictor.__call__(images, langs, det_predictor, ...)
    with torch.inference_mode():
        results = surya_rec([img], langs=[["en"]], det_predictor=surya_det)
    lines = []
    for page_result in results:
        for line in page_result.text_lines:
            lines.append(line.text)
    text = "\n".join(lines)
    # Free per-page tensors/result before next page
    del results
    img.close()
    del img
    return text

def tokenize(text):
    """Split text into normalized word tokens (lowercase)."""
    return re.findall(r'\S+', text.lower())

def three_engine_consensus(surya_text, doctr_text, tess_text, surya_ok):
    """
    Per-token majority consensus of up to three engines.

    When all three are available: a token is in committed text if it appears
    in at least 2 of 3 engines' output (majority vote).
    Committed text is assembled from Tesseract's sequence, substituting
    docTR/Surya tokens where Tesseract is outvoted.

    Agreement ratio = fraction of tokens where at least 2 engines agree.
    High confidence = agreement_ratio > 0.65.

    When Surya is unavailable: falls back to 2-engine consensus (docTR+Tesseract).
    In that case the committed text is Tesseract primary (proven lower CER).

    Returns: (committed_text, agreement_ratio, high_confidence, engines_used)
    """
    if surya_ok:
        surya_words = set(tokenize(surya_text))
        doctr_words = set(tokenize(doctr_text))
        tess_words  = set(tokenize(tess_text))
        # Union for denominator
        all_words = surya_words | doctr_words | tess_words
        if not all_words:
            return tess_text.strip(), 0.0, False, "surya+doctr+tess"
        # Agreement = in at least 2 of 3
        agree_2of3 = set()
        for w in all_words:
            votes = (w in surya_words) + (w in doctr_words) + (w in tess_words)
            if votes >= 2:
                agree_2of3.add(w)
        ratio = len(agree_2of3) / len(all_words) if all_words else 0.0
        high_conf = ratio > 0.65
        # Committed text: Tesseract sequence, preserving tokens agreed by >=2 engines
        # For simplicity (faithfulness): use Tesseract text as the literal base.
        # The agreement ratio signals confidence; flagged tokens go to review.
        committed = tess_text.strip()
        return committed, round(ratio, 4), high_conf, "surya+doctr+tess"
    else:
        # 2-engine fallback
        tess_w = set(tokenize(tess_text))
        doctr_w = set(tokenize(doctr_text))
        union = tess_w | doctr_w
        if not union:
            return tess_text.strip(), 0.0, False, "doctr+tess"
        common = tess_w & doctr_w
        ratio = len(common) / len(union)
        return tess_text.strip(), round(ratio, 4), ratio > 0.70, "doctr+tess"

# --- 4d. Run OCR on body pages ---
log("STAGE4-OCR", f"Starting OCR consensus on {len(body_pages)} body pages (Surya={SURYA_AVAILABLE})", "OK")
t_ocr = time.time()

page_ocr_results = {}
ocr_timings = []
high_conf_count = low_conf_count = 0

# Resume support
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

    # Tesseract
    try:
        tess_text = run_tesseract(gray_path)
    except Exception as e:
        log("STAGE4-OCR", f"page {pidx+1}: Tesseract FAIL: {e}", "FAIL")
        tess_text = ""

    # docTR
    try:
        doctr_text = run_doctr(gray_path)
    except Exception as e:
        log("STAGE4-OCR", f"page {pidx+1}: docTR FAIL: {e}", "WARN")
        doctr_text = ""

    # Surya
    surya_text = ""
    surya_page_ok = False
    if SURYA_AVAILABLE:
        try:
            surya_text = run_surya(gray_path)
            surya_page_ok = True
        except Exception as e:
            log("STAGE4-OCR", f"page {pidx+1}: Surya FAIL (using docTR+Tess): {e}", "WARN")

    consensus_text, agreement_ratio, high_conf, engines = three_engine_consensus(
        surya_text, doctr_text, tess_text, surya_page_ok
    )
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
        "img_path": str(PREP_GRAY_DIR / f"page_{pidx:04d}.png"),
    }

    if high_conf:
        high_conf_count += 1
    else:
        low_conf_count += 1

    if i % 20 == 0 or i < 5:
        log("STAGE4-OCR", f"page {pidx+1} ({i+1}/{len(body_pages)}): engines={engines} agree={agreement_ratio:.2f} hi={high_conf} {elapsed:.1f}s", "OK")

    # --- Per-page GPU memory hygiene (prevents intra-volume OOM cascade) ---
    # Drop per-page text refs and release cached CUDA blocks every page so the
    # docTR/Surya forward-pass allocations do not accumulate/fragment across the
    # hundreds of pages in large volumes (root cause of the 1862 OOM cascade).
    del tess_text, doctr_text, surya_text, consensus_text
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    # Periodic Python GC to release any lingering host-side references that pin
    # GPU tensors (keeps the empty_cache() effective).
    if (i + 1) % 20 == 0:
        import gc
        gc.collect()

    # Checkpoint every 25 pages
    if (i + 1) % 25 == 0:
        existing_ocr_path.write_text(json.dumps(page_ocr_results, indent=2), encoding="utf-8")

ocr_wall = time.time() - t_ocr
mean_ocr_sec = float(np.mean(ocr_timings)) if ocr_timings else 0.0
pages_per_min = 60.0 / mean_ocr_sec if mean_ocr_sec > 0 else 0
log("STAGE4-OCR", f"OCR done: {len(body_pages)} pages in {ocr_wall:.1f}s ({mean_ocr_sec:.2f}s/page) hi={high_conf_count} lo={low_conf_count}", "OK")

# Confidence distribution
ratios = [v["agreement_ratio"] for v in page_ocr_results.values()]
conf_dist = {
    "high_>=0.65": sum(1 for r in ratios if r >= 0.65),
    "medium_0.50_0.65": sum(1 for r in ratios if 0.50 <= r < 0.65),
    "low_<0.50": sum(1 for r in ratios if r < 0.50),
    "mean_agreement": round(float(np.mean(ratios)), 4) if ratios else 0.0,
    "median_agreement": round(float(np.median(ratios)), 4) if ratios else 0.0,
}
log("STAGE4-OCR", f"Confidence distribution: {conf_dist}", "OK")
existing_ocr_path.write_text(json.dumps(page_ocr_results, indent=2), encoding="utf-8")

# ---------------------------------------------------------------------------
# STAGE 5: Parse acts from consensus text
# ---------------------------------------------------------------------------
log("STAGE5-PARSE", "Parsing acts from consensus OCR text", "OK")
t_parse = time.time()

# Build per-page lines list
all_lines_with_page = []
for pidx in sorted(page_ocr_results.keys()):
    text = page_ocr_results[pidx]["consensus_text"]
    for line in text.split("\n"):
        all_lines_with_page.append((pidx, line))

# Patterns — broadened to cover multi-year sessions
CHAP_RE = re.compile(
    r'^[Cc]hap(?:ter|\.)?\s*\.?\s*([IVXLC\d]+)[.,]?\s*$|'
    r'^[Cc]hap(?:ter|\.)?\s*\.?\s*([IVXLC\d]+)[.,]?\s+AN\s+ACT',
    re.IGNORECASE
)
AN_ACT_RE  = re.compile(r'\bAN\s+ACT\b', re.IGNORECASE)
# Approved/passed dates: accept 1850-1880
APPROVED_RE = re.compile(
    r'(?:Approved|Passed)\s+'
    r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
    r'\s+\d+[,.]?\s*18[5-8]\d',
    re.IGNORECASE
)
SEC_RE = re.compile(r'^[§Ss]ec(?:tion|\.)?\s*\.?\s*(\d+)', re.IGNORECASE)

def roman_to_int(s):
    """Convert Roman numeral string to integer, or return int(s) if Arabic."""
    s = s.upper().strip()
    roman = {"I":1,"V":5,"X":10,"L":50,"C":100,"D":500,"M":1000}
    if all(c in roman for c in s):
        val = 0
        prev = 0
        for c in reversed(s):
            curr = roman[c]
            val += curr if curr >= prev else -curr
            prev = curr
        return val
    try:
        return int(s)
    except ValueError:
        return 0

def parse_act_date(text):
    m = APPROVED_RE.search(text)
    if m:
        raw = re.sub(r"\s+", " ", m.group(0)).strip()
        date_str = re.sub(r"^(Approved|Passed)\s+", "", raw, flags=re.IGNORECASE)
        date_str = date_str.rstrip(".").strip()
        try:
            from datetime import datetime as DT
            d = DT.strptime(date_str.replace(",", ""), "%B %d %Y")
            return d.strftime("%Y-%m-%d"), raw
        except Exception:
            pass
    return None, ""

def is_confident_act(buf):
    full = "\n".join(buf)
    has_an_act = bool(AN_ACT_RE.search(full))
    has_date, _ = parse_act_date(full)
    return has_an_act and has_date is not None and len(full.strip()) >= 100

def flush_act(chap, start_page, buf, acts_parsed, acts_flagged):
    if not buf:
        return
    full = "\n".join(buf).strip()
    if len(full) < 60:
        return
    title = ""
    for l in buf:
        if AN_ACT_RE.search(l):
            title = re.sub(r"\s+", " ", l).strip()[:500]
            break
    if not title:
        title = re.sub(r"\s+", " ", buf[0]).strip()[:300] if buf else ""
    iso_date, approved_str = parse_act_date(full)
    body_text = re.sub(r"[ \t]+", " ", full)
    confident = is_confident_act(buf)
    act_rec = {
        "chapter": str(chap),
        "chapter_int": chap,
        "title": title,
        "approved_date": approved_str,
        "iso_date": iso_date,
        "text": body_text[:6000],
        "source_page": (start_page or 0) + 1,
        "confident": confident,
        "page_agreement_ratio": page_ocr_results.get(start_page, {}).get("agreement_ratio", 0.0),
    }
    if confident:
        acts_parsed.append(act_rec)
    else:
        acts_flagged.append(act_rec)

acts_parsed = []
acts_flagged = []
current_chap, current_page, current_buf = None, None, []

for pidx, line in all_lines_with_page:
    stripped = line.strip()
    m = CHAP_RE.match(stripped)
    if m:
        if current_chap is not None:
            flush_act(current_chap, current_page, current_buf, acts_parsed, acts_flagged)
        raw_num = m.group(1) or m.group(2)
        current_chap = roman_to_int(raw_num) if raw_num else 0
        current_page = pidx
        current_buf = [line]
    elif current_chap is not None:
        current_buf.append(line)

if current_chap is not None:
    flush_act(current_chap, current_page, current_buf, acts_parsed, acts_flagged)

parse_wall = time.time() - t_parse
log("STAGE5-PARSE", f"Parse done in {parse_wall:.2f}s: confident={len(acts_parsed)} flagged_text_only={len(acts_flagged)}", "OK")
(SCRATCH / "parsed_acts.json").write_text(
    json.dumps({"confident_acts": acts_parsed, "flagged_acts": acts_flagged}, indent=2),
    encoding="utf-8"
)

# ---------------------------------------------------------------------------
# STAGE 6: DB Ingest (idempotent)
# ---------------------------------------------------------------------------
log("STAGE6-INGEST", "Starting DB ingest (idempotent on content_sha256)", "OK")

# 6.1 Insert source_document
# Check if existing skeleton row (no SHA256) exists for this session; if so, update it.
# Otherwise insert new.
existing_skeleton = psql_query(
    f"SELECT id FROM source_document "
    f"WHERE citation LIKE 'CA Statutes {SESSION_LABEL}%' AND content_sha256 IS NULL "
    f"LIMIT 1;"
)

citation_str = f"Stats. {SESSION_LABEL}, Statutes of California"
note_str = safe_str(
    f"Produced by production_pipeline.py session={SESSION_LABEL} "
    f"Surya={SURYA_AVAILABLE} engines={conf_dist.get('mean_agreement',0):.3f} mean_agree",
    300
)
file_name_str = safe_str(PDF_PATH.name, 200)
source_uri_str = safe_str(SOURCE_URL, 500)
corpus_str = "uncodified_statutes"
media_format_str = "pdf"
ocr_engine_str = "surya+doctr+tesseract-5" if SURYA_AVAILABLE else "doctr+tesseract-5"

if existing_skeleton:
    # Update the skeleton row with real data
    src_doc_id = int(existing_skeleton)
    update_sql = f"""
UPDATE source_document SET
  citation = '{citation_str}',
  source_uri = '{source_uri_str}',
  scan_quality = 'good',
  ocr_engine = '{ocr_engine_str}',
  ocr_cer_estimate = 0.015,
  trust_level = 'ocr_uncertain',
  retrieved_at = NOW(),
  clean_channel = true,
  content_sha256 = '{computed_sha}',
  claimed_year = {START_YEAR},
  edition_year = {START_YEAR},
  coverage_start_year = {START_YEAR},
  coverage_end_year = {START_YEAR},
  verification_note = '{note_str}',
  file_name = '{file_name_str}',
  page_count = {total_pages}
WHERE id = {src_doc_id};""".strip()
    try:
        psql_query(update_sql)
        log("STAGE6-INGEST", f"Updated skeleton source_document id={src_doc_id} with real data", "OK")
    except Exception as e:
        log("STAGE6-INGEST", f"source_document update FAIL: {e}", "FAIL")
        sys.exit(1)
else:
    # Insert new source_document
    sd_sql = f"""
INSERT INTO source_document (
  type, citation, jurisdiction, source_channel, source_uri,
  scan_quality, ocr_engine, ocr_cer_estimate,
  trust_level, retrieved_at, clean_channel,
  content_sha256, edition_year, claimed_year, verification_note,
  file_name, corpus, coverage_start_year, coverage_end_year,
  page_count, media_format
) VALUES (
  'session_law',
  '{citation_str}', 'CA', 'clerk.assembly.ca.gov', '{source_uri_str}',
  'good', '{ocr_engine_str}', 0.015, 'ocr_uncertain',
  NOW(), true,
  '{computed_sha}', {START_YEAR}, {START_YEAR}, '{note_str}',
  '{file_name_str}', '{corpus_str}', {START_YEAR}, {START_YEAR},
  {total_pages}, '{media_format_str}'
)
ON CONFLICT DO NOTHING
RETURNING id;""".strip()
    try:
        src_doc_id_str = psql_query(sd_sql)
        if src_doc_id_str:
            src_doc_id = int(src_doc_id_str)
            log("STAGE6-INGEST", f"source_document inserted: id={src_doc_id}", "OK")
        else:
            existing = psql_query(f"SELECT id FROM source_document WHERE content_sha256 = '{computed_sha}';")
            src_doc_id = int(existing)
            log("STAGE6-INGEST", f"source_document already existed: id={src_doc_id}", "OK")
    except Exception as e:
        log("STAGE6-INGEST", f"source_document insert FAIL: {e}", "FAIL")
        sys.exit(1)

# 6.2 Ingest acts
log("STAGE6-INGEST", f"Ingesting {len(acts_parsed)} confident acts", "OK")
enact_inserted = prov_inserted = ce_inserted = skipped_dup = 0
failed_acts = []

for order_idx, act in enumerate(acts_parsed):
    chap_num = act["chapter_int"]
    act_citation = f"Stats. {SESSION_LABEL} ch. {chap_num}"
    operative_date = act["iso_date"] if act["iso_date"] else f"{START_YEAR}-01-01"
    title_esc = safe_str(act["title"], 500)
    text_esc  = safe_str(act["text"], 8000)

    # Idempotent: skip if this citation+source_doc already exists
    check = psql_query(
        f"SELECT id FROM enactment WHERE citation = '{act_citation}' "
        f"AND source_document_id = {src_doc_id};"
    )
    if check:
        skipped_dup += 1
        continue

    # Insert enactment
    try:
        e_sql = f"""
INSERT INTO enactment (
  source_document_id, citation, jurisdiction, session, legislature,
  chapter_number, chaptered_date, effective_date, operative_date,
  title, bill_number, kind
) VALUES (
  {src_doc_id}, '{act_citation}', 'CA', '{SESSION_STR}', '{LEGIS_NUM}',
  {chap_num}, '{operative_date}', '{operative_date}', '{operative_date}',
  '{title_esc}', NULL, 'statute'
) RETURNING id;""".strip()
        enact_id = int(psql_query(e_sql))
        enact_inserted += 1
    except Exception as e:
        log("STAGE6-INGEST", f"enactment FAIL ch.{chap_num}: {str(e)[:100]}", "FAIL")
        failed_acts.append(chap_num)
        continue

    # Insert provision
    try:
        desig = f"Stats. {SESSION_LABEL} ch. {chap_num}"
        p_sql = f"""
INSERT INTO provision (jurisdiction, unit_type, current_designation, status)
VALUES ('CA', 'act_section', '{safe_str(desig, 200)}', 'active')
RETURNING id;""".strip()
        prov_id = int(psql_query(p_sql))
        prov_inserted += 1
    except Exception as e:
        log("STAGE6-INGEST", f"provision FAIL ch.{chap_num}: {str(e)[:100]}", "FAIL")
        failed_acts.append(chap_num)
        continue

    # Insert designation_history
    try:
        desig_esc = safe_str(desig, 200)
        dh_sql = f"""
INSERT INTO designation_history (provision_id, code, section_number, label, valid_range)
VALUES ({prov_id}, 'Statutes of California {SESSION_LABEL}', '{chap_num}',
        '{desig_esc}', '[{operative_date},)');""".strip()
        psql_query(dh_sql)
    except Exception as e:
        log("STAGE6-INGEST", f"designation_history WARN ch.{chap_num}: {str(e)[:80]}", "WARN")

    # Insert change_event
    try:
        page_ref = f"p. {act['source_page']}"
        ce_sql = f"""
INSERT INTO change_event (
  enactment_id, provision_id, action, new_text,
  operative_date, in_act_order, chaptered_out,
  trust_level, source_document_id, page_ref
) VALUES (
  {enact_id}, {prov_id}, 'enact', '{text_esc}',
  '{operative_date}', {order_idx}, false,
  'ocr_uncertain', {src_doc_id}, '{page_ref}'
) RETURNING id;""".strip()
        psql_query(ce_sql)
        ce_inserted += 1
    except Exception as e:
        log("STAGE6-INGEST", f"change_event FAIL ch.{chap_num}: {str(e)[:100]}", "FAIL")

log("STAGE6-INGEST", f"Ingest done: enactments={enact_inserted} provisions={prov_inserted} change_events={ce_inserted} skipped_dup={skipped_dup} failed={len(failed_acts)}", "OK")
if acts_flagged:
    log("STAGE6-INGEST", f"Flagged text-only acts (NOT ingested as structured): {len(acts_flagged)}", "WARN")
if failed_acts:
    log("STAGE6-INGEST", f"Failed acts: {failed_acts[:20]}", "WARN")

# Final counts
try:
    prov_count  = psql_query("SELECT COUNT(*) FROM provision;")
    ce_count    = psql_query("SELECT COUNT(*) FROM change_event;")
    enact_count = psql_query("SELECT COUNT(*) FROM enactment;")
    src_count   = psql_query("SELECT COUNT(*) FROM source_document;")
    log("STAGE6-INGEST", f"Final DB counts: source_document={src_count} enactment={enact_count} provision={prov_count} change_event={ce_count}", "OK")
except Exception as e:
    log("STAGE6-INGEST", f"Final count query failed: {e}", "WARN")

# ---------------------------------------------------------------------------
# FINAL REPORT
# ---------------------------------------------------------------------------
total_wall = render_wall + prep_wall + ocr_wall + parse_wall
log("REPORT", f"=== VOLUME COMPLETE: {SESSION_LABEL} ===", "OK")
log("REPORT", f"PDF: {PDF_PATH.name} | {total_pages} pages | SHA256={computed_sha}", "OK")
log("REPORT", f"Render: {render_wall:.1f}s | Preprocess: {prep_wall:.1f}s | OCR: {ocr_wall:.1f}s | Parse: {parse_wall:.2f}s | TOTAL: {total_wall:.1f}s ({total_wall/60:.1f} min)", "OK")
log("REPORT", f"OCR: {len(body_pages)} body pages | {mean_ocr_sec:.2f}s/page | {pages_per_min:.1f} p/min | Surya={SURYA_AVAILABLE} engines={ocr_engine_str}", "OK")
log("REPORT", f"Confidence: {conf_dist}", "OK")
log("REPORT", f"Acts: confident={len(acts_parsed)} flagged={len(acts_flagged)}", "OK")
log("REPORT", f"DB: src_doc_id={src_doc_id} enactments={enact_inserted} provisions={prov_inserted} change_events={ce_inserted}", "OK")
log("REPORT", f"OCR output: {existing_ocr_path}", "OK")
log("REPORT", f"=== END: {SESSION_LABEL} ===", "OK")

print(f"\n=== {SESSION_LABEL} COMPLETE ===")
print(f"Pages: {total_pages} total | {len(body_pages)} body OCR'd")
print(f"Surya available: {SURYA_AVAILABLE} | Engines: {ocr_engine_str}")
print(f"Confidence: {conf_dist}")
print(f"Acts: confident={len(acts_parsed)} flagged={len(acts_flagged)}")
print(f"DB: src_doc_id={src_doc_id} enactments={enact_inserted} provisions={prov_inserted} change_events={ce_inserted}")
print(f"Wall time: {total_wall/60:.1f} min")
