#!/usr/bin/env python3
"""
derive_modern_from_body.py  -- READ-ONLY body-based chapter-count derivation.

The MODERN statute volumes (~1905+) were OCR'd starting at the statute BODY
(`CHAPTER 1.`) -- their printed CONTENTS/index pages are not in the bundles. But
the body is SELF-INDEXING: chapters run sequentially 1..N, so the contiguous-
from-1 top of the body's `CHAPTER N` headers IS the session's chapter count.

This derives that count per volume and COMPARES it to the oracle
(ca_chapter_counts.tsv) -- a SECOND authoritative denominator signal that needs
no CONTENTS-page acquisition. Overwrites nothing (new files only, no DB).

Reuses the from-1 / coverage machinery from rederive_index_counts.py so the
robustness logic is shared (garbled headers and stray high numerals that aren't
reachable from 1 are discarded).

Outputs (under SCRATCH):
  _body_rederivation.tsv        one row per production volume
  _body_rederivation_report.md  human-readable report

Usage:
  python derive_modern_from_body.py \
      --scratch C:/Users/patolex/PatoLex-scratch \
      --oracle  C:/github/PatoLex/docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv \
      [--min-year 1905] [--max-year 1999] [--only label,label]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import rederive_index_counts as R

# Body chapter header: "CHAPTER 123." at the start of a line. The statute body
# prints each act under its own CHAPTER N. header. Cross-references ("...of
# Chapter 7 of Title 11...") sit mid-line and are excluded by the ^ anchor.
CHAP_HDR = re.compile(r"^\s*CHAPTER\s+(\d{1,4})\b", re.IGNORECASE | re.MULTILINE)


def derive_body_count(ocr_path):
    """Scan every page's consensus_text for CHAPTER N headers; return the
    contiguous-from-1 top + coverage. Returns dict or None if unreadable."""
    try:
        with open(ocr_path, "r", encoding="utf-8") as f:
            pages = json.load(f)
    except Exception as e:  # noqa
        return {"status": "UNREADABLE", "note": str(e)}
    if not isinstance(pages, dict) or not pages:
        return {"status": "EMPTY", "note": "ocr_json_empty"}

    nums = []
    for k in R.numeric_page_order(pages.keys()):
        rec = pages.get(k) or {}
        txt = rec.get("consensus_text") or ""
        if not txt:
            continue
        for m in CHAP_HDR.finditer(txt):
            try:
                v = int(m.group(1))
            except ValueError:
                continue
            if 1 <= v <= 9999:
                nums.append(v)

    distinct = sorted(set(nums))
    if not distinct:
        return {"status": "NO_BODY_HEADERS", "note": "no CHAPTER headers found"}

    rmax = R.robust_max_chapter(distinct)
    in_run = [c for c in distinct if c <= rmax]
    coverage = (len(in_run) / rmax) if rmax else 0.0
    return {
        "status": "BODY",
        "body_max_chapter": rmax,
        "body_distinct": len(distinct),
        "header_hits": len(nums),
        "coverage": coverage,
        "note": "cov=%.2f(%d/%d)" % (coverage, len(in_run), rmax),
    }


def classify(body_max, oracle_n, coverage):
    if body_max is None:
        return "NO_BODY"
    if coverage < 0.75:
        return "LOW_COVERAGE"          # body under-read; count not trustworthy
    if oracle_n is None:
        return "NO_ORACLE"
    if abs(body_max - oracle_n) <= 2:
        return "MATCH"                  # confirms the oracle (±2 OCR clip)
    if body_max > oracle_n:
        return "ORACLE_LOW"             # body shows MORE chapters than oracle
    return "ORACLE_HIGH"                # body shows fewer (OCR gap or oracle high)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--oracle", required=True)
    ap.add_argument("--min-year", type=int, default=0)
    ap.add_argument("--max-year", type=int, default=9999)
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    scratch = args.scratch.replace("\\", "/").rstrip("/")
    oracle_rows = R.load_oracle(args.oracle)
    only = set(s.strip() for s in args.only.split(",") if s.strip())

    vols = []
    for name in sorted(os.listdir(scratch)):
        if not name.startswith("production-") or not os.path.isdir(os.path.join(scratch, name)):
            continue
        if only and name not in only:
            continue
        yr = R.label_to_year_key(name)
        if yr is None or yr < args.min_year or yr > args.max_year:
            continue
        vols.append(name)

    rows = []
    for i, label in enumerate(vols, 1):
        ocr = os.path.join(scratch, label, "ocr_consensus", "page_ocr_results.json")
        okey, on, _ = R.find_oracle_match(label, oracle_rows)
        if not os.path.exists(ocr):
            res = {"status": "OCR_MISSING", "note": "ocr_consensus_missing"}
        else:
            res = derive_body_count(ocr)
        bmax = res.get("body_max_chapter")
        cov = res.get("coverage", 0.0)
        disc = classify(bmax, on, cov) if res.get("status") == "BODY" else "NO_BODY"
        rows.append([
            label, okey or "", "" if on is None else str(on),
            "" if bmax is None else str(bmax),
            str(res.get("body_distinct", "")), "%.2f" % cov if res.get("status") == "BODY" else "",
            disc, res.get("note", ""),
        ])
        # progress (foreground monitor; large volumes take a moment each)
        print("[%3d/%d] %-40s oracle=%s body=%s %s" %
              (i, len(vols), label, on, bmax, disc))
        sys.stdout.flush()

    tsv = os.path.join(scratch, "_body_rederivation.tsv")
    header = ["label", "oracle_session_key", "oracle_N", "body_max_chapter",
              "body_distinct", "coverage", "discrepancy", "note"]
    with open(tsv, "w", encoding="utf-8") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(r) + "\n")

    from collections import Counter
    counts = Counter(r[6] for r in rows)

    def gap(r):
        try:
            return int(r[3]) - int(r[2])
        except (ValueError, TypeError):
            return 0

    lines = ["# Body-based Chapter-Count Re-derivation (READ-ONLY)\n",
             "Derived each volume's chapter count from the contiguous-from-1 top "
             "of its statute BODY `CHAPTER N` headers and compared to the oracle. "
             "Self-indexing cross-check; no CONTENTS pages needed. Oracle not modified.\n",
             "## Tally"]
    lines.append("- Volumes examined: **%d** (years %d-%d)" % (len(rows), args.min_year, args.max_year))
    for k in ("MATCH", "ORACLE_LOW", "ORACLE_HIGH", "LOW_COVERAGE", "NO_BODY", "NO_ORACLE"):
        lines.append("- %s: **%d**" % (k, counts.get(k, 0)))
    lines.append("")
    for tier, title in [("ORACLE_LOW", "Body shows MORE chapters than oracle (possible undercount)"),
                        ("ORACLE_HIGH", "Body shows FEWER than oracle (OCR gap or oracle high)")]:
        sub = [r for r in rows if r[6] == tier]
        sub.sort(key=lambda r: -abs(gap(r)))
        lines.append("## %s\n" % title)
        lines.append("| label | oracle_N | body_max | gap | coverage | note |")
        lines.append("|---|---|---|---|---|---|")
        for r in sub[:60]:
            lines.append("| %s | %s | %s | %+d | %s | %s |" % (r[0], r[2], r[3], gap(r), r[5], r[7]))
        lines.append("")

    rep = os.path.join(scratch, "_body_rederivation_report.md")
    with open(rep, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("\nWROTE", tsv)
    print("WROTE", rep)
    for k in ("MATCH", "ORACLE_LOW", "ORACLE_HIGH", "LOW_COVERAGE", "NO_BODY", "NO_ORACLE"):
        print(k, counts.get(k, 0))


if __name__ == "__main__":
    main()
