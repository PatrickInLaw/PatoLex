"""Read-only triage of within-volume duplicate chapter numbers (OCR-era).

NO writes to corpus, NO DB. Emits a report to stdout only.
"""
import json
import os
import glob
from collections import defaultdict

ROOT = r"C:\PatoLex-scratch"

FILES = [
    ("parsed_acts_merged.json", "merged_acts"),
    ("parsed_acts_clauserec.json", None),       # key unknown -> autodetect
    ("parsed_acts_visual.json", "recovered_acts"),
]


def load_acts(path, key):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        return [], f"ERR {e}"
    if isinstance(d, list):
        return d, "list"
    if isinstance(d, dict):
        if key and key in d:
            return d[key], key
        # autodetect: first list-of-dicts value
        for k, v in d.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v, k
    return [], "empty"


def chap_of(a):
    for k in ("chapter_int_final", "chapter_int"):
        v = a.get(k)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return int(v)
    c = a.get("chapter")
    if isinstance(c, int):
        return c
    if isinstance(c, str) and c.strip().lstrip("-").isdigit():
        return int(c)
    return None


def page_of(a):
    return a.get("source_page")


def title_of(a):
    for k in ("title", "title_text", "heading"):
        v = a.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# Determine OCR-era production dirs: those that have a parsed_acts_merged.json
# AND are in the 1850-1879 range (OCR consensus era). Exclude *-code siblings.
dirs = sorted(glob.glob(os.path.join(ROOT, "production-18[5-7]*")))
ocr_dirs = []
code_dirs = []
for d in dirs:
    name = os.path.basename(d)
    if name.endswith("-code"):
        code_dirs.append(name)
        continue
    if os.path.exists(os.path.join(d, "parsed_acts_merged.json")):
        ocr_dirs.append(d)

print("=== OCR-era dirs scanned (have parsed_acts_merged.json) ===")
for d in ocr_dirs:
    print("  ", os.path.basename(d))
print("=== -code siblings noted (skipped) ===")
for n in code_dirs:
    print("  ", n)
print()

# For each volume, collect per-chapter the set of (page,title,source-file) entries.
all_dups = []  # (vol, chap, entries)
file_presence = defaultdict(list)

for d in ocr_dirs:
    vol = os.path.basename(d).replace("production-", "")
    # chap -> page -> representative entry (page, title, srcfile)
    chap_pages = defaultdict(dict)  # chap -> {page: (title, srcfiles set)}
    for fn, key in FILES:
        path = os.path.join(d, fn)
        if not os.path.exists(path):
            continue
        acts, usedkey = load_acts(path, key)
        file_presence[vol].append(f"{fn}({usedkey}:{len(acts)})")
        for a in acts:
            if not isinstance(a, dict):
                continue
            ch = chap_of(a)
            pg = page_of(a)
            if ch is None or pg is None:
                continue
            t = title_of(a)
            if pg not in chap_pages[ch]:
                chap_pages[ch][pg] = [t, set()]
            chap_pages[ch][pg][1].add(fn.replace("parsed_acts_", "").replace(".json", ""))
            # prefer a non-empty title if we have one
            if not chap_pages[ch][pg][0] and t:
                chap_pages[ch][pg][0] = t

    for ch, pages in chap_pages.items():
        if len(pages) >= 2:
            entries = []
            for pg in sorted(pages):
                t, srcs = pages[pg]
                entries.append((pg, t, sorted(srcs)))
            all_dups.append((vol, ch, entries))

print("=== file presence per volume ===")
for vol, fl in file_presence.items():
    print(f"  {vol}: {', '.join(fl)}")
print()

print(f"=== TOTAL within-volume duplicate chapter numbers: {len(all_dups)} ===\n")

# Heuristic classification
def norm(s):
    return "".join(c.lower() for c in s if c.isalnum())[:50]


def classify(entries):
    titles = [t for (_, t, _) in entries]
    nonempty = [t for t in titles if t]
    if len(nonempty) <= 1:
        return "MULTI-ACT/CONTINUATION"
    # compare pairwise
    nt = [norm(t) for t in nonempty]
    # same if any pair shares a long common prefix
    same = True
    base = nt[0]
    for o in nt[1:]:
        # prefix overlap
        common = 0
        for a, b in zip(base, o):
            if a == b:
                common += 1
            else:
                break
        if common < 12 and base[:20] != o[:20]:
            same = False
    if same:
        return "SAME-ACT"
    return "COLLISION"


for vol, ch, entries in all_dups:
    cls = classify(entries)
    all_dups[all_dups.index((vol, ch, entries))] = (vol, ch, entries, cls)

# print grouped
order = ["COLLISION", "MULTI-ACT/CONTINUATION", "SAME-ACT", "UNCLEAR"]
counts = defaultdict(int)
print("=== DUPLICATES (raw, for manual review) ===")
for cls in order:
    print(f"\n----- {cls} -----")
    for item in all_dups:
        vol, ch, entries, c = item
        if c != cls:
            continue
        counts[cls] += 1
        print(f"\n[{vol}] chapter {ch}:")
        for pg, t, srcs in entries:
            print(f"    p{pg:<5} [{'/'.join(srcs)}] {t[:60]!r}")

print("\n=== COUNTS ===")
for cls in order:
    print(f"  {cls}: {counts[cls]}")
print(f"  TOTAL: {sum(counts.values())}")
