"""
setup_shape_3060.py -- apply the shape-pass schema extension and seed the authoritative manifest into the
3060 PatoLexQueue, for the page-shape job. Idempotent. Runs where pyodbc + ODBC Driver 18 exist (the 5090).

Reads PATOLEX_QUEUE_DSN from the environment (never hardcoded). Inputs:
  --manifest <manifest.tsv>   from consolidate_manifest.py (label, pdf, yr, pdf_exists, source, note)
  --schema   <schema_shape_ext.sql>
Seeds each volume into dbo.volume_manifest (record of truth) and dbo.ocr_queue with shape_state='pending'
and prep/ocr='na' (this is a SHAPE-ONLY run -- the OCR passes stay inert). Idempotent: existing labels skipped.
"""
import argparse, os, sys

def connect():
    import pyodbc
    dsn = os.environ.get("PATOLEX_QUEUE_DSN")
    if not dsn:
        sys.stderr.write("PATOLEX_QUEUE_DSN not set\n"); sys.exit(2)
    return pyodbc.connect(dsn, autocommit=True)

def apply_schema(cx, schema_path):
    sql = open(schema_path, encoding="utf-8").read()
    batches = [b.strip() for b in sql.replace("\r\n", "\n").split("\nGO") if b.strip()]
    for b in batches:
        cx.execute(b)
    print(f"schema applied ({len(batches)} batches)")

def read_manifest(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        header = f.readline()
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            p = line.split("\t")
            # label, pdf, yr, pdf_exists, source, note
            rows.append({"label": p[0], "pdf": p[1], "yr": int(p[2]),
                         "exists": p[3] == "1", "source": p[4], "note": p[5] if len(p) > 5 else ""})
    return rows

def seed(cx, rows):
    have_mani = {r[0] for r in cx.execute("SELECT label FROM dbo.volume_manifest").fetchall()}
    have_q    = {r[0] for r in cx.execute("SELECT label FROM dbo.ocr_queue").fetchall()}
    mins = qins = skipped_missing = 0
    for r in rows:
        if not r["exists"]:
            skipped_missing += 1   # do not enqueue a volume whose source PDF is absent
            continue
        if r["label"] not in have_mani:
            cx.execute("INSERT INTO dbo.volume_manifest(label,pdf,yr,source,note) VALUES (?,?,?,?,?)",
                       r["label"], r["pdf"], r["yr"], r["source"], r["note"][:400])
            mins += 1
        if r["label"] not in have_q:
            cx.execute("INSERT INTO dbo.ocr_queue(label,pdf,yr,prep_state,ocr_state,shape_state) "
                       "VALUES (?,?,?, 'na','na','pending')", r["label"], r["pdf"], r["yr"])
            qins += 1
    print(f"volume_manifest +{mins}   ocr_queue(shape pending) +{qins}   skipped(missing PDF) {skipped_missing}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--skip-schema", action="store_true")
    a = ap.parse_args()
    cx = connect()
    if not a.skip_schema:
        apply_schema(cx, a.schema)
    rows = read_manifest(a.manifest)
    seed(cx, rows)
    tot = cx.execute("SELECT COUNT(*) FROM dbo.ocr_queue WHERE shape_state='pending'").fetchone()[0]
    print(f"TOTAL shape-pending in queue: {tot}")

if __name__ == "__main__":
    main()
