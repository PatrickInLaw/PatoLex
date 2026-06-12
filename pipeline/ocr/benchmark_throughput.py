"""
benchmark_throughput.py -- consolidated, repeatable pages/min throughput
benchmark for the PatoLex historical OCR campaign.
=========================================================================
READ-ONLY. This script does NOT touch the live queue, the OCR workers, or
the ingest loop. It only *reads*:

  1. production_queue_state.json on the 5090 (per-volume claimed_at/done_at
     + worker_id) -- pulled over SSH (read-only `type`).
  2. source_document.page_count from the local Postgres `patolex` DB
     (total PDF pages -- coarse; body pages come from the logs).
  3. The box-side OCR run logs:
        5090: C:\\Users\\patolex\\PatoLex-scratch\\ocr-5090-run.log   (via SSH findstr)
        5080: C:\\Users\\PatrickKolasinski\\PatoLex-scratch\\ocr-5080-run.log (local)
     These carry, per volume:
        STAGE3-CLASSIFY | body=<N> ...           (body page count)
        STAGE4-OCR | OCR done: <N> body pages in <wall>s (<s/page>, <p/min>) ...
     The "OCR done" line is the *OCR-loop* time (sum of per-page seconds);
     it EXCLUDES render + preprocess. The queue done_at-claimed_at delta is
     the *end-to-end wall* time (render+preprocess+classify+OCR).
  4. Optionally, per-page `seconds` from each volume's
        production-<label>/ocr_consensus/page_ocr_results.json
     for fine-grained per-page rate (use --per-page).

Two rates are reported and clearly distinguished:
  - OCR-loop p/min   = 60 / mean(per-page seconds)        [from log / json]
  - End-to-end p/min = body_pages / (done_at - claimed_at) [from queue]

Hardware axis (captured live):
  - 5090 box: RTX 5090 32GB  + Intel Core Ultra 9 285K
  - 5080 box: RTX 5080 16GB  + Intel Core Ultra 7 265F  (this local box)

Usage:
    python benchmark_throughput.py                # queue + logs table
    python benchmark_throughput.py --per-page     # also pull per-page json rates
    python benchmark_throughput.py --no-ssh       # skip 5090 (local 5080 only)

Re-run anytime during the multi-day campaign to re-measure.
"""

import sys
import re
import json
import subprocess
from datetime import datetime
from pathlib import Path
import config

# --------------------------------------------------------------------------
# CONFIG (read-only endpoints)
# --------------------------------------------------------------------------
SSH_KEY   = r"C:/Users/PatrickKolasinski/.ssh/patolex_5090"
SSH_HOST  = "patolex@100.70.54.56"
SSH_OPTS  = ["-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=no"]

QUEUE_5090     = r"C:\Users\patolex\PatoLex-scratch\production_queue_state.json"
LOG_5090       = r"C:\Users\patolex\PatoLex-scratch\ocr-5090-run.log"
SCRATCH_5090   = r"C:\Users\patolex\PatoLex-scratch"

LOG_5080       = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch\ocr-5080-run.log")
SCRATCH_5080   = Path(config.path_for("data_root"))

PSQL = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"

HW = {
    "5090-1": ("5090", "RTX 5090 32GB", "Core Ultra 9 285K"),
    "5090-2": ("5090", "RTX 5090 32GB", "Core Ultra 9 285K"),
    "5090-3": ("5090", "RTX 5090 32GB", "Core Ultra 9 285K"),
    "5080-1": ("5080", "RTX 5080 16GB", "Core Ultra 7 265F"),
}


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


# --------------------------------------------------------------------------
# 1. QUEUE (5090, over SSH, read-only `type`)
# --------------------------------------------------------------------------
def fetch_queue(use_ssh=True):
    if not use_ssh:
        return []
    try:
        out = subprocess.run(
            ["ssh", "-i", SSH_KEY, *SSH_OPTS, SSH_HOST, f"type {QUEUE_5090}"],
            capture_output=True, text=True, timeout=40,
        ).stdout
        start = out.find("{")
        return json.loads(out[start:]).get("volumes", []) if start >= 0 else []
    except Exception as e:
        print(f"[warn] could not fetch queue: {e}", file=sys.stderr)
        return []


