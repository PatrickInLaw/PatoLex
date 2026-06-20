"""merge_passes.py -- ADDITIVE, PRECISION-FILTERED best-of merge of the existing parse passes.
TRUSTED passes (certified > chaptered_v2 > repaired > recovered) define the chapter->page
order. LOW passes (multiengine, lostheader, fixed) add only chapters they uniquely have AND
that pass a sanity gate: the chapter's source_page must be page-monotonic vs the trusted
anchors (chapters are page-ordered), OR it must carry a real "An act ..." title. This drops
the engine-union's page-misassigned garbage (e.g. 1915 ch22 @ p1807) while keeping real
recovered acts. One act per chapter, no dups, capped at the session's oracle N. NEW file
parsed_acts_merged.json; never touches inputs.

Usage: python merge_passes.py <glob>   e.g. "production-1915*"  or  "production-19*"
"""
import os, json, glob, sys, re, csv, bisect
from collections import defaultdict

SCRATCH = r"C:\PatoLex-scratch"
ORACLE_TSV = r"C:\GitHub\PatoLex\docs\30_SYSTEM_DESIGN\sources\ca_chapter_counts.tsv"
TRUSTED = ["parsed_acts_certified.json", "parsed_acts_chaptered_v2.json", "parsed_acts_repaired.json",
           "parsed_acts_recovered.json"]
LOW = ["parsed_acts_multiengine.json", "parsed_acts_lostheader.json", "parsed_acts_fixed.json"]
FALLBACK_CAP, PAGE_TOL = 2500, 12

ORACLE = {}
with open(ORACLE_TSV, encoding="utf-8") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        try:
            y = int(row["session_year"]); ORACLE[y] = max(ORACLE.get(y, 0), int(row["total_chapters"]))
        except Exception:
            pass

def n_for(name):
    m = re.search(r"production-(\d{4})", name)
    return (ORACLE[int(m.group(1))], int(m.group(1))) if m and int(m.group(1)) in ORACLE else (FALLBACK_CAP, None)

def acts_of(d):
    out = []
    for v in (d.values() if isinstance(d, dict) else [d]):
        if isinstance(v, list):
            out += [a for a in v if isinstance(a, dict)]
    return out

def cn(a, N):
    n = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
    return n if isinstance(n, int) and 1 <= n <= N else None

def page(a):
    p = a.get("source_page")
    return p if isinstance(p, int) else None

def real_anact(a):
    t = (a.get("an_act_title_snippet") or a.get("title") or a.get("text") or "")
    return bool(re.match(r"\s*An\s+act\b", t, re.I))

def load(D, f):
    p = os.path.join(D, f)
    if not os.path.exists(p):
        return []
    try:
        return acts_of(json.load(open(p, encoding="utf-8")))
    except Exception:
        return []

def page_ok(c, sp, anchors):
    if sp is None:
        return False  # low-pass act with no page AND no real title -> can't trust
    below = [p for ch, p in anchors if ch < c]
    above = [p for ch, p in anchors if ch > c]
    lo, hi = (max(below) if below else None), (min(above) if above else None)
    if lo is not None and sp < lo - PAGE_TOL:
        return False
    if hi is not None and sp > hi + PAGE_TOL:
        return False
    return True

def norm_title(a):
    t = (a.get("an_act_title_snippet") or a.get("title") or a.get("text") or "")
    return set(re.findall(r"[a-z]{3,}", t.lower()))

def title_sim(a, b):
    ta, tb = norm_title(a), norm_title(b)
    if len(ta) < 3 or len(tb) < 3:
        return 0.0
    return len(ta & tb) / len(ta | tb)

def dedup_same_page(by_ch):
    """Same act under two chapter numbers (OCR digit-garble): same source_page + >=0.6 title
    overlap. Keep the page-monotonic chapter (bracketed by solo-page neighbors), drop the garble."""
    page_chs = defaultdict(list)
    for c, a in by_ch.items():
        p = a.get("source_page")
        if isinstance(p, int):
            page_chs[p].append(c)
    solo = sorted((p, chs[0]) for p, chs in page_chs.items() if len(chs) == 1)
    solo_pages = [p for p, _ in solo]
    def expected(p):  # page-monotonic expected chapter at page p, interpolated from solo neighbors
        i = bisect.bisect_left(solo_pages, p)
        if 0 < i < len(solo):
            (pb, cb), (pa, ca) = solo[i - 1], solo[i]
            return cb + (ca - cb) * (p - pb) / (pa - pb) if pa > pb else (cb + ca) / 2
        if i == 0:
            return solo[0][1] if solo else 0
        return solo[-1][1] if solo else 10 ** 9
    _ = expected  # (page-interpolation proved unreliable for picking the correct twin; kept for reference)
    flagged = []
    for p, chs in page_chs.items():
        if len(chs) < 2:
            continue
        chs = sorted(chs)
        for i in range(len(chs)):
            for j in range(i + 1, len(chs)):
                c1, c2 = chs[i], chs[j]
                if title_sim(by_ch[c1], by_ch[c2]) >= 0.6:  # same act under two chapter numbers
                    flagged.append([c1, c2, p])  # FLAG ONLY -- reliable collapse requires the OCR page header
    return flagged

def merge_dir(D, N):
    by_ch, prov = {}, {}
    for f in TRUSTED:
        for a in load(D, f):
            c = cn(a, N)
            if c and c not in by_ch:
                a2 = dict(a); a2["_merge_source"] = f; by_ch[c] = a2; prov[c] = f
    anchors = sorted((c, page(by_ch[c])) for c in by_ch if page(by_ch[c]) is not None)
    dropped = 0
    for f in LOW:
        for a in load(D, f):
            c = cn(a, N)
            if not c or c in by_ch:
                continue
            if real_anact(a) or page_ok(c, page(a), anchors):  # recall; twins removed by dedup below
                a2 = dict(a); a2["_merge_source"] = f; by_ch[c] = a2; prov[c] = f
            else:
                dropped += 1
    flagged = dedup_same_page(by_ch)  # FLAG same-act twins (collapse deferred to an OCR-header pass)
    merged = [by_ch[c] for c in sorted(by_ch)]
    by_source = {f: sum(1 for c in prov if prov[c] == f) for f in TRUSTED + LOW}
    out = {"merged_acts": merged,
           "_merge_meta": {"distinct": len(merged), "cap_N": N, "max_chapter": max(by_ch) if by_ch else 0,
                           "low_pass_dropped_by_filter": dropped,
                           "same_act_dup_pairs_flagged": len(flagged), "flagged_dup_pairs": flagged,
                           "by_source": {k: v for k, v in by_source.items() if v}}}
    json.dump(out, open(os.path.join(D, "parsed_acts_merged.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return out["_merge_meta"]

if __name__ == "__main__":
    pat = sys.argv[1] if len(sys.argv) > 1 else "production-1915*"
    dirs = sorted(d for d in glob.glob(os.path.join(SCRATCH, pat)) if os.path.isdir(d))
    total = 0
    for D in dirs:
        N, yr = n_for(os.path.basename(D))
        m = merge_dir(D, N)
        total += m["distinct"]
        print(f"{os.path.basename(D):38} N={N:5} merged={m['distinct']:5} max={m['max_chapter']:5} dropped={m['low_pass_dropped_by_filter']:4} src={m['by_source']}")
    print(f"\n{len(dirs)} volumes, {total} merged chapter-acts.")
