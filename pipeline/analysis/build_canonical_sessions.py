#!/usr/bin/env python3
"""
build_canonical_sessions.py  -- READ-ONLY: P2 of the session-number remodel.

Assigns a canonical session id to every oracle row, then VALIDATES it against the
ordinals the corpus actually declared (`_session_reference.tsv`):
  * Regular sessions form a continuous ordinal sequence -> walk them chronologically
    and assign 1,2,3,...  The legislature's reality: each regular session is the
    next ordinal regardless of the annual->biennial gap.
  * The declared ordinals (read from the volumes' own title pages) are the ANCHORS:
    where the chronological assignment disagrees with a declared ordinal, it's
    flagged (OCR misread vs real gap) -- never silently reconciled.
  * Extra/special sessions get their own id (year + designation), outside the
    regular ordinal sequence.

Output (under SCRATCH): _canonical_sessions.tsv  + stdout conflict report.
Changes no oracle, no matcher, no parse. Usage: --scratch <dir> --oracle <tsv>
"""
import argparse, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import rederive_index_counts as R

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--oracle", required=True)
    args = ap.parse_args()
    scratch = args.scratch.replace("\\", "/").rstrip("/")
    oracle = R.load_oracle(args.oracle)

    # declared ordinals from the corpus: leading-year -> declared session_number
    declared = {}
    ref_path = os.path.join(scratch, "_session_reference.tsv")
    if os.path.exists(ref_path):
        with open(ref_path, encoding="utf-8") as f:
            hdr = f.readline().rstrip("\n").split("\t")
            for line in f:
                c = dict(zip(hdr, line.rstrip("\n").split("\t")))
                num = c.get("session_number", "")
                if not num.isdigit():
                    continue
                m = re.match(r"production-(\d{4})", c["label"])
                if m:
                    y = int(m.group(1))
                    # keep the first/lowest declared per year (anchor); prefer the
                    # plain "production-YYYY"/"-YY" volumes over -code which is +1 era-shifted
                    if y not in declared or "code" not in c["label"]:
                        declared[y] = int(num)

    def yr(r):
        try:
            return int(r.get("session_year") or 0)
        except ValueError:
            return 0

    regulars = sorted([r for r in oracle if r.get("session_type") == "regular"], key=yr)
    extras = [r for r in oracle if r.get("session_type") != "regular"]

    rows, conflicts = [], []
    for i, r in enumerate(regulars, 1):
        y = yr(r)
        d = declared.get(y)
        status = "ok"
        if d is not None and d != i:
            status = f"CONFLICT(declared={d}, assigned={i})"
            conflicts.append((r.get("session_label"), y, d, i))
        rows.append([f"S{i}", "regular", str(i), str(y), r.get("session_label", ""),
                     r.get("total_chapters", ""), "" if d is None else str(d), status])
    for r in extras:
        y = yr(r)
        rows.append([f"{y}X", "extra/special", "", str(y), r.get("session_label", ""),
                     r.get("total_chapters", ""), "", "extra"])

    out = os.path.join(scratch, "_canonical_sessions.tsv")
    with open(out, "w", encoding="utf-8") as f:
        f.write("canonical_id\tkind\tordinal\tstart_year\toracle_label\ttotal_chapters\t"
                "declared_ordinal\tstatus\n")
        for r in rows:
            f.write("\t".join(r) + "\n")

    # anchors that CONFIRM the assignment (declared == assigned)
    anchors = [(r[4], r[2], r[6]) for r in rows if r[1] == "regular" and r[6] and r[7] == "ok"]
    print(f"regular sessions: {len(regulars)}  extra/special: {len(extras)}")
    print(f"declared-ordinal ANCHORS confirming the sequence: {len(anchors)}")
    print("  sample anchors:", [(a[0], a[1]) for a in anchors[:6]], "...",
          [(a[0], a[1]) for a in anchors[-4:]])
    print(f"\nCONFLICTS (declared != assigned -> investigate): {len(conflicts)}")
    for lbl, y, d, a in conflicts:
        print(f"   {lbl} (year {y}): declared={d} assigned={a}  diff={d-a:+d}")
    print(f"\nWROTE {out}")

if __name__ == "__main__":
    main()
