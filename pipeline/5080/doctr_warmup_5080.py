"""
docTR standalone warm-up / hang diagnostic for the RTX 5080.

Goal: determine WHERE ocr_predictor(pretrained=True) stalls and prove docTR
can load + OCR one page on the 5080. Offline env vars are set BEFORE any
torch / doctr / huggingface import so no network round-trip can stall load.

Usage:
    python doctr_warmup_5080.py <test_page_png>
"""
import os
import sys
import time

# --- CRITICAL: set offline + cache env BEFORE importing torch/doctr/hf ---
os.environ.setdefault("DOCTR_CACHE_DIR", os.path.join(os.path.expanduser("~"), ".cache", "doctr"))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["DOCTR_MULTIPROCESSING_DISABLE"] = "TRUE"
# USE_TORCH tells docTR to skip the TensorFlow backend probe entirely
os.environ["USE_TORCH"] = "1"

def stamp(msg):
    print(f"[{time.strftime('%H:%M:%S')}] +{time.time()-T0:6.1f}s  {msg}", flush=True)

T0 = time.time()
stamp("START warm-up (env set: HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE/USE_TORCH=1)")

import torch
stamp(f"torch {torch.__version__} imported; cuda={torch.cuda.is_available()}")
if torch.cuda.is_available():
    stamp(f"device = {torch.cuda.get_device_name(0)}")

from doctr.io import DocumentFile
from doctr.models import ocr_predictor
import doctr
stamp(f"doctr {doctr.__version__} imported")

# Load the predictor. assume_straight_pages + disable_page_orientation/
# disable_crop_orientation skip the extra MobileNet orientation classifiers,
# which are a separate set of weights docTR otherwise tries to fetch -- a
# prime suspect for the offline stall.
stamp("Calling ocr_predictor(pretrained=True) ...")
try:
    model = ocr_predictor(
        det_arch="fast_base",
        reco_arch="crnn_vgg16_bn",
        pretrained=True,
        assume_straight_pages=True,
        disable_page_orientation=True,
        disable_crop_orientation=True,
    )
    stamp("ocr_predictor RETURNED (no hang)")
except TypeError:
    # Older docTR signature without the orientation kwargs
    stamp("orientation kwargs unsupported on this docTR; retrying minimal")
    model = ocr_predictor(det_arch="fast_base", reco_arch="crnn_vgg16_bn", pretrained=True)
    stamp("ocr_predictor RETURNED (minimal, no hang)")

if torch.cuda.is_available():
    model = model.cuda()
    stamp("model.cuda() done")
    torch.cuda.synchronize()
    stamp(f"VRAM after load: {torch.cuda.memory_allocated()/1e9:.3f} GB alloc, "
          f"{torch.cuda.memory_reserved()/1e9:.3f} GB reserved")

# OCR one test page
test_png = sys.argv[1] if len(sys.argv) > 1 else None
if test_png and os.path.exists(test_png):
    stamp(f"OCR test page: {test_png}")
    docfile = DocumentFile.from_images(test_png)
    with torch.inference_mode():
        result = model(docfile)
    nlines = sum(len(b.lines) for p in result.pages for b in p.blocks)
    stamp(f"OCR done: {nlines} lines on page")
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        stamp(f"PEAK VRAM during page: {torch.cuda.max_memory_allocated()/1e9:.3f} GB")
    # show a few sample lines as a sanity check
    sample = []
    for p in result.pages:
        for b in p.blocks:
            for ln in b.lines:
                sample.append(" ".join(w.value for w in ln.words))
    print("--- SAMPLE (first 5 lines) ---", flush=True)
    for s in sample[:5]:
        print("   ", s, flush=True)
else:
    stamp("No valid test page provided; load-only test complete")

stamp("WARM-UP COMPLETE -- docTR loads + runs on 5080")
