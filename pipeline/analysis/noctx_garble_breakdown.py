"""
noctx_garble_breakdown.py -- split the no_candidate residual into PROPER NAMES (correctly transcribed,
in the ~370k name gazetteer -> NOT errors) vs GENUINE GARBLE (char-salad -> the real re-OCR target), and
detect INDEX / ROSTER pages (member lists, tables of acts -- text-dense so page_classification calls them
'body', but they're name-directories, not statute body, and are NOT ingested as chapters/sections).

For each still-flagged token (post-context) that is recoverable (unknown / not-roman / not-garbage-shaped):
  affix-of-common                  -> FRAGMENT
  edit-1-known or SymSpell cand     -> ROUTED (weak/no_ctx, already to Sonnet)
  in name gazetteer (single word)   -> NAME   (correctly transcribed proper name)
  else                              -> GARBLE (genuine char-salad)
Pages are flagged INDEX/ROSTER by marker tokens (index/officers/members/contents) + very low statute-keyword
density, or very high name density with ~no statute keywords.

REAL re-OCR target = GARBLE tokens on NON-index pages.

Run from the repo:  python -m analysis.noctx_garble_breakdown
Writes: <cascade_dir>/real_garble_by_volume.tsv  +  real_garble_by_page.tsv
"""
import os, re, json, glob, time
import multiprocessing as mp
from collections import Counter, defaultdict
import config

CASCADE   = config.path_for("cascade_dir")
STAGE_OUT = os.path.join(CASCADE, "out_context")
CORPUS_FREQ = config.path_for("cascade_dir", "corpus_freq.json")
GAZ_PATH  = config.path_for("gazetteer")
OUT_VOL   = os.path.join(CASCADE, "real_garble_by_volume.tsv")
OUT_PAGE  = os.path.join(CASCADE, "real_garble_by_page.tsv")
_ROMAN    = re.compile(r"^[ivxlcdm]+$")
_YEAR     = re.compile(r"(\d{4})")
_MARKERS  = {"index", "officers", "members", "contents", "roster"}
_STATKW   = {"section", "chapter", "approved", "whereas", "act", "shall", "enact", "provided", "sec", "title"}

_WS=None;_HASWF=False;_WF=None;_ZIPF=None;_SORTED=None;_SORTED_REV=None;_SYM=None;_GAZ=None
def _init():
    global _WS,_HASWF,_WF,_ZIPF,_SORTED,_SORTED_REV,_SYM,_GAZ
    from ocrcorrect.dictionary import build_dictionary, build_sorted_common
    from ocrcorrect.symspell_e2 import SymSpellE2, load_target_freq
    from wordfreq import zipf_frequency
    ws,_s,has,wf = build_dictionary()
    _WS=frozenset(ws);_HASWF=has;_WF=wf;_ZIPF=zipf_frequency
    _SORTED,_SORTED_REV = build_sorted_common(_WS,_ZIPF)
    _SYM = SymSpellE2(load_target_freq(CORPUS_FREQ)) if os.path.exists(CORPUS_FREQ) else None
    g = set()
    if os.path.exists(GAZ_PATH):
        for line in open(GAZ_PATH, encoding="utf-8", errors="replace"):
            for w in line.strip().lower().split():
                if len(w) >= 3 and w.isalpha():
                    g.add(w)
    _GAZ = frozenset(g)

def known(t): return (t in _WS) or (_HASWF and _WF(t,"en")>0)
from ocrcorrect.edits import edits1 as _edits1, affix_of_common as _affix
from ocrcorrect.symspell_e2 import _garbage_shaped

def _has_candidate(t):
    if any(known(c) for c in _edits1(t)): return True
    if _SYM is not None and len(t) >= 5 and _SYM.lookup(t): return True
    return False

