"""chapter_vs_oracle.py -- measure parse completeness against the AUTHORITATIVE chapter-count oracle.

Joins our parsed chapters (chapters.tsv, from extract_chapters.py) against the authoritative per-session
totals (docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts*.tsv, Gate 2). For each session: how many of the
authoritative 1..N chapters did our parse actually capture? Uses the oracle total N as the cap, so OCR-garbled
high chapter numbers can't distort the measurement.

  python -m analysis.chapter_vs_oracle <chapters.tsv> <ca_chapter_counts.tsv> [--volume-map <tsv>]

Session matching (P4 of the session-number remodel): both sides keyed by CANONICAL_ID, not (year, type).
The oracle is keyed by its `canonical_id` column (S14, S15, 1881X1, ...). Each parsed chapter's volume
label is resolved to a canonical_id via the volume map (_volume_canonical_map.tsv, from
build_volume_canonical_map.py), which is what finally separates the two 1863 regular sessions (S14 vs S15)
that a leading-year key collides. If a label is not in the map (or no map is given), it falls back to the
legacy (year/biennium/NNchapters) decode -> the oracle row's canonical_id -- so the tool still runs against
a canonical oracle without a prebuilt map, and against the LEGACY (no-canonical) oracle it degrades to the
old (year, type) key.

parse_session_year / parse_type remain the year/biennium decode primitives (also reused by
build_volume_canonical_map.py).
"""
import argparse
import os
import re
import sys
from collections import defaultdict


def parse_type(s):
    l = s.lower()
    if "prior" in l: return "prior"
    if "firstextra" in l or "1stextra" in l or "extra1" in l or "first extra" in l: return "extra1"
    if "secondextra" in l or "extra2" in l or "second extra" in l: return "extra2"
    if "thirdextra" in l or "extra3" in l or "third extra" in l: return "extra3"
    if "extra" in l: return "extra1"
    return "regular"

def parse_session_year(label, oracle_reg_years=None):
    # NNchapters suffix -> real statute year (1900s); else leading 4-digit year.
    m = re.search(r"(\d{2})chapters", label.lower())
    if m: return 1900 + int(m.group(1))

    # Spanning biennial labels "YYYY-YY" (e.g. 1900-01, 1906-07, 1907-09, 1910-11):
    # the PHYSICAL volume holds the SECOND (odd) year's Regular Session statutes, so
    # the leading 4 digits (the even/first year) mis-file the chapters. Remap to the
    # odd-suffix year (century-prefix + "-YY") whenever THAT year's Regular Session is a
    # key in the oracle. For 20th-c. biennial volumes the odd-suffix year's regular session
    # IS an oracle key (1901/1907/1909/1911), so they remap. Pre-1900 "YYYY-YY" labels are
    # genuine single-session names already keyed by their (odd) START year, and their
    # even/odd SUFFIX year (1864, 1866, ...) is NOT a regular oracle session, so the test
    # is false and they are left untouched -- start-year behavior preserved.
    # Note 1907-09: BOTH 1907 and 1909 are oracle regular sessions; the suffix-year rule
    # correctly resolves the volume to 1909 (max-chapter ~729 = oracle 1909 N=729, not the
    # 1907 N=539). Verified by max-chapter match: 1900-01 max~274->1901(N=275),
    # 1906-07 max~539->1907, 1907-09 max~729->1909, 1910-11 bulk->1911(N=753).
    # See gap_biennium prototype (5090).
    sp = re.match(r"^(\d{4})-(\d{2})(?:$|-)", label)
    if sp and oracle_reg_years is not None:
        start = int(sp.group(1))
        odd = int(sp.group(1)[:2] + sp.group(2))
        if odd != start and odd in oracle_reg_years:
            return odd

    m = re.match(r"(\d{4})", label)
    return int(m.group(1)) if m else 0


# ----------------------------------------------------------------------------
# Canonical-id resolution (P4)
# ----------------------------------------------------------------------------

def strip_production(label):
    return label[len("production-"):] if label.startswith("production-") else label


def load_oracle_canonical(oracle_tsv):
    """
    Read the oracle. Returns:
      oracle:       {canonical_id: total_N}
      by_year_type: {(year:int, type:str): canonical_id}  -- decode fallback
      reg_years:    set of years with a regular session   -- biennium remap input
      has_canonical: bool                                  -- canonical_id column present?
    For a LEGACY oracle (no canonical_id column) the canonical id is synthesized as
    "<year>/<type>" so the tool still runs (degrading to the old (year,type) key).
    """
    oracle = {}
    by_year_type = {}
    reg_years = set()
    with open(oracle_tsv, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        idx = {h: i for i, h in enumerate(header)}
        has_canonical = "canonical_id" in idx
        # column positions, tolerant of the legacy 4-col layout
        c_year = idx.get("session_year", 1)
        c_type = idx.get("session_type", 2)
        c_tot = idx.get("total_chapters", 3)
        c_can = idx.get("canonical_id", None)
        for line in f:
            if not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) <= max(c_year, c_type, c_tot):
                continue
            ym = re.match(r"(\d{4})", p[c_year])
            if not ym:
                continue
            y = int(ym.group(1))
            t = p[c_type].strip()
            try:
                n = int(p[c_tot])
            except ValueError:
                continue
            cid = (p[c_can].strip() if (c_can is not None and len(p) > c_can) else "")
            if not cid:
                cid = "%d/%s" % (y, t)   # legacy synthesized key
            oracle[cid] = n
            by_year_type[(y, t)] = cid
            if t == "regular":
                reg_years.add(y)
    return oracle, by_year_type, reg_years, has_canonical


