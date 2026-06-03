"""
ocr_only_5090_sql.py -- SQL-pipeline replacement for ocr_only_5090.py.
=======================================================================
Accepts 3-root named args (--inbox/--midbox/--outbox) and --label/--pdf/--stage
so the SQL queue worker can invoke it without hardcoded paths.

Key differences from ocr_only_5090.py (the live production script -- DO NOT EDIT THAT):
  1. Named args (argparse) instead of positional sys.argv[1]/[2].
  2. SCRATCH root derived from --midbox (UNC-safe); LOG_FILE defaults to SCRATCH/ocr-script.log
     (per-volume, no cross-worker interleaving) or overridden via $PATOLEX_RUN_LOG.
  3. TESS_PATH from $PATOLEX_TESS_PATH env var (fallback = patolex-user default).
  4. PREP_COMPLETE marker written at end of --stage prep as an atomic rename.
     Defense-in-depth barrier: --stage ocr checks for the marker and exits rc=1 if absent.
     The SQL gate (prep_state='done' in the claim predicate) is the PRIMARY prevention;
     this is a last-resort check only.
  5. --stage ocr skips STAGES 1-3 (they already ran during prep). Instead:
       - page_classification.json loaded from SCRATCH to recover body_pages.
       - total_pages loaded from JSON (prep stored it there); sha256 read from sha256.txt.
       - No fitz.open() in ocr mode, eliminating the PDF re-read cost.
  6. On OCR completion, page_ocr_results.json + page_classification.json are copied to
     --outbox/<label>/ (atomic: write-to-tmp then replace, with retry on OSError).
  7. --stage all: current coupled behavior. PREP_COMPLETE IS written in all mode too
     (the marker reflects real prep state regardless of whether OCR follows immediately).

Preprocessing functions are at module level and MUST remain byte-for-byte identical to
the same functions in ocr_only_5090.py. Do not diverge from that file without syncing both.

Usage (queue worker invocation):
    python ocr_only_5090_sql.py --label <label> --pdf <pdf_path>
        --midbox <midbox_root> --outbox <outbox_root> [--inbox <inbox_root>]
        --stage prep|ocr|all

Local testing (local paths, no UNC needed):
    python ocr_only_5090_sql.py --label test_vol --pdf C:\\path\\to\\vol.pdf
        --midbox C:\\scratch --outbox C:\\outbox --stage all
"""

import argparse
import sys
import os
import re
import json
import time
import hashlib
import shutil
import datetime
import gc
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Parse args -- must happen before any other work so paths are defined.
# ---------------------------------------------------------------------------
_ap = argparse.ArgumentParser(description="SQL-pipeline OCR worker script (replacement for ocr_only_5090.py)")
_ap.add_argument("--label",   required=True,  help="volume label, e.g. statutes_1877_001")
_ap.add_argument("--pdf",     required=True,  help="full path to input PDF (local or UNC)")
_ap.add_argument("--midbox",  required=True,  help="root of the midbox share (per-vol scratch lives here)")
_ap.add_argument("--outbox",  required=True,  help="root of the outbox share (completed vols land here)")
_ap.add_argument("--inbox",   default="",     help="root of the inbox share (informational; PDF already resolved)")
_ap.add_argument("--stage",   default="all",  choices=["prep", "ocr", "all"],
                 help="prep=STAGES 0-3 only; ocr=STAGE4 only (SQL gate is primary guard); all=both (default)")
_ARGS = _ap.parse_args()

SESSION_LABEL  = _ARGS.label.strip()
PDF_PATH       = Path(_ARGS.pdf)
STAGE          = _ARGS.stage

SCRATCH        = Path(_ARGS.midbox) / f"production-{SESSION_LABEL}"
OUTBOX_VOL     = Path(_ARGS.outbox) / SESSION_LABEL
PAGES_DIR      = SCRATCH / "pages_raw"
PREP_GRAY_DIR  = SCRATCH / "pages_prep_gray"
OCR_OUT_DIR    = SCRATCH / "ocr_consensus"
PREP_MARKER    = SCRATCH / "PREP_COMPLETE"

