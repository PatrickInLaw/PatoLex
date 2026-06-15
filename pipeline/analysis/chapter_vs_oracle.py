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

def parse_session_year(label):
    # NNchapters suffix -> real statute year (1900s); else leading 4-digit year
    m = re.search(r"(\d{2})chapters", label.lower())
    if m: return 1900 + int(m.group(1))
    m = re.match(r"(\d{4})", label)
    return int(m.group(1)) if m else 0

def main():
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

    # our parse: (year,type) -> set of chapter ints
    got = defaultdict(set)
    with open(chap_tsv, encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 4 or not p[3].isdigit(): continue
            key = (parse_session_year(p[0]), parse_type(p[0]))
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
