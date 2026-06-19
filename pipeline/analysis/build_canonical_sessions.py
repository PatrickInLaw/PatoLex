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

    # declared ordinals from the corpus -> declared session_number, REGULAR sessions
    # only. Keyed by EVERY year a volume's label spans (Hans CRITICAL-3: the oracle's
    # session_year uses the START year for some biennia (1863-64->1863) and the END
    # year for others (1873-74->1874), so a single leading-year key silently lost
    # anchors -- register both years to match either convention).
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
                phrase = (c.get("ordinal_phrase") or "").lower()
                if "extraordinary" in phrase or "special" in phrase:
                    continue  # Hans MAJOR-4: an extra-session ordinal, NOT the regular sequence
                m = re.match(r"production-(\d{4})(?:-(\d{2}))?", c["label"])
                if not m:
                    continue
                y0 = int(m.group(1))
                years = [y0] + ([(y0 // 100) * 100 + int(m.group(2))] if m.group(2) else [])
                n = int(num)
                for y in years:
                    # OCR reads ordinals one LOW (Fifth<Sixth, Eleventh<Twelfth,
                    # Nineteenth<Twentieth -- all Hans's examples). On a per-year
                    # disagreement keep the larger reading (the conflict list still prints).
                    declared[y] = max(declared.get(y, 0), n)

    def yr(r):
        try:
            return int(r.get("session_year") or 0)
        except ValueError:
            return 0

    # Hans MINOR-2: secondary key on label so ordering is deterministic once the
    # missing 14th (session_year=1863, tying the 1863-64 row) is added.
    regulars = sorted([r for r in oracle if r.get("session_type") == "regular"],
                      key=lambda r: (yr(r), r.get("session_label", "")))
    extras = [r for r in oracle if r.get("session_type") != "regular"]

    rows, conflicts, garbage = [], [], []
    for i, r in enumerate(regulars, 1):
        y = yr(r)
        d = declared.get(y)
        status = "ok"
        if d is not None and d != i:
            # Hans 2nd pass: a declared ordinal WILDLY off its chronological position is
            # OCR garbage (e.g. 1937 "Fifty-Second" OCR'd "Firry-SEcOND" -> parser grabbed
            # the substring "second"=2), NOT a real anchor. Gate at |diff|>2 so a genuine
            # +1 (missing-14th offset) or even a real +2 still shows as a CONFLICT.
            if abs(d - i) > 2:
                status = f"OCR_GARBAGE(declared={d}, assigned={i})"
                garbage.append((r.get("session_label"), y, d, i))
            else:
                status = f"CONFLICT(declared={d}, assigned={i})"
                conflicts.append((r.get("session_label"), y, d, i))
        rows.append([f"S{i}", "regular", str(i), str(y), r.get("session_label", ""),
                     r.get("total_chapters", ""), "" if d is None else str(d), status])
    from collections import Counter
    xcount = Counter()
    for r in extras:
        y = yr(r)
        xcount[y] += 1  # Hans MINOR-3: unique id per year (was a bare {y}X collision)
        rows.append([f"{y}X{xcount[y]}", "extra/special", "", str(y), r.get("session_label", ""),
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
    print(f"\nCONFLICTS (declared != assigned, |diff|<=2 -> real anchors of the offset): {len(conflicts)}")
    for lbl, y, d, a in conflicts:
        print(f"   {lbl} (year {y}): declared={d} assigned={a}  diff={d-a:+d}")
    print(f"\nOCR_GARBAGE (declared wildly off position -> excluded, not a real anchor): {len(garbage)}")
    for lbl, y, d, a in garbage:
        print(f"   {lbl} (year {y}): declared={d} assigned={a}  diff={d-a:+d}")
    print(f"\nWROTE {out}")

if __name__ == "__main__":
    main()
