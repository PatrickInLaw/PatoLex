"""
substitution_sample.py -- Path 2 step 1: draw a STRATIFIED RANDOM sample of text
windows from the OCR corpus, to measure the real-word->real-word substitution rate
(the class vocab-diff is blind to: State->Slate, fight->light, wrong digits, inserted
margin words). Sample, don't sweep.

Output: _vocab/substitution_sample.jsonl  -- one window per line:
  {"id", "vol", "era", "page", "nwords", "text"}
Deterministic (fixed seed). ~N windows of ~WORDS_PER_WIN consecutive words, stratified
across eras so the OCR-heavy older volumes are well represented.
"""
import os, sys, re, json, glob, random
from datetime import datetime, timezone, timedelta
import config

SCRATCH = config.path_for("data_root")
OUT_DIR = config.path_for("vocab_dir")
OUT     = os.path.join(OUT_DIR, "substitution_sample.jsonl")
LOG     = os.path.join(OUT_DIR, "substitution-sample-run.log")

TARGET_TOTAL  = int(os.environ.get("SUB_SAMPLE_N", "500"))
WORDS_PER_WIN = 80
MIN_PAGE_WORDS = 150
SEED = 20260611

WORD = re.compile(r"\S+")

def rlog(msg):
    z = timezone(timedelta(hours=-7))
    line = f"[{datetime.now(timezone.utc).astimezone(z):%Y-%m-%d %H:%M PT}] {msg}\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.rstrip()); sys.stdout.flush()

def era_of(vol):
    m = re.search(r"production-(\d{4})", vol)
    if not m:
        return "unknown"
    y = int(m.group(1))
    if y <= 1900: return "<=1900"
    if y <= 1950: return "1901-1950"
    if y <= 1999: return "1951-1999"
    return ">=2000"

def main():
    rlog(f"START substitution sampler target={TARGET_TOTAL} win={WORDS_PER_WIN}w seed={SEED}")
    files = sorted(glob.glob(os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json")))
    pool = {}   # era -> list of (vol, page, words)
    for jf in files:
        vol = os.path.basename(os.path.dirname(os.path.dirname(jf)))
        era = era_of(vol)
        try:
            data = json.load(open(jf, encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for pk, po in data.items():
            txt = (po.get("consensus_text") or "")
            words = WORD.findall(txt)
            if len(words) >= MIN_PAGE_WORDS:
                pool.setdefault(era, []).append((vol, pk, words))
    rlog("pool sizes: " + ", ".join(f"{e}={len(v):,}" for e, v in sorted(pool.items())))

    rng = random.Random(SEED)
    eras = [e for e in ["<=1900", "1901-1950", "1951-1999", ">=2000"] if pool.get(e)]
    per = max(1, TARGET_TOTAL // len(eras)) if eras else 0
    sample = []
    sid = 0
    for era in eras:
        cand = pool[era]
        rng.shuffle(cand)
        for (vol, pk, words) in cand[:per]:
            maxstart = max(0, len(words) - WORDS_PER_WIN)
            start = rng.randint(0, maxstart)
            win = words[start:start + WORDS_PER_WIN]
            sample.append({"id": sid, "vol": vol, "era": era, "page": pk,
                           "nwords": len(win), "text": " ".join(win)})
            sid += 1

    with open(OUT, "w", encoding="utf-8") as f:
        for row in sample:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    total_words = sum(r["nwords"] for r in sample)
    by_era = {}
    for r in sample:
        by_era[r["era"]] = by_era.get(r["era"], 0) + 1
    rlog(f"DONE sample={len(sample)} windows  total_words={total_words:,}  by_era={by_era}  -> {OUT}")

if __name__ == "__main__":
    main()