# --------------------------------------------------------------------------
# 2. DB page_count (total PDF pages -- coarse)
# --------------------------------------------------------------------------
def fetch_db_pagecounts():
    q = ("SELECT file_name, edition_year, page_count FROM source_document "
         "WHERE page_count IS NOT NULL ORDER BY edition_year;")
    try:
        import os
        env = dict(os.environ, PGPASSWORD=os.environ.get("PGPASSWORD", "postgres"))  # no hardcoded secret
        out = subprocess.run(
            [PSQL, "-U", "postgres", "-d", "patolex", "-t", "-A", "-F", "|", "-c", q],
            capture_output=True, text=True, timeout=30, env=env,
        ).stdout
    except Exception as e:
        print(f"[warn] DB query failed: {e}", file=sys.stderr)
        return {}
    counts = {}
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) == 3 and parts[2].strip().isdigit():
            counts[parts[0].strip()] = int(parts[2])
    return counts


# --------------------------------------------------------------------------
# 3. OCR run logs -> per-volume body count + OCR-loop time
# --------------------------------------------------------------------------
RE_BODY = re.compile(r"\[([^\]]+)\] STAGE3-CLASSIFY \| body=(\d+)")
RE_DONE = re.compile(
    r"\[([^\]]+)\] STAGE4-OCR \| OCR done: (\d+) body pages in "
    r"([\d.]+)s \(([\d.]+)s/page, ([\d.]+) p/min\)")


def read_5090_log():
    try:
        out = subprocess.run(
            ["ssh", "-i", SSH_KEY, *SSH_OPTS, SSH_HOST,
             f'findstr /C:"STAGE3-CLASSIFY | body=" /C:"OCR done" {LOG_5090}'],
            capture_output=True, text=True, timeout=40,
        ).stdout
        return out
    except Exception as e:
        print(f"[warn] could not read 5090 log: {e}", file=sys.stderr)
        return ""


def read_5080_log():
    try:
        return LOG_5080.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def parse_log(text):
    """Return {label: {body, ocr_wall_s, s_per_page, ocrloop_ppm}}."""
    vols = {}
    for line in text.splitlines():
        m = RE_BODY.search(line)
        if m:
            vols.setdefault(m.group(1), {})["body"] = int(m.group(2))
        m = RE_DONE.search(line)
        if m:
            v = vols.setdefault(m.group(1), {})
            v["body"] = int(m.group(2))
            v["ocr_wall_s"] = float(m.group(3))
            v["s_per_page"] = float(m.group(4))
            v["ocrloop_ppm"] = float(m.group(5))
    return vols


