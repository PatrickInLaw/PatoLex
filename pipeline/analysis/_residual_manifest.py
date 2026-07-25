"""Residual manifest for the VISUAL run: for a session-year, list every chapter still missing after
merge + clause_seq recovery, each bracketed by the nearest present chapters (with known pages) so a
visual agent knows exactly which page IMAGES to open. Writes C:\\PatoLex-scratch\\_manifest_<year>.json.

Page-image mapping: source_page p (1-indexed) -> <vol>/pages_raw/page_{p-1:04d}.png.
Usage: python _residual_manifest.py 1915"""
import os, json, glob, csv, sys, bisect
# cc019 (2026-07-24): both roots were hardcoded. SCR ignored PATOLEX_LOCATION_ROOT
# (set machine-wide after the 2026-06-19 scratch relocation), and ORACLE pointed at
# "C:\GitHub\PatoLex\..." -- a root that does not exist on any current machine.
SCR = os.environ.get("PATOLEX_LOCATION_ROOT", r"C:\PatoLex-scratch")
_REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ORACLE = os.path.join(_REPO, "docs", "30_SYSTEM_DESIGN", "sources", "ca_chapter_counts.tsv")

# How far to extend a one-sided bracket when only one neighbour has a page.
# Was a bare literal 4 in two places with no rationale. Acts routinely run
# longer than 4 pages, so this is a floor, not an estimate.
ONE_SIDED_MARGIN = 6
# Safety margin added to a two-sided bracket. source_page is the act's START
# page and is known to be unreliable in the early era -- some recorded pages
# point at a mid-act continuation page with no heading on it. Widening costs a
# reviewer a few page-turns; a too-narrow bracket costs them the chapter.
BRACKET_MARGIN = 2

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
BUDGET_OWNED_DIRS = _yda.BUDGET_OWNED_DIRS  # dirs the greedy odd-year glob must EXCLUDE so they are
# handed solely to their own alias year -- WITHOUT this, the greedy `production-<yr>*` glob sweeps a
# transition/budget sibling (e.g. production-1907-09 = the 1909 regular session) into the wrong year,
# whose fully-present chapters make this manifest report missing=0 (the 2026-06-23 1907 bug). Mirrors
# _recall_allyears.py line ~85 -- the scoreboard already applies this exact exclusion.

def bracket_for(c, have, pages, run_len=1):
    """Compute the candidate page range for missing chapter `c`.

    Split out of main() (cc019) so it is unit-testable without corpus data.

    KNOWN LIMITATION -- read before trusting the output. The bracket is derived
    from the neighbouring chapters' START pages (`source_page`), which silently
    assumes chapters sit on adjacent pages. That assumption breaks when the
    preceding act is long, and it breaks harder when `source_page` is itself
    corrupt. VERIFIED FAILURE (cc019): for 1872 ch.125-128 the emitted range was
    PDF 224-227, but the true pages are 221-222 -- the stated range lands on
    chapter 128's own BODY. A reviewer following it finds no heading and cannot
    tell "chapter missing" from "range wrong".

    The durable fix is to scan forward from lo_p for the next heading line
    (recover_chaptered.is_header_line / detect_headers) instead of trusting
    hi_p. That is NOT implemented here -- it needs page text this function does
    not receive. Until then: widen, and flag implausible spans.

    `run_len` -- how many consecutive chapters are missing in this run. Used to
    sanity-check the span: N missing chapters cannot plausibly fit in fewer
    than N pages.

    Returns (rng, lo, hi, lo_p, hi_p, implausible_bool).
    """
    i = bisect.bisect_left(have, c)
    lo = have[i - 1] if i > 0 else None
    hi = have[i] if i < len(have) else None
    lo_p = pages.get(lo)
    hi_p = pages.get(hi)

    rng = None
    implausible = False
    # NOTE `is not None`, not truthiness: a source_page of 0 is falsy and the
    # old `if lo_p and hi_p` silently dropped it, producing rng=None which was
    # then filtered out of the histogram entirely.
    if lo_p is not None and hi_p is not None:
        a, b = min(lo_p, hi_p), max(lo_p, hi_p)
        if b < a:
            a, b = b, a
        rng = [max(1, a - BRACKET_MARGIN), b + BRACKET_MARGIN]
        # N consecutive missing chapters need at least ~N pages between the
        # bracketing neighbours. If they do not fit, one of the two recorded
        # source_pages is wrong (or an intervening act is long) -- say so.
        if (b - a) < run_len:
            implausible = True
    elif lo_p is not None:
        rng = [lo_p, lo_p + ONE_SIDED_MARGIN + run_len]
    elif hi_p is not None:
        rng = [max(1, hi_p - ONE_SIDED_MARGIN - run_len), hi_p]

    return rng, lo, hi, lo_p, hi_p, implausible


def _run_lengths(missing):
    """chapter -> length of the consecutive-missing run it belongs to."""
    out = {}
    if not missing:
        return out
    run = [missing[0]]
    for c in missing[1:]:
        if c == run[-1] + 1:
            run.append(c)
        else:
            for x in run:
                out[x] = len(run)
            run = [c]
    for x in run:
        out[x] = len(run)
    return out


def main(yr):
    N = oracle_N(yr)
    dirs = [d for d in glob.glob(os.path.join(SCR, f"production-{yr}*"))
            if os.path.isdir(d) and os.path.basename(d) not in BUDGET_OWNED_DIRS]
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
    runs = _run_lengths(missing)
    items = []
    for c in missing:
        rng, lo, hi, lo_p, hi_p, implausible = bracket_for(
            c, have, pages, run_len=runs.get(c, 1))
        v = vol.get(lo) or vol.get(hi)
        items.append({"chapter": c, "lo_ch": lo, "lo_page": lo_p, "hi_ch": hi, "hi_page": hi_p,
                      "page_range": rng, "vol": v,
                      "run_len": runs.get(c, 1),
                      # True => the recorded neighbour pages cannot physically
                      # hold this many missing chapters. Do NOT drive off the
                      # numeric range in that case; page to the printed running
                      # head just before/after the neighbour chapters.
                      "span_implausible": implausible})
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
    bad = [it["chapter"] for it in items if it["span_implausible"]]
    if bad:
        print(f"  WARN span_implausible ({len(bad)}): {bad[:40]}{' ...' if len(bad) > 40 else ''}")
        print("       -> recorded neighbour pages cannot hold that many missing chapters;")
        print("          the bracket is WRONG, not merely wide. Page to the printed running")
        print("          head next to the neighbour chapters instead of trusting the range.")
    no_range = [it["chapter"] for it in items if not it["page_range"]]
    if no_range:
        print(f"  WARN no page_range ({len(no_range)}): {no_range[:40]}")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1915)
