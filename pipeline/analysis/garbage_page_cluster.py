"""
garbage_page_cluster.py -- for the tokens Sonnet labeled GARBAGE in the Pass C
review tier, find WHERE they occur (which volume + page) across the OCR corpus,
to size an image-based (vision-model) resolution pass.

Reads the 5 Sonnet verdict files, filters verdict==GARBAGE -> token set.
Scans the 205 consensus JSON files; for each garbage token records total
occurrences and the set of distinct (volume,page) locations.

Outputs _vocab/garbage_locations.json + a summary (total occ, distinct pages,
clustering: how many pages you'd need to view to see 1 instance of every token,
and the most-clustered tokens). CPU-only, heartbeat run log.
"""
import os, sys, re, json, glob, time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import config

SCRATCH  = config.path_for("data_root")
OUT_DIR  = config.path_for("vocab_dir")
LOG_PATH = os.path.join(OUT_DIR, "garbage-cluster-run.log")
SONNET   = OUT_DIR  # dir holding review_sonnet_part*.json
OUT_JSON = os.path.join(OUT_DIR, "garbage_locations.json")

_TOK = re.compile(r"[A-Za-z\xc0-\xff]+")

def pt():
    try:
        z = timezone(timedelta(hours=-7))
        return datetime.now(timezone.utc).astimezone(z).strftime("%Y-%m-%d %H:%M PT")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

def rlog(phase, desc, status="OK"):
    line = f"[{pt()}] {phase} | {desc} | {status}\n"
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line); f.flush()
    print(line.rstrip()); sys.stdout.flush()

def load_garbage_tokens():
    toks = set()
    for p in sorted(glob.glob(os.path.join(SONNET, "review_sonnet_part*.json"))):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        for tok, v in d.items():
            if (v.get("verdict") or "").upper() == "GARBAGE":
                toks.add(tok.lower())
    return toks

def main():
    rlog("START", "garbage page-cluster scan")
    garbage = load_garbage_tokens()
    rlog("LOAD", f"{len(garbage)} GARBAGE tokens from Sonnet verdicts")

    occ = defaultdict(int)                 # token -> total occurrences
    pages = defaultdict(set)               # token -> set of (vol,page)
    page_garbage = defaultdict(set)        # (vol,page) -> set of garbage tokens present

    pattern = os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json")
    files = sorted(glob.glob(pattern))
    rlog("SCAN", f"{len(files)} consensus files")
    t0 = time.time(); last = time.time(); pagecount = 0

    for jf in files:
        vol = os.path.basename(os.path.dirname(os.path.dirname(jf)))
        try:
            with open(jf, encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except Exception:
            continue
        for pk, po in data.items():
            txt = (po.get("consensus_text") or "")
            if not txt:
                continue
            loc = (vol, pk)
            for m in _TOK.finditer(txt):
                w = m.group(0).lower()
                if w in garbage:
                    occ[w] += 1
                    pages[w].add(loc)
                    page_garbage[loc].add(w)
            pagecount += 1
            now = time.time()
            if now - last >= 15:
                rlog("SCAN", f"pages={pagecount:,} | hits={sum(occ.values()):,} | elapsed={now-t0:.0f}s", "HEARTBEAT")
                last = now

    # ---- summary ----
    total_occ = sum(occ.values())
    all_pages = set()
    for s in pages.values():
        all_pages |= s
    # greedy set-cover-ish: pages sorted by how many distinct garbage tokens they hold
    page_rank = sorted(page_garbage.items(), key=lambda kv: -len(kv[1]))
    covered = set(); cover_pages = 0
    for loc, toks in page_rank:
        new = toks - covered
        if new:
            covered |= new
            cover_pages += 1
        if len(covered) >= len(occ):
            break

    per_token = {t: {"occ": occ[t], "pages": len(pages[t])} for t in occ}
    out = {
        "n_garbage_tokens_found": len(occ),
        "n_garbage_tokens_unseen": len(garbage) - len(occ),
        "total_occurrences": total_occ,
        "distinct_pages_touched": len(all_pages),
        "min_pages_to_cover_all_tokens_once": cover_pages,
        "per_token": per_token,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)

    top = sorted(per_token.items(), key=lambda kv: -kv[1]["occ"])[:20]
    rlog("DONE",
         f"tokens_found={len(occ)}/{len(garbage)} | total_occ={total_occ:,} | "
         f"distinct_pages={len(all_pages):,} | min_pages_cover_all={cover_pages:,} | "
         f"wall={time.time()-t0:.0f}s")
    print("\n[TOP 20 garbage tokens by occ]  token  occ  on_n_pages")
    for t, d in top:
        print(f"   {t:24} {d['occ']:>6} {d['pages']:>6}")
    # distribution: tokens appearing on a single page (fully clustered)
    one_page = sum(1 for t in occ if len(pages[t]) == 1)
    le3 = sum(1 for t in occ if len(pages[t]) <= 3)
    print(f"\n[CLUSTERING] tokens on exactly 1 page: {one_page}/{len(occ)}  |  on <=3 pages: {le3}/{len(occ)}")
    sys.stdout.flush()

if __name__ == "__main__":
    main()