# --------------------------------------------------------------------------
# 4. Optional per-page timing from page_ocr_results.json (5080 local only here)
# --------------------------------------------------------------------------
def per_page_rate_local(label):
    p = SCRATCH_5080 / f"production-{label}" / "ocr_consensus" / "page_ocr_results.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        secs = [v.get("seconds", 0) for v in data.values() if v.get("seconds")]
        if not secs:
            return None
        mean = sum(secs) / len(secs)
        return (len(secs), 60.0 / mean if mean else 0.0)
    except Exception:
        return None


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
def main():
    use_ssh = "--no-ssh" not in sys.argv
    want_per_page = "--per-page" in sys.argv

    queue = fetch_queue(use_ssh)
    db = fetch_db_pagecounts()
    log_vols = {}
    if use_ssh:
        log_vols.update(parse_log(read_5090_log()))
    # local 5080 log entries (may overwrite/add)
    for k, v in parse_log(read_5080_log()).items():
        log_vols.setdefault(k, {}).update(v)

    # Build per-volume rows from the queue (has worker_id + timestamps)
    rows = []
    for vol in queue:
        label = vol.get("label")
        wid = vol.get("worker_id", "")
        card, gpu, cpu = HW.get(wid, ("?", "?", "?"))
        claimed = parse_ts(vol.get("claimed_at"))
        done = parse_ts(vol.get("done_at"))
        lv = log_vols.get(label, {})
        body = lv.get("body")
        wall_min = (done - claimed).total_seconds() / 60.0 if (claimed and done) else None
        e2e_ppm = (body / wall_min) if (body and wall_min) else None
        rows.append({
            "label": label, "year": vol.get("year"), "status": vol.get("status"),
            "worker": wid, "card": card, "cpu": cpu,
            "body": body,
            "claimed": vol.get("claimed_at"), "done": vol.get("done_at"),
            "wall_min": wall_min, "e2e_ppm": e2e_ppm,
            "ocr_wall_s": lv.get("ocr_wall_s"), "ocrloop_ppm": lv.get("ocrloop_ppm"),
            "s_per_page": lv.get("s_per_page"),
        })

    # ---- print per-volume table ----
    print("\n=== PER-VOLUME (queue + logs) ===")
    hdr = (f"{'label':<10}{'card':<6}{'worker':<8}{'status':<12}"
           f"{'body':>6}{'wall_min':>10}{'e2e_ppm':>9}{'ocrloop_ppm':>13}{'s/pg':>7}")
    print(hdr)
    print("-" * len(hdr))
    for r in sorted(rows, key=lambda x: (x["year"] or 0)):
        print(f"{str(r['label']):<10}{r['card']:<6}{r['worker']:<8}{str(r['status']):<12}"
              f"{(r['body'] or 0):>6}"
              f"{(f'{r['wall_min']:.1f}' if r['wall_min'] else '-'):>10}"
              f"{(f'{r['e2e_ppm']:.1f}' if r['e2e_ppm'] else '-'):>9}"
              f"{(f'{r['ocrloop_ppm']:.1f}' if r['ocrloop_ppm'] else '-'):>13}"
              f"{(f'{r['s_per_page']:.2f}' if r['s_per_page'] else '-'):>7}")

    if want_per_page:
        print("\n=== PER-PAGE (local 5080 page_ocr_results.json) ===")
        for r in rows:
            if r["card"] == "5080":
                pp = per_page_rate_local(r["label"])
                if pp:
                    print(f"  {r['label']}: {pp[0]} pages timed, {pp[1]:.1f} p/min (OCR-loop)")

    # ---- aggregate by configuration ----
    print("\n=== AGGREGATE BY CONFIG (completed volumes only) ===")
    done_rows = [r for r in rows if r["e2e_ppm"]]

    # Detect concurrent-worker windows per card by overlapping claim/done.
    def card_window(card):
        cr = [r for r in done_rows if r["card"] == card]
        if not cr:
            return None
        starts = [parse_ts(r["claimed"]) for r in cr if r["claimed"]]
        ends = [parse_ts(r["done"]) for r in cr if r["done"]]
        if not starts or not ends:
            return None
        span = (max(ends) - min(starts)).total_seconds() / 60.0
        tot_body = sum(r["body"] or 0 for r in cr)
        n_workers = len(set(r["worker"] for r in cr))
        return (n_workers, len(cr), tot_body, span, tot_body / span if span else 0)

    for card in ("5090", "5080"):
        w = card_window(card)
        if w:
            print(f"  {card}: {w[1]} vols across {w[0]} worker-ids | "
                  f"{w[2]} body pages / {w[3]:.1f} min window = {w[4]:.1f} pp/min aggregate")

    print("\nNOTE: e2e_ppm = body / (done_at - claimed_at), includes render+preprocess.")
    print("      ocrloop_ppm = 60 / mean per-page OCR seconds, EXCLUDES render+preprocess.")
    print("      Aggregate window can overlap idle gaps; treat as lower bound on busy rate.")


if __name__ == "__main__":
    main()
