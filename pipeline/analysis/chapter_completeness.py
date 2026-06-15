"""chapter_completeness.py -- TRUSTWORTHY per-session chapter-sequence gap check.

CA session laws are numbered Chapter 1..N per legislative session. A real "missing act" = a chapter
number absent from an otherwise-contiguous session sequence. The naive version (used by the old
completeness-report.json) is dominated by false positives; this version fixes the known modes:

  1. MULTI-VOLUME sessions: merge all physical volumes of one session before checking
     (e.g. 1971-vol1-chapters + 1971-vol2 -> session 1971).
  2. NNchapters SUFFIX: the real statute year is encoded in the suffix, NOT the physical-volume year
     (e.g. 1963-vol1-62chapters -> 1962 statutes; 1951-vol1-50chapters -> 1950). Map by suffix.
  3. EXTRA/EXTRAORDINARY sessions: numbered independently -> separate session key (reg / extraN / prior).
  4. OCR-GARBLED chapter numbers: isolated absurd values (e.g. "8888") inflate the max and manufacture
     huge fake gaps -> detected as suspects and excluded from the max, reported separately.
  5. CODE volumes (codifications, not chapter-numbered session laws) are not in the parse set -> n/a.

Output is TRIAGED, not a single number:
  CLEAN      max == distinct, 0 missing  -> session verifiably complete
  SMALL_GAP  <=5 missing in a contiguous run -> CANDIDATE missing acts (listed)
  LARGE_GAP  >5 missing -> needs review (mapping ambiguity or real loss)
  ANOMALY    max >> distinct, or suspects present, or no-number acts -> structural/OCR, manual look

Run locally on the extracted TSV:
  python -m analysis.chapter_completeness C:\\Users\\PatrickKolasinski\\PatoLex-scratch\\chapters.tsv
"""
import sys, re
from collections import defaultdict

def session_key(label):
    l = label.lower()
    typ = "reg"
    if "prior" in l:                              typ = "prior"
    elif "firstextra" in l or "1stextra" in l:    typ = "extra1"
    elif "secondextra" in l:                      typ = "extra2"
    elif "thirdextra" in l:                       typ = "extra3"
    elif "extra" in l:                            typ = "extra"
    m = re.search(r"(\d{2})chapters", l)          # NNchapters -> real statute year (1900s)
    if m:
        year = 1900 + int(m.group(1))
        disp = str(year)
        return (year, typ, disp + ("" if typ == "reg" else "/" + typ))
    m = re.match(r"(\d{4})(?:-(\d{2,4}))?", label)  # leading year / range
    if m:
        return (int(m.group(1)), typ, m.group(0) + ("" if typ == "reg" else "/" + typ))
    return (0, typ, label)


CA_HARD_CEILING = 2300   # no CA legislative session ever exceeded ~2,200 chapters

def robust_max(ints, n_acts):
    """drop OCR-garble high outliers (provably-impossible chapter numbers); return (real_max, suspects).
    A chapter number is implausible if it exceeds the CA hard ceiling OR is far above what the
    session's own act-count could support (each act ~= one chapter, so true_max ~= n_acts)."""
    if not ints:
        return 0, []
    rel_cap = max(300, int(n_acts * 1.8))
    cap = min(CA_HARD_CEILING, rel_cap)
    plausible = [c for c in set(ints) if c <= cap]
    suspects = sorted(c for c in set(ints) if c > cap)
    return (max(plausible) if plausible else 0), suspects


def main():
    tsv = sys.argv[1]
    by_sess = defaultdict(list)      # key -> list of chapter_int (None for no-number)
    disp = {}
    vols_per = defaultdict(set)
    with open(tsv, encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 4:
                continue
            label, _list, _raw, ci = p[0], p[1], p[2], p[3]
            key = session_key(label)
            disp[key] = key[2]
            vols_per[key].add(label)
            by_sess[key].append(int(ci) if ci.isdigit() else None)

    buckets = {"CLEAN": [], "SMALL_GAP": [], "LARGE_GAP": [], "ANOMALY": []}
    tot_missing_small = 0
    for key in sorted(by_sess):
        ch = by_sess[key]
        nums = [c for c in ch if c is not None]
        nonum = sum(1 for c in ch if c is None)
        rmax, suspects = robust_max(nums, len(ch))
        sset = set(suspects)
        plausible = [c for c in nums if c not in sset]      # drop provably-corrupt numbers
        distinct = sorted(set(plausible))
        present = set(distinct)
        missing = [n for n in range(1, rmax + 1) if n not in present] if rmax else []
        dupes = len(plausible) - len(distinct)
        rec = {"sess": disp[key], "vols": len(vols_per[key]), "acts": len(ch),
               "distinct": len(distinct), "min": (distinct[0] if distinct else 0),
               "max": rmax, "missing": missing, "nonum": nonum, "dupes": dupes,
               "suspects": suspects}
        if suspects or nonum > 5 or (rmax and len(distinct) < 0.7 * rmax):
            buckets["ANOMALY"].append(rec)
        elif not missing:
            buckets["CLEAN"].append(rec)
        elif len(missing) <= 5:
            buckets["SMALL_GAP"].append(rec); tot_missing_small += len(missing)
        else:
            buckets["LARGE_GAP"].append(rec)

    def show(name, recs, listmiss=False):
        print(f"\n===== {name} ({len(recs)} sessions) =====")
        for r in recs:
            extra = ""
            if listmiss and r["missing"]:
                mm = r["missing"]
                extra = "  MISSING=" + (",".join(map(str, mm)) if len(mm) <= 20 else f"{len(mm)} nums")
            sus = f"  suspects={r['suspects']}" if r["suspects"] else ""
            nn = f"  no-num={r['nonum']}" if r["nonum"] else ""
            dp = f"  dupes={r['dupes']}" if r["dupes"] else ""
            print(f"  {r['sess']:<14} vols={r['vols']} acts={r['acts']:>4} distinct={r['distinct']:>4} "
                  f"min={r['min']} max={r['max']:>4}{extra}{sus}{nn}{dp}")

    print(f"TOTAL sessions: {sum(len(v) for v in buckets.values())}  |  acts: {sum(len(by_sess[k]) for k in by_sess):,}")
    show("CLEAN (verifiably complete, 0 gaps)", buckets["CLEAN"])
    show("SMALL_GAP (<=5 missing -- CANDIDATE missing acts)", buckets["SMALL_GAP"], listmiss=True)
    show("LARGE_GAP (>5 missing -- needs review)", buckets["LARGE_GAP"], listmiss=True)
    show("ANOMALY (structural/OCR -- manual look)", buckets["ANOMALY"], listmiss=True)
    print(f"\nSUMMARY: CLEAN={len(buckets['CLEAN'])} SMALL_GAP={len(buckets['SMALL_GAP'])} "
          f"LARGE_GAP={len(buckets['LARGE_GAP'])} ANOMALY={len(buckets['ANOMALY'])}  "
          f"| candidate missing acts in SMALL_GAP sessions = {tot_missing_small}")

if __name__ == "__main__":
    main()
