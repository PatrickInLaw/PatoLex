"""
precision_sample.py -- (a) reservoir-sample a random N from the STRONG-collocation band for a precision
measure, and (b) break EVERY band into single-candidate (n=1) vs multi-candidate, so we can see whether the
weak band is full of lone edit-1 candidates (which might be higher-confidence than their weak collocation
suggests). Reuses score_tail's scoring (candidates + collocation). Applies nothing.

Run from the repo:  python -m analysis.precision_sample
Writes: <cascade_dir>/precision_sample.tsv   (dist  prev  token  next  proposed_fix)  -- the strong-band sample
Prints: per-band single-candidate breakdown.
"""
import os, glob, json, re, random, time
import multiprocessing as mp
from collections import Counter
import config
from analysis import score_tail as st

CASCADE   = config.path_for("cascade_dir")
STAGE_OUT = os.path.join(CASCADE, "out_autocorrect")
OUT       = os.path.join(CASCADE, "precision_sample.tsv")
N          = 300
PER_WORKER = 150
_ROMAN     = re.compile(r"^[ivxlcdm]+$")

def _vol(fp):
    res = []; strong_seen = 0
    nsingle = Counter(); ntot = Counter()
    try:
        d = json.load(open(fp, encoding="utf-8", errors="replace"))
    except Exception:
        return res, nsingle, ntot
    for pk, lines in d.items():
        for toks in lines:
            for i, t in enumerate(toks):
                if len(t) < 4 or st.known(t) or _ROMAN.match(t) or st._garbage_shaped(t):
                    continue
                prev = toks[i-1] if i > 0 else ""
                nxt  = toks[i+1] if i+1 < len(toks) else ""
                cands = st._candidates(t)
                if not cands:
                    cell = ("none", "no_candidate"); ntot[cell] += 1
                    continue
                scored = sorted(((c, dst, st._colloc(c, prev, nxt)) for c, dst in cands.items()), key=lambda x:-x[2])
                pc, pd, ps = scored[0]
                runner = scored[1][2] if len(scored) > 1 else 0.0
                margin = ps - runner
                eband = "d1" if pd == 1 else "d2"
                cband = "no_ctx" if ps <= 0.0 else ("strong" if margin >= 1.0 else "weak")
                cell = (eband, cband)
                ntot[cell] += 1
                if len(cands) == 1:
                    nsingle[cell] += 1
                if cband == "strong":
                    strong_seen += 1
                    item = (pd, prev, t, nxt, pc)
                    if len(res) < PER_WORKER:
                        res.append(item)
                    else:
                        j = random.randint(0, strong_seen - 1)
                        if j < PER_WORKER:
                            res[j] = item
    return res, nsingle, ntot

def main():
    files = sorted(glob.glob(os.path.join(STAGE_OUT, "*.json")))
    nw = max(2, min(8, (os.cpu_count() or 4) - 2))
    print(f"sampling over {len(files)} volumes, {nw} workers...", flush=True)
    t0 = time.time()
    pool_res = []; nsingle = Counter(); ntot = Counter()
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw, initializer=st._init) as pool:
        for res, ns, nt in pool.imap_unordered(_vol, files, chunksize=1):
            pool_res.extend(res); nsingle.update(ns); ntot.update(nt)
    sample = random.sample(pool_res, min(N, len(pool_res)))
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("dist\tprev\ttoken\tnext\tproposed_fix\n")
        for pd, prev, t, nxt, pc in sample:
            fh.write(f"d{pd}\t{prev}\t{t}\t{nxt}\t{pc}\n")
    print(f"\nwrote {len(sample)} strong-band fixes -> {OUT}  ({time.time()-t0:.0f}s)\n")
    print(f"{'edit x colloc':<22} {'total':>10} {'single(n=1)':>12} {'%single':>8}")
    order = [("d1","strong"),("d1","weak"),("d1","no_ctx"),
             ("d2","strong"),("d2","weak"),("d2","no_ctx"),("none","no_candidate")]
    for cell in order:
        tt = ntot.get(cell, 0); ss = nsingle.get(cell, 0)
        print(f"{cell[0]+' x '+cell[1]:<22} {tt:>10,} {ss:>12,} {100.0*ss/max(1,tt):>7.1f}%")

if __name__ == "__main__":
    main()
