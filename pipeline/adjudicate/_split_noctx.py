import os, math
base = os.path.dirname(__file__)
src = os.path.join(base, "_noctx_worklist.tsv")
cd = os.path.join(base, "_noctx_chunks")
os.makedirs(cd, exist_ok=True)
os.makedirs(os.path.join(base, "_noctx_verdicts"), exist_ok=True)
rows = [l.rstrip("\n") for l in open(src, encoding="utf-8")][1:]   # skip header
PER = 1000
N = math.ceil(len(rows) / PER)
for i in range(N):
    part = rows[i*PER:(i+1)*PER]
    if not part:
        continue
    with open(os.path.join(cd, f"chunk_{i:03d}.tsv"), "w", encoding="utf-8") as f:
        f.write("\n".join(part) + "\n")
print(f"{len(rows)} rows -> {N} chunks of <= {PER} in {cd}")
