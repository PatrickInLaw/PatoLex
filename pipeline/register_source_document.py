#!/usr/bin/env python3
"""
register_source_document.py -- Create a source_document row for a volume.

This is the MISSING LINK between ocr_only_5090.py (which writes sha256.txt)
and ingest_clean.py (which requires source_document to pre-exist, resolved by
content_sha256). Must be run once per volume before ingest_clean.py --commit.

Also used for born-digital volumes (2000-2008 Chief Clerk PDFs) that bypass
OCR but still need a source_document record to anchor ingest_clean.py.

Usage:
    # Set DATABASE_URL or PATOLEX_PG_DSN env var first
    python register_source_document.py <session_label> <pdf_path> [--type ocr|born_digital]

    # Example OCR volume:
    python register_source_document.py 1877-78-code /path/to/1877_vol.pdf

    # Example born-digital volume:
    python register_source_document.py 2000_Vol1 /path/to/2000_Vol1.pdf --type born_digital

The script:
  1. Computes SHA256 of the PDF (or reads existing sha256.txt)
  2. Writes sha256.txt to production-<session_label>/ if not present
  3. INSERTs source_document row (ON CONFLICT DO NOTHING -- idempotent)
  4. Prints the source_document id
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

try:
    import psycopg
except ImportError:
    print("ERROR: psycopg not installed. Run: pip install psycopg[binary]", file=sys.stderr)
    sys.exit(1)

SCRATCH_ROOT = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch")

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

INSERT_SQL = """
INSERT INTO source_document (
    type, citation, jurisdiction, source_channel, source_uri,
    scan_quality, ocr_engine, ocr_cer_estimate,
    trust_level, retrieved_at, clean_channel,
    content_sha256, edition_year, claimed_year, verification_note,
    file_name, corpus, coverage_start_year, coverage_end_year,
    page_count, media_format
) VALUES (
    'session_law',
    %s, 'CA', 'clerk.assembly.ca.gov', NULL,
    %s, %s, %s,
    %s, NOW(), TRUE,
    %s, %s, %s, %s,
    %s, 'uncodified_statutes', %s, %s,
    %s, 'pdf'
)
ON CONFLICT (content_sha256) WHERE content_sha256 IS NOT NULL DO NOTHING
RETURNING id
"""

SELECT_SQL = "SELECT id FROM source_document WHERE content_sha256 = %s"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _page_count(pdf_path: Path) -> int:
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        n = len(doc)
        doc.close()
        return n
    except Exception:
        return 0


def _parse_year(session_label: str) -> int:
    """Extract the start year from a session label like '1877-78-code' or '2000_Vol1'."""
    import re
    m = re.search(r'(\d{4})', session_label)
    return int(m.group(1)) if m else 0


def _citation(session_label: str, vol_type: str) -> str:
    """Build a human-readable citation string."""
    year = _parse_year(session_label)
    if '_Vol' in session_label:
        vol = session_label.split('_Vol')[-1]
        return f"Stats. {year} Vol. {vol}"
    return f"Stats. {session_label}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def register(session_label: str, pdf_path: Path, vol_type: str, dry_run: bool) -> int:
    """Register source_document. Returns source_document id."""
    scratch = SCRATCH_ROOT / f"production-{session_label}"
    sha_path = scratch / "sha256.txt"

    # Compute or read sha256
    if sha_path.exists():
        sha = sha_path.read_text(encoding='utf-8').strip()
        print(f"  sha256 (from file): {sha[:16]}...")
    else:
        print(f"  Computing sha256 of {pdf_path.name} ...")
        sha = _sha256_file(pdf_path)
        print(f"  sha256: {sha[:16]}...")

    # Write sha256.txt if missing
    if not sha_path.exists():
        if not dry_run:
            scratch.mkdir(parents=True, exist_ok=True)
            sha_path.write_text(sha, encoding='utf-8')
            print(f"  Wrote {sha_path}")
        else:
            print(f"  [DRY RUN] Would write {sha_path}")

    year = _parse_year(session_label)
    citation = _citation(session_label, vol_type)
    pages = _page_count(pdf_path)

    if vol_type == 'born_digital':
        scan_quality  = None
        ocr_engine    = None
        cer_estimate  = None
        trust_level   = 'derived'
        note          = 'Born-digital PDF; text extracted via PyMuPDF fitz.get_text()'
    else:
        scan_quality  = 'good'
        ocr_engine    = 'surya+doctr+tesseract-5'
        cer_estimate  = None      # ingest_clean.py will UPDATE this with computed value
        trust_level   = 'ocr_uncertain'
        note          = 'OCR consensus (Surya + docTR + Tesseract 5); quality updated at ingest'

    print(f"  citation={citation!r}  year={year}  pages={pages}  trust={trust_level}")

    if dry_run:
        print(f"  [DRY RUN] Would INSERT source_document for sha={sha[:16]}...")
        return -1

    dsn = os.environ.get('PATOLEX_PG_DSN') or os.environ.get('DATABASE_URL')
    if not dsn:
        print("ERROR: set PATOLEX_PG_DSN or DATABASE_URL before running", file=sys.stderr)
        sys.exit(1)

    conn = psycopg.connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(INSERT_SQL, (
            citation,
            scan_quality, ocr_engine, cer_estimate,
            trust_level,
            sha,
            year, year,
            note,
            pdf_path.name,
            year, year,
            pages
        ))
        row = cur.fetchone()
        if row:
            src_doc_id = row[0]
            print(f"  INSERT -> source_document id={src_doc_id}")
        else:
            # ON CONFLICT: row already exists
            cur.execute(SELECT_SQL, (sha,))
            row = cur.fetchone()
            src_doc_id = row[0] if row else None
            print(f"  Already existed -> source_document id={src_doc_id}")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

    return src_doc_id


def main():
    ap = argparse.ArgumentParser(
        description='Register a source_document row for a PatoLex volume')
    ap.add_argument('session_label',
                    help='Production label, e.g. "1877-78-code" or "2000_Vol1"')
    ap.add_argument('pdf_path',
                    help='Path to the source PDF file')
    ap.add_argument('--type', choices=['ocr', 'born_digital'], default='ocr',
                    help='Volume type: ocr (default) or born_digital')
    ap.add_argument('--dry-run', action='store_true',
                    help='Show what would be done without writing to DB')
    args = ap.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found", file=sys.stderr)
        sys.exit(1)

    mode = "DRY RUN" if args.dry_run else "COMMIT"
    print(f"register_source_document [{mode}]: {args.session_label} ({args.type})")

    src_doc_id = register(args.session_label, pdf_path, args.type, args.dry_run)

    if not args.dry_run and src_doc_id:
        print(f"\nDone. source_document id={src_doc_id}")
        print(f"sha256.txt written to: {SCRATCH_ROOT / ('production-' + args.session_label) / 'sha256.txt'}")


if __name__ == '__main__':
    main()
