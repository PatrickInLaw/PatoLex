"""
run_chapter_vision.py -- resolve the REVIEW chapter cases by READING THE SCAN.

For each act whose chapter number neither the OCR nor the sequence could resolve
(tier=REVIEW in chapter_corrections.tsv), load its source page image and ask a local
vision model (qwen2.5vl) to read the printed chapter heading. This is the ground
truth -- the actual numeral on the page.

Writes _vocab/chapter_vision_results.tsv (vol, in_act_order, chapter_raw, ocr_value,
vision_value, raw). Heartbeat run log. Free (5090 GPU).
"""
import os, sys, re, json, glob, time, base64, urllib.request
from datetime import datetime, timezone, timedelta
import config

ROOT    = config.path_for("data_root")
OUT_DIR = config.path_for("vocab_dir")
CORR    = os.path.join(OUT_DIR, "chapter_corrections.tsv")
OUT     = os.path.join(OUT_DIR, "chapter_vision_results.tsv")
LOG     = os.path.join(OUT_DIR, "chapter-vision-run.log")
OLLAMA  = "http://127.0.0.1:11434/api/chat"
MODEL   = os.environ.get("VIS_MODEL", "qwen2.5vl:latest")
LIMIT   = int(os.environ.get("VIS_LIMIT", "0"))   # 0 = all; >0 = smoke

def rlog(msg, status="OK"):
    z = timezone(timedelta(hours=-7))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now(timezone.utc).astimezone(z):%Y-%m-%d %H:%M PT}] {msg} | {status}\n")
    print(msg, flush=True)

def load_review_cases():
    cases = []
    with open(CORR, encoding="utf-8") as f:
        next(f, None)
        for ln in f:
            p = ln.rstrip("\n").split("\t")
            if len(p) >= 7 and p[5] == "REVIEW":
                cases.append({"vol": p[0], "in_act_order": int(p[1]),
                              "chapter_raw": p[2], "ocr": p[3], "reason": p[6]})
    return cases

_vol_cache = {}
def act_meta(vol, order):
    """Return (source_page, title) for an act by in_act_order, from parsed_acts_fixed.json."""
    if vol not in _vol_cache:
        path = os.path.join(ROOT, vol, "parsed_acts_fixed.json")
        idx = {}
        try:
            data = json.load(open(path, encoding="utf-8", errors="replace"))
            for a in list(data.get("confident_acts", [])) + list(data.get("flagged_acts", [])):
                idx[a.get("in_act_order")] = (a.get("source_page", 0), (a.get("title") or "")[:120])
        except Exception:
            pass
        _vol_cache[vol] = idx
    return _vol_cache[vol].get(order, (0, ""))

def img_b64(vol, source_page):
    # source_page is 1-indexed; image page file is 0-indexed page_<n:04d>.png
    n = max(0, source_page - 1)
    path = os.path.join(ROOT, vol, "pages_prep_gray", f"page_{n:04d}.png")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")

def ask_vision(b64, chapter_raw, title):
    prompt = (
        "This is a scanned page from a 19th-century California statutes book. Acts begin "
        "with a heading printed as 'CHAP. <Roman numeral>.' (for example 'CHAP. CCCLIV.'). "
        f"One act on this page is titled (approximately): \"{title}\". The OCR misread its "
        f"chapter heading numeral as '{chapter_raw}'. Look at the page, find that act's "
        "'CHAP.' heading, and read its chapter number. Reply with ONLY the number -- either an "
        "Arabic integer (e.g. 354) OR the Roman numeral exactly as printed (e.g. CCCLIV) -- or "
        "the single word UNKNOWN if you cannot read it clearly."
    )
    body = {"model": MODEL, "stream": False, "options": {"temperature": 0},
            "messages": [{"role": "user", "content": prompt, "images": [b64]}]}
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8")).get("message", {}).get("content", "")

_RV = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
def _roman(s):
    val = prev = 0
    for c in reversed(s.upper()):
        cur = _RV.get(c, 0)
        if cur == 0:
            return 0
        val += cur if cur >= prev else -cur
        prev = cur
    return val

def parse_int(text):
    if re.search(r"\bUNKNOWN\b", text, re.I):
        return None
    m = re.search(r"\d{1,4}", text)
    if m:
        return int(m.group(0))
    # accept a Roman numeral if the model answered in Roman
    rm = re.search(r"\b([IVXLCDM]{1,12})\b", text.upper())
    if rm:
        v = _roman(rm.group(1))
        return v if v > 0 else None
    return None

def main():
    rlog(f"START chapter vision model={MODEL}")
    cases = load_review_cases()
    if LIMIT:
        cases = cases[:LIMIT]
    rlog(f"{len(cases)} REVIEW cases to read")
    results = []
    read = unknown = noimg = 0
    t0 = time.time(); last = time.time()
    for i, c in enumerate(cases):
        sp, title = act_meta(c["vol"], c["in_act_order"])
        b64 = img_b64(c["vol"], sp)
        vis = None; raw = ""
        if b64 is None:
            noimg += 1; raw = "NO_IMAGE"
        else:
            for attempt in range(2):
                try:
                    raw = ask_vision(b64, c["chapter_raw"], title)
                    vis = parse_int(raw)
                    break
                except Exception as e:
                    if attempt == 1:
                        raw = f"ERR:{e}"
        if vis is not None: read += 1
        elif b64 is not None: unknown += 1
        results.append((c["vol"], c["in_act_order"], c["chapter_raw"], c["ocr"],
                        ("" if vis is None else vis), re.sub(r"\s+", " ", raw)[:120]))
        now = time.time()
        if now - last >= 15 or i + 1 == len(cases):
            rlog(f"{i+1}/{len(cases)} | read={read} unknown={unknown} no_image={noimg} | "
                 f"elapsed={now-t0:.0f}s | rate={(i+1)/max(now-t0,0.001):.2f}/s", "HEARTBEAT")
            last = now
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("vol\tin_act_order\tchapter_raw\tocr_value\tvision_value\traw_response\n")
        for r in results:
            f.write("\t".join(str(x) for x in r) + "\n")
    rlog(f"DONE read={read} unknown={unknown} no_image={noimg} of {len(cases)} | "
         f"-> {OUT} | wall={time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
