"""chapter_vs_oracle.py -- measure parse completeness against the AUTHORITATIVE chapter-count oracle.

Joins our parsed chapters (chapters.tsv, from extract_chapters.py) against the authoritative per-session
totals (docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv, Gate 2). For each session: how many of the
authoritative 1..N chapters did our parse actually capture? Uses the oracle total N as the cap, so OCR-garbled
high chapter numbers can't distort the measurement.

  python -m analysis.chapter_vs_oracle <chapters.tsv> <ca_chapter_counts.tsv> [--parse-col 3]

Session matching: both sides keyed by (start_year, type). start_year = first 4 digits of the label;
type = regular unless the label marks an extra/extraordinary session.
"""
import sys, re
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


def _selftest():
    # The 4 known 20th-century spanning labels must bucket to the ODD (second) year;
    # pre-1900 "YYYY-YY" labels and plain labels must keep their leading-year behavior.
    oracle_reg = {1901, 1907, 1909, 1911,  # 20th-c. odd regular sessions
                  1863, 1865, 1867, 1885}  # pre-1900 start-year regular sessions
    cases = {
        "1900-01": 1901, "1906-07": 1907, "1907-09": 1909, "1910-11": 1911,
        "1863-64": 1863, "1865-66": 1865, "1867-68": 1867, "1885-86": 1885,
        "1913-statutes": 1913, "1927-vol1-26chapters": 1926, "1907": 1907,
    }
    bad = []
    for lab, want in cases.items():
        got = parse_session_year(lab, oracle_reg)
        if got != want:
            bad.append(f"{lab}: got {got}, want {want}")
    if bad:
        raise AssertionError("parse_session_year self-test FAILED: " + "; ".join(bad))
    print("parse_session_year self-test OK (4 spanning labels bucket to odd year)")

def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        _selftest(); return
    chap_tsv, oracle_tsv = sys.argv[1], sys.argv[2]

    # oracle: (year,type) -> total
    oracle = {}
    with open(oracle_tsv, encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 4: continue
            y = int(re.match(r"(\d{4})", p[0]).group(1))
            oracle[(y, p[2].strip())] = int(p[3])

    # set of years that have a Regular Session in the oracle -- used to remap the spanning
    # biennial labels (YYYY-YY) onto the odd (second) year they actually cover.
    oracle_reg_years = {y for (y, t) in oracle if t == "regular"}

    # our parse: (year,type) -> set of chapter ints
    got = defaultdict(set)
    with open(chap_tsv, encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 4 or not p[3].isdigit(): continue
            key = (parse_session_year(p[0], oracle_reg_years), parse_type(p[0]))
            got[key].add(int(p[3]))

    rows = []
    tot_auth = tot_have = 0
    for key in sorted(oracle):
        N = oracle[key]
        present = {c for c in got.get(key, ()) if 1 <= c <= N}
        have = len(present)
        miss = N - have
        our_max = max(got.get(key, {0}))
        trailing = sum(1 for n in range(1, N + 1) if n not in present and n > (max(present) if present else 0))
        rows.append((key, N, have, miss, 100.0 * have / N if N else 0, our_max, trailing,
                     key in got))
        # only count sessions we actually have OCR for (present any) toward corpus totals
        if got.get(key):
            tot_auth += N; tot_have += have

    # report
    print(f"{'session':<16}{'auth_N':>7}{'have':>7}{'miss':>7}{'compl%':>8}{'ourmax':>8}{'trail':>7}")
    have_oracle_no_parse = []
    for (key, N, have, miss, pct, omax, trail, inparse) in rows:
        if not inparse:
            have_oracle_no_parse.append((key, N)); continue
        flag = "" if pct >= 98 else ("  <-- LOW" if pct < 85 else "  <- gap")
        print(f"{str(key[0])+'/'+key[1]:<16}{N:>7}{have:>7}{miss:>7}{pct:>7.0f}%{omax:>8}{trail:>7}{flag}")

    print(f"\nCORPUS (sessions we have OCR for): authoritative {tot_auth:,} chapters, "
          f"parsed {tot_have:,} -> {100.0*tot_have/max(1,tot_auth):.1f}% complete, "
          f"missing {tot_auth-tot_have:,}")

    # parse sessions with no oracle match (sanity)
    unmatched = sorted(k for k in got if k not in oracle)
    if unmatched:
        print(f"\nparse sessions with NO oracle match ({len(unmatched)}): "
              + ", ".join(f"{y}/{t}" for (y, t) in unmatched[:40]))
    if have_oracle_no_parse:
        reg = [(y, N) for ((y, t), N) in have_oracle_no_parse if t == 'regular']
        print(f"\noracle regular sessions we have NO parse for ({len(reg)}): "
              + ", ".join(f"{y}({N})" for (y, N) in reg[:60]))

if __name__ == "__main__":
    main()