TESS_PATH      = os.environ.get("PATOLEX_TESS_PATH",
                                r"C:\Users\patolex\AppData\Local\Tesseract-OCR\tesseract.exe")
PRODUCTION_DPI = 300

# Per-volume log (no cross-worker interleaving). Supervisor may override via env.
_log_env = os.environ.get("PATOLEX_RUN_LOG", "")
LOG_FILE = Path(_log_env) if _log_env else (SCRATCH / "ocr-script.log")

for d in [SCRATCH, PAGES_DIR, PREP_GRAY_DIR, OCR_OUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)
# Ensure parent exists for LOG_FILE (if it lives outside SCRATCH).
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log(phase, description, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    entry = f"[{ts}] [{SESSION_LABEL}] {phase} | {description} | {status}\n"
    with open(str(LOG_FILE), "a", encoding="utf-8") as f:
        f.write(entry)
    print(entry.strip(), flush=True)


# ---------------------------------------------------------------------------
# Preprocessing functions -- at module level, identical to ocr_only_5090.py.
# DO NOT change these without syncing the live production script.
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


def ink_density(img_path):
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0
    return float((img < 128).sum()) / (img.shape[0] * img.shape[1])


def detect_body_start(total_pages, prep_dir):
    densities = []
    for pidx in range(min(80, total_pages)):
        p = prep_dir / f"page_{pidx:04d}.png"
        densities.append(ink_density(p) if p.exists() else 0.0)
    mid = [densities[i] for i in range(min(10, len(densities)), min(40, len(densities)))
           if densities[i] > 0.005]
    if not mid:
        return 30
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


# ---------------------------------------------------------------------------
# Validate PDF exists (all modes need it in prep/all; ocr uses stored sha256.txt).
# In pure ocr mode we skip fitz.open entirely -- prep already rendered all pages.
# ---------------------------------------------------------------------------
if STAGE in ("prep", "all") and not PDF_PATH.exists():
    log("INIT", f"PDF not found: {PDF_PATH}", "FAIL")
    sys.exit(1)

# Defense-in-depth barrier for ocr mode.
# The SQL gate (prep_state='done' in the claim predicate) is the primary guard.
# This check exists in case the gate was somehow bypassed; treat as a normal failure
# so the worker increments attempts and eventually dead-letters for investigation.
if STAGE == "ocr" and not PREP_MARKER.exists():
    log("BARRIER", f"PREP_COMPLETE marker missing at {PREP_MARKER} -- SQL gate should have prevented this claim", "FAIL")
    sys.exit(1)

log("OCR5090-SQL", f"=== START stage={STAGE} label={SESSION_LABEL} pdf={PDF_PATH.name} ===", "OK")

# ---------------------------------------------------------------------------
# STAGES 0-3: prep and all modes only.
# In ocr mode, classification is loaded from the JSON written by prep (below).
# ---------------------------------------------------------------------------
if STAGE in ("prep", "all"):
    # STAGE 0: SHA256 + page count.
    import fitz
    h = hashlib.sha256()
    with open(str(PDF_PATH), "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    computed_sha = h.hexdigest()
    (SCRATCH / "sha256.txt").write_text(computed_sha, encoding="utf-8")
    log("STAGE0", f"SHA256={computed_sha}", "OK")

    doc = fitz.open(str(PDF_PATH))
    total_pages = doc.page_count
    log("STAGE0", f"PDF opened: {total_pages} pages", "OK")

    # STAGE 1: Render at 300 DPI (grayscale).
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
        if pidx % 100 == 0:
            log("STAGE1-RENDER", f"page {pidx+1}/{total_pages}", "OK")
    render_wall = time.time() - t_render
    log("STAGE1-RENDER", f"Render done in {render_wall:.1f}s ({render_wall/total_pages:.2f}s/page)", "OK")
    doc.close()

    # STAGE 2: v2-grayscale preprocess.
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

    # STAGE 3: Body classification.
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

    # Atomic publish: write JSON then PREP_COMPLETE.
    # PREP_COMPLETE must appear AFTER the JSON is fully committed (ordering is critical).
    _cls = SCRATCH / "page_classification.json"
    _cls_tmp = _cls.with_suffix(".json.tmp")
    _cls_tmp.write_text(json.dumps({
        "body_start_idx": BODY_START_IDX,
        "total_pages": total_pages,      # stored so ocr mode avoids fitz.open
        "front_matter": [p+1 for p in FRONT_MATTER_RANGE],
        "body": [p+1 for p in body_pages],
        "index": [p+1 for p in index_pages],
        "empty": [p+1 for p in empty_pages],
        "median_body_density": median_density,
    }, indent=2), encoding="utf-8")
    _cls_tmp.replace(_cls)    # JSON fully committed before marker appears

    _prep_tmp = PREP_MARKER.with_suffix(".tmp")
    _prep_tmp.write_text(datetime.datetime.utcnow().isoformat(), encoding="utf-8")
    _prep_tmp.replace(PREP_MARKER)
    log("STAGE3-CLASSIFY", "page_classification.json + PREP_COMPLETE written (atomic)", "OK")

    if STAGE == "prep":
        log("PREP-DONE", "STAGES 0-3 complete (render/preprocess/classify/PREP_COMPLETE) -- exiting before OCR", "OK")
        sys.exit(0)

# ---------------------------------------------------------------------------
# OCR mode: skip STAGES 0-3; load what prep wrote.
# No fitz.open -- total_pages comes from JSON; sha256 read from sha256.txt.
# ---------------------------------------------------------------------------
if STAGE == "ocr":
    _cls_path = SCRATCH / "page_classification.json"
    # Retry briefly: on UNC paths, SMB client cache can briefly show an absent file
    # even after the prep worker's atomic rename is complete on the source machine.
    for _attempt in range(4):
        if _cls_path.exists():
            break
        if _attempt < 3:
            log("BARRIER", f"page_classification.json not visible yet (SMB cache?), retry {_attempt+1}/4", "WARN")
            time.sleep(8)
    else:
        log("BARRIER", f"page_classification.json still absent after 4 attempts at {_cls_path}", "FAIL")
        sys.exit(1)

    try:
        _cls_data = json.loads(_cls_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log("BARRIER", f"page_classification.json unreadable: {e}", "FAIL")
        sys.exit(1)

    body_pages = [p - 1 for p in _cls_data["body"]]    # JSON stores 1-indexed; convert to 0-indexed
    total_pages = _cls_data.get("total_pages", 0)

    _sha_path = SCRATCH / "sha256.txt"
    if not _sha_path.exists():
        log("BARRIER", f"sha256.txt missing at {_sha_path} -- prep did not complete cleanly", "FAIL")
        sys.exit(1)
    computed_sha = _sha_path.read_text(encoding="utf-8").strip()

    log("STAGE3-SKIP", f"Loaded classification: {len(body_pages)} body pages, "
        f"total_pages={total_pages} sha={computed_sha[:12]}... (prep already ran)", "OK")

# ---------------------------------------------------------------------------
# STAGE 4: OCR -- Surya + docTR + Tesseract consensus (identical to ocr_only_5090.py).
# ---------------------------------------------------------------------------
log("STAGE4-OCR", "Loading docTR model (GPU)", "OK")
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
import torch

doctr_model = ocr_predictor(pretrained=True)
if torch.cuda.is_available():
    doctr_model = doctr_model.cuda()
    log("STAGE4-OCR", f"docTR on GPU: {torch.cuda.get_device_name(0)}", "OK")
    torch.cuda.reset_peak_memory_stats()
else:
    log("STAGE4-OCR", "docTR on CPU (no GPU) -- ABORT, 5090 expected", "FAIL")
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
log("OCR5090-SQL", f"PEAK VRAM: allocated={peak_alloc_mb:.0f}MB reserved={peak_resv_mb:.0f}MB "
    f"(GPU {torch.cuda.get_device_name(0)})", "OK")

# ---------------------------------------------------------------------------
# Publish to outbox: page_ocr_results.json + page_classification.json.
# write-to-tmp then replace; retry on OSError (UNC rename can fail transiently
# if ingest has the file open; OCR work is done so a retry is safe).
# Two-file atomicity: OUTBOX_COMPLETE marker is written ONLY after both files
# succeed. Ingest must wait for OUTBOX_COMPLETE before reading the pair.
# Exit rc=1 if any file fails all retries (queue worker will mark_failed; on
# re-run OCR resumes from the checkpoint and re-publishes to outbox).
# ---------------------------------------------------------------------------
OUTBOX_VOL.mkdir(parents=True, exist_ok=True)
_outbox_fail = False
for src_path, dest_name in [
    (existing_ocr_path,                    "page_ocr_results.json"),
    (SCRATCH / "page_classification.json", "page_classification.json"),
]:
    if not src_path.exists():
        log("OUTBOX", f"{dest_name} not found at {src_path} -- skipped", "WARN")
        _outbox_fail = True
        continue
    dest = OUTBOX_VOL / dest_name
    tmp  = dest.with_suffix(".tmp")
    _published = False
    for _r in range(3):
        try:
            shutil.copy2(str(src_path), str(tmp))
            tmp.replace(dest)
            log("OUTBOX", f"published {dest_name} -> {dest}", "OK")
            _published = True
            break
        except OSError as e:
            if _r == 2:
                log("OUTBOX", f"failed to publish {dest_name} after 3 tries: {e}", "FAIL")
            else:
                log("OUTBOX", f"publish {dest_name} OSError retry {_r+1}/3: {e}", "WARN")
                time.sleep(5)
    if not _published:
        _outbox_fail = True

if _outbox_fail:
    log("OUTBOX", "one or more outbox files failed to publish -- exiting rc=1 so worker retries", "FAIL")
    sys.exit(1)

# Both files published; write atomically so ingest sees a complete pair.
_marker = OUTBOX_VOL / "OUTBOX_COMPLETE"
_marker_tmp = _marker.with_suffix(".tmp")
_marker_tmp.write_text(datetime.datetime.utcnow().isoformat(), encoding="utf-8")
_marker_tmp.replace(_marker)
log("OUTBOX", f"OUTBOX_COMPLETE written -> {_marker}", "OK")

log("OCR5090-SQL", f"=== OCR-ONLY-SQL COMPLETE: {SESSION_LABEL} | sha={computed_sha} | "
    f"body={len(body_pages)} total={total_pages} | outbox={OUTBOX_VOL} ===", "OK")

_vol_ppm = (len(body_pages) / (ocr_wall / 60.0)) if ocr_wall > 0 else 0.0
log("VOLUME", f"{SESSION_LABEL} | {len(body_pages)} pages | {ocr_wall:.0f}s | "
    f"{_vol_ppm:.1f} pages/min | card=5090 workers=auto", "OK")

print(f"\n=== {SESSION_LABEL} OCR-ONLY-SQL COMPLETE ===")
print(f"Pages: {total_pages} total | {len(body_pages)} body OCR'd")
print(f"Surya: {SURYA_AVAILABLE} | mean agreement: {conf_dist['mean_agreement']}")
print(f"PEAK VRAM: allocated={peak_alloc_mb:.0f}MB reserved={peak_resv_mb:.0f}MB")
print(f"Throughput: {pages_per_min:.1f} pages/min")
print(f"Output: {existing_ocr_path}")
print(f"Outbox: {OUTBOX_VOL}")
print(f"SHA256: {computed_sha}")
