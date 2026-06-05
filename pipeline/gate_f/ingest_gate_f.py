#!/usr/bin/env python3
"""
ingest_gate_f.py -- Load Gate F JSONL records into the PatoLex PostgreSQL database.

Reads gate_f_YYYY_actions.jsonl files produced by parse_bill_versions.py and
inserts records into: enactment, provision, designation_history, change_event.

Usage:
    # Set DB connection first:
    #   $env:DATABASE_URL = "postgresql://postgres:<pw>@<host>:5432/postgres"
    python ingest_gate_f.py <jsonl_file_or_dir> [--commit] [--years 2005 2007 ...]

Default mode is DRY RUN. Pass --commit to write to the database.

Idempotency: enactments are keyed by citation ("CA YYYY Ch. N"). If a chapter
already exists in the DB, all its records are skipped. Provisions are looked up
by current_designation before insert. designation_history is inserted once per
(provision_id, code, section_number); subsequent changes to the same section do
not update the designation row (renumbering is handled separately via lineage_edge).
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import psycopg
except ImportError:
    print("ERROR: psycopg not installed. Run: pip install psycopg[binary]", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

ENACTMENT_SELECT = """
    SELECT id FROM enactment WHERE citation = %s AND jurisdiction = 'CA'
"""

ENACTMENT_INSERT = """
    INSERT INTO enactment
        (citation, jurisdiction, session, chapter_number,
         chaptered_date, operative_date, title, kind)
    VALUES (%s, 'CA', %s, %s, %s, %s, %s, 'statute')
    RETURNING id
"""

PROVISION_SELECT = """
    SELECT id FROM provision
    WHERE jurisdiction = 'CA' AND unit_type = 'code_section'
      AND current_designation = %s
"""

PROVISION_INSERT = """
    INSERT INTO provision (jurisdiction, unit_type, current_designation, status)
    VALUES ('CA', 'code_section', %s, 'active')
    RETURNING id
"""

DESIG_CHECK = """
    SELECT id FROM designation_history
    WHERE provision_id = %s AND code = %s AND section_number = %s
    LIMIT 1
"""

# Cast to daterange required because psycopg3 sends Python str as text by default.
DESIG_INSERT = """
    INSERT INTO designation_history (provision_id, code, section_number, label, valid_range)
    VALUES (%s, %s, %s, %s, %s::daterange)
"""

CHANGE_EVENT_INSERT = """
    INSERT INTO change_event
        (enactment_id, provision_id, action, new_text, operative_date,
         in_act_order, chaptered_out, trust_level, confident, confidence)
    VALUES (%s, %s, %s, %s, %s, %s, FALSE, 'official_xml', TRUE, 1.0)
"""

PROVISION_REPEAL = """
    UPDATE provision SET status = 'repealed' WHERE id = %s
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session_label(year: int) -> str:
    """Return two-year session label, e.g. 2005 -> '2005-2006'."""
    if year % 2 == 1:
        return f"{year}-{year + 1}"
    return f"{year - 1}-{year}"


def _designation(code_id: str, section_num: str) -> str:
    return f"{code_id} {section_num}"


def _daterange(date_str: str | None) -> str:
    """Postgres daterange literal: '[YYYY-MM-DD,)' or '(,)' if unknown."""
    return f"[{date_str},)" if date_str else "(,)"


# ---------------------------------------------------------------------------
# Per-file ingest
# ---------------------------------------------------------------------------

