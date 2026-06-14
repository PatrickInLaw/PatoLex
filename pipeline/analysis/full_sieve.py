"""
full_sieve.py -- the COMPLETE page-shape sieve, all three layers joined per page, no approximation.

For every OCR'd page (the universe = out_context pages) it joins:
  - raw Surya shape class      (page-shapes/<pdfbase>.shapes.tsv)   -> body vs non-body
  - reconcile decision         (reconciled/<label>.reconciled.tsv)  -> rescued / confirmed / ambiguous
  - VLM verdict on ambiguous   (vlm_verdicts.tsv)                   -> kept-body / removed / failed
and assigns it to ONE of six mutually-exclusive final categories, accumulating PAGES and GARBLE
(same recoverable-but-uncorrectable token logic as garble_by_shape, via roster_detect._page_garble).

Six categories (exhaustive, disjoint):
  SURYA_BODY        Surya said body                          -> kept
  RESCUED           Surya non-body, reconcile rescued->body  -> kept
  CONFIRMED         Surya non-body, reconcile confirmed      -> REMOVED (deterministic)
  AMB_VLM_BODY      ambiguous, VLM verdict BODY/OTHER        -> kept
  AMB_VLM_REMOVED   ambiguous, VLM verdict ROSTER/INDEX/REPRINT -> REMOVED (VLM)
  AMB_FAILED        ambiguous, no VLM verdict (failed render)-> residual

Run on the 5080 (all inputs local):
  set PATOLEX_LOCATION_ROOT=C:\\Users\\PatrickKolasinski\\PatoLex-scratch
  set PYTHONPATH=...\\pipeline
  set PATOLEX_SHAPES=C:\\Users\\PatrickKolasinski\\PatoLex-scratch\\page-shapes-5090
  python -m analysis.full_sieve
"""
import os, glob, json, re
from collections import Counter, defaultdict
import config
from analysis import roster_detect as nb

CASCADE    = config.path_for("cascade_dir")
OUTCTX     = os.path.join(CASCADE, "out_context")
SHAPES     = os.environ.get("PATOLEX_SHAPES", os.path.join(os.path.dirname(CASCADE), "page-shapes"))
RECONCILED = os.environ.get("PATOLEX_RECONCILED", os.path.join(CASCADE, "reconciled"))
VLM_VERD   = os.environ.get("PATOLEX_VLM_VERDICTS", os.path.join(CASCADE, "vlm_verdicts.tsv"))
MANIFEST   = os.path.join(CASCADE, "manifest.tsv")

SURYA_NONBODY = {"INDEX_TOC", "TABLE_ROSTER", "DIVIDER_TITLE", "PICTURE", "MARGIN"}
VLM_REMOVE    = {"INDEX_TOC", "ROSTER", "REPRINT"}   # BODY/OTHER -> kept
KEPT    = {"SURYA_BODY", "RESCUED", "AMB_VLM_BODY"}
REMOVED = {"CONFIRMED", "AMB_VLM_REMOVED"}
_YEAR   = re.compile(r"(\d{4})")


