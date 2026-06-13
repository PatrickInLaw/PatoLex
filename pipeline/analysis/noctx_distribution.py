"""
noctx_distribution.py -- map the NOT-ROUTED recoverable residual (the ~202k that Sonnet never saw:
no edit-1/edit-2 candidate at all = deep garble, OR an orphan affix-fragment) across volume / year /
page, to find CLUSTERS where a different OCR approach (re-OCR, VLM, manual) would have high ROI.

A still-flagged token in the post-context corpus is classified:
  known/roman/garbage-shaped -> not counted (already accounted as known/roman/garbage floor)
  else RECOVERABLE; within it:
    affix-of-common               -> FRAGMENT      (orphan; reunify's partner missing)   [not-routed]
    has edit-1-known or SymSpell  -> ROUTED         (weak/no_ctx -> already went to Sonnet)
    else (no candidate)           -> NO_CANDIDATE   (deep garble)                          [not-routed]
NOT-ROUTED = FRAGMENT + NO_CANDIDATE.

Run from the repo:  python -m analysis.noctx_distribution
Reads: <cascade_dir>/out_context/*.json
Writes: <cascade_dir>/noctx_dist_by_volume.tsv  +  noctx_dist_by_page.tsv
Prints: top clusters by count and by density, year rollup, page-concentration for the worst volumes.
"""
import os, re, json, glob, time
import multiprocessing as mp
from collections import Counter, defaultdict
import config

CASCADE   = config.path_for("cascade_dir")
STAGE_OUT = os.path.join(CASCADE, "out_context")
CORPUS_FREQ = config.path_for("cascade_dir", "corpus_freq.json")
BODY_ONLY = os.environ.get("BODY_ONLY", "1") == "1"   # restrict to page_classification body pages
OUT_VOL  = os.path.join(CASCADE, "noctx_dist_body_by_volume.tsv" if BODY_ONLY else "noctx_dist_by_volume.tsv")
OUT_PAGE = os.path.join(CASCADE, "noctx_dist_body_by_page.tsv" if BODY_ONLY else "noctx_dist_by_page.tsv")
_ROMAN   = re.compile(r"^[ivxlcdm]+$")
_YEAR    = re.compile(r"(\d{4})")

_WS=None;_HASWF=False;_WF=None;_ZIPF=None;_SORTED=None;_SORTED_REV=None;_SYM=None
def _init():
    global _WS,_HASWF,_WF,_ZIPF,_SORTED,_SORTED_REV,_SYM
    from ocrcorrect.dictionary import build_dictionary, build_sorted_common
    from ocrcorrect.symspell_e2 import SymSpellE2, load_target_freq
    from wordfreq import zipf_frequency
    ws,_s,has,wf = build_dictionary()
    _WS=frozenset(ws);_HASWF=has;_WF=wf;_ZIPF=zipf_frequency
    _SORTED,_SORTED_REV = build_sorted_common(_WS,_ZIPF)
    _SYM = SymSpellE2(load_target_freq(CORPUS_FREQ)) if os.path.exists(CORPUS_FREQ) else None

def known(t): return (t in _WS) or (_HASWF and _WF(t,"en")>0)
from ocrcorrect.edits import edits1 as _edits1, affix_of_common as _affix
from ocrcorrect.symspell_e2 import _garbage_shaped

def _has_candidate(t):
    if any(known(c) for c in _edits1(t)):
        return True
    if _SYM is not None and len(t) >= 5 and _SYM.lookup(t):
        return True
    return False

def _analyze(fp):
    vol = os.path.basename(fp)[:-5] if fp.endswith(".json") else os.path.basename(fp)
    body = None                            # set of body pidx (0-based) when classification available
    if BODY_ONLY:
        cls_path = config.path_for("data_root", vol, "page_classification.json")
        if os.path.exists(cls_path):
            try:
                body = {p - 1 for p in json.load(open(cls_path, encoding="utf-8")).get("body", [])}
            except Exception:
                body = None
    has_cls = body is not None
    tot = 0; recov = 0; frag = 0; nocand = 0
    page = Counter()                       # pk -> not_routed count
    try:
        d = json.load(open(fp, encoding="utf-8", errors="replace"))
    except Exception:
        return vol, tot, recov, frag, nocand, page, has_cls
    for pk, lines in d.items():
        if body is not None:
            try:
                if int(pk) not in body:
                    continue               # skip front-matter / index / empty pages
            except Exception:
                pass
        for toks in lines:
            for t in toks:
                tot += 1
                if len(t) < 4 or known(t) or _ROMAN.match(t) or _garbage_shaped(t):
                    continue
                recov += 1
                if _affix(t, _SORTED, _SORTED_REV):
                    frag += 1; page[pk] += 1
                elif _has_candidate(t):
                    pass                    # routed (weak/no_ctx)
                else:
                    nocand += 1; page[pk] += 1
    return vol, tot, recov, frag, nocand, page, has_cls

