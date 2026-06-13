"""
garble_by_shape.py -- THE payoff metric: how much of the long-tail OCR garble sits on NON-BODY pages
(rosters / indexes / dividers) that we never ingest -> garble removed from the re-OCR / cleaning consideration.

Joins, per page: garble count (same recoverable-but-uncorrectable logic as noctx_garble_breakdown) x the Surya
page-shape class (page-shapes/<pdfbase>.shapes.tsv). Buckets garble by body vs non-body, corpus + per era.

Run from the repo with the python that has the ocrcorrect deps (the one that ran noctx_garble_breakdown):
  python -m analysis.garble_by_shape
"""
import os, glob, json, re
from collections import Counter, defaultdict
import config
from analysis import noctx_garble_breakdown as nb   # reuse _init (dictionary) + _page_garble

CASCADE  = config.path_for("cascade_dir")
OUTCTX   = os.path.join(CASCADE, "out_context")
SHAPES   = os.environ.get("PATOLEX_SHAPES", os.path.join(os.path.dirname(CASCADE), "page-shapes"))
MANIFEST = os.path.join(CASCADE, "manifest.tsv")
NONBODY  = {"INDEX_TOC", "TABLE_ROSTER", "DIVIDER_TITLE", "PICTURE", "MARGIN"}
_YEAR    = re.compile(r"(\d{4})")

def load_pdfbase_to_label():
    m = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            f.readline()
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 2:
                    m[os.path.splitext(p[1])[0]] = p[0]   # pdfbase -> label
    return m

def read_shape(fp):
    d = {}
    with open(fp, encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 2:
                try:
                    d[int(p[0])] = p[1]
                except ValueError:
                    pass
    return d

def main():
    nb._init()
    p2l = load_pdfbase_to_label()
    shape_files = sorted(glob.glob(os.path.join(SHAPES, "*.shapes.tsv")))
    print(f"joining {len(shape_files)} shape-classified volumes with per-page garble...", flush=True)

    g_body = g_nonbody = g_total = 0
    by_class = Counter(); by_era_body = Counter(); by_era_nb = Counter()
    pages_body = pages_nb = 0
    for sf in shape_files:
        pdfbase = os.path.basename(sf)[:-len(".shapes.tsv")]
        label = p2l.get(pdfbase, pdfbase)
        oc = os.path.join(OUTCTX, "production-" + label + ".json")
        if not os.path.exists(oc):
            continue
        shape = read_shape(sf)
        try:
            text = json.load(open(oc, encoding="utf-8", errors="replace"))
        except Exception:
            continue
        era = (_YEAR.search(label).group(1)[:3] + "0s") if _YEAR.search(label) else "????"
        for pk, lines in text.items():
            try:
                pidx = int(pk)
            except ValueError:
                continue
            cls = shape.get(pidx, "BODY")
            flat = [t for ln in lines for t in ln]
            g = nb._page_garble(flat)
            g_total += g
            if cls in NONBODY:
                g_nonbody += g; pages_nb += 1; by_class[cls] += g; by_era_nb[era] += g
            else:
                g_body += g; pages_body += 1; by_era_body[era] += g

    print(f"\n=== GARBLE BY PAGE SHAPE ({pages_body+pages_nb:,} pages) ===")
    print(f"  garble on BODY pages (real cleaning/re-OCR target): {g_body:,}")
    print(f"  garble on NON-BODY pages (REMOVED from consideration): {g_nonbody:,}")
    print(f"  total garble: {g_total:,}   non-body share REMOVED: {100.0*g_nonbody/max(1,g_total):.1f}%")
    print(f"  non-body garble by class: {dict(by_class.most_common())}")
    print("\n=== non-body garble REMOVED, by era ===")
    for era in sorted(set(by_era_nb) | set(by_era_body)):
        nbg = by_era_nb[era]; tot = nbg + by_era_body[era]
        print(f"  {era}: removed {nbg:,} of {tot:,}  ({100.0*nbg/max(1,tot):.0f}%)")

if __name__ == "__main__":
    main()