def ingest_file(jsonl_path: Path, cur, commit: bool, stats: dict) -> int:
    """
    Ingest one gate_f_YYYY_actions.jsonl file.
    Returns total number of JSONL records processed (not just inserted).
    """
    records = []
    with open(jsonl_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        return 0

    # Group by (chapter_year, chapter_num) -> one enactment each
    chapters: dict = defaultdict(list)
    for rec in records:
        chapters[(rec['chapter_year'], rec['chapter_num'])].append(rec)

    processed = 0

    for (chapter_year, chapter_num), recs in sorted(chapters.items()):
        citation = f"CA {chapter_year} Ch. {chapter_num}"

        # --- Enactment lookup / insert ---
        cur.execute(ENACTMENT_SELECT, (citation,))
        row = cur.fetchone()
        if row:
            # Enactment exists — check for partial-commit crash (enactment committed
            # but change_events not). If change_events present, skip. If absent,
            # delete and re-ingest to close the gap.
            cur.execute(
                "SELECT COUNT(*) FROM change_event WHERE enactment_id = %s",
                (row[0],)
            )
            ce_count = cur.fetchone()[0]
            if ce_count > 0:
                stats['chapters_skipped'] += 1
                processed += len(recs)
                continue
            # Partial commit — purge orphan enactment and fall through to re-insert
            if commit:
                cur.execute("DELETE FROM enactment WHERE id = %s", (row[0],))

        stats['chapters_new'] += 1

        first = recs[0]
        chaptering_date = first.get('chaptering_date')
        operative_date  = first.get('operative_date')
        session         = _session_label(chapter_year)

        if commit:
            cur.execute(ENACTMENT_INSERT, (
                citation, session, chapter_num,
                chaptering_date, operative_date, None  # title unknown from CAML
            ))
            enactment_id = cur.fetchone()[0]
        else:
            enactment_id = None  # dry-run placeholder

        # --- Per-section records ---
        for rec in sorted(recs, key=lambda r: r['bill_section_order']):
            code_id     = rec['code_id']
            section_num = rec['section_num']
            action      = rec['action']   # 'amend' | 'add' | 'repeal'
            new_text    = rec.get('new_text') or ''
            op_date     = rec.get('operative_date')
            # bill_section_order is 1-based in JSONL; schema expects 0-based
            order_0     = rec.get('bill_section_order', 1) - 1

            desig = _designation(code_id, section_num)

            # --- Provision lookup / insert ---
            cur.execute(PROVISION_SELECT, (desig,))
            prow = cur.fetchone()
            if prow:
                provision_id = prow[0]
                stats['provisions_existing'] += 1
            else:
                stats['provisions_new'] += 1
                if commit:
                    cur.execute(PROVISION_INSERT, (desig,))
                    provision_id = cur.fetchone()[0]
                else:
                    provision_id = None

            # --- designation_history (once per provision) ---
            if commit and provision_id is not None:
                cur.execute(DESIG_CHECK, (provision_id, code_id, section_num))
                if not cur.fetchone():
                    label  = f"{code_id} § {section_num}"
                    drange = _daterange(op_date)
                    cur.execute(DESIG_INSERT, (provision_id, code_id, section_num, label, drange))
                    stats['designations_new'] += 1

            # --- change_event ---
            # source_document_id intentionally NULL: Gate F derives from structured
            # CAML XML, not a registered scan/source_document. The unique index on
            # (source_document_id, in_act_order) does not fire on NULLs, so
            # double-ingest prevention relies on the enactment-level skip above.
            stats['change_events'] += 1
            if commit and enactment_id is not None and provision_id is not None:
                cur.execute(CHANGE_EVENT_INSERT, (
                    enactment_id, provision_id, action, new_text,
                    op_date, order_0
                ))
                if action == 'repeal':
                    cur.execute(PROVISION_REPEAL, (provision_id,))
                    stats['provisions_repealed'] += 1

            processed += 1

    return processed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(paths: list, commit: bool, years_filter: set | None):
    dsn = os.environ.get('DATABASE_URL') or os.environ.get('DIRECT_URL')
    if not dsn:
        print("ERROR: set DATABASE_URL (direct port 5432) before running", file=sys.stderr)
        sys.exit(1)

    # Collect JSONL files
    jsonl_files = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.glob('gate_f_*_actions.jsonl')):
                if years_filter:
                    m = re.search(r'(\d{4})', f.name)
                    if m and int(m.group(1)) not in years_filter:
                        continue
                jsonl_files.append(f)
        elif p.is_file():
            if years_filter:
                m = re.search(r'(\d{4})', p.name)
                if m and int(m.group(1)) not in years_filter:
                    continue
            jsonl_files.append(p)

    if not jsonl_files:
        print("No gate_f_*_actions.jsonl files found.", file=sys.stderr)
        sys.exit(1)

    mode = "COMMIT" if commit else "DRY RUN"
    print(f"Gate F ingest — {mode} — {len(jsonl_files)} file(s)\n")

    stats = {
        'chapters_new':        0,
        'chapters_skipped':    0,
        'provisions_new':      0,
        'provisions_existing': 0,
        'designations_new':    0,
        'change_events':       0,
        'provisions_repealed': 0,
    }

    conn = psycopg.connect(dsn)
    try:
        cur = conn.cursor()
        for jf in jsonl_files:
            print(f"  {jf.name} ...", end=' ', flush=True)
            try:
                n = ingest_file(jf, cur, commit, stats)
                if commit:
                    conn.commit()   # commit per file — one file failure doesn't roll back others
                print(f"{n} records")
            except Exception as exc:
                conn.rollback()
                print(f"FAILED: {exc}", file=sys.stderr)
                raise

        if not commit:
            conn.rollback()
    finally:
        conn.close()

    print(f"""
Summary ({mode}):
  Chapters new:          {stats['chapters_new']}
  Chapters skipped:      {stats['chapters_skipped']}  (already in DB)
  Provisions new:        {stats['provisions_new']}
  Provisions existing:   {stats['provisions_existing']}
  Designations new:      {stats['designations_new']}
  Change events:         {stats['change_events']}
  Provisions repealed:   {stats['provisions_repealed']}
""")
    if not commit:
        print("  Re-run with --commit to write to the database.")


def main():
    ap = argparse.ArgumentParser(description='Ingest Gate F JSONL into PatoLex DB')
    ap.add_argument('paths', nargs='+',
                    help='gate_f_*_actions.jsonl file(s) or directory containing them')
    ap.add_argument('--commit', action='store_true',
                    help='Write to DB (default: dry run)')
    ap.add_argument('--years', nargs='+', type=int, default=None,
                    help='Only ingest specific years, e.g. --years 2005 2006')
    args = ap.parse_args()

    run(args.paths, args.commit, set(args.years) if args.years else None)


if __name__ == '__main__':
    main()
