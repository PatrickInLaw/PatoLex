"""Born-digital 2000-2024 completeness: DB distinct chapters per year (capped at oracle N)
vs the oracle per-year denominator. The DB is the system of record for the modern era."""
import os, csv, psycopg
ENV = r"C:\GitHub\PatoLex\.env.local"
for line in open(ENV, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
ORACLE = r"C:\GitHub\PatoLex\docs\30_SYSTEM_DESIGN\sources\ca_chapter_counts.tsv"
oracle = {}
with open(ORACLE, encoding="utf-8") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        try:
            yr = int(row["session_year"])
        except Exception:
            continue
        if 2000 <= yr <= 2024 and row["session_type"] == "regular":
            oracle[yr] = oracle.get(yr, 0) + int(row["total_chapters"])
conn = psycopg.connect(os.environ["PATOLEX_PG_DSN"], connect_timeout=10)
cur = conn.cursor()
cur.execute("""select extract(year from chaptered_date)::int yr, count(distinct chapter_number)
               from enactment where chaptered_date >= '2000-01-01' and chaptered_date < '2025-01-01'
               group by yr order by yr""")
db = {r[0]: r[1] for r in cur.fetchall()}
conn.close()
print("YEAR | oracle_N | db_distinct | have(capped) | %")
th = ta = 0
for yr in sorted(oracle):
    N = oracle[yr]
    have = min(db.get(yr, 0), N)
    ta += N; th += have
    pct = f"{100*have/N:.0f}%" if N else "-"
    print(f"  {yr} | {N} | {db.get(yr, 0)} | {have} | {pct}")
print(f"\nBORN-DIGITAL 2000-2024 completeness: {th}/{ta} = {100*th/ta:.1f}%")
