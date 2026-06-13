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
from analysis import roster_detect as nb   # reuse _init (dictionary+gazetteer) + _page_garble

CASCADE  = config.path_for("cascade_dir")
OUTCTX   = os.path.join(CASCADE, "out_context")
SHAPES   = os.environ.get("PATOLEX_SHAPES", os.path.join(os.path.dirname(CASCADE), "page-shapes"))
RECONCILED = os.environ.get("PATOLEX_RECONCILED", os.path.join(CASCADE, "reconciled"))
MANIFEST = os.path.join(CASCADE, "manifest.tsv")
NONBODY  = {"INDEX_TOC", "TABLE_ROSTER", "DIVIDER_TITLE", "PICTURE", "MARGIN"}
USE_RECONCILED = os.environ.get("PATOLEX_USE_RECONCILED", "1") == "1"   # prefer the post-reconcile labels
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

def read_reconciled(fp):
    """reconciled TSV: pidx, final(BODY|NONBODY|AMBIGUOUS), why, surya_conf."""
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
    if USE_RECONCILED:
        files = sorted(glob.glob(os.path.join(RECONCILED, "*.reconciled.tsv")))
        labels = [os.path.basename(f)[:-len(".reconciled.tsv")] for f in files]
        print(f"joining {len(files)} RECONCILED volumes with per-page garble (post-reconcile labels)...", flush=True)
    else:
        p2l = load_pdfbase_to_label()
        files = sorted(glob.glob(os.path.join(SHAPES, "*.shapes.tsv")))
        labels = [p2l.get(os.path.basename(f)[:-len(".shapes.tsv")], os.path.basename(f)[:-len(".shapes.tsv")]) for f in files]
        print(f"joining {len(files)} RAW-shape volumes with per-page garble...", flush=True)

    g = Counter(); by_era = defaultdict(Counter); pages = Counter()
    for fp, label in zip(files, labels):
        oc = os.path.join(OUTCTX, "production-" + label + ".json")
        if not os.path.exists(oc):
            continue
        lab = read_reconciled(fp) if USE_RECONCILED else read_shape(fp)
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
            cls = lab.get(pidx, "BODY")
            if USE_RECONCILED:
                bucket = cls if cls in ("BODY", "NONBODY", "AMBIGUOUS") else "BODY"
            else:
                bucket = "NONBODY" if cls in NONBODY else "BODY"
            gr = nb._page_garble([t for ln in lines for t in ln])
            g[bucket] += gr; pages[bucket] += 1; by_era[era][bucket] += gr

    tot = sum(g.values())
    print(f"\n=== GARBLE BY {'RECONCILED' if USE_RECONCILED else 'RAW-SHAPE'} LABEL ({sum(pages.values()):,} pages) ===")
    print(f"  garble on BODY (real cleaning/re-OCR target):        {g['BODY']:,}")
    print(f"  garble on NON-BODY confirmed (REMOVED, deterministic): {g['NONBODY']:,}")
    if USE_RECONCILED:
        print(f"  garble on AMBIGUOUS (pending VLM verdict):            {g['AMBIGUOUS']:,}")
    print(f"  total garble: {tot:,}")
    print(f"  REMOVED so far: {g['NONBODY']:,} ({100.0*g['NONBODY']/max(1,tot):.1f}%)"
          + (f"  + up to {g['AMBIGUOUS']:,} more pending VLM ({100.0*(g['NONBODY']+g['AMBIGUOUS'])/max(1,tot):.1f}% max)" if USE_RECONCILED else ""))
    print("\n=== by era (removed / pending / total) ===")
    for era in sorted(by_era):
        e = by_era[era]; t = sum(e.values())
        amb = f"  pending {e['AMBIGUOUS']:,}" if USE_RECONCILED else ""
        print(f"  {era}: removed {e['NONBODY']:,}{amb}  of {t:,}")

if __name__ == "__main__":
    main()