def main():
    files = sorted(glob.glob(os.path.join(STAGE_OUT, "*.json")))
    nw = max(2, min(8, (os.cpu_count() or 4) - 2))
    print(f"analyzing not-routed residual over {len(files)} volumes, {nw} workers...", flush=True)
    t0 = time.time()
    rows = []; page_rows = []; no_cls = []
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw, initializer=_init) as pool:
        for vol, tot, recov, frag, nocand, page, has_cls in pool.imap_unordered(_analyze, files, chunksize=1):
            nr = frag + nocand
            rows.append((vol, tot, recov, frag, nocand, nr))
            for pk, c in page.items():
                page_rows.append((vol, pk, c))
            if BODY_ONLY and not has_cls:
                no_cls.append(vol)
    if BODY_ONLY:
        print(f"BODY-ONLY mode: {len(rows)-len(no_cls)} vols filtered to body pages; "
              f"{len(no_cls)} vols had NO page_classification (counted full): {no_cls[:8]}")

    rows.sort(key=lambda r: -r[5])
    with open(OUT_VOL, "w", encoding="utf-8") as f:
        f.write("vol\ttotal_tokens\trecoverable\tfragment\tno_candidate\tnot_routed\tnot_routed_per_10k\n")
        for vol, tot, recov, frag, nocand, nr in rows:
            f.write(f"{vol}\t{tot}\t{recov}\t{frag}\t{nocand}\t{nr}\t{10000.0*nr/max(1,tot):.1f}\n")
    page_rows.sort(key=lambda r: -r[2])
    with open(OUT_PAGE, "w", encoding="utf-8") as f:
        f.write("vol\tpk\tnot_routed\n")
        for vol, pk, c in page_rows:
            f.write(f"{vol}\t{pk}\t{c}\n")

    tot_nr = sum(r[5] for r in rows); tot_frag = sum(r[3] for r in rows); tot_nc = sum(r[4] for r in rows)
    print(f"\nNOT-ROUTED total: {tot_nr:,}  (fragment {tot_frag:,} / no_candidate {tot_nc:,})   [{time.time()-t0:.0f}s]")

    print("\n=== TOP 20 VOLUMES by not-routed COUNT ===")
    print(f"{'vol':<34}{'not_routed':>11}{'/10k tok':>9}{'frag':>8}{'nocand':>8}")
    for vol, tot, recov, frag, nocand, nr in rows[:20]:
        print(f"{vol:<34}{nr:>11,}{10000.0*nr/max(1,tot):>9.1f}{frag:>8,}{nocand:>8,}")

    bigs = [r for r in rows if r[1] >= 50000]
    bigs.sort(key=lambda r: -10000.0*r[5]/max(1,r[1]))
    print("\n=== TOP 20 VOLUMES by not-routed DENSITY (per 10k tokens, vols >=50k tok) ===")
    for vol, tot, recov, frag, nocand, nr in bigs[:20]:
        print(f"{vol:<34}{10000.0*nr/max(1,tot):>9.1f}/10k  not_routed={nr:,}  ({tot:,} tok)")

    print("\n=== YEAR ROLLUP (not-routed) ===")
    yr = Counter(); yrtot = Counter()
    for vol, tot, recov, frag, nocand, nr in rows:
        m = _YEAR.search(vol); y = m.group(1) if m else "????"
        yr[y] += nr; yrtot[y] += tot
    for y in sorted(yr):
        print(f"  {y}: not_routed={yr[y]:>8,}  ({10000.0*yr[y]/max(1,yrtot[y]):.1f}/10k tok)")

    # page concentration for the 5 worst-count volumes
    print("\n=== PAGE CONCENTRATION (5 worst-count vols): how much of the volume's not-routed sits on its worst pages ===")
    by_vol_pages = defaultdict(list)
    for vol, pk, c in page_rows:
        by_vol_pages[vol].append(c)
    for vol, tot, recov, frag, nocand, nr in rows[:5]:
        pcs = sorted(by_vol_pages.get(vol, []), reverse=True)
        npages = len(pcs)
        top10pct = max(1, npages // 10)
        share = 100.0 * sum(pcs[:top10pct]) / max(1, sum(pcs))
        print(f"  {vol}: {nr:,} not_routed over {npages} pages; top 10% of pages ({top10pct}) hold {share:.0f}%")

if __name__ == "__main__":
    main()
