"""Load reconcile's ambiguous pages (vlm_worklist.tsv: label, pidx, surya_class, surya_conf) into dbo.vlm_queue.
Idempotent (UNIQUE(label,pidx)). Re-runnable as the worklist grows. PATOLEX_QUEUE_DSN from env.
  python load_vlm_queue.py <vlm_worklist.tsv> [--watch]   # --watch: re-load every 60s until reconcile is done
"""
import os, sys, time, pyodbc

def load_once(cx, worklist):
    pdfmap = {r[0]: r[1] for r in cx.execute("SELECT label, pdf FROM dbo.ocr_queue").fetchall()}
    existing = {(r[0], r[1]) for r in cx.execute("SELECT label, pidx FROM dbo.vlm_queue").fetchall()}
    ins = skip = nopdf = 0
    if not os.path.exists(worklist):
        print(f"no worklist yet: {worklist}"); return
    for line in open(worklist, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) < 2:
            continue
        try:
            label, pidx = p[0], int(p[1])
        except ValueError:
            continue
        cls = p[2] if len(p) > 2 else None
        conf = float(p[3]) if len(p) > 3 and p[3] else None
        if (label, pidx) in existing:
            skip += 1; continue
        pdf = pdfmap.get(label)
        if not pdf:
            nopdf += 1; continue
        try:
            cx.execute("INSERT INTO dbo.vlm_queue(label,pdf,pidx,surya_class,surya_conf) VALUES (?,?,?,?,?)",
                       label, pdf, pidx, cls, conf)
            existing.add((label, pidx)); ins += 1
        except pyodbc.IntegrityError:
            skip += 1
    tot = cx.execute("SELECT COUNT(*), SUM(CASE WHEN state='pending' THEN 1 ELSE 0 END) FROM dbo.vlm_queue").fetchone()
    print(f"vlm_queue +{ins} inserted, {skip} dup-skip, {nopdf} no-pdf | total {tot[0]} ({tot[1]} pending)", flush=True)

def main():
    worklist = sys.argv[1]
    watch = "--watch" in sys.argv[2:]
    cx = pyodbc.connect(os.environ["PATOLEX_QUEUE_DSN"], autocommit=True)
    load_once(cx, worklist)
    if not watch:
        return
    while cx.execute("SELECT COUNT(*) FROM dbo.ocr_queue WHERE reconcile_state IN ('pending','working')").fetchone()[0] > 0:
        time.sleep(60)
        load_once(cx, worklist)
    load_once(cx, worklist)   # final sweep after reconcile finishes
    print("reconcile complete -> vlm_queue fully loaded", flush=True)

if __name__ == "__main__":
    main()
