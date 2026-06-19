#!/usr/bin/env python3
"""
build_oracle_canonical.py  -- P3 of the session-number remodel (DRAFT generator).

Produces a NEW oracle TSV with canonical-session columns APPENDED (additive; existing
columns untouched, so header-based readers keep working). Writes a DRAFT file for Hans
review -- does NOT overwrite the live oracle.

Canonical assignment (built on the twice-Hans-cleared P2 conclusion):
  * Regular sessions sorted chronologically. Their TRUE ordinal = chrono position for
    1..13, then +1 from position 14 onward -- because the 14th session (1863) has no
    oracle row yet (proven by the +1 anchor chain). This RESERVES S14 for the 1863 row
    that P5 adds, so nothing has to re-shift later.
  * canonical_id = S{true_ordinal} for regular; {year}X{n} for extra/special.
Validation: the corpus-declared ordinals should now match session_number at OFFSET 0
(was +1 against the raw chrono index) -- the proof the +1 correction is applied right.

Usage: --scratch <dir> --oracle <tsv> --out <draft tsv>
"""
import argparse, os, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
import rederive_index_counts as R

MISSING_AT = 14   # chrono position of the missing 14th session (the 1863-64 row sorts here)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--oracle", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    scratch = args.scratch.replace("\\", "/").rstrip("/")

    # raw oracle lines (preserve order + exact columns for additive append)
    with open(args.oracle, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        raw = [ln.rstrip("\n").split("\t") for ln in f if ln.strip()]
    rows = [dict(zip(header, r + [""] * (len(header) - len(r)))) for r in raw]

    def yr(r):
        try:
            return int(r.get("session_year") or 0)
        except ValueError:
            return 0

    # declared ordinals (regular only, both-year keys, garbage-gated) -- same logic as P2
    declared = {}
    ref_path = os.path.join(scratch, "_session_reference.tsv")
    if os.path.exists(ref_path):
        with open(ref_path, encoding="utf-8") as f:
            rh = f.readline().rstrip("\n").split("\t")
            for line in f:
                c = dict(zip(rh, line.rstrip("\n").split("\t")))
                num = c.get("session_number", "")
                if not num.isdigit():
                    continue
                ph = (c.get("ordinal_phrase") or "").lower()
                if "extraordinary" in ph or "special" in ph:
                    continue
                m = re.match(r"production-(\d{4})(?:-(\d{2}))?", c["label"])
                if not m:
                    continue
                y0 = int(m.group(1))
                for y in [y0] + ([(y0 // 100) * 100 + int(m.group(2))] if m.group(2) else []):
                    declared[y] = max(declared.get(y, 0), int(num))

    regs = sorted([r for r in rows if r.get("session_type") == "regular"],
                  key=lambda r: (yr(r), r.get("session_label", "")))
    canon = {}   # id(row dict) -> (session_number, kind, canonical_id)
    for i, r in enumerate(regs, 1):
        sn = i if i < MISSING_AT else i + 1     # reserve S14 for the missing 14th
        canon[id(r)] = (str(sn), "regular", f"S{sn}")

    xcount = Counter()
    for r in rows:
        if r.get("session_type") != "regular":
            y = yr(r)
            xcount[y] += 1
            canon[id(r)] = ("", "extra/special", f"{y}X{xcount[y]}")

    # validate: declared should now equal session_number (offset 0) at the anchors
    match = mism = garbage = 0
    for r in regs:
        sn = int(canon[id(r)][0])
        d = declared.get(yr(r))
        if d is None:
            continue
        if d == sn:
            match += 1
        elif abs(d - sn) > 2:
            garbage += 1
        else:
            mism += 1
            print(f"  residual mismatch: {r.get('session_label')} declared={d} session_number={sn} diff={d-sn:+d}")

    # write the draft oracle with appended columns
    newcols = ["session_number", "session_kind", "canonical_id"]
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\t".join(header + newcols) + "\n")
        for r in rows:
            sn, kind, cid = canon[id(r)]
            f.write("\t".join([r.get(h, "") for h in header] + [sn, kind, cid]) + "\n")

    print(f"\nregular={len(regs)} extra={len(rows)-len(regs)}")
    print(f"declared anchors: MATCH(offset0)={match}  residual-mismatch={mism}  garbage-gated={garbage}")
    print(f"S14 reserved for the missing 1863 (14th) session; 1863-64 -> {canon[id(next(r for r in regs if r.get('session_label')=='1863-64 Regular Session'))][2]}")
    print(f"WROTE {args.out}")

if __name__ == "__main__":
    main()