def load_label_to_pdfbase():
    m = {}
    with open(MANIFEST, encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 2:
                m[p[0]] = os.path.splitext(p[1])[0]   # label -> pdfbase
    return m


def read_two_col(fp):
    """generic pidx -> col1 reader for shape (class) and reconciled (final)."""
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


def load_vlm():
    v = {}
    if os.path.exists(VLM_VERD):
        with open(VLM_VERD, encoding="utf-8") as f:
            f.readline()
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 3:
                    try:
                        v[(p[0], int(p[1]))] = p[2]
                    except ValueError:
                        pass
    return v


def classify(surya_cls, recon, verdict):
    """return one of the six categories for a single page."""
    surya_nb = surya_cls in SURYA_NONBODY
    if not surya_nb and recon != "AMBIGUOUS":
        return "SURYA_BODY"
    if recon == "BODY":
        return "RESCUED"            # surya non-body, reconcile pulled it back
    if recon == "NONBODY":
        return "CONFIRMED"
    # AMBIGUOUS -> VLM
    if verdict is None:
        return "AMB_FAILED"
    return "AMB_VLM_REMOVED" if verdict in VLM_REMOVE else "AMB_VLM_BODY"


def main():
    nb._init()
    l2p = load_label_to_pdfbase()
    vlm = load_vlm()
    recon_files = sorted(glob.glob(os.path.join(RECONCILED, "*.reconciled.tsv")))
    print(f"sieve over {len(recon_files)} volumes; {len(vlm):,} VLM verdicts loaded", flush=True)

    g = Counter(); pg = Counter(); by_era = defaultdict(Counter); by_era_pg = defaultdict(Counter)
    miss_shape = miss_recon = vols = 0
    for rf in recon_files:
        label = os.path.basename(rf)[:-len(".reconciled.tsv")]
        oc = os.path.join(OUTCTX, "production-" + label + ".json")
        if not os.path.exists(oc):
            continue
        pdfbase = l2p.get(label, label)
        sf = os.path.join(SHAPES, pdfbase + ".shapes.tsv")
        shape = read_two_col(sf) if os.path.exists(sf) else {}
        if not shape:
            miss_shape += 1
        recon = read_two_col(rf)
        try:
            text = json.load(open(oc, encoding="utf-8", errors="replace"))
        except Exception:
            continue
        vols += 1
        era = (_YEAR.search(label).group(1)[:3] + "0s") if _YEAR.search(label) else "????"
        for pk, lines in text.items():
            try:
                pidx = int(pk)
            except ValueError:
                continue
            scls = shape.get(pidx, "BODY")
            rec  = recon.get(pidx)
            if rec is None:
                miss_recon += 1
                rec = "BODY"
            cat = classify(scls, rec, vlm.get((label, pidx)))
            gr = nb._page_garble([t for ln in lines for t in ln])
            g[cat] += gr; pg[cat] += 1
            by_era[era][cat] += gr; by_era_pg[era][cat] += 1

    totg = sum(g.values()); totp = sum(pg.values())

    def row(name, cat):
        return f"  {name:<34} pages {pg[cat]:>8,}  garble {g[cat]:>9,}"

    print(f"\n================ FULL SIEVE ({vols} vols, {totp:,} pages, {totg:,} garble tokens) ================")
    print(f"  (volumes missing shape file: {miss_shape}; pages missing reconcile entry: {miss_recon})")

    print("\n--- LAYER 1: Surya raw shape ---")
    sb_g = g["SURYA_BODY"]; sb_p = pg["SURYA_BODY"]
    snb_cats = ["RESCUED", "CONFIRMED", "AMB_VLM_BODY", "AMB_VLM_REMOVED", "AMB_FAILED"]
    snb_g = sum(g[c] for c in snb_cats); snb_p = sum(pg[c] for c in snb_cats)
    print(f"  Surya BODY                         pages {sb_p:>8,}  garble {sb_g:>9,}")
    print(f"  Surya NON-BODY (-> reconcile)      pages {snb_p:>8,}  garble {snb_g:>9,}")

    print("\n--- LAYER 2: reconcile (of the Surya non-body) ---")
    print(row("rescued -> BODY (kept)", "RESCUED"))
    print(row("confirmed -> non-body (REMOVED)", "CONFIRMED"))
    amb_cats = ["AMB_VLM_BODY", "AMB_VLM_REMOVED", "AMB_FAILED"]
    amb_g = sum(g[c] for c in amb_cats); amb_p = sum(pg[c] for c in amb_cats)
    print(f"  ambiguous -> VLM                   pages {amb_p:>8,}  garble {amb_g:>9,}")

    print("\n--- LAYER 3: VLM (of the ambiguous) ---")
    print(row("VLM kept -> BODY", "AMB_VLM_BODY"))
    print(row("VLM removed (roster/index/reprint)", "AMB_VLM_REMOVED"))
    print(row("VLM failed (no render) residual", "AMB_FAILED"))

    kept_g = sum(g[c] for c in KEPT); kept_p = sum(pg[c] for c in KEPT)
    rem_g  = sum(g[c] for c in REMOVED); rem_p = sum(pg[c] for c in REMOVED)
    print("\n--- FINAL ---")
    print(f"  KEPT (real statute body)           pages {kept_p:>8,} ({100.0*kept_p/totp:>5.2f}%)  garble {kept_g:>9,} ({100.0*kept_g/totg:>5.1f}%)")
    print(f"  REMOVED (never ingested)           pages {rem_p:>8,} ({100.0*rem_p/totp:>5.2f}%)  garble {rem_g:>9,} ({100.0*rem_g/totg:>5.1f}%)")
    print(f"  residual (failed)                  pages {pg['AMB_FAILED']:>8,}            garble {g['AMB_FAILED']:>9,}")
    dens_body = kept_g / max(1, kept_p); dens_rem = rem_g / max(1, rem_p)
    print(f"  garble density: removed pages {dens_rem:.1f} tok/pg vs body {dens_body:.1f} tok/pg  ({dens_rem/max(0.01,dens_body):.1f}x)")

    print("\n--- by era (removed garble / total garble, removed%) ---")
    for era in sorted(by_era):
        e = by_era[era]; t = sum(e.values()); rm = sum(e[c] for c in REMOVED)
        print(f"  {era}: removed {rm:>7,} of {t:>7,} ({100.0*rm/max(1,t):>5.1f}%)")


if __name__ == "__main__":
    main()
