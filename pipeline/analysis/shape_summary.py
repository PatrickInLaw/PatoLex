"""
shape_summary.py -- turn the per-volume Surya page-shape maps (page-shapes/<vol>.shapes.tsv) into the answer:
how much of each volume / era is statute BODY (ingestable) vs non-body (INDEX_TOC / TABLE_ROSTER / DIVIDER /
PICTURE / MARGIN), corpus-wide. Runs on partial output too (safe to run while the job is still going).

  python shape_summary.py --shapes-dir <page-shapes> [--out shape_summary.tsv]
  python shape_summary.py --shapes-dir <page-shapes> --sample-class INDEX_TOC --sample-n 12   # spot-check pool
"""
import argparse, os, glob, re, random
from collections import Counter, defaultdict

ORDER = ["BODY", "INDEX_TOC", "TABLE_ROSTER", "DIVIDER_TITLE", "PICTURE", "MARGIN", "OTHER", "Empty"]
NONBODY = {"INDEX_TOC", "TABLE_ROSTER", "DIVIDER_TITLE", "PICTURE"}   # not ingested as statute text

def year_of(vol):
    m = re.match(r"(\d{4})", vol)
    return int(m.group(1)) if m else 0

def read_shapes(d):
    vols = {}
    for fp in sorted(glob.glob(os.path.join(d, "*.shapes.tsv"))):
        vol = os.path.basename(fp)[:-len(".shapes.tsv")]
        rows = []
        with open(fp, encoding="utf-8") as f:
            f.readline()
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 4:
                    try:
                        rows.append((int(p[0]), p[1], p[2], float(p[3])))
                    except ValueError:
                        pass
        vols[vol] = rows
    return vols

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shapes-dir", required=True)
    ap.add_argument("--out", default="shape_summary.tsv")
    ap.add_argument("--sample-class")
    ap.add_argument("--sample-n", type=int, default=12)
    a = ap.parse_args()
    vols = read_shapes(a.shapes_dir)

    if a.sample_class:
        pool = [(v, pidx, conf) for v, rows in vols.items() for (pidx, cls, lab, conf) in rows if cls == a.sample_class]
        rnd = random.Random(20260613)
        for v, pidx, conf in rnd.sample(pool, min(a.sample_n, len(pool))):
            print(f"{v}\t{pidx}\t{conf}")
        return

    corpus = Counter(); per_era = defaultdict(Counter); per_vol = {}; lowconf = 0; total = 0
    for vol, rows in vols.items():
        c = Counter()
        for pidx, cls, lab, conf in rows:
            c[cls] += 1; corpus[cls] += 1; total += 1
            if conf < 0.5:
                lowconf += 1
        per_vol[vol] = c
        per_era[str(year_of(vol))[:3] + "0s"].update(c)

    def pct(n): return f"{100.0*n/max(1,total):.1f}%"
    nonbody = sum(corpus[k] for k in NONBODY)

    print(f"=== CORPUS PAGE-SHAPE SUMMARY ({len(vols)} volumes, {total:,} pages classified) ===")
    for k in ORDER:
        if corpus[k]:
            print(f"  {k:<14}{corpus[k]:>9,}  {pct(corpus[k])}")
    print(f"  {'-'*30}")
    print(f"  BODY (ingestable):   {corpus['BODY']:,}  {pct(corpus['BODY'])}")
    print(f"  NON-BODY (exclude):  {nonbody:,}  {pct(nonbody)}   [index/roster/divider/picture]")
    print(f"  low-confidence (<0.5): {lowconf:,}  {pct(lowconf)}")

    print("\n=== BY ERA (non-body % = front-matter/index/roster share) ===")
    print(f"  {'era':<8}{'pages':>9}{'body':>9}{'nonbody':>9}{'nonbody%':>9}")
    for era in sorted(per_era):
        c = per_era[era]; t = sum(c.values()); nb = sum(c[k] for k in NONBODY)
        print(f"  {era:<8}{t:>9,}{c['BODY']:>9,}{nb:>9,}{100.0*nb/max(1,t):>8.1f}%")

    rows = []
    for vol, c in per_vol.items():
        t = sum(c.values()); nb = sum(c[k] for k in NONBODY)
        rows.append((vol, year_of(vol), t, c["BODY"], c["INDEX_TOC"], c["TABLE_ROSTER"],
                     c["DIVIDER_TITLE"], c["PICTURE"], nb, 100.0*nb/max(1, t)))
    rows.sort(key=lambda r: -r[9])
    print("\n=== TOP 12 VOLUMES by non-body share ===")
    for r in rows[:12]:
        print(f"  {r[0]:<32}{r[2]:>6,}pp  nonbody {r[8]:>5,} ({r[9]:.0f}%)  "
              f"[toc {r[4]} roster {r[5]} div {r[6]} pic {r[7]}]")

    with open(a.out, "w", encoding="utf-8") as f:
        f.write("vol\tyr\tpages\tbody\tindex_toc\ttable_roster\tdivider\tpicture\tnonbody\tnonbody_pct\n")
        for r in sorted(rows, key=lambda r: (r[1], r[0])):
            f.write("\t".join(str(x) for x in r[:9]) + f"\t{r[9]:.1f}\n")
    print(f"\n-> {a.out}")

if __name__ == "__main__":
    main()
