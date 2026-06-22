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

def distinct(path, key, N, only_status=None):
    """Distinct chapter_int in a parse file. If only_status is given (e.g. 'image_verified'), count
    ONLY acts with that status -- so visual not_found/legislative_gap entries do NOT inflate the
    recovered count. Returns (counted_set, legislative_gap_set) -- the gap set lists oracle chapters
    that were NEVER enacted (denominator over-count) when present in a visual file."""
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return set(), set()
    acts = d.get(key, d) if isinstance(d, dict) else d
    out, leggap = set(), set()
    for a in (acts if isinstance(acts, list) else []):
        if isinstance(a, dict):
            n = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
            if isinstance(n, int) and 1 <= n <= N:
                st = a.get("status")
                if st == "legislative_gap":
                    leggap.add(n)
                elif only_status is None or st == only_status or (
                        isinstance(only_status, (tuple, list)) and st in only_status):
                    out.add(n)
    return out, leggap

rows, unmapped = [], []
for yr, N in sorted(oracle.items()):
    dirs = [d for d in glob.glob(os.path.join(SCRATCH, f"production-{yr}*")) if os.path.isdir(d)]
    if not dirs:
        unmapped.append((yr, N)); continue
    before, after, leg = set(), set(), set()
    for d in dirs:
        mp = os.path.join(d, "parsed_acts_merged.json")
        if os.path.exists(mp):
            b, _ = distinct(mp, "merged_acts", N); before |= b; after |= b
        cp = os.path.join(d, "parsed_acts_clauserec.json")
        if os.path.exists(cp):
            c, _ = distinct(cp, "recovered_acts", N); after |= c
        vp = os.path.join(d, "parsed_acts_visual.json")  # image_verified + ocr_text_verified count; gaps tracked
        if os.path.exists(vp):
            v, g = distinct(vp, "recovered_acts", N, only_status=("image_verified", "ocr_text_verified")); after |= v; leg |= g
    leg -= after  # a chapter both recovered somewhere AND marked gap elsewhere -> trust the recovery
    eff_N = N - len(leg)  # legislative gaps were never enacted -> reduce the true denominator
    rows.append({"year": yr, "N": N, "eff_N": eff_N, "before": len(before), "after": len(after),
                 "leg_gap": len(leg), "residual": eff_N - len(after),
                 "pct": round(100 * len(after) / eff_N, 1) if eff_N else 100.0, "vols": len(dirs)})

tot_N = sum(r["eff_N"] for r in rows)        # true denominator = oracle N minus legislative gaps
tot_oracleN = sum(r["N"] for r in rows)
tot_before = sum(r["before"] for r in rows)
tot_after = sum(r["after"] for r in rows)
tot_resid = sum(r["residual"] for r in rows)
tot_leg = sum(r["leg_gap"] for r in rows)
unmap_wt = sum(n for _, n in unmapped)
summary = {"mapped_years": len(rows), "tot_eff_N": tot_N, "tot_oracleN": tot_oracleN,
           "tot_before": tot_before, "tot_after": tot_after, "tot_residual": tot_resid,
           "legislative_gaps": tot_leg,
           "pct_before": round(100 * tot_before / tot_N, 1) if tot_N else 0,
           "pct_after": round(100 * tot_after / tot_N, 1) if tot_N else 0,
           "unmapped_years": [y for y, _ in unmapped], "unmapped_weight": unmap_wt}
json.dump({"summary": summary, "rows": rows}, open(os.path.join(SCRATCH, "_recall_allyears.json"), "w"),
          indent=1)

print(f"OCR era 1850-1999 mapped years: {len(rows)}  oracleN={tot_oracleN} effN(minus {tot_leg} leg-gaps)={tot_N}")
print(f"  BEFORE (merge only):  {tot_before}/{tot_N} = {summary['pct_before']}%")
print(f"  AFTER (clause+VISUAL image-verified): {tot_after}/{tot_N} = {summary['pct_after']}%   RESIDUAL={tot_resid}")
print(f"  unmapped (biennium-named, not measured): {summary['unmapped_years']} (weight {unmap_wt})")
print(f"\nYears still short (residual desc):")
print(f"  {'year':>5} {'effN':>5} {'before':>6} {'after':>6} {'resid':>5} {'leg':>4} {'pct':>5} vols")
for r in sorted(rows, key=lambda x: -x["residual"]):
    if r["residual"] > 0:
        print(f"  {r['year']:>5} {r['eff_N']:>5} {r['before']:>6} {r['after']:>6} {r['residual']:>5} {r['leg_gap']:>4} {r['pct']:>5} {r['vols']}")
