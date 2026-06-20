"""True 1900-1999 completeness as the UNION of ALL parse passes per session (certified,
chaptered_v2, recovered, repaired, multiengine, lostheader, fixed) across all physical
volumes, capped at oracle N. Each pass catches a different subset, so the union is the real
recoverable ceiling with existing artifacts. Ranks by gap."""
import os, json, glob, csv
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

def distinct(path, N):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return set()
    chs = set()
    lists = list(d.values()) if isinstance(d, dict) else [d]
    for v in lists:
        if isinstance(v, list):
            for a in v:
                if isinstance(a, dict):
                    n = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
                    if isinstance(n, int) and 1 <= n <= N:
                        chs.add(n)
    return chs

rows = []
nomap = []
for yr, N in oracle.items():
    dirs = [d for d in glob.glob(os.path.join(SCRATCH, f"production-{yr}*")) if os.path.isdir(d)]
    if not dirs:
        nomap.append(yr); continue
    union = set()
    for d in dirs:
        fp = os.path.join(d, "parsed_acts_merged.json")
        if os.path.exists(fp):
            union |= distinct(fp, N)
    rows.append((yr, N, len(union), len(dirs)))

rows.sort(key=lambda r: r[2] / r[1])
have = sum(r[2] for r in rows); tot = sum(r[1] for r in rows)
print(f"1900-1999 mapped sessions: {len(rows)}; UNION-of-passes completeness {have}/{tot} = {100*have/tot:.1f}%")
print(f"unmapped (biennium/budget-bundle naming, not real gaps): {sorted(nomap)}\n")
print("worst 18 by union % (year | oracle | union | % | #vols):")
for yr, N, n, nd in rows[:18]:
    print(f"  {yr} | {N} | {n} | {100*n/N:.0f}% | {nd}")
