#!/usr/bin/env python3
"""
build_volume_canonical_map.py  -- P4 of the session-number remodel (READ-ONLY, NEW FILE).

For every `production-*` volume under SCRATCH, resolve its CANONICAL session id
(`canonical_id`, e.g. S14, S15, 1881X1) and write `_volume_canonical_map.tsv`.

This map is the join layer the rewritten matchers consume: it lets a parsed
chapter's volume label be resolved to a canonical session WITHOUT year-keying,
which is what finally separates the two 1863 regular sessions (the 14th and the
15th) that a leading-year key collides.

Resolution order (precision-first; identical to the legacy year/biennium decode
for EVERY non-collision volume, so no validated number moves except the 1863 fix):

  1. SPECIAL CASE -- bare `production-1863` (the 14th regular session, whose
     ordinal did not OCR) -> S14.  `production-1863-64` (the 15th) is left to the
     normal decode, which lands it on the 1863-64 oracle row (S15).  This is the
     one case a year key cannot separate (both lead with "1863").
  2. `-code` / `-regular` SUFFIX -- a "...-code" (Amendments to the Codes) or a
     redundant "...-regular" volume shares its session with the main volume; strip
     the suffix and resolve the base label (same canonical_id).
  3. YEAR / BIENNIUM / NNchapters DECODE -- reuse chapter_vs_oracle.parse_session_year
     + parse_type to find the matching DRAFT-oracle row, then take THAT row's
     canonical_id.  This is exactly how the live tools resolve today, so the map
     reproduces the existing behavior for all 220 non-1863 volumes.

Output (under SCRATCH): _volume_canonical_map.tsv
  columns: label  canonical_id  basis
where `label` is the volume's bare label (the `production-` prefix stripped, so it
matches the `vol_label` form emitted by extract_chapters.py) and `basis` records
which rule fired.

Usage:
  python build_volume_canonical_map.py \
      --scratch C:/Users/patolex/PatoLex-scratch \
      --oracle  C:/github/PatoLex/docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts_CANONICAL_DRAFT.tsv
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import chapter_vs_oracle as C  # parse_session_year / parse_type

# The one volume whose ordinal did not OCR and whose year collides with the 15th.
SPECIAL_1863 = {"1863": "S14"}

# Suffixes that mark a volume sharing the MAIN volume's session (same canonical_id).
SHARED_SESSION_SUFFIXES = ("-code", "-regular")


def strip_production(name):
    """`production-1863-64` -> `1863-64`; passthrough if no prefix."""
    return name[len("production-"):] if name.startswith("production-") else name


def load_draft_oracle(path):
    """
    Read the DRAFT oracle (canonical columns appended). Returns:
      by_year_type: {(year:int, type:str): row dict}   -- year-decode target
      reg_years:    set of years with a regular session -- biennium remap input
      header:       column list (for sanity)
    A row dict carries at least session_year, session_type, total_chapters,
    canonical_id (+ session_label for reporting).
    """
    by_year_type = {}
    reg_years = set()
    with open(path, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        idx = {h: i for i, h in enumerate(header)}
        if "canonical_id" not in idx:
            raise SystemExit("ERROR: oracle %s has no canonical_id column "
                             "(use the CANONICAL_DRAFT oracle)" % path)
        for line in f:
            if not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < len(header):
                p += [""] * (len(header) - len(p))
            row = dict(zip(header, p))
            ystr = row.get("session_year", "")
            m = re.match(r"(\d{4})", ystr)
            if not m:
                continue
            y = int(m.group(1))
            t = row.get("session_type", "").strip()
            by_year_type[(y, t)] = row
            if t == "regular":
                reg_years.add(y)
    return by_year_type, reg_years, header


def resolve_label(label, by_year_type, reg_years, canonical_ids):
    """
    Resolve a BARE volume label (no `production-` prefix) -> (canonical_id, basis).
    Returns (None, reason) when unresolved.
    """
    # 1. special case -- S14 is the RESERVED canonical id for the missing 14th
    # session (its oracle row is added in P5), so it is NOT yet in canonical_ids;
    # the reservation is by design, so assign it unconditionally.
    if label in SPECIAL_1863:
        return SPECIAL_1863[label], "special-1863-14th"

    # 2. shared-session suffix -> resolve the base label, keep its canonical_id
    for suf in SHARED_SESSION_SUFFIXES:
        if label.endswith(suf):
            base = label[: -len(suf)]
            cid, _basis = resolve_label(base, by_year_type, reg_years, canonical_ids)
            if cid:
                return cid, "shared-session(%s)" % suf.lstrip("-")
            return None, "shared-session-base-unresolved(%s)" % base

    # 3. year / biennium / NNchapters decode -> oracle row -> canonical_id
    year = C.parse_session_year(label, reg_years)
    typ = C.parse_type(label)  # regular | extra1 | extra2 | extra3 | prior

    # Try, in order: the decoded type; the regular row of that year (dominant
    # statutes volume -- mirrors find_oracle_match's regular-preference); and, as
    # a last resort, the SOLE extra row of that year.  The last case only fires
    # for the NNchapters / leading-year volumes whose decoded year (1926/1928/
    # 1934/1938/1942/1946) has NO regular session at all -- those years carry only
    # an extra session, which is exactly the small extra-session volume bound into
    # the odd-year set.  It never fires when a regular row exists, so it can only
    # NEWLY resolve volumes the legacy tool left unmatched -- it moves nothing.
    extras = sorted(t for (y, t) in by_year_type
                    if y == year and t != "regular")
    for t, tag in [(typ, "year-decode"),
                   ("regular", "year-decode-regfallback")]:
        row = by_year_type.get((year, t))
        if row and row.get("canonical_id", "").strip():
            return row["canonical_id"].strip(), "%s(%d/%s)" % (tag, year, t)
    if extras:
        # No regular row for this decoded year -> the volume is the extra-session
        # set bound into the odd-year volumes (1926/1928/1934/1938/1942/1946 etc.).
        # Prefer the FIRST extra (the dominant one; matches the "First
        # Extraordinary" the 1947-46chapters volume declares); deterministic.
        pick = "extra1" if "extra1" in extras else extras[0]
        row = by_year_type[(year, pick)]
        if row.get("canonical_id", "").strip():
            return (row["canonical_id"].strip(),
                    "year-decode-extra(%d/%s)" % (year, pick))
    return None, "no-oracle-row(year=%d,type=%s)" % (year, typ)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--oracle", required=True,
                    help="DRAFT oracle WITH canonical_id column")
    ap.add_argument("--out", default="",
                    help="output tsv (default <scratch>/_volume_canonical_map.tsv)")
    args = ap.parse_args()
    scratch = args.scratch.replace("\\", "/").rstrip("/")
    out_path = args.out or os.path.join(scratch, "_volume_canonical_map.tsv")

    by_year_type, reg_years, _header = load_draft_oracle(args.oracle)
    canonical_ids = {r.get("canonical_id", "").strip()
                     for r in by_year_type.values() if r.get("canonical_id", "").strip()}

    vols = sorted(n for n in os.listdir(scratch)
                  if n.startswith("production-")
                  and os.path.isdir(os.path.join(scratch, n)))

    rows = []
    unresolved = []
    for name in vols:
        label = strip_production(name)
        cid, basis = resolve_label(label, by_year_type, reg_years, canonical_ids)
        rows.append((label, cid or "", basis))
        if not cid:
            unresolved.append((label, basis))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("label\tcanonical_id\tbasis\n")
        for label, cid, basis in rows:
            f.write("%s\t%s\t%s\n" % (label, cid, basis))

    resolved = sum(1 for _, cid, _ in rows if cid)
    print("WROTE", out_path)
    print("volumes:            %d" % len(rows))
    print("resolved:           %d" % resolved)
    print("unresolved:         %d" % len(unresolved))
    for label, basis in unresolved:
        print("   UNRESOLVED  %-32s %s" % (label, basis))

    # collision proof: the two 1863 regular sessions must land on DISTINCT ids
    m = {label: cid for label, cid, _ in rows}
    a, b = m.get("1863"), m.get("1863-64")
    print("\n1863 collision check: 1863 -> %s ; 1863-64 -> %s  (%s)"
          % (a, b, "DISTINCT-OK" if a and b and a != b else "COLLISION-FAIL"))

    return 0 if not unresolved else 1


if __name__ == "__main__":
    sys.exit(main())
