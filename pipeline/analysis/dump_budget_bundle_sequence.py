#!/usr/bin/env python3
"""dump_budget_bundle_sequence.py -- READ-ONLY investigation of even-year budget-bundle volumes.

The even-year "budget" volumes (1948,1950,1952,1954,1956,1958,1960,1962,1964 -> S58..S74)
physically bind TWO sessions onto one canonical_id: the tiny budget/regular session AND that
year's First (and sometimes later) Extra session(s). Both sequences number from CHAPTER 1, so a
self-index of the volume CANNOT isolate either session's count.

This script dumps, per budget volume, the in-order sequence of `CHAPTER N.` body headers with
their printed page numbers, so the boundary page where the chapter numbering RESETS (budget run
ends, extra run begins at 1) can be found. That reset page is the split point for range-based
attribution.

Uses the SAME cross-engine header scan as the production recovery (recover_multiengine_headers.
scan_page_headers) so the sequence is the witness-grade one, not a single-engine read.

Usage:
  python dump_budget_bundle_sequence.py [--only 1950-vol1-chapters]
"""
import argparse
import json
import sys
from pathlib import Path
import importlib.util

PIPE = "C:/GitHub/PatoLex/pipeline"
sys.path.insert(0, PIPE)
sys.path.insert(0, PIPE + "/ingest")
_MX = Path(PIPE) / "ingest" / "recover_multiengine_headers.py"
_spec = importlib.util.spec_from_file_location("recover_multiengine_dbb", str(_MX))
mx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mx)

SCRATCH = Path("C:/Users/patolex/PatoLex-scratch")

# Even-year budget volumes -> canonical_id (the BUDGET session) + the budget year.
# The 1948 and 1950 budget volumes are physically separate even-year volumes
# ("1948-vol1-chapters" / "1950-vol1-chapters"). From 1952 on, the budget session
# is bound into the ODD-year volume under an "NNchapters" suffix carrying the BUDGET
# year ("1953-vol1-52chapters" holds the 1952 budget run + 1952 extra runs). The
# volume map resolves the NNchapters suffix to the budget canonical_id.
BUDGET_VOLS = [
    ("1948-vol1-chapters", "S58", 1948),
    ("1950-vol1-chapters", "S60", 1950),
    ("1953-vol1-52chapters", "S62", 1952),
    ("1955-vol1-54chapters", "S64", 1954),
    ("1957-vol1-56chapters", "S66", 1956),
    ("1959-vol1-58chapters", "S68", 1958),
    ("1961-vol1-60chapters", "S70", 1960),
    ("1963-vol1-62chapters", "S72", 1962),
    ("1965-vol1-64chapters", "S74", 1964),
]


def load_pages(label):
    p = SCRATCH / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    if not p.exists():
        return None
    return {int(k): v for k, v in json.loads(p.read_text(encoding="utf-8")).items()}


def header_sequence(label):
    """Return list of (page_1indexed, chapter_n, n_engines, is_resolution, has_body_witness)
    in physical page order, for every cross-engine header (>=1 engine) on each page."""
    pages = load_pages(label)
    if pages is None:
        return None
    seq = []
    for pidx in sorted(pages):
        pg = pages[pidx]
        p1 = pg.get("page_1indexed", pidx + 1)
        hits = mx.scan_page_headers(pg, mode="arabic")
        for n in sorted(hits):
            indep = {e: hits[n][e] for e in mx.INDEPENDENT_ENGINES if e in hits[n]}
            if not indep:
                continue
            min_idx = min(indep.values())
            is_res = mx.is_resolution_near(pg, min_idx)
            body = False
            for e in mx.INDEPENDENT_ENGINES + ("consensus_text",):
                if e in hits[n]:
                    o, _t, _w = mx.body_witness(pg, e, hits[n][e], n, mode="arabic")
                    if o:
                        body = True
                        break
            seq.append((p1, n, len(indep), is_res, body))
    return seq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = set(s.strip() for s in args.only.split(",") if s.strip())

    for label, cid, year in BUDGET_VOLS:
        if only and label not in only:
            continue
        seq = header_sequence(label)
        print("=" * 80)
        print("VOLUME %s  (budget cid=%s, year=%d)" % (label, cid, year))
        if seq is None:
            print("  MISSING")
            continue
        # detect resets: a chapter number <= a previously-seen high number, going back near 1
        prev = 0
        for (p1, n, neng, is_res, body) in seq:
            reset = ""
            if n < prev - 2 and n <= 5:
                reset = "   <==== NUMBERING RESET (was at %d)" % prev
            tag = []
            if is_res:
                tag.append("RES")
            if body:
                tag.append("BODY")
            print("  p%-5d CHAPTER %-4d eng=%d %-10s%s"
                  % (p1, n, neng, ",".join(tag), reset))
            prev = max(prev, n)


if __name__ == "__main__":
    main()