def load_volume_map(path):
    """label -> canonical_id from _volume_canonical_map.tsv. {} if absent."""
    m = {}
    if not path or not os.path.exists(path):
        return m
    with open(path, encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 2 and p[1].strip():
                m[p[0].strip()] = p[1].strip()
    return m


def label_to_canonical(label, vol_map, by_year_type, reg_years):
    """
    Resolve a parsed-chapter volume label -> canonical_id.
      1. exact lookup in the volume map (bare label, `production-` stripped);
      2. fallback: year/biennium/NNchapters decode -> oracle row's canonical_id
         (decoded type, then the regular row, then the sole/first extra row).
    Returns canonical_id or None.

    KNOWN ISSUE (pre-existing, not introduced here; parity guard = 0 diffs):
      `1949-vol1-49chapters-prior` resolves to S59 (1949 Regular, N=?) via the
      NNchapters decode (49chapters -> year 1949 -> regular row).  The volume is
      actually the 1st Extraordinary Session of 1949 (should be 1949X1, N=16).
      The old code made the same wrong match; we carry it forward unchanged.
    """
    bare = strip_production(label)
    if bare in vol_map:
        return vol_map[bare]
    year = parse_session_year(bare, reg_years)
    typ = parse_type(bare)
    if (year, typ) in by_year_type:
        return by_year_type[(year, typ)]
    if (year, "regular") in by_year_type:
        return by_year_type[(year, "regular")]
    extras = sorted(t for (y, t) in by_year_type if y == year and t != "regular")
    if extras:
        pick = "extra1" if "extra1" in extras else extras[0]
        return by_year_type[(year, pick)]
    return None


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------

def _selftest():
    bad = []

    # (a) the legacy year/biennium decode primitive is unchanged.
    oracle_reg = {1901, 1907, 1909, 1911,  # 20th-c. odd regular sessions
                  1863, 1865, 1867, 1885}  # pre-1900 start-year regular sessions
    decode_cases = {
        "1900-01": 1901, "1906-07": 1907, "1907-09": 1909, "1910-11": 1911,
        "1863-64": 1863, "1865-66": 1865, "1867-68": 1867, "1885-86": 1885,
        "1913-statutes": 1913, "1927-vol1-26chapters": 1926, "1907": 1907,
    }
    for lab, want in decode_cases.items():
        got = parse_session_year(lab, oracle_reg)
        if got != want:
            bad.append(f"decode {lab}: got {got}, want {want}")

    # (b) THE 1863 COLLISION IS RESOLVED. A small canonical oracle + volume map:
    # bare 1863 -> S14, 1863-64 -> S15, DISTINCT (a leading-year key would collide).
    vol_map = {"1863": "S14", "1863-64": "S15", "1900-01": "S34"}
    by_year_type = {(1863, "regular"): "S15", (1901, "regular"): "S34",
                    (1934, "extra1"): "1934X1"}
    reg_years = {1863, 1901}
    c1863 = label_to_canonical("1863", vol_map, by_year_type, reg_years)
    c1863_64 = label_to_canonical("1863-64", vol_map, by_year_type, reg_years)
    if c1863 != "S14":
        bad.append(f"1863 -> {c1863}, want S14")
    if c1863_64 != "S15":
        bad.append(f"1863-64 -> {c1863_64}, want S15")
    if c1863 == c1863_64:
        bad.append(f"1863 collision NOT resolved: both -> {c1863}")

    # (c) production- prefix is stripped before map lookup.
    if label_to_canonical("production-1863", vol_map, by_year_type, reg_years) != "S14":
        bad.append("production-1863 did not strip to 1863 -> S14")

    # (d) fallback path (label absent from map): decode -> oracle canonical_id.
    if label_to_canonical("1935-vol1-34chapters", {}, by_year_type, reg_years) != "1934X1":
        bad.append("decode-fallback 1935-vol1-34chapters -> 1934X1 failed")

    if bad:
        raise AssertionError("chapter_vs_oracle self-test FAILED: " + "; ".join(bad))
    print("chapter_vs_oracle self-test OK")
    print("  - legacy year/biennium decode unchanged (4 spanning labels + plain labels)")
    print("  - 1863 collision RESOLVED: 1863 -> S14, 1863-64 -> S15 (DISTINCT)")
    print("  - production- prefix stripping + decode-fallback verified")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        _selftest(); return

    ap = argparse.ArgumentParser()
    ap.add_argument("chapters")
    ap.add_argument("oracle")
    ap.add_argument("--volume-map", default="",
                    help="_volume_canonical_map.tsv (label->canonical_id); "
                         "defaults to one alongside chapters.tsv if present")
    args = ap.parse_args()
    chap_tsv, oracle_tsv = args.chapters, args.oracle

    oracle, by_year_type, reg_years, has_canonical = load_oracle_canonical(oracle_tsv)

    # volume map: explicit, else auto-discover next to chapters or oracle.
    # FIX 2: Only apply the volume map when the oracle is canonical (has_canonical=True).
    # Against a LEGACY oracle the volume map resolves labels to canonical ids (S1, 1926X1, …)
    # that the legacy oracle does NOT have → every chapter becomes "unresolved" → 0% silently.
    # When the oracle is legacy we skip the map entirely and fall back to the old (year,type)
    # decode so that the tool reproduces the pre-rewrite numbers.
    # An explicit --volume-map flag is honoured only when the oracle is canonical.
    vm_path = args.volume_map if has_canonical else ""
    if not vm_path and has_canonical:
        for cand in (os.path.join(os.path.dirname(os.path.abspath(chap_tsv)),
                                  "_volume_canonical_map.tsv"),
                     os.path.join(os.path.dirname(os.path.abspath(oracle_tsv)),
                                  "_volume_canonical_map.tsv")):
            if os.path.exists(cand):
                vm_path = cand
                break
    vol_map = load_volume_map(vm_path)

    # our parse: canonical_id -> set of chapter ints
    got = defaultdict(set)
    unresolved_labels = set()
    with open(chap_tsv, encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 4 or not p[3].isdigit():
                continue
            cid = label_to_canonical(p[0], vol_map, by_year_type, reg_years)
            if cid is None:
                unresolved_labels.add(p[0])
                continue
            got[cid].add(int(p[3]))

    # decorate each canonical row with a year for sorted/readable output
    cid_year = {}
    for (y, _t), cid in by_year_type.items():
        cid_year.setdefault(cid, y)

    rows = []
    tot_auth = tot_have = 0
    for cid in sorted(oracle, key=lambda c: (cid_year.get(c, 0), c)):
        N = oracle[cid]
        present = {c for c in got.get(cid, ()) if 1 <= c <= N}
        have = len(present)
        miss = N - have
        our_max = max(got.get(cid, {0}))
        trailing = sum(1 for n in range(1, N + 1)
                       if n not in present and n > (max(present) if present else 0))
        rows.append((cid, N, have, miss, 100.0 * have / N if N else 0,
                     our_max, trailing, cid in got))
        if got.get(cid):
            tot_auth += N; tot_have += have

    # report
    print(f"{'session':<16}{'auth_N':>7}{'have':>7}{'miss':>7}{'compl%':>8}{'ourmax':>8}{'trail':>7}")
    have_oracle_no_parse = []
    for (cid, N, have, miss, pct, omax, trail, inparse) in rows:
        if not inparse:
            have_oracle_no_parse.append((cid, N)); continue
        flag = "" if pct >= 98 else ("  <-- LOW" if pct < 85 else "  <- gap")
        print(f"{cid:<16}{N:>7}{have:>7}{miss:>7}{pct:>7.0f}%{omax:>8}{trail:>7}{flag}")

    print(f"\nCORPUS (sessions we have OCR for): authoritative {tot_auth:,} chapters, "
          f"parsed {tot_have:,} -> {100.0*tot_have/max(1,tot_auth):.1f}% complete, "
          f"missing {tot_auth-tot_have:,}")
    print(f"keying: canonical_id  (oracle has canonical column: {has_canonical}; "
          f"volume map: {os.path.basename(vm_path) if vm_path else 'NONE'}, "
          f"{len(vol_map)} entries)")

    # parse sessions with no oracle match (sanity)
    unmatched = sorted(c for c in got if c not in oracle)
    if unmatched:
        print(f"\nparse canonical ids with NO oracle match ({len(unmatched)}): "
              + ", ".join(unmatched[:40]))
    if unresolved_labels:
        print(f"\nparse labels that did NOT resolve to a canonical id "
              f"({len(unresolved_labels)}): "
              + ", ".join(sorted(unresolved_labels)[:40]))
    if have_oracle_no_parse:
        # FIX 1: filter regular sessions under BOTH key forms:
        #   canonical oracle: key is "S14", "S15", … → startswith("S")
        #   legacy oracle:    key is "1850/regular", "1863/regular", … → endswith("/regular")
        reg = [(cid, N) for (cid, N) in have_oracle_no_parse
               if cid.startswith("S") or cid.endswith("/regular")]
        print(f"\noracle regular sessions we have NO parse for ({len(reg)}): "
              + ", ".join(f"{cid}({N})" for (cid, N) in reg[:60]))


if __name__ == "__main__":
    main()
