"""Residual manifest for the VISUAL run: for a session-year, list every chapter still missing after
merge + clause_seq recovery, each bracketed by the nearest present chapters (with known pages) so a
visual agent knows exactly which page IMAGES to open. Writes C:\\PatoLex-scratch\\_manifest_<year>.json.

Page-image mapping: source_page p (1-indexed) -> <vol>/pages_raw/page_{p-1:04d}.png.
Usage: python _residual_manifest.py 1915"""
import os, json, glob, csv, sys, bisect
SCR = r"C:\PatoLex-scratch"
ORACLE = r"C:\GitHub\PatoLex\docs\30_SYSTEM_DESIGN\sources\ca_chapter_counts.tsv"

def oracle_N(yr):
    best = 0
    with open(ORACLE, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try:
                if int(row["session_year"]) == yr and row["session_type"] == "regular":
                    best = max(best, int(row["total_chapters"]))
            except Exception:
                pass
    return best

def chap_pages(D, N):
    """chapter -> source_page from merge (present) and clauserec (recovered). Returns (present_set,
    page_map, vol_of_page)."""
    pages, vol = {}, {}
    for fn, key in (("parsed_acts_merged.json", "merged_acts"), ("parsed_acts_clauserec.json", "recovered_acts"),
                    ("parsed_acts_visual.json", "recovered_acts")):
        p = os.path.join(D, fn)
        if not os.path.exists(p):
            continue
        try:
            acts = json.load(open(p, encoding="utf-8")).get(key, [])
        except Exception:
            continue
        for a in acts:
            c = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
            pg = a.get("source_page")
            if isinstance(c, int) and 1 <= c <= N:
                if isinstance(pg, int) and c not in pages:
                    pages[c] = pg; vol[c] = os.path.basename(D)
    return pages, vol

# biennial / session-year -> production-dir aliases: SOURCED from the shared single-source-of-truth
# `pipeline/year_dir_alias.py` so this manifest can't drift from the scoreboard + merge (F1 fix,
# 2026-06-22; previously this file carried a divergent partial copy -- a stray 1864 entry, and it
# MISSED the transition 1901/1907/1909/1911 + the budget 1952-1964 aliases). These files run as
# standalone scripts, so load the module by absolute path via importlib (a package import is fragile).
import importlib.util as _ilu
_yda_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "year_dir_alias.py")
_yda_spec = _ilu.spec_from_file_location("year_dir_alias", _yda_path)
_yda = _ilu.module_from_spec(_yda_spec)
_yda_spec.loader.exec_module(_yda)
YEAR_DIR_ALIAS = _yda.YEAR_DIR_ALIAS

def main(yr):
    N = oracle_N(yr)
    dirs = [d for d in glob.glob(os.path.join(SCR, f"production-{yr}*")) if os.path.isdir(d)]
    for alias in YEAR_DIR_ALIAS.get(yr, []):
        ad = os.path.join(SCR, alias)
        if os.path.isdir(ad) and ad not in dirs:
            dirs.append(ad)
    pages, vol = {}, {}
    for D in dirs:
        pg, v = chap_pages(D, N)
        for c, p in pg.items():
            pages.setdefault(c, p); vol.setdefault(c, v[c])
    present = set(pages)
    have = sorted(present)
    missing = [c for c in range(1, N + 1) if c not in present]
    items = []
    for c in missing:
        i = bisect.bisect_left(have, c)
        lo = have[i - 1] if i > 0 else None
        hi = have[i] if i < len(have) else None
        lo_p = pages.get(lo); hi_p = pages.get(hi)
        v = vol.get(lo) or vol.get(hi)
        rng = None
        if lo_p and hi_p:
            rng = [min(lo_p, hi_p), max(lo_p, hi_p)]
        elif lo_p:
            rng = [lo_p, lo_p + 4]
        elif hi_p:
            rng = [max(1, hi_p - 4), hi_p]
        items.append({"chapter": c, "lo_ch": lo, "lo_page": lo_p, "hi_ch": hi, "hi_page": hi_p,
                      "page_range": rng, "vol": v})
    out = {"year": yr, "N": N, "present": len(present), "missing_count": len(missing),
           "volumes": [os.path.basename(d) for d in dirs],
           "page_image_pattern": "<vol>/pages_raw/page_{source_page-1:04d}.png",
           "missing": items}
    path = os.path.join(SCR, f"_manifest_{yr}.json")
    json.dump(out, open(path, "w"), indent=1)
    print(f"{yr}: N={N} present={len(present)} missing={len(missing)} -> {path}")
    # compact page-range histogram so the orchestrator sees the read cost
    ranges = [it["page_range"][1] - it["page_range"][0] for it in items if it["page_range"]]
    print(f"  missing chapters: {missing[:40]}{' ...' if len(missing) > 40 else ''}")
    if ranges:
        print(f"  page-span per missing: min={min(ranges)} max={max(ranges)} avg={sum(ranges)/len(ranges):.1f}")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1915)
