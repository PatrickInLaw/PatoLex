#!/usr/bin/env python3
"""
batch_ingest_born_digital.py -- Run the full born-digital ingest chain for
all 2000-2008 Chief Clerk volumes.

Pipeline per volume:
  1. parse_born_digital_prod.py  (extract text, identify chapters)
  2. ingest_born_digital_prep.py (convert to parsed_acts_fixed.json format)
  3. register_source_document.py (create source_document row + sha256.txt)
  4. ingest_clean.py --commit     (insert into DB)

Prerequisites:
  - PDF files at C:\\Users\\PatrickKolasinski\\PatoLex-scratch\\chief-clerk-archive\\
    named YYYY_VolN.pdf (e.g., 2000_Vol1.pdf)
  - env: PATOLEX_PG_DSN or DATABASE_URL set to direct PostgreSQL URL
  - env: PATOLEX_ALLOW_COMMIT=1

Usage:
    python batch_ingest_born_digital.py [--dry-run] [--years 2000 2001 ...]
    python batch_ingest_born_digital.py --commit [--years 2000]

Default mode is DRY RUN (parse + prep only; no DB writes). Pass --commit for
full ingestion. In --commit mode, each volume is atomic: all its acts land or
none do.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRATCH = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch")
ARCHIVE = SCRATCH / "chief-clerk-archive"
PIPELINE = Path(__file__).parent

PARSE_SCRIPT   = PIPELINE / "5080" / "parse_born_digital_prod.py"
PREP_SCRIPT    = PIPELINE / "ingest_born_digital_prep.py"
REGISTER_SCRIPT = PIPELINE / "register_source_document.py"
INGEST_SCRIPT  = PIPELINE / "ingest_clean.py"

YEARS = range(2000, 2009)


def _find_volumes(years_filter=None):
    """Return sorted list of (session_label, pdf_path) for all available PDFs."""
    vols = []
    for pdf in sorted(ARCHIVE.glob("*_Vol*.pdf")):
        stem = pdf.stem  # e.g. "2000_Vol1"
        parts = stem.split('_')
        if len(parts) < 2:
            continue
        try:
            year = int(parts[0])
        except ValueError:
            continue
        if year not in YEARS:
            continue
        if years_filter and year not in years_filter:
            continue
        vols.append((stem, pdf))
    return vols


def _run(cmd, label, step):
    """Run a subprocess command; raise on failure."""
    result = subprocess.run(
        [sys.executable] + cmd,
        capture_output=True, text=True, encoding='utf-8', errors='replace'
    )
    if result.returncode != 0:
        print(f"  [{step}] FAIL (exit {result.returncode})", file=sys.stderr)
        if result.stderr:
            print(result.stderr[:2000], file=sys.stderr)
        raise RuntimeError(f"{label} {step} failed")
    return result.stdout


def process_volume(session_label, pdf_path, commit):
    prod_dir = SCRATCH / f"production-{session_label}"
    print(f"\n--- {session_label} ({pdf_path.name}) ---")

    # Step 1: Parse born-digital PDF
    parsed_json = prod_dir / "born_digital_parsed.json"
    if parsed_json.exists():
        print(f"  [parse] already done ({parsed_json.stat().st_size // 1024}KB), skipping")
    else:
        print(f"  [parse] running parse_born_digital_prod.py ...")
        _run(
            [str(PARSE_SCRIPT), "--out", str(SCRATCH), str(pdf_path)],
            session_label, "parse"
        )
        if not parsed_json.exists():
            raise RuntimeError(f"parse_born_digital_prod.py did not produce {parsed_json}")
        print(f"  [parse] OK -> {parsed_json.stat().st_size // 1024}KB")

    # Step 2: Prep adapter (born_digital_parsed.json -> parsed_acts_fixed.json)
    acts_json = prod_dir / "parsed_acts_fixed.json"
    if acts_json.exists():
        print(f"  [prep]  already done ({acts_json.stat().st_size // 1024}KB), skipping")
    else:
        print(f"  [prep]  running ingest_born_digital_prep.py ...")
        _run(
            [str(PREP_SCRIPT), str(prod_dir)],
            session_label, "prep"
        )
        if not acts_json.exists():
            raise RuntimeError(f"ingest_born_digital_prep.py did not produce {acts_json}")
        print(f"  [prep]  OK -> {acts_json.stat().st_size // 1024}KB")

    # Report chapter count
    try:
        data = json.loads(acts_json.read_text(encoding='utf-8'))
        n_acts = len(data.get('confident_acts', []))
        print(f"  [prep]  {n_acts} confident acts ready for ingest")
    except Exception:
        pass

    if not commit:
        print(f"  [register/ingest] SKIPPED (dry-run mode)")
        return

    # Step 3: Register source_document
    sha_path = prod_dir / "sha256.txt"
    print(f"  [register] running register_source_document.py ...")
    _run(
        [str(REGISTER_SCRIPT), session_label, str(pdf_path), "--type", "born_digital"],
        session_label, "register"
    )
    if not sha_path.exists():
        raise RuntimeError(f"register_source_document.py did not produce {sha_path}")
    print(f"  [register] OK -> sha256.txt written")

    # Step 4: DB ingest
    print(f"  [ingest] running ingest_clean.py --commit ...")
    _run(
        [str(INGEST_SCRIPT), session_label, "--commit"],
        session_label, "ingest"
    )
    print(f"  [ingest] OK")


def main():
    ap = argparse.ArgumentParser(
        description='Batch ingest born-digital 2000-2008 Chief Clerk volumes')
    ap.add_argument('--commit', action='store_true',
                    help='Write to DB (default: dry-run, parse+prep only)')
    ap.add_argument('--years', nargs='+', type=int, default=None,
                    help='Restrict to specific years, e.g. --years 2000 2001')
    args = ap.parse_args()

    years_filter = set(args.years) if args.years else None
    volumes = _find_volumes(years_filter)

    if not volumes:
        print("No 2000-2008 PDFs found in chief-clerk-archive.", file=sys.stderr)
        sys.exit(1)

    mode = "COMMIT" if args.commit else "DRY RUN (parse+prep only)"
    print(f"batch_ingest_born_digital -- {mode}")
    print(f"Found {len(volumes)} volume(s): {', '.join(l for l, _ in volumes)}\n")

    ok = failed = 0
    for session_label, pdf_path in volumes:
        try:
            process_volume(session_label, pdf_path, args.commit)
            ok += 1
        except RuntimeError as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            failed += 1

    print(f"\n=== Done: {ok} OK, {failed} failed ===")
    if not args.commit:
        print("Re-run with --commit to write to DB.")
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
