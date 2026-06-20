"""Verify DB access (5080 Postgres over Tailnet) + dump the enactment schema for the
born-digital completeness pass. Reads the DSN from .env.local / PATOLEX_PG_DSN."""
import os, psycopg
ENV = r"C:\GitHub\PatoLex\.env.local"
if os.path.exists(ENV):
    for line in open(ENV, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
dsn = os.environ.get("PATOLEX_PG_DSN") or os.environ.get("DATABASE_URL")
conn = psycopg.connect(dsn, connect_timeout=10)
cur = conn.cursor()
cur.execute("select count(*) from enactment")
print("enactment count:", cur.fetchone()[0], "(expect 35332)")
cur.execute("""select column_name, data_type from information_schema.columns
               where table_name='enactment' order by ordinal_position""")
print("enactment columns:")
for r in cur.fetchall():
    print("   ", r[0], "::", r[1])
conn.close()
print("DB ACCESS OK")
