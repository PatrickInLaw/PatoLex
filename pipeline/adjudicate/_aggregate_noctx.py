import os, glob
base = os.path.dirname(__file__)
vd = os.path.join(base, "_noctx_verdicts")
OUT = os.path.join(base, "noctx_adjudicated.tsv")
fixed = 0; none = 0; bad = 0; total = 0
seen = set(); dup = 0
with open(OUT, "w", encoding="utf-8") as out:
    out.write("vol\tpk\tidx\ttoken\tfix\n")
    for vf in sorted(glob.glob(os.path.join(vd, "verdicts_*.tsv"))):
        for line in open(vf, encoding="utf-8"):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            p = line.split("\t")
            if len(p) != 5:
                bad += 1; continue
            key = (p[0], p[1], p[2])
            if key in seen:
                dup += 1; continue
            seen.add(key)
            out.write(line + "\n"); total += 1
            if p[4].strip().upper() == "NONE":
                none += 1
            else:
                fixed += 1
print(f"aggregated {total:,} occurrences -> {OUT}")
print(f"FIXED (real word): {fixed:,}   NONE: {none:,}   malformed-skipped: {bad}   dup-skipped: {dup}")
