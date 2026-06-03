"""
seed_ocr_queue.py -- one-time seed of the MSSQL ocr_queue from the legacy JSON queue,
plus an optional inbox scan for the 1976-1999 (and beyond) add.

Authoritative design: docs/30_SYSTEM_DESIGN/SQL_PIPELINE_DESIGN_2026-06-03.md (REVISION 2 / §6).

ORDER (per §6): the JSON-queue workers are drained to 0 FIRST, THEN this runs -- so at seed time
there should be no live 'in_progress'. Any leftover in_progress/failed is mapped to a fresh prep
(full re-OCR -- acceptable for the ~0-5 in-flight volumes per Hans SERIOUS-7; logged, not silent).

IDEMPOTENT: a label already present in ocr_queue is left untouched (never clobbers advanced rows).
Seeds STEP-1 rows: prep+ocr live, Step-2 passes inert ('na'). Step 2 is enabled later by a
separate per-row UPDATE, not by this seed.

Connection from PATOLEX_QUEUE_DSN (never hardcoded). Run with --dry-run first and eyeball the plan.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import pyodbc
except ImportError:
    sys.stderr.write("pyodbc not installed (Step-1 prerequisite)\n")
    raise

YEAR_RE = re.compile(r"(1[89]\d\d|20\d\d)")   # 1800-2099, first match wins


def pdf_name_for(v: dict) -> str:
    """Mirror queue_claim.pdf_name_for: explicit 'pdf' else '<label>_Statutes.pdf'."""
    return v.get("pdf") or (v["label"] + "_Statutes.pdf")


def map_status(json_status: str) -> tuple[str, str, bool]:
    """Return (prep_state, ocr_state, set_done_at) for a Step-1 row from a legacy JSON status."""
    if json_status == "done":
        return "done", "done", True
    if json_status == "pending":
        return "pending", "pending", False
    # in_progress / failed at seed -> full re-do (drain-first should make this rare)
    return "pending", "pending", False


def load_json_volumes(path: Path) -> list[dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    return d.get("volumes", list(d.values())) if isinstance(d, dict) else d


def scan_inbox(inbox: Path) -> list[dict]:
    """Heuristic add: every *.pdf in inbox -> a pending volume. label=stem, year=first year in name.
    HEURISTIC -- review the derived (label, year) in --dry-run output before committing."""
    out = []
    for p in sorted(inbox.glob("*.pdf")):
        m = YEAR_RE.search(p.name)
        if not m:
            print(f"  SKIP (no year in name): {p.name}", file=sys.stderr)
            continue
        out.append({"label": p.stem, "year": int(m.group(1)), "pdf": p.name})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue-json", help="path to legacy production_queue_state.json")
    ap.add_argument("--inbox", help="dir to scan for additional PDFs (e.g. the 1976-1999 add)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    args = ap.parse_args()
    if not args.queue_json and not args.inbox:
        ap.error("provide --queue-json and/or --inbox")

    rows: dict[str, dict] = {}     # label -> {label, yr, pdf, prep_state, ocr_state, set_done}
    requeued = 0

    if args.queue_json:
        for v in load_json_volumes(Path(args.queue_json)):
            label = v["label"]
            prep_s, ocr_s, set_done = map_status(v.get("status", "pending"))
            if v.get("status") in ("in_progress", "failed"):
                requeued += 1
            rows[label] = {"label": label, "yr": int(v.get("year") or YEAR_RE.search(label).group(1)),
                           "pdf": pdf_name_for(v), "prep_state": prep_s, "ocr_state": ocr_s,
                           "set_done": set_done}

    if args.inbox:
        for v in scan_inbox(Path(args.inbox)):
            if v["label"] in rows:
                continue   # JSON entry wins
            rows[v["label"]] = {"label": v["label"], "yr": v["year"], "pdf": v["pdf"],
                                "prep_state": "pending", "ocr_state": "pending", "set_done": False}

    plan = sorted(rows.values(), key=lambda r: (r["yr"], r["label"]))
    done_n = sum(1 for r in plan if r["set_done"])
    print(f"PLAN: {len(plan)} volumes  ({done_n} done, {len(plan) - done_n} pending, "
          f"{requeued} re-queued from in_progress/failed)")
    print(f"  year span: {plan[0]['yr']}..{plan[-1]['yr']}" if plan else "  (empty)")

    if args.dry_run:
        for r in plan:
            print(f"  {r['yr']}  {r['label']:<28} {r['prep_state']}/{r['ocr_state']}  <- {r['pdf']}")
        print("DRY RUN -- nothing written.")
        return

    dsn = os.environ.get("PATOLEX_QUEUE_DSN")
    if not dsn:
        sys.stderr.write("PATOLEX_QUEUE_DSN not set\n")
        sys.exit(2)
    cx = pyodbc.connect(dsn, autocommit=True)

    inserted = skipped = 0
    for r in plan:
        # idempotent: only insert when the label is absent (never clobber an advanced row)
        cur = cx.execute(
            "INSERT INTO dbo.ocr_queue (label, pdf, yr, prep_state, ocr_state, done_at) "
            "SELECT ?, ?, ?, ?, ?, CASE WHEN ?=1 THEN sysutcdatetime() ELSE NULL END "
            "WHERE NOT EXISTS (SELECT 1 FROM dbo.ocr_queue WHERE label = ?)",
            r["label"], r["pdf"], r["yr"], r["prep_state"], r["ocr_state"],
            1 if r["set_done"] else 0, r["label"],
        )
        if cur.rowcount == 1:
            inserted += 1
        else:
            skipped += 1
    print(f"SEEDED: {inserted} inserted, {skipped} already present (left untouched).")


if __name__ == "__main__":
    main()
