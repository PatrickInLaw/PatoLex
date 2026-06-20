"""1900-1999 OCR-era completeness, measured HONESTLY and reproducibly.

For each oracle REGULAR session 1900-1999, completeness = (distinct chapter numbers present in the
best-of merge `parsed_acts_merged.json`, unioned across that session's physical volumes, capped at
oracle N) / N. Two numerators are reported: ALL distinct chapters, and CONTENT-COMPLETE only
(chapters whose merged act carries >=15 body tokens -- excludes bodyless title-stubs so they don't
silently inflate the number).

Volume->session mapping is by exact leading year in the dir name (`production-<year>*`). Sessions
whose volumes do not map this way (biennium-named dirs like 1900-01 carry a different/mixed chapter
numbering and do NOT cleanly hold a single session) are NOT silently dropped: they are listed with
their oracle weight so the denominator is fully transparent. The headline % is over MAPPED sessions;
the unmapped weight is stated explicitly (this is the limitation Hans flagged in cc015)."""
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
        if 1900 <= yr <= 1999 and row["session_type"] == "regular":
            oracle[yr] = int(row["total_chapters"])

def chapters(path, N):
    """(all_distinct, content_complete) sets of chapter numbers in a merged file, capped at N."""
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return set(), set()
    acts = d.get("merged_acts", d) if isinstance(d, dict) else d
    allc, full = set(), set()
    for a in (acts if isinstance(acts, list) else []):
        if not isinstance(a, dict):
            continue
        n = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
        if isinstance(n, int) and 1 <= n <= N:
            allc.add(n)
            if len(re.findall(r"[a-z]{4,}", (a.get("text") or "").lower())) >= 15:
                full.add(n)
    return allc, full

def dirs_for(yr):
    return [d for d in glob.glob(os.path.join(SCRATCH, f"production-{yr}*")) if os.path.isdir(d)]

mapped, unmapped = [], []
for yr, N in sorted(oracle.items()):
    ds = dirs_for(yr)
    if not ds:
        unmapped.append((yr, N)); continue
    allu, fullu = set(), set()
    for d in ds:
        fp = os.path.join(d, "parsed_acts_merged.json")
        if os.path.exists(fp):
            a, f = chapters(fp, N)
            allu |= a; fullu |= f
    mapped.append((yr, N, len(allu), len(fullu), len(ds)))

tot_oracle = sum(oracle.values())
map_den = sum(r[1] for r in mapped)
map_all = sum(r[2] for r in mapped)
map_full = sum(r[3] for r in mapped)
unmap_wt = sum(n for _, n in unmapped)

print(f"1900-1999 regular sessions in oracle: {len(oracle)}  (total {tot_oracle} chapters)")
print(f"MAPPED sessions: {len(mapped)}  denominator {map_den} chapters")
print(f"  all-distinct union   {map_all}/{map_den} = {100*map_all/map_den:.1f}%  (incl. bodyless stubs)")
print(f"  content-complete (>=15 body tok) {map_full}/{map_den} = {100*map_full/map_den:.1f}%  (honest floor)")
print(f"UNMAPPED sessions (volumes not dir-mapped -- NOT measured): {len(unmapped)}, "
      f"oracle weight {unmap_wt} chapters ({100*unmap_wt/tot_oracle:.1f}% of the era)")
print(f"  {sorted(y for y, _ in unmapped)}")
print(f"\nworst 18 mapped by all-distinct % (year | oracle N | all | full | %all | #vols):")
for yr, N, na, nf, nd in sorted(mapped, key=lambda r: r[2] / r[1])[:18]:
    print(f"  {yr} | {N} | {na} | {nf} | {100*na/N:.0f}% | {nd}")
