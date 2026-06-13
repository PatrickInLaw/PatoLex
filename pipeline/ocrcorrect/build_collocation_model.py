"""
build_collocation_model.py -- persist the corpus-wide known-known collocation bigram model that the
context heuristic stage needs. The cascade processes volumes INDEPENDENTLY (per-volume workers), but the
context disambiguation needs collocations from the WHOLE corpus, so we build the model once here and
persist it; stage_context then loads it in each worker's _init.

Reuses context_resolve's validated _init + _bigrams (the exact logic behind the 77.4% resolution measure)
so the model is identical to what the feasibility run used. Reads the post-autocorrect cascade output.

Run from the repo:  python -m ocrcorrect.build_collocation_model
Writes: <cascade_dir>/collocation_bigrams.pkl   ({(prev, next): count})
"""
import os, glob, time, pickle
import multiprocessing as mp
from collections import Counter
import config
from ocrcorrect import context_resolve as cr

CASCADE   = config.path_for("cascade_dir")
STAGE_OUT = os.path.join(CASCADE, "out_autocorrect")
OUT_PKL   = os.path.join(CASCADE, "collocation_bigrams.pkl")

def main():
    files = sorted(glob.glob(os.path.join(STAGE_OUT, "*.json")))
    nw = max(2, min(12, (os.cpu_count() or 4) - 2))
    print(f"building collocation model over {len(files)} post-autocorrect volumes, {nw} workers...", flush=True)
    t0 = time.time()
    big = Counter()
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw, initializer=cr._init) as pool:        # cr._init builds the dict + known()
        for c in pool.imap_unordered(cr._bigrams, files, chunksize=1):
            big.update(c)
    os.makedirs(os.path.dirname(OUT_PKL), exist_ok=True)
    with open(OUT_PKL, "wb") as f:
        pickle.dump(dict(big), f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"persisted {len(big):,} known-known bigrams -> {OUT_PKL} "
          f"({os.path.getsize(OUT_PKL)/1e6:.0f}MB, {time.time()-t0:.0f}s)")

if __name__ == "__main__":
    main()
