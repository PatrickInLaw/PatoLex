#!/usr/bin/env python3
"""
run_all_years.py -- Run Gate F parser over all available pubinfo_{year}/ directories.

Usage:
    python run_all_years.py <scratch_root> [--out <output_dir>] [--years 2005 2007 ...]
"""

import argparse
import re
import sys
from pathlib import Path

from parse_bill_versions import parse_pubinfo_dir


def main():
    ap = argparse.ArgumentParser(description='Run Gate F parser over all pubinfo years')
    ap.add_argument('scratch_root', help='Directory containing pubinfo_YYYY/ subdirs')
    ap.add_argument('--out', default=None, help='Output directory for JSONL files')
    ap.add_argument('--years', nargs='+', type=int, default=None,
                    help='Specific years to process (default: all found)')
    args = ap.parse_args()

    scratch = Path(args.scratch_root)
    out_dir = Path(args.out) if args.out else scratch / 'gate_f_out'
    out_dir.mkdir(parents=True, exist_ok=True)

    # Discover pubinfo_YYYY dirs
    candidates = sorted(
        d for d in scratch.iterdir()
        if d.is_dir() and re.match(r'pubinfo_\d{4}$', d.name)
    )

    if args.years:
        candidates = [d for d in candidates
                      if int(re.search(r'\d{4}', d.name).group()) in args.years]

    if not candidates:
        print(f"No pubinfo_YYYY directories found in {scratch}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(candidates)} pubinfo directories: "
          f"{', '.join(d.name for d in candidates)}")
    print(f"Output -> {out_dir}\n")

    total_actions = 0
    errors = []

    for pubinfo_dir in candidates:
        year_match = re.search(r'(\d{4})', pubinfo_dir.name)
        year_label = year_match.group(1) if year_match else 'unknown'
        out_path = out_dir / f'gate_f_{year_label}_actions.jsonl'

        print(f"--- {pubinfo_dir.name} ---")
        try:
            n = parse_pubinfo_dir(pubinfo_dir, out_path)
            total_actions += n
        except SystemExit:
            errors.append(pubinfo_dir.name)
            print(f"  FAILED: {pubinfo_dir.name}")
        print()

    print(f"=== Complete: {total_actions} total section actions across "
          f"{len(candidates) - len(errors)} years ===")
    if errors:
        print(f"Failed years: {', '.join(errors)}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
