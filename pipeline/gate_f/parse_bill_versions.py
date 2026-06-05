#!/usr/bin/env python3
"""
parse_bill_versions.py -- Gate F: Extract chaptered bill section actions from PUBINFO.

For each leginfo pubinfo_{year}/ archive, reads BILL_VERSION_TBL.dat + .lob files
and extracts every (code_id, section_num, action, new_text) record from chaptered bills.

Usage:
    python parse_bill_versions.py <pubinfo_dir> [--out <output_dir>]

Output: gate_f_actions.jsonl (one JSON record per section action).
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Column indices in BILL_VERSION_TBL.dat (0-based, tab-delimited)
# ---------------------------------------------------------------------------
COL_BILL_VERSION_ID = 0
COL_BILL_ID         = 1
COL_ACTION_DATE     = 3
COL_ACTION          = 4
COL_URGENCY         = 12
COL_BILL_XML        = 14   # value = .lob filename, e.g. BILL_VERSION_TBL_1000.lob

# ---------------------------------------------------------------------------
# XML helpers: namespace-agnostic tag matching
# ---------------------------------------------------------------------------

def _local(tag):
    """Strip {namespace_uri} prefix from ElementTree tag."""
    return tag.split('}')[-1] if '}' in tag else tag


def _find_local(elem, local_name):
    """Find first child with the given local (namespace-stripped) tag name."""
    for child in elem:
        if _local(child.tag) == local_name:
            return child
    return None


def _findall_local(elem, local_name):
    """Find all children with the given local tag name (non-recursive)."""
    return [c for c in elem if _local(c.tag) == local_name]


def _find_recursive(elem, local_name):
    """Recursive depth-first search by local tag name."""
    if _local(elem.tag) == local_name:
        return elem
    for child in elem:
        result = _find_recursive(child, local_name)
        if result is not None:
            return result
    return None


def _findall_recursive(elem, local_name):
    """Collect all elements matching local_name anywhere in the subtree."""
    results = []
    if _local(elem.tag) == local_name:
        results.append(elem)
    for child in elem:
        results.extend(_findall_recursive(child, local_name))
    return results


# ---------------------------------------------------------------------------
# .dat row parser: tab-delimited, backtick-enclosed, NULL = None
# ---------------------------------------------------------------------------

def _parse_dat_row(line):
    """Parse one tab-delimited, backtick-quoted row from a PUBINFO .dat file."""
    fields = line.rstrip('\n').split('\t')
    result = []
    for f in fields:
        f = f.strip()
        if f == 'NULL' or f == '':
            result.append(None)
        else:
            # Strip enclosing backticks if present
            if f.startswith('`') and f.endswith('`'):
                f = f[1:-1]
            result.append(f)
    return result


# ---------------------------------------------------------------------------
# XML text cleaning: strip CAML tracked-change processing instructions
# ---------------------------------------------------------------------------

_PI_INSERTION_START = re.compile(r'<\?xm-insertion_mark_start\?>', re.IGNORECASE)
_PI_INSERTION_END   = re.compile(r'<\?xm-insertion_mark_end\?>', re.IGNORECASE)
_PI_DELETION        = re.compile(r'<\?xm-deletion_mark\s[^?]*\?>', re.IGNORECASE)


def _clean_text(text):
    """Remove tracked-change PIs and normalise whitespace."""
    if not text:
        return ''
    text = _PI_INSERTION_START.sub('', text)
    text = _PI_INSERTION_END.sub('', text)
    text = _PI_DELETION.sub('', text)
    return text.strip()


def _collect_text(elem):
    """Recursively collect all text content under an element."""
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.extend([_collect_text(child)])
        if child.tail:
            parts.append(child.tail)
    return ''.join(parts)


# ---------------------------------------------------------------------------
# href -> (code_id, section_num) extractor
# ---------------------------------------------------------------------------

_HREF_RE = re.compile(
    r'urn:caml:codes:([A-Za-z]+):caml#.*?caml:LawSection\[caml:Num=\'([^\']+)\'',
    re.IGNORECASE
)


def _parse_href(href):
    """Return (code_id, section_num) from an ActionLine xlink:href, or (None, None).
    Handles both plain and URL-encoded XPointer formats."""
    if not href:
        return None, None
    m = _HREF_RE.search(unquote(href))
    if m:
        return m.group(1).upper(), m.group(2)
    return None, None


# ---------------------------------------------------------------------------
# Action mapping
# ---------------------------------------------------------------------------

ACTION_MAP = {
    'IS_AMENDED':  'amend',
    'IS_ADDED':    'add',
    'IS_REPEALED': 'repeal',
}


# ---------------------------------------------------------------------------
# Parse one chaptered bill XML blob -> list of action records
# ---------------------------------------------------------------------------

def parse_lob(lob_path, bill_version_id, action_date_str, urgency_str):
    """
    Parse a CAML .lob XML file for one bill version.
    Returns a list of action dicts (one per amended/added/repealed section).
    Returns [] on parse error (caller logs warning).
    """
    try:
        for enc in ('utf-8', 'latin-1'):
            try:
                text = lob_path.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return []

        # ElementTree chokes on <?xm-*?> PIs inside the XML body; strip them first.
        text = _PI_INSERTION_START.sub('', text)
        text = _PI_INSERTION_END.sub('', text)
        text = _PI_DELETION.sub('', text)

        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    # ---- Extract chapter metadata from the Description block ---------------
    desc = _find_recursive(root, 'Description')
    if desc is None:
        desc = root  # some bills embed metadata at top level

    def _txt(local):
        el = _find_recursive(desc, local) if desc is not root else _find_recursive(root, local)
        return el.text.strip() if el is not None and el.text else None

    chapter_year_s = _txt('ChapterYear')
    chapter_num_s  = _txt('ChapterNum')
    chapter_type   = _txt('ChapterType') or _txt('MeasureType')
    urgency_xml    = _txt('Urgency')

    # Use XML urgency if .dat row didn't have it
    urgency_flag = (urgency_str or urgency_xml or 'NO').strip().upper() == 'YES'

    if not chapter_year_s or not chapter_num_s:
        return []  # not a chaptered bill version

    try:
        chapter_year = int(chapter_year_s)
        chapter_num  = int(chapter_num_s)
    except (ValueError, TypeError):
        return []

    # Chaptering date from action_date column (format: "YYYY-MM-DD HH:MM:SS")
    chaptering_date = None
    if action_date_str:
        chaptering_date = action_date_str[:10]  # just the date part

    # Operative date: urgency -> chaptering date, else Jan 1 next year
    if urgency_flag and chaptering_date:
        operative_date = chaptering_date
    else:
        operative_date = f"{chapter_year + 1}-01-01"

    # ---- Walk BillSections -> ActionLines -----------------------------------
    records = []
    bill_sections = _findall_recursive(root, 'BillSection')

    for section_order, bill_section in enumerate(bill_sections, start=1):
        action_lines = _findall_local(bill_section, 'ActionLine')
        if not action_lines:
            action_lines = _findall_recursive(bill_section, 'ActionLine')

        for action_line in action_lines:
            # Only process LAW_SECTION actions (not STATUTE, UNCODIFIED, etc.)
            # Pre-2005 archives lack the xlink:label attribute entirely; when
            # absent we skip this filter and let _parse_href() be the gate.
            label = action_line.get(
                '{http://www.w3.org/1999/xlink}label', ''
            ) or action_line.get('label', '')
            if label and 'LAW_SECTION' not in label.upper():
                continue

            action_attr = action_line.get('action', '')
            action_type = ACTION_MAP.get(action_attr.upper())
            if not action_type:
                continue

            href = (
                action_line.get('{http://www.w3.org/1999/xlink}href', '')
                or action_line.get('href', '')
            )
            code_id, section_num = _parse_href(href)
            if not code_id:
                continue

            # Find the Fragment/LawSection/Content sibling
            new_text = ''
            fragment = _find_local(bill_section, 'Fragment')
            if fragment is None:
                fragment = _find_recursive(bill_section, 'Fragment')
            if fragment is not None:
                content = _find_recursive(fragment, 'Content')
                if content is not None:
                    new_text = _clean_text(_collect_text(content))

            records.append({
                'chapter_year':      chapter_year,
                'chapter_num':       chapter_num,
                'bill_type':         chapter_type,
                'chaptering_date':   chaptering_date,
                'urgency':           urgency_flag,
                'operative_date':    operative_date,
                'code_id':           code_id,
                'section_num':       section_num,
                'action':            action_type,
                'new_text':          new_text,
                'bill_section_order': section_order,
                'bill_version_id':   bill_version_id,
            })

    return records


# ---------------------------------------------------------------------------
# Main: walk BILL_VERSION_TBL.dat, process chaptered versions
# ---------------------------------------------------------------------------

def parse_pubinfo_dir(pubinfo_dir, out_path):
    pubinfo_dir = Path(pubinfo_dir)
    dat_path = pubinfo_dir / 'BILL_VERSION_TBL.dat'
    if not dat_path.exists():
        print(f"ERROR: {dat_path} not found", file=sys.stderr)
        sys.exit(1)

    total = chaptered = skipped = actions = 0

    with open(out_path, 'w', encoding='utf-8') as out_f:
        for enc in ('utf-8', 'latin-1'):
            try:
                lines = dat_path.read_text(encoding=enc).splitlines()
                break
            except UnicodeDecodeError:
                continue
        else:
            print(f"ERROR: cannot decode {dat_path}", file=sys.stderr)
            sys.exit(1)

        for line in lines:
            if not line.strip():
                continue
            total += 1
            row = _parse_dat_row(line)
            if len(row) <= COL_BILL_XML:
                skipped += 1
                continue

            action_val = row[COL_ACTION] or ''
            if 'chaptered' not in action_val.lower():
                continue

            chaptered += 1
            lob_filename = row[COL_BILL_XML]
            if not lob_filename:
                skipped += 1
                continue

            lob_path = pubinfo_dir / lob_filename
            if not lob_path.exists():
                print(f"WARN: missing lob {lob_path.name}", file=sys.stderr)
                skipped += 1
                continue

            bill_version_id = row[COL_BILL_VERSION_ID] or ''
            action_date     = row[COL_ACTION_DATE] or ''
            urgency_str     = row[COL_URGENCY] or ''

            records = parse_lob(lob_path, bill_version_id, action_date, urgency_str)
            for rec in records:
                out_f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                actions += 1

            if chaptered % 100 == 0:
                print(f"  {chaptered} chaptered bills processed, {actions} actions so far...")

    print(f"Done: {total} rows, {chaptered} chaptered, {skipped} skipped, {actions} section actions")
    print(f"Output: {out_path}")
    return actions


def main():
    ap = argparse.ArgumentParser(description='Extract Gate F section actions from PUBINFO archive')
    ap.add_argument('pubinfo_dir', help='Path to pubinfo_{year}/ directory')
    ap.add_argument('--out', default=None, help='Output directory (default: pubinfo_dir)')
    args = ap.parse_args()

    pubinfo_dir = Path(args.pubinfo_dir)
    out_dir = Path(args.out) if args.out else pubinfo_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    year_match = re.search(r'(\d{4})', pubinfo_dir.name)
    year_label = year_match.group(1) if year_match else 'unknown'
    out_path = out_dir / f'gate_f_{year_label}_actions.jsonl'

    print(f"Gate F parser: {pubinfo_dir.name} -> {out_path.name}")
    parse_pubinfo_dir(pubinfo_dir, out_path)


if __name__ == '__main__':
    main()
