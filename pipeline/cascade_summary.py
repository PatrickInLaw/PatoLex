"""
cascade_summary.py -- consolidate the per-volume cascade counts (_cascade/counts/{vol}.json) into
one readable table: per-volume flagged-rate at each stage + corrections, sorted worst-first.
Run standalone after a cascade, or import build_summary() (the harness calls it at end of a run).
Output: _cascade/per_volume_summary.tsv
"""
import os, json, glob

CASCADE = r"C:\Users\patolex\PatoLex-scratch\_cascade"

def build_summary(cascade_dir=CASCADE):
    rows = []
    for fp in glob.glob(os.path.join(cascade_dir, "counts", "*.json")):
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        m = d.get("meas", {}); s = d.get("stages", {}); ti = d.get("timings", {})
        def rate(k):
            v = m.get(k)
            return round(100.0 * v[0] / max(1, v[1]), 4) if v else None
        raw = m.get("raw", [0, 0]); aut = m.get("autocorrect", m.get("split", m.get("reunify", [0, 0])))
        red = round(100.0 * (raw[0] - aut[0]) / max(1, raw[0]), 1) if raw[0] else 0.0
        t_total = round(sum(v for v in ti.values() if isinstance(v, (int, float))), 2)
        rows.append({
            "vol": d.get("vol", os.path.basename(fp)[:-5]),
            "raw_flag": raw[0], "raw_tot": raw[1],
            "raw_pct": rate("raw"), "reunify_pct": rate("reunify"),
            "split_pct": rate("split"), "presonnet_pct": rate("autocorrect"),
            "reduction_pct": red,
            "n_reunify": s.get("reunify_break", 0) + s.get("reunify_space", 0) + s.get("reunify_xpage", 0),
            "n_split": s.get("split", 0),
            "n_autocorrect": s.get("autocorrect_e1", 0) + s.get("autocorrect_e2", 0),
            "t_load": ti.get("load", ""), "t_reunify": ti.get("reunify", ""),
            "t_split": ti.get("split", ""), "t_autocorrect": ti.get("autocorrect", ""),
            "t_total": t_total,
        })
    # worst pre-sonnet rate first (where quality is lowest = where to focus)
    rows.sort(key=lambda r: -(r["presonnet_pct"] or 0))
    out = os.path.join(cascade_dir, "per_volume_summary.tsv")
    cols = ["vol", "raw_flag", "raw_tot", "raw_pct", "reunify_pct", "split_pct", "presonnet_pct",
            "reduction_pct", "n_reunify", "n_split", "n_autocorrect",
            "t_load", "t_reunify", "t_split", "t_autocorrect", "t_total"]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in cols) + "\n")
    return out, rows

if __name__ == "__main__":
    out, rows = build_summary()
    print(f"{len(rows)} volumes -> {out}")
    print("\nworst 15 by pre-sonnet flagged rate:")
    print(f"{'vol':32s} {'raw%':>7} {'pre-son%':>8} {'reduc%':>7} {'n_auto':>8}")
    for r in rows[:15]:
        print(f"{r['vol']:32s} {str(r['raw_pct']):>7} {str(r['presonnet_pct']):>8} {str(r['reduction_pct']):>7} {r['n_autocorrect']:>8}")
    print("\nbest 5:")
    for r in rows[-5:]:
        print(f"{r['vol']:32s} {str(r['raw_pct']):>7} {str(r['presonnet_pct']):>8} {str(r['reduction_pct']):>7} {r['n_autocorrect']:>8}")
    print("\nslowest 12 volumes by total cpu seconds:")
    print(f"{'vol':32s} {'t_total':>8} {'reunify':>8} {'split':>8} {'autoc':>8}")
    for r in sorted(rows, key=lambda x: -(x['t_total'] or 0))[:12]:
        print(f"{r['vol']:32s} {str(r['t_total']):>8} {str(r['t_reunify']):>8} {str(r['t_split']):>8} {str(r['t_autocorrect']):>8}")
