"""
shape_worker_sql.py -- SQL-queue-driven page-SHAPE worker. Reuses the proven lease/heartbeat/fence machinery
from queue_worker_sql.py (atomic claim, lease token, self-abort on fence/DB-loss, attempts->held) and, for each
claimed volume, runs surya_page_shapes.py on its source PDF (render every page + Surya layout classify, PNGs
persisted, resumable). Crash-safe: a dead worker's lease expires and another re-claims.

Runs in the surya venv (pyodbc + surya + fitz). Connection comes from PATOLEX_QUEUE_DSN (never hardcoded).

Usage:
  shape_worker_sql.py <worker_id> --archive <pdf_dir> --render-root <dir> --out-dir <dir>
                      [--vram-frac 0.15] [--render-threads 4] [--once]
"""
import argparse, os, subprocess, sys, time

# reuse the battle-tested primitives (same package dir)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import queue_worker_sql as qw

ROLE = "shape"
SHAPE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analysis", "surya_page_shapes.py")


def run_shape(pdf_path, render_root, out_dir, vram_frac, threads):
    cmd = [sys.executable, os.path.abspath(SHAPE_SCRIPT), pdf_path,
           "--out-dir", out_dir, "--render-root", render_root,
           "--vram-frac", str(vram_frac), "--render-threads", str(threads), "--reuse"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    tail = ((proc.stdout or "")[-300:] + " || " + (proc.stderr or "")[-300:]).strip()
    return proc.returncode, tail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("worker_id")
    ap.add_argument("--archive", required=True, help="directory holding the source PDFs")
    ap.add_argument("--render-root", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--vram-frac", type=float, default=0.15)
    ap.add_argument("--render-threads", type=int, default=4)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()

    cx = qw.connect()
    qw.log("WORKER", f"{a.worker_id} online role=shape vram-frac={a.vram_frac}", "OK")

    while True:
        row = qw.claim_next(cx, ROLE, a.worker_id)
        if not row:
            if a.once:
                qw.log("WORKER", f"{a.worker_id} no claimable shape work", "OK"); return
            time.sleep(qw.IDLE_SLEEP_SEC); continue

        qw.record_history(cx, row["label"], ROLE, row["from"], "working", a.worker_id)
        lease = qw.Lease(qw.connect, ROLE, row["id"], row["lease"], a.worker_id)
        lease.start()
        pdf_path = os.path.join(a.archive, row["pdf"])
        try:
            if not os.path.exists(pdf_path):
                rc, tail = 2, f"source PDF not found: {pdf_path}"
            else:
                rc, tail = run_shape(pdf_path, a.render_root, a.out_dir, a.vram_frac, a.render_threads)
        except Exception as e:  # noqa: BLE001
            rc, tail = 99, str(e)[:400]
        finally:
            lease.stop()

        if lease.lost:
            qw.log("RUN", f"shape {row['label']} ABORTED (lease lost) -- not marking", "WARN")
        elif rc == 0:
            if qw.mark_done(cx, ROLE, row["id"], row["lease"]):
                qw.record_history(cx, row["label"], ROLE, "working", "done", a.worker_id)
                qw.log("RUN", f"shape {row['label']} DONE", "OK")
            else:
                qw.log("RUN", f"shape {row['label']} done but lease lost at commit -- skipped", "WARN")
        else:
            qw.mark_failed(cx, ROLE, row["id"], row["lease"], tail)
            qw.record_history(cx, row["label"], ROLE, "working", "failed", a.worker_id, tail[:200])
            qw.log("RUN", f"shape {row['label']} FAILED rc={rc}: {tail[:160]}", "FAIL")

        if a.once:
            return


if __name__ == "__main__":
    main()
