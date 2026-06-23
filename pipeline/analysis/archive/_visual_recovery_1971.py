"""
Visual recovery script for 1971 missing chapters.
Reads OCR consensus to locate acts, reads page images to confirm chapter numbers.
Writes parsed_acts_visual.json per volume + run log.
NO DB writes. NO overwrites. Additive only.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

# ---- Configuration ----
YEAR = 1971
MANIFEST_PATH = r"C:\PatoLex-scratch\_manifest_1971.json"
VOL_BASE = r"C:\PatoLex-scratch"
LOG_PATH = r"C:\GitHub\PatoLex\docs\80_PROJECT_HISTORY\run-logs\visual-1971-run.log"

# Pacific time offset (PDT = UTC-7 in June)
def now_pt():
    from datetime import timezone, timedelta
    return datetime.now(timezone(timedelta(hours=-7))).strftime("%Y-%m-%d %H:%M PT")

def log(msg):
    line = f"[{now_pt()}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ---- Helpers ----
ACT_START_RE = re.compile(
    r"(?:the\s+people\s+of\s+the\s+state\s+of\s+california\s+do\s+enact|"
    r"\[approved\s+\w+\s+\d+|"
    r"approved\s+\w+\s+\d+\s*,\s*19\d\d)",
    re.IGNORECASE
)
CHAPTER_HEADER_RE = re.compile(r"CHAPTER\s+(\d+)", re.IGNORECASE)

def load_ocr(vol_path):
    """Load OCR consensus dict {str(page_num): entry}"""
    ocr_file = os.path.join(vol_path, "ocr_consensus", "page_ocr_results.json")
    with open(ocr_file, "r", encoding="utf-8") as f:
        return json.load(f)

def get_ocr_text(ocr_data, source_page):
    """Get consensus text for a given source_page (1-indexed = OCR key)."""
    entry = ocr_data.get(str(source_page), {})
    if isinstance(entry, dict):
        return entry.get("consensus_text", "") or entry.get("tess_text", "")
    return str(entry) if entry else ""

def image_path(vol_path, source_page):
    """Return path to raw page image for source_page."""
    return os.path.join(vol_path, "pages_raw", f"page_{source_page-1:04d}.png")

def read_image(img_path):
    """Read image and return it (for visual inspection in multimodal context)."""
    return img_path  # caller will use Read tool

def find_act_starts_in_range(ocr_data, page_range):
    """
    Scan pages in page_range for act-start signatures.
    Returns list of (source_page, position_in_text, snippet) for each act start found.
    Also returns chapter headers found: list of (source_page, chapter_num, snippet).
    """
    act_starts = []
    chapter_headers = []

    lo, hi = min(page_range), max(page_range)
    for sp in range(lo, hi + 1):
        txt = get_ocr_text(ocr_data, sp)
        if not txt:
            continue
        # Find chapter headers
        for m in CHAPTER_HEADER_RE.finditer(txt):
            ch_num = int(m.group(1))
            chapter_headers.append((sp, ch_num, txt[max(0,m.start()-10):m.start()+60].replace('\n',' ')))
        # Find act starts
        for m in ACT_START_RE.finditer(txt):
            act_starts.append((sp, m.start(), txt[max(0,m.start()-20):m.start()+80].replace('\n',' ')))

    return act_starts, chapter_headers

# ---- Main Recovery Logic ----
def recover_chapter(target_ch, lo_ch, lo_page, hi_ch, hi_page, page_range, vol_path, ocr_data):
    """
    Attempt to recover a single missing chapter via OCR + image read.
    Returns a result dict.
    """
    lo, hi = min(page_range), max(page_range)

    # Step 1: Find chapter headers in the page range via OCR
    _, chapter_headers = find_act_starts_in_range(ocr_data, page_range)

    # Filter to headers near target_ch
    candidates = [(sp, ch, snip) for sp, ch, snip in chapter_headers
                  if abs(ch - target_ch) <= 2]

    exact = [(sp, ch, snip) for sp, ch, snip in candidates if ch == target_ch]

    if exact:
        sp, ch, snip = exact[0]
        img = image_path(vol_path, sp)
        return {
            "found_in_ocr": True,
            "source_page": sp,
            "printed_chapter": ch,
            "snip": snip,
            "img_path": img,
            "needs_image_verify": True
        }

    # If not exact, return all nearby for manual inspection
    return {
        "found_in_ocr": False,
        "nearby_headers": candidates,
        "all_headers_in_range": chapter_headers,
        "source_page": None,
        "img_path": None,
        "needs_image_verify": True
    }

def main():
    log(f"VISUAL-RECOVERY 1971 | START | Loading manifest")

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    missing = manifest["missing"]
    log(f"VISUAL-RECOVERY 1971 | MANIFEST | {len(missing)} missing chapters loaded")

    # Group missing by volume
    by_vol = {}
    for item in missing:
        v = item["vol"]
        by_vol.setdefault(v, []).append(item)

    log(f"VISUAL-RECOVERY 1971 | VOLUMES | {list(by_vol.keys())}")

    # Load OCR data for each volume
    ocr_by_vol = {}
    for vol_name in by_vol:
        vol_path = os.path.join(VOL_BASE, vol_name)
        ocr_by_vol[vol_name] = load_ocr(vol_path)
        log(f"VISUAL-RECOVERY 1971 | OCR LOADED | {vol_name} ({len(ocr_by_vol[vol_name])} pages)")

    # Process each missing chapter
    results_by_vol = {v: [] for v in by_vol}

    for item in missing:
        ch = item["chapter"]
        vol = item["vol"]
        vol_path = os.path.join(VOL_BASE, vol)
        ocr_data = ocr_by_vol[vol]
        page_range = item["page_range"]
        lo_ch = item["lo_ch"]
        hi_ch = item["hi_ch"]
        lo_page = item["lo_page"]
        hi_page = item["hi_page"]

        log(f"VISUAL-RECOVERY 1971 | SCANNING | ch={ch} pages={min(page_range)}-{max(page_range)} vol={vol}")

        info = recover_chapter(ch, lo_ch, lo_page, hi_ch, hi_page, page_range, vol_path, ocr_data)
        info["target_chapter"] = ch
        info["vol"] = vol
        results_by_vol[vol].append(info)

    log(f"VISUAL-RECOVERY 1971 | OCR SCAN COMPLETE | Writing intermediate results")

    # Save intermediate scan results
    scan_out = os.path.join(VOL_BASE, "_scan_results_1971.json")
    with open(scan_out, "w", encoding="utf-8") as f:
        json.dump(results_by_vol, f, indent=2)
    log(f"VISUAL-RECOVERY 1971 | SCAN SAVED | {scan_out}")

    # Print summary
    total = len(missing)
    found_in_ocr = sum(1 for v in results_by_vol.values() for r in v if r.get("found_in_ocr"))
    not_found = total - found_in_ocr
    log(f"VISUAL-RECOVERY 1971 | OCR SUMMARY | total={total} found_in_ocr={found_in_ocr} not_found_in_ocr={not_found}")

    return results_by_vol

if __name__ == "__main__":
    main()
