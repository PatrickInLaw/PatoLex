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
VLM_VERDICTS = os.environ.get("PATOLEX_VLM_VERDICTS", os.path.join(CASCADE, "vlm_verdicts.tsv"))
NONBODY  = {"INDEX_TOC", "TABLE_ROSTER", "DIVIDER_TITLE", "PICTURE", "MARGIN"}
USE_RECONCILED = os.environ.get("PATOLEX_USE_RECONCILED", "1") == "1"   # prefer the post-reconcile labels
USE_VLM  = os.environ.get("PATOLEX_USE_VLM", "1") == "1"   # fold VLM verdicts into AMBIGUOUS pages
# VLM verdicts that mean "non-body, never ingested" -> removed. BODY/OTHER stay (conservative: OTHER is not removed).
VLM_REMOVE = {"INDEX_TOC", "ROSTER", "REPRINT"}
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

def load_vlm_verdicts():
    """vlm_verdicts.tsv: label, pidx, verdict -> {(label,pidx): verdict}. Exported from PatoLexQueue.vlm_queue."""
    v = {}
    if not os.path.exists(VLM_VERDICTS):
        return v
    with open(VLM_VERDICTS, encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 3:
                try:
                    v[(p[0], int(p[1]))] = p[2]
                except ValueError:
                    pass
    return v

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

    vlm = load_vlm_verdicts() if (USE_RECONCILED and USE_VLM) else {}
    if USE_RECONCILED and USE_VLM:
        print(f"folding in {len(vlm):,} VLM verdicts (AMBIGUOUS -> BODY or REMOVED_VLM)...", flush=True)

    # buckets: BODY (real target) | NONBODY_DET (reconcile-confirmed removed) |
    #          NONBODY_VLM (VLM-confirmed removed) | AMBIGUOUS (no verdict residual)
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
                if bucket == "NONBODY":
                    bucket = "NONBODY_DET"
                elif bucket == "AMBIGUOUS" and USE_VLM:
                    verdict = vlm.get((label, pidx))
                    if verdict in VLM_REMOVE:
                        bucket = "NONBODY_VLM"
                    elif verdict is not None:   # BODY / OTHER -> real text (kept)
                        bucket = "BODY"
                    # else: no verdict (failed page) -> stays AMBIGUOUS
            else:
                bucket = "NONBODY_DET" if cls in NONBODY else "BODY"
            gr = nb._page_garble([t for ln in lines for t in ln])
            g[bucket] += gr; pages[bucket] += 1; by_era[era][bucket] += gr

    tot = sum(g.values())
    removed = g['NONBODY_DET'] + g['NONBODY_VLM']
    print(f"\n=== GARBLE BY FINAL LABEL ({sum(pages.values()):,} pages) ===")
    print(f"  garble on BODY (real cleaning/re-OCR target):          {g['BODY']:,}")
    print(f"  garble REMOVED, deterministic (reconcile non-body):    {g['NONBODY_DET']:,}")
    if USE_RECONCILED and USE_VLM:
        print(f"  garble REMOVED, VLM (roster/index/reprint):            {g['NONBODY_VLM']:,}")
        print(f"  garble still AMBIGUOUS (no VLM verdict, failed pages): {g['AMBIGUOUS']:,}")
    print(f"  total garble: {tot:,}")
    print(f"  TOTAL REMOVED: {removed:,} ({100.0*removed/max(1,tot):.1f}%)  "
          f"[det {100.0*g['NONBODY_DET']/max(1,tot):.1f}% + VLM {100.0*g['NONBODY_VLM']/max(1,tot):.1f}%]")
    print(f"  REMAINS on BODY (real cleaning target): {g['BODY']:,} ({100.0*g['BODY']/max(1,tot):.1f}%)")
    print("\n=== by era (removed[det+vlm] / total, removed%) ===")
    for era in sorted(by_era):
        e = by_era[era]; t = sum(e.values()); rm = e['NONBODY_DET'] + e['NONBODY_VLM']
        print(f"  {era}: removed {rm:,} of {t:,} ({100.0*rm/max(1,t):.1f}%)")

if __name__ == "__main__":
    main()