def _analyze(fp):
    vol = os.path.basename(fp)[:-5] if fp.endswith(".json") else os.path.basename(fp)
    c = Counter()           # global counts: frag, name, garble, routed, idx_pages, garble_on_idx
    page_garble = Counter()  # pk -> real garble (non-index pages only)
    try:
        d = json.load(open(fp, encoding="utf-8", errors="replace"))
    except Exception:
        return vol, c, page_garble
    for pk, lines in d.items():
        flat = [t for toks in lines for t in toks]
        n = len(flat)
        if n == 0:
            continue
        head = set(flat[:40])
        name_frac = (sum(1 for t in flat if t in _GAZ) / n) if _GAZ else 0.0
        stat_frac = sum(1 for t in flat if t in _STATKW) / n
        is_index = ((head & _MARKERS) and stat_frac < 0.006) or (name_frac > 0.35 and stat_frac < 0.003)
        if is_index:
            c["idx_pages"] += 1
        for t in flat:
            if len(t) < 4 or known(t) or _ROMAN.match(t) or _garbage_shaped(t):
                continue
            # recoverable
            if _affix(t, _SORTED, _SORTED_REV):
                c["frag"] += 1; continue
            if _has_candidate(t):
                c["routed"] += 1; continue
            # no_candidate -> name vs garble
            if t in _GAZ:
                c["name"] += 1; continue
            c["garble"] += 1
            if is_index:
                c["garble_on_idx"] += 1
            else:
                page_garble[pk] += 1
    return vol, c, page_garble

def main():
    files = sorted(glob.glob(os.path.join(STAGE_OUT, "*.json")))
    nw = max(2, min(8, (os.cpu_count() or 4) - 2))
    print(f"breaking down garble over {len(files)} volumes, {nw} workers (gazetteer + index-page detect)...", flush=True)
    t0 = time.time()
    G = Counter(); vol_real = {}; page_rows = []
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw, initializer=_init) as pool:
        for vol, c, page_garble in pool.imap_unordered(_analyze, files, chunksize=1):
            G.update(c)
            real = c["garble"] - c["garble_on_idx"]
            vol_real[vol] = real
            for pk, n in page_garble.items():
                page_rows.append((vol, pk, n))

    nocand = G["name"] + G["garble"]
    print(f"\n[{time.time()-t0:.0f}s] no_candidate breakdown:")
    print(f"  PROPER NAMES (gazetteer, correctly transcribed -- NOT errors): {G['name']:,}")
    print(f"  GENUINE GARBLE (char-salad):                                   {G['garble']:,}")
    print(f"  of which on INDEX/ROSTER pages ({G['idx_pages']:,} pages):      {G['garble_on_idx']:,}")
    print(f"  => REAL re-OCR target (garble on NON-index pages):             {G['garble']-G['garble_on_idx']:,}")
    print(f"  [fragments (orphan halves): {G['frag']:,}   routed-to-Sonnet already: {G['routed']:,}]")

    rows = sorted(vol_real.items(), key=lambda kv: -kv[1])
    with open(OUT_VOL, "w", encoding="utf-8") as f:
        f.write("vol\treal_garble\n")
        for vol, n in rows:
            f.write(f"{vol}\t{n}\n")
    page_rows.sort(key=lambda r: -r[2])
    with open(OUT_PAGE, "w", encoding="utf-8") as f:
        f.write("vol\tpk\treal_garble\n")
        for vol, pk, n in page_rows:
            f.write(f"{vol}\t{pk}\t{n}\n")

    print("\n=== TOP 15 VOLUMES by REAL garble (non-name, non-index) ===")
    for vol, n in rows[:15]:
        print(f"  {vol:<34}{n:>8,}")
    print("\n=== TOP 12 PAGES by REAL garble ===")
    for vol, pk, n in page_rows[:12]:
        print(f"  {vol:<34} pk={pk:<6} {n}")
    print("\n=== YEAR ROLLUP (REAL garble) ===")
    yr = Counter()
    for vol, n in rows:
        m = _YEAR.search(vol); yr[m.group(1) if m else "????"] += n
    for y in sorted(yr):
        print(f"  {y}: {yr[y]:,}")

if __name__ == "__main__":
    main()
