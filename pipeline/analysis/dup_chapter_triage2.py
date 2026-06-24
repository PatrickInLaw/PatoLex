"""Per-file duplicate analysis to separate cross-file artifacts from real
within-file duplicate chapter numbers. Read-only."""
import json
import os
import glob
from collections import defaultdict

ROOT = r"C:\PatoLex-scratch"
FILES = [
    ("parsed_acts_merged.json", "merged_acts"),
    ("parsed_acts_clauserec.json", None),
    ("parsed_acts_visual.json", "recovered_acts"),
]


def load_acts(path, key):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return []
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        if key and key in d:
            return d[key]
        for k, v in d.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []


def chap_of(a):
    for k in ("chapter_int_final", "chapter_int", "chapter"):
        v = a.get(k)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return int(v)
    return None


def title_of(a):
    for k in ("title", "title_text", "heading"):
        v = a.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


dirs = sorted(glob.glob(os.path.join(ROOT, "production-18[5-7]*")))
ocr_dirs = [d for d in dirs
            if not os.path.basename(d).endswith("-code")
            and os.path.exists(os.path.join(d, "parsed_acts_merged.json"))]

# (a) within a single file: same chap at >=2 pages
print("===== (A) DUPLICATES WITHIN A SINGLE FILE =====")
single_file_dups = 0
for d in ocr_dirs:
    vol = os.path.basename(d).replace("production-", "")
    for fn, key in FILES:
        path = os.path.join(d, fn)
        if not os.path.exists(path):
            continue
        acts = load_acts(path, key)
        chmap = defaultdict(set)
        titles = defaultdict(dict)
        for a in acts:
            ch = chap_of(a)
            pg = a.get("source_page")
            if ch is None or pg is None:
                continue
            chmap[ch].add(pg)
            titles[ch][pg] = title_of(a)
        for ch, pgs in chmap.items():
            if len(pgs) >= 2:
                single_file_dups += 1
                print(f"  [{vol}] {fn.replace('parsed_acts_','')} ch{ch}:")
                for pg in sorted(pgs):
                    print(f"      p{pg}  {titles[ch][pg][:60]!r}")
print(f"  -> within-single-file duplicate count: {single_file_dups}\n")

# (b) cross-file only: chap on pageX in fileA and pageY in fileB (X!=Y), not in same file
print("===== (B) CROSS-FILE PAGE DISAGREEMENTS (per vol, by file) =====")
for d in ocr_dirs:
    vol = os.path.basename(d).replace("production-", "")
    # ch -> {file: {page:title}}
    perfile = defaultdict(lambda: defaultdict(dict))
    for fn, key in FILES:
        path = os.path.join(d, fn)
        if not os.path.exists(path):
            continue
        acts = load_acts(path, key)
        short = fn.replace("parsed_acts_", "").replace(".json", "")
        for a in acts:
            ch = chap_of(a)
            pg = a.get("source_page")
            if ch is None or pg is None:
                continue
            perfile[ch][short][pg] = title_of(a)
    n = 0
    for ch, fm in perfile.items():
        allpages = set()
        for fp in fm.values():
            allpages.update(fp.keys())
        if len(allpages) >= 2 and len(fm) >= 2:
            n += 1
    if n:
        print(f"  {vol}: {n} chapters differ in page across files")
