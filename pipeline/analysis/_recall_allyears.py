"""Per-year OCR-era recall: completeness BEFORE (best-of merge only) and AFTER (merge + the additive
clause_seq recovery), capped at oracle N, unioned across each session-year's physical volumes.
Reports residual (oracle N - after) per year and the corpus total -- the campaign's scoreboard.

Mapping: exact leading year `production-<year>*` (biennium-named dirs are reported as UNMAPPED with
their oracle weight, never silently dropped). Writes a machine-readable table to
C:\\PatoLex-scratch\\_recall_allyears.json and prints a human table sorted by residual."""
import os, json, glob, csv, re
SCRATCH = r"C:\PatoLex-scratch"
ORACLE = r"C:\GitHub\PatoLex\docs\30_SYSTEM_DESIGN\sources\ca_chapter_counts.tsv"

oracle = {}
with open(ORACLE, encoding="utf-8") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        try:
            yr = int(row["session_year"])
        except Exception:
            continue
        if 1850 <= yr <= 1999 and row["session_type"] == "regular":
            oracle[yr] = int(row["total_chapters"])

def distinct(path, key, N):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return set()
    acts = d.get(key, d) if isinstance(d, dict) else d
    out = set()
    for a in (acts if isinstance(acts, list) else []):
        if isinstance(a, dict):
            n = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
            if isinstance(n, int) and 1 <= n <= N:
                out.add(n)
    return out

rows, unmapped = [], []
for yr, N in sorted(oracle.items()):
    dirs = [d for d in glob.glob(os.path.join(SCRATCH, f"production-{yr}*")) if os.path.isdir(d)]
    if not dirs:
        unmapped.append((yr, N)); continue
    before, after = set(), set()
    for d in dirs:
        mp = os.path.join(d, "parsed_acts_merged.json")
        if os.path.exists(mp):
            b = distinct(mp, "merged_acts", N); before |= b; after |= b
        cp = os.path.join(d, "parsed_acts_clauserec.json")
        if os.path.exists(cp):
            after |= distinct(cp, "recovered_acts", N)
    rows.append({"year": yr, "N": N, "before": len(before), "after": len(after),
                 "residual": N - len(after), "pct": round(100 * len(after) / N, 1), "vols": len(dirs)})

tot_N = sum(r["N"] for r in rows)
tot_before = sum(r["before"] for r in rows)
tot_after = sum(r["after"] for r in rows)
tot_resid = sum(r["residual"] for r in rows)
unmap_wt = sum(n for _, n in unmapped)
summary = {"mapped_years": len(rows), "tot_N": tot_N, "tot_before": tot_before, "tot_after": tot_after,
           "tot_residual": tot_resid, "pct_before": round(100 * tot_before / tot_N, 1) if tot_N else 0,
           "pct_after": round(100 * tot_after / tot_N, 1) if tot_N else 0,
           "unmapped_years": [y for y, _ in unmapped], "unmapped_weight": unmap_wt}
json.dump({"summary": summary, "rows": rows}, open(os.path.join(SCRATCH, "_recall_allyears.json"), "w"),
          indent=1)

print(f"OCR era 1850-1999 mapped years: {len(rows)}  N(total)={tot_N}")
print(f"  BEFORE (merge only):  {tot_before}/{tot_N} = {summary['pct_before']}%")
print(f"  AFTER  (+clause_seq):  {tot_after}/{tot_N} = {summary['pct_after']}%   RESIDUAL={tot_resid} chapters")
print(f"  unmapped (biennium-named, not measured): {summary['unmapped_years']} (weight {unmap_wt})")
print(f"\nYears still short (residual desc):")
print(f"  {'year':>5} {'N':>5} {'before':>6} {'after':>6} {'resid':>5} {'pct':>5} vols")
for r in sorted(rows, key=lambda x: -x["residual"]):
    if r["residual"] > 0:
        print(f"  {r['year']:>5} {r['N']:>5} {r['before']:>6} {r['after']:>6} {r['residual']:>5} {r['pct']:>5} {r['vols']}")
