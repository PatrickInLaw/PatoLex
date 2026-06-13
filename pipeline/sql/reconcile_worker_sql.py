"""
reconcile_worker_sql.py -- SQL-queue-driven RECONCILE worker, runs on the 5080 (CPU/text, no GPU). Claims
volumes whose shape pass is done, pulls that volume's shape TSV live from the 5090 (scp), reads the local
out_context page text, and runs shape_reconcile.py to procedurally rescue/confirm the non-body flags -- routing
only the ambiguous residual to a VLM worklist. Reuses queue_worker_sql's lease/heartbeat/fence primitives.

  reconcile_worker_sql.py <worker_id> --key <sshkey> --out-context <dir> --reconciled-dir <dir>
                          --ambiguous <vlm_worklist.tsv> [--host patolex@100.70.54.56] [--once]
PATOLEX_QUEUE_DSN comes from the environment.
"""
import argparse, os, re, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import queue_worker_sql as qw

ROLE = "reconcile"
RECON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analysis", "shape_reconcile.py")

def pull_shape_tsv(key, host, pdfbase, dest):
    remote = f"{host}:C:/Users/patolex/PatoLex-scratch/page-shapes/{pdfbase}.shapes.tsv"
    r = subprocess.run(["scp", "-i", key, "-o", "BatchMode=yes", remote, dest], capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or "")[-200:]

def mark_done_counts(cx, row_id, token, rescued, confirmed, ambiguous):
    cur = cx.execute(
        "UPDATE dbo.ocr_queue SET reconcile_state='done', reconcile_done_at=sysutcdatetime(), "
        "reconcile_rescued=?, reconcile_confirmed=?, reconcile_ambiguous=?, updated_at=sysutcdatetime() "
        "WHERE id=? AND reconcile_lease_token=?", rescued, confirmed, ambiguous, row_id, token)
    return cur.rowcount == 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("worker_id")
    ap.add_argument("--key", required=True)
    ap.add_argument("--host", default="patolex@100.70.54.56")
    ap.add_argument("--out-context", required=True)
    ap.add_argument("--reconciled-dir", required=True)
    ap.add_argument("--ambiguous", required=True)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.reconciled_dir, exist_ok=True)

    cx = qw.connect()
    qw.log("WORKER", f"{a.worker_id} online role=reconcile", "OK")
    while True:
        row = qw.claim_next(cx, ROLE, a.worker_id)
        if not row:
            if a.once:
                qw.log("WORKER", f"{a.worker_id} no claimable reconcile work", "OK"); return
            time.sleep(qw.IDLE_SLEEP_SEC); continue
        qw.record_history(cx, row["label"], ROLE, row["from"], "working", a.worker_id)
        lease = qw.Lease(qw.connect, ROLE, row["id"], row["lease"], a.worker_id); lease.start()
        counts = (0, 0, 0)
        try:
            pdfbase = os.path.splitext(row["pdf"])[0]
            tsv = os.path.join(tempfile.gettempdir(), pdfbase + ".shapes.tsv")
            ok, err = pull_shape_tsv(a.key, a.host, pdfbase, tsv)
            text = os.path.join(a.out_context, "production-" + row["label"] + ".json")
            if not ok:
                rc, tail = 2, f"scp failed: {err}"
            elif not os.path.exists(text):
                rc, tail = 3, f"no out_context: {os.path.basename(text)}"
            else:
                out = os.path.join(a.reconciled_dir, row["label"] + ".reconciled.tsv")
                p = subprocess.run([sys.executable, os.path.abspath(RECON), "--shape-tsv", tsv,
                                    "--text-json", text, "--out", out, "--ambiguous", a.ambiguous,
                                    "--label", row["label"]], capture_output=True, text=True)
                rc = p.returncode; tail = (p.stdout or "")[-300:] + (p.stderr or "")[-200:]
                m = dict(re.findall(r"(rescued|confirmed|ambiguous)=(\d+)", tail))
                counts = (int(m.get("rescued", 0)), int(m.get("confirmed", 0)), int(m.get("ambiguous", 0)))
        except Exception as e:  # noqa: BLE001
            rc, tail = 99, str(e)[:300]
        finally:
            lease.stop()

        if lease.lost:
            qw.log("RUN", f"reconcile {row['label']} ABORTED (lease lost)", "WARN")
        elif rc == 0:
            if mark_done_counts(cx, row["id"], row["lease"], *counts):
                qw.record_history(cx, row["label"], ROLE, "working", "done", a.worker_id)
                qw.log("RUN", f"reconcile {row['label']} DONE (rescued {counts[0]} confirmed {counts[1]} amb {counts[2]})", "OK")
            else:
                qw.log("RUN", f"reconcile {row['label']} lease lost at commit", "WARN")
        else:
            qw.mark_failed(cx, ROLE, row["id"], row["lease"], tail)
            qw.record_history(cx, row["label"], ROLE, "working", "failed", a.worker_id, tail[:200])
            qw.log("RUN", f"reconcile {row['label']} FAILED rc={rc}: {tail[:150]}", "FAIL")
        if a.once:
            return

if __name__ == "__main__":
    main()
