"""Diagnose the born-digital gap: where does the DB stop (2024? 2025? 2026?), and WHAT is
missing in the ~90% years (the tail, a block, or scattered?)."""
import os, psycopg
ENV = r"C:\GitHub\PatoLex\.env.local"
for line in open(ENV, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
conn = psycopg.connect(os.environ["PATOLEX_PG_DSN"], connect_timeout=10)
cur = conn.cursor()
cur.execute("select min(chaptered_date), max(chaptered_date) from enactment")
print("chaptered_date range:", cur.fetchone())
cur.execute("""select extract(year from chaptered_date)::int yr, count(distinct chapter_number) dc,
               max(chapter_number) mx from enactment where chaptered_date >= '2023-01-01'
               group by yr order by yr""")
print("2023+ (year, distinct_chapters, max_chapter):")
for r in cur.fetchall():
    print("  ", r)
for yr, N in [(2024, 1017), (2016, 893), (2012, 876)]:
    cur.execute("select distinct chapter_number from enactment where extract(year from chaptered_date)=%s", (yr,))
    present = set(r[0] for r in cur.fetchall())
    missing = [c for c in range(1, N + 1) if c not in present]
    # contiguity: is the missing set a trailing block?
    tail = max(present) if present else 0
    print(f"\n{yr}: {len(missing)} missing of {N}; DB max present = {tail}.")
    print("   first 40 missing:", missing[:40])
conn.close()
