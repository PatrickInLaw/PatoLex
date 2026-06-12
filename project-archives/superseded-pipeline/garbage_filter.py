"""
garbage_filter.py -- procedurally classify the post-cascade FLAGGED tokens into GUARANTEED
structural garbage (illegible OCR -> re-OCR territory) vs RECOVERABLE residual. High precision:
only structural signals that no real word exhibits, applied ONLY to already-flagged (unknown)
tokens, so a real rare word is never mislabeled.

Reads the cascade's autocorrect-stage output (_cascade/out_autocorrect/{vol}.json). Reports the
garbage vs recoverable split corpus-wide + per volume. Does NOT modify text.

Output: _cascade/garbage_report.json  +  _cascade/garbage_per_volume.tsv
"""
import os, sys, re, json, glob, time
from collections import Counter
import multiprocessing as mp

SCRATCH = r"C:\Users\patolex\PatoLex-scratch"
CASCADE = os.path.join(SCRATCH, "_cascade")
STAGE_OUT = os.path.join(CASCADE, "out_autocorrect")
VOWELS = set("aeiouy")
_REPEAT3 = re.compile(r"(.)\1\1")                          # 3+ same char in a row
_CONS5   = re.compile(r"[bcdfghjklmnpqrstvwxz]{5,}")       # 5+ consonants in a row
_ROMAN   = re.compile(r"^[ivxlcdm]+$")                     # valid roman numeral charset

def classify(t):
    """roman (valid numeral) | garbage:<rule> (unrecoverable) | recoverable (everything else flagged)."""
    if _ROMAN.match(t) and len(t) >= 2:
        return "roman"                                     # chapter/section numeral -- NOT an error
    if _REPEAT3.search(t): return "garbage:repeat3"        # eeee / llll / char salad
    if _CONS5.search(t): return "garbage:cons5"            # consonant salad
    if len(t) >= 5 and not (set(t) & VOWELS): return "garbage:novowel"
    if len(t) >= 25: return "garbage:toolong"
    return "recoverable"                                   # typos/fragments/rare words/single-mojibake

_WS = None; _HASWF = False; _WF = None
def _init():
    global _WS, _HASWF, _WF
    from correction_passes import build_dictionary
    ws, _spell, has_wf, wf = build_dictionary()
    _WS = frozenset(ws); _HASWF = has_wf; _WF = wf
def known(t): return (t in _WS) or (_HASWF and _WF(t, "en") > 0)

def _process(vol_file):
    vol = os.path.basename(vol_file)[:-5]
    try:
        d = json.load(open(vol_file, encoding="utf-8"))
    except Exception:
        return None
    flagged = 0; cat = Counter(); ex = {}
    for pk, lines in d.items():
        for toks in lines:
            for t in toks:
                if len(t) >= 2 and not known(t):
                    flagged += 1
                    c = classify(t)
                    cat[c] += 1
                    ex.setdefault(c, [])
                    if len(ex[c]) < 4 and t not in ex[c]: ex[c].append(t)
    garbage = sum(v for k, v in cat.items() if k.startswith("garbage"))
    roman = cat.get("roman", 0)
    return {"vol": vol, "flagged": flagged, "garbage": garbage, "roman": roman,
            "recoverable": cat.get("recoverable", 0), "by_cat": dict(cat), "ex": ex}

def main():
    files = sorted(glob.glob(os.path.join(STAGE_OUT, "*.json")))
    print(f"{len(files)} post-cascade volumes", flush=True)
    if not files:
        print("no cascade output found -- run correction_cascade.py first"); return
    nw = max(2, min(12, (os.cpu_count() or 4) - 2))
    tot = Counter(); cats = Counter(); examples = {}; perv = []; done = 0; t0 = time.time()
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw, initializer=_init) as pool:
        for r in pool.imap_unordered(_process, files, chunksize=1):
            done += 1
            if r:
                for k in ("flagged", "garbage", "roman", "recoverable"): tot[k] += r[k]
                cats.update(r["by_cat"])
                for g, lst in r["ex"].items():
                    examples.setdefault(g, [])
                    for w in lst:
                        if len(examples[g]) < 12 and w not in examples[g]: examples[g].append(w)
                perv.append(r)
            if done % 40 == 0 or done == len(files):
                print(f"  {done}/{len(files)} vols | {time.time()-t0:.0f}s", flush=True)
    fl = tot["flagged"]; ga = tot["garbage"]; ro = tot["roman"]; rc = tot["recoverable"]
    report = {"flagged": fl, "garbage": ga, "roman": ro, "recoverable": rc,
              "garbage_pct_of_flagged": round(100.0 * ga / max(1, fl), 1),
              "roman_pct_of_flagged": round(100.0 * ro / max(1, fl), 1),
              "recoverable_pct_of_flagged": round(100.0 * rc / max(1, fl), 1),
              "by_category": dict(cats), "examples": examples}
    json.dump(report, open(os.path.join(CASCADE, "garbage_report.json"), "w", encoding="utf-8"), indent=2)
    perv.sort(key=lambda r: -r["garbage"])
    with open(os.path.join(CASCADE, "garbage_per_volume.tsv"), "w", encoding="utf-8") as f:
        f.write("vol\tflagged\tgarbage\troman\trecoverable\tgarbage_pct\n")
        for r in perv:
            f.write(f"{r['vol']}\t{r['flagged']}\t{r['garbage']}\t{r['roman']}\t{r['recoverable']}\t{round(100.0*r['garbage']/max(1,r['flagged']),1)}\n")
    print(f"\nflagged = {fl:,}")
    print(f"  GUARANTEED GARBAGE = {ga:,} ({report['garbage_pct_of_flagged']}% of flagged)")
    print(f"  roman numerals (valid, not errors) = {ro:,} ({report['roman_pct_of_flagged']}%)")
    print(f"  recoverable residual = {rc:,} ({report['recoverable_pct_of_flagged']}%)")
    print(f"by category: {dict(cats)}")
    print("examples:")
    for g, lst in examples.items():
        print(f"  {g}: {lst}")

if __name__ == "__main__":
    main()
