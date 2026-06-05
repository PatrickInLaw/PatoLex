r"""
ingest_born_digital_prep.py -- Bridge born_digital_parsed.json to parsed_acts_fixed.json
=======================================================================================
Adapter script that transforms parse_born_digital_prod.py output into the format
expected by ingest_clean.py.

Input:  born_digital_parsed.json (from parse_born_digital_prod.py)
Output: parsed_acts_fixed.json (for ingest_clean.py)

The transformation is a direct field subset with confidence filtering:
  - Include acts where: chapter_int > 0 AND iso_date is not None/empty AND len(text.strip()) >= 50
  - Drop: chapter (str), approved_date, confident (ingest_clean.py recomputes confidence)
  - Drop envelope fields: label, source_pdf, year, vol, page_count, has_text_layer, etc.

Usage:
    python ingest_born_digital_prep.py <production_label_dir>

where <production_label_dir> is the directory containing born_digital_parsed.json
(e.g., C:\...\production-2005_Vol1)

Exits 0 on success, 1 on error.
"""

import sys
import json
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("Usage: python ingest_born_digital_prep.py <production_label_dir>",
              file=sys.stderr)
        sys.exit(1)

    prod_dir = Path(sys.argv[1])
    if not prod_dir.is_dir():
        print(f"Error: {prod_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    input_path = prod_dir / "born_digital_parsed.json"
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    # Read input
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error reading {input_path}: {e}", file=sys.stderr)
        sys.exit(1)

    acts = data.get("acts", [])
    total_acts = len(acts)

    # Filter acts
    confident_acts = []
    for act in acts:
        chapter_int = act.get("chapter_int", 0)
        iso_date = (act.get("iso_date") or "").strip()
        text = (act.get("text") or "").strip()

        # Include only if: chapter_int > 0 AND iso_date not None/empty AND text >= 50 chars
        if chapter_int > 0 and iso_date and len(text) >= 50:
            # Map fields: drop chapter, approved_date, confident
            clean_act = {
                "chapter_int": chapter_int,
                "chapter_raw": act.get("chapter_raw", ""),
                "iso_date": iso_date,
                "title": act.get("title", ""),
                "text": text,
                "source_page": act.get("source_page", 0),
            }
            confident_acts.append(clean_act)

    filtered_count = total_acts - len(confident_acts)

    # Write output
    output_path = prod_dir / "parsed_acts_fixed.json"
    output_data = {"confident_acts": confident_acts}
    try:
        output_path.write_text(
            json.dumps(output_data, ensure_ascii=False, indent=1),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"Error writing {output_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Log summary
    print(f"Total acts: {total_acts}")
    print(f"Included: {len(confident_acts)}")
    print(f"Filtered: {filtered_count}")
    print(f"Output: {output_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
