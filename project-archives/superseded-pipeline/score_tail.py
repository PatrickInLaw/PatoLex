"""
score_tail.py -- score the ENTIRE remaining recoverable tail (no pre-filtering on candidate type).

For every still-flagged token in the post-autocorrect corpus (skip only known / roman / garbage-shaped),
generate candidates outward by edit distance -- edit-1 known words AND the corpus-aware SymSpell edit-1/2
candidate -- then score the best one on TWO SEPARATE axes:
  * edit distance  : how many edits to the nearest real-word match (d1 / d2 / none)
  * collocation    : corpus (prev,cand)/(cand,next) bigram support, and the MARGIN over the runner-up
                     (strong = margin>=1.0 ~2.7x dominance / weak = attested but not dominant / no_ctx = none)

It APPLIES NOTHING. It emits the joint (edit-distance x collocation) distribution + samples per cell, so the
SCORE -- not a pre-filter -- tells us what can auto-apply (near match + strong collocation), what should go to
Sonnet (the uncertain middle, handed a proposed fix), and what's deep tail (no candidate / no signal).

Run from the repo:  python -m analysis.score_tail
Needs: out_autocorrect (cascade output), corpus_freq.json, collocation_bigrams.pkl.
"""
import os, re, json, glob, time, math, pickle
from collections import Counter, defaultdict
import multiprocessing as mp
import config

CASCADE     = config.path_for("cascade_dir")
STAGE_OUT   = os.path.join(CASCADE, "out_autocorrect")
CORPUS_FREQ = config.path_for("cascade_dir", "corpus_freq.json")
COLLOC      = os.path.join(CASCADE, "collocation_bigrams.pkl")
OUT_TSV     = os.path.join(CASCADE, "tail_scored_samples.tsv")
_ROMAN      = re.compile(r"^[ivxlcdm]+$")
STRONG_MARGIN = 1.0

_WS=None;_HASWF=False;_WF=None;_ZIPF=None;_SYM=None;_BIG=None
def _init():
    global _WS,_HASWF,_WF,_ZIPF,_SYM,_BIG
    from ocrcorrect.dictionary import build_dictionary
    from ocrcorrect.symspell_e2 import SymSpellE2, load_target_freq
    from wordfreq import zipf_frequency
    ws,_s,has,wf = build_dictionary()
    _WS=frozenset(ws);_HASWF=has;_WF=wf;_ZIPF=zipf_frequency
    _SYM = SymSpellE2(load_target_freq(CORPUS_FREQ)) if os.path.exists(CORPUS_FREQ) else None
    _BIG = pickle.load(open(COLLOC,"rb")) if os.path.exists(COLLOC) else {}

def known(t): return (t in _WS) or (_HASWF and _WF(t,"en")>0)

from ocrcorrect.edits import edits1 as _edits1
from ocrcorrect.symspell_e2 import _garbage_shaped

def _candidates(t):
    """{cand: edit_dist} -- edit-1 known words (dist 1) + the SymSpell corpus candidate (dist 1 or 2)."""
    cands = {}
    for c in _edits1(t):
        if known(c):
            cands[c] = 1
    if _SYM is not None and len(t) >= 5:
        res = _SYM.lookup(t)                 # (word, 's1'|'s2') or None
        if res:
            cand, tag = res
            cands.setdefault(cand, 1 if tag == "s1" else 2)
    return cands

def _colloc(cand, prev, nxt):
    return math.log(_BIG.get((prev,cand),0)+1) + math.log(_BIG.get((cand,nxt),0)+1)

def _score_vol(fp):
    cells = Counter()                        # (edit_band, colloc_band) -> occurrences
    samples = defaultdict(list)
    try:
        d = json.load(open(fp, encoding="utf-8", errors="replace"))
    except Exception:
        return cells, samples
    for pk, lines in d.items():
        for toks in lines:
            for i, t in enumerate(toks):
                if len(t) < 4 or known(t) or _ROMAN.match(t) or _garbage_shaped(t):
                    continue
                prev = toks[i-1] if i > 0 else ""
                nxt  = toks[i+1] if i+1 < len(toks) else ""
                cands = _candidates(t)
                if not cands:
                    cell = ("none", "no_candidate")
                    cells[cell] += 1
                    if len(samples[cell]) < 10: samples[cell].append(f"{prev}|{t}|{nxt}")
                    continue
                scored = sorted(((c, dst, _colloc(c, prev, nxt)) for c, dst in cands.items()), key=lambda x:-x[2])
                pc, pd, ps = scored[0]
                runner = scored[1][2] if len(scored) > 1 else 0.0
                margin = ps - runner
                eband = "d1" if pd == 1 else "d2"
                cband = "no_ctx" if ps <= 0.0 else ("strong" if margin >= STRONG_MARGIN else "weak")
                cell = (eband, cband)
                cells[cell] += 1
                if len(samples[cell]) < 10:
                    samples[cell].append(f"{prev}|{t}|{nxt} -> {pc} (d{pd} s{ps:.1f} m{margin:.1f} n{len(cands)})")
    return cells, samples

def main():
    files = sorted(glob.glob(os.path.join(STAGE_OUT, "*.json")))
    nw = max(2, min(8, (os.cpu_count() or 4) - 2))
    print(f"scoring tail over {len(files)} post-autocorrect volumes, {nw} workers...", flush=True)
    t0 = time.time()
    cells = Counter(); samples = defaultdict(list)
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw, initializer=_init) as pool:
        for c, s in pool.imap_unordered(_score_vol, files, chunksize=1):
            cells.update(c)
            for k, v in s.items():
                if len(samples[k]) < 10:
                    samples[k].extend(v[:10 - len(samples[k])])
    total = sum(cells.values())
    print(f"\nscored {total:,} recoverable occurrences in {time.time()-t0:.0f}s\n")
    print(f"{'edit':>5} x {'colloc':<13} {'occ':>10} {'%':>7}")
    order = [("d1","strong"),("d1","weak"),("d1","no_ctx"),
             ("d2","strong"),("d2","weak"),("d2","no_ctx"),("none","no_candidate")]
    for cell in order:
        n = cells.get(cell, 0)
        print(f"{cell[0]:>5} x {cell[1]:<13} {n:>10,} {100.0*n/max(1,total):>6.1f}%")
    # headline bands
    auto = cells[("d1","strong")] + cells[("d2","strong")]
    sonnet = cells[("d1","weak")] + cells[("d1","no_ctx")] + cells[("d2","weak")] + cells[("d2","no_ctx")]
    deep = cells[("none","no_candidate")]
    print(f"\nAUTO-APPLY band (strong collocation, d1+d2): {auto:,} ({100.0*auto/max(1,total):.1f}%)")
    print(f"SONNET band (has candidate, weak/no collocation): {sonnet:,} ({100.0*sonnet/max(1,total):.1f}%)")
    print(f"DEEP tail (no candidate): {deep:,} ({100.0*deep/max(1,total):.1f}%)")
    with open(OUT_TSV, "w", encoding="utf-8") as fh:
        for cell in order:
            fh.write(f"# === {cell[0]} x {cell[1]}  ({cells.get(cell,0):,}) ===\n")
            for s in samples.get(cell, []):
                fh.write(s + "\n")
    print(f"\nsamples per cell -> {OUT_TSV}")

if __name__ == "__main__":
    main()
