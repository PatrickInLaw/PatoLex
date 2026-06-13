import os, glob
base = os.path.dirname(__file__)
cd = os.path.join(base, "_noctx_chunks")
vd = os.path.join(base, "_noctx_verdicts")

problems = []
ok = 0
total_chunk = 0; total_verd = 0
for ch in sorted(glob.glob(os.path.join(cd, "chunk_*.tsv"))):
    name = os.path.basename(ch)[len("chunk_"):-len(".tsv")]
    if name.endswith("a") or name.endswith("b"):   # skip transient half-chunks
        continue
    crows = [l for l in open(ch, encoding="utf-8") if l.strip()]
    cn = len(crows); total_chunk += cn
    vf = os.path.join(vd, f"verdicts_{name}.tsv")
    if not os.path.exists(vf):
        problems.append((name, f"MISSING verdicts (chunk={cn})")); continue
    vrows = [l.rstrip("\n") for l in open(vf, encoding="utf-8") if l.strip()]
    vn = len(vrows); total_verd += vn
    badcols = sum(1 for r in vrows if len(r.split("\t")) != 5)
    if vn < cn:
        problems.append((name, f"SHORT verdicts={vn} chunk={cn}"))
    elif badcols:
        problems.append((name, f"MALFORMED {badcols} rows != 5 cols (verdicts={vn})"))
    else:
        ok += 1

print(f"chunks checked (105 expected): {ok + len(problems)}")
print(f"OK: {ok}")
print(f"PROBLEMS: {len(problems)}")
for n, msg in problems:
    print(f"  {n}: {msg}")
print(f"total chunk rows: {total_chunk:,}  total verdict rows: {total_verd:,}")
