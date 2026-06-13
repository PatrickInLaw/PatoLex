"""
roster_detect.py -- garble-TOLERANT index/roster-page detector + re-measure of the REAL re-OCR target.

The first classifier (in noctx_garble_breakdown) flagged index/roster pages by MARKER tokens
(index/officers/members) and by GAZETTEER name-density. Both fail on the pages we care about most:
member/officer ROSTER tables whose names are OCR-GARBLED -> they match no gazetteer, so name-density
reads low and the page looks like statute "body". The two pages we visually CONFIRMED are rosters
(production-1863 pk36, production-1862 pk34) were missed and still top the real-garble list.

This detector adds two garble-tolerant signals that survive name garbling:
  * COUNTY density   -- CA county tokens stay CLEAN (they're short, dictionary-backed) even when the
                        adjacent surname is mangled; rosters are dense with "... <name> Sacramento ..." etc.
  * SHORT-LINE ratio -- roster/index rows are short (Name | County | Residence; or Title .... page-no),
                        unlike running statute prose.
CALIBRATION (2026-06-13, against confirmed rosters 1863 pk36 / 1862 pk34 + body 1863 pk20):
  rosters have short_line_ratio ~0.02 (LOW -- OCR collapsed the table columns into long garble runs),
  but stat_frac == 0.0 (no statute keywords), garble_frac ~0.33, and the column-header tokens SURVIVE
  cleanly in the head ("name counties represented residence"). The body page has stat_frac 0.088 and
  garble_frac 0.05. So the discriminators are HEADER MARKERS + zero statute keywords + high garble --
  NOT short lines or county density.

A page is INDEX/ROSTER if ANY of:
  R1 markers   : >=2 roster/index header tokens in head AND statute-keyword density < ST_M   (column headers
                 like name/counties/represented/residence, or index/officers/members/contents/roster/assembly)
  R2 gaz-names : gazetteer name-frac > 0.35 + ~no statute keywords                            (original)
  R3 fingerprint (garble-tolerant): garble_frac >= GF and name_frac >= NF and county_frac >= CF
                 and stat_frac < ST -- a name/county-flavored page that's mostly un-correctable + no legal prose.
                 (Deliberately requires the name+county fingerprint so a badly-OCR'd STATUTE page -- which we
                  DO want to re-OCR, not exclude -- is NOT swept in just for being garbled.)

Run from the repo:  python -m analysis.roster_detect
  DEBUG_PAGES="production-1863:36,production-1862:34,production-1863:20"  -> dump signals for those pages, no full run
  SAMPLE_N=5  -> also write spot_sample.tsv (random flagged + high-garble-body pages, pre-1914 _Statutes only)
Writes: <cascade_dir>/roster_pages.tsv  + real_garble_by_volume_v2.tsv  + spot_sample.tsv
"""
import os, re, json, glob, time, random
import multiprocessing as mp
from collections import Counter
import config

CASCADE   = config.path_for("cascade_dir")
STAGE_OUT = os.path.join(CASCADE, "out_context")
CORPUS_FREQ = config.path_for("cascade_dir", "corpus_freq.json")
GAZ_PATH  = config.path_for("gazetteer")
OUT_ROST  = os.path.join(CASCADE, "roster_pages.tsv")
OUT_VOL   = os.path.join(CASCADE, "real_garble_by_volume_v2.tsv")
OUT_SAMP  = os.path.join(CASCADE, "spot_sample.tsv")
_ROMAN    = re.compile(r"^[ivxlcdm]+$")
_NUMERIC  = re.compile(r"^\d+$")
# roster/index header tokens (column headers + section titles) -- survive OCR even when the names below garble
_MARKERS  = {"index", "officers", "members", "contents", "roster", "list", "assembly", "senate",
             "name", "names", "counties", "represented", "residence", "residences", "district", "districts",
             "post", "office", "nativity", "occupation"}
_STATKW   = {"section", "chapter", "approved", "whereas", "act", "shall", "enact", "provided", "sec", "title"}

# tunables (env-overridable)
MARK_MIN = int(os.environ.get("ROSTER_MARK_MIN", "2"))    # R1 min distinct header markers in head
ST_M     = float(os.environ.get("ROSTER_ST_M", "0.008"))  # R1 statute-kw ceiling
GF       = float(os.environ.get("ROSTER_GF",  "0.15"))    # R3 garble-frac floor
NF       = float(os.environ.get("ROSTER_NF",  "0.18"))    # R3 name-frac floor
CF       = float(os.environ.get("ROSTER_CF",  "0.012"))   # R3 county-frac floor
ST       = float(os.environ.get("ROSTER_ST",  "0.005"))   # R3 statute-kw ceiling

DEBUG_PAGES = os.environ.get("DEBUG_PAGES", "")
SAMPLE_N    = int(os.environ.get("SAMPLE_N", "0"))

# --- CA county tokens, garble-tolerant signal (distinctive only) ---
def _county_tokens():
    from ocrcorrect.ca_gazetteer import COUNTIES
    stop = {"san", "santa", "los", "del", "contra", "lake", "orange", "luis", "new", "el"}
    out = set()
    for name in COUNTIES:
        for part in name.lower().split():
            if len(part) >= 4 and part.isalpha() and part not in stop:
                out.add(part)
    return frozenset(out)

_WS=None;_HASWF=False;_WF=None;_ZIPF=None;_SORTED=None;_SORTED_REV=None;_SYM=None;_GAZ=None;_COUNTY=None
def _init():
    global _WS,_HASWF,_WF,_ZIPF,_SORTED,_SORTED_REV,_SYM,_GAZ,_COUNTY
    from ocrcorrect.dictionary import build_dictionary, build_sorted_common
    from ocrcorrect.symspell_e2 import SymSpellE2, load_target_freq
    from wordfreq import zipf_frequency
    ws,_s,has,wf = build_dictionary()
    _WS=frozenset(ws);_HASWF=has;_WF=wf;_ZIPF=zipf_frequency
    _SORTED,_SORTED_REV = build_sorted_common(_WS,_ZIPF)
    _SYM = SymSpellE2(load_target_freq(CORPUS_FREQ)) if os.path.exists(CORPUS_FREQ) else None
    _COUNTY = _county_tokens()
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

def _page_signals(lines):
    flat = [t for toks in lines for t in toks]
    n = len(flat)
    if n == 0:
        return None
    nonempty = [toks for toks in lines if toks]
    nl = len(nonempty) or 1
    short = sum(1 for toks in nonempty if 2 <= len(toks) <= 6)
    # TOC column-header "TITLE OF ACT" surviving in the head (page numbers are stripped from the
    # token stream, so this header is the only reliable table-of-acts/contents signal). Guarded by a
    # minimum count of "an act" entries so a lone prose mention doesn't trigger.
    h = flat[:20]
    an_act = sum(1 for i in range(len(flat)-1) if flat[i] == "an" and flat[i+1] == "act")
    toc_header = an_act >= 5 and any(
        h[i] == "title" and ("act" in h[i+1:i+3] or "acts" in h[i+1:i+3])
        for i in range(len(h)-1)
    )
    return {
        "n": n,
        "toc_header": toc_header,
        "head": set(flat[:40]),
        "name_frac": (sum(1 for t in flat if t in _GAZ) / n) if _GAZ else 0.0,
        "county_frac": sum(1 for t in flat if t in _COUNTY) / n,
        "stat_frac": sum(1 for t in flat if t in _STATKW) / n,
        "num_frac": sum(1 for t in flat if _NUMERIC.match(t)) / n,
        "short_line_ratio": short / nl,
        "flat": flat,
    }

def _classify(s, garble_frac):
    """return (is_index, rule) where rule names the trigger ('-' if body)."""
    if len(s["head"] & _MARKERS) >= MARK_MIN and s["stat_frac"] < ST_M:
        return True, "R1_marker"
    if s["name_frac"] > 0.35 and s["stat_frac"] < 0.003:
        return True, "R2_gazname"
    if (garble_frac >= GF and s["name_frac"] >= NF and s["county_frac"] >= CF
            and s["stat_frac"] < ST):
        return True, "R3_fingerprint"
    # R4 TABLE-OF-ACTS / CONTENTS: page numbers are stripped from the token stream, so the only
    # surviving TOC signal is the column header "TITLE OF ACT" (+ chap/page) in the head. NOTE: this
    # cannot catch a TOC/index whose header was itself garbled (e.g. a code index OCR'd to noise).
    if s["toc_header"]:
        return True, "R4_toc_header"
    return False, "-"

def _page_garble(flat):
    g = 0
    for t in flat:
        if len(t) < 4 or known(t) or _ROMAN.match(t) or _garbage_shaped(t):
            continue
        if _affix(t, _SORTED, _SORTED_REV):
            continue
        if _has_candidate(t):
            continue
        if t in _GAZ:
            continue
        g += 1
    return g

def _analyze(fp):
    vol = os.path.basename(fp)[:-5] if fp.endswith(".json") else os.path.basename(fp)
    rows = []          # (pk, rule, garble, signals) for flagged + body-with-garble
    real = 0; idx_pages = 0; garble_idx = 0; garble_body = 0
    try:
        d = json.load(open(fp, encoding="utf-8", errors="replace"))
    except Exception:
        return vol, real, idx_pages, garble_idx, garble_body, rows
    for pk, lines in d.items():
        s = _page_signals(lines)
        if s is None:
            continue
        g = _page_garble(s["flat"])
        is_index, rule = _classify(s, g / s["n"])
        if is_index:
            idx_pages += 1; garble_idx += g
        else:
            garble_body += g; real += g
        if is_index or g >= 40:    # keep flagged pages + heavy-garble body pages for the spot sample
            rows.append((pk, rule, g, round(s["short_line_ratio"],3),
                         round(s["county_frac"],4), round(s["stat_frac"],4),
                         round(s["name_frac"],4), round(s["num_frac"],4)))
    return vol, real, idx_pages, garble_idx, garble_body, rows

def _debug():
    want = {}
    for spec in DEBUG_PAGES.split(","):
        v, pk = spec.rsplit(":", 1); want.setdefault(v.strip(), set()).add(pk.strip())
    _init()
    print(f"county tokens: {len(_COUNTY)} (sample: {sorted(list(_COUNTY))[:12]})")
    for v, pks in want.items():
        fp = os.path.join(STAGE_OUT, v + ".json")
        d = json.load(open(fp, encoding="utf-8", errors="replace"))
        for pk in pks:
            if pk not in d:
                print(f"\n{v} pk={pk}  (not a page key in this volume -- skipped)"); continue
            s = _page_signals(d[pk])
            g = _page_garble(s["flat"])
            is_index, rule = _classify(s, g / s["n"])
            print(f"\n{v} pk={pk}  n={s['n']} garble={g} garble_frac={g/s['n']:.3f}  "
                  f"-> {'INDEX/ROSTER' if is_index else 'BODY'} ({rule})")
            print(f"   markers={sorted(s['head'] & _MARKERS)}  short_line_ratio={s['short_line_ratio']:.3f}  "
                  f"county_frac={s['county_frac']:.4f}  stat_frac={s['stat_frac']:.4f}  name_frac={s['name_frac']:.4f}")
            # --- TOC/index probe signals ---
            flat = s["flat"]; n = s["n"]
            act_frac  = sum(1 for t in flat if t in ("act","acts")) / n
            num_frac  = s["num_frac"]
            toc_words = sum(1 for t in flat if t in ("page","pages","pago","chap","chapter","contents","index","table","title"))/n
            # "an act" bigram count (TOC entries each start "An Act ...")
            an_act = sum(1 for i in range(n-1) if flat[i]=="an" and flat[i+1]=="act")
            lines = d[pk]; nl = sum(1 for ln in lines if ln) or 1
            tail_num = sum(1 for ln in lines if ln and _NUMERIC.match(ln[-1])) / nl
            print(f"   act_frac={act_frac:.4f}  an_act={an_act}  num_frac={num_frac:.4f}  "
                  f"toc_words={toc_words:.4f}  tail_num_line_frac={tail_num:.3f}")
            print(f"   head: {' '.join(flat[:24])}")

def main():
    if DEBUG_PAGES:
        _debug(); return
    files = sorted(glob.glob(os.path.join(STAGE_OUT, "*.json")))
    nw = max(2, min(8, (os.cpu_count() or 4) - 2))
    print(f"roster-detect over {len(files)} volumes, {nw} workers "
          f"(MARK_MIN={MARK_MIN} ST_M={ST_M} GF={GF} NF={NF} CF={CF} ST={ST})...", flush=True)
    t0 = time.time()
    G_real=0; G_idx=0; G_gidx=0; G_gbody=0; vol_real={}; all_rows=[]
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw, initializer=_init) as pool:
        for vol, real, idx_pages, garble_idx, garble_body, rows in pool.imap_unordered(_analyze, files, chunksize=1):
            G_real+=real; G_idx+=idx_pages; G_gidx+=garble_idx; G_gbody+=garble_body
            vol_real[vol]=real
            for r in rows:
                all_rows.append((vol,)+r)

    print(f"\n[{time.time()-t0:.0f}s] garble-tolerant roster detection:")
    print(f"  INDEX/ROSTER pages flagged:                 {G_idx:,}")
    print(f"  garble on index/roster pages (excluded):    {G_gidx:,}")
    print(f"  => REAL re-OCR target (garble on body):     {G_gbody:,}")
    print(f"  (v1 detector was: 8,200 pages / 18,738 excluded / 127,899 target)")

    flagged = [r for r in all_rows if r[2] != "-"]
    with open(OUT_ROST, "w", encoding="utf-8") as f:
        f.write("vol\tpk\trule\tgarble\tshort_line_ratio\tcounty_frac\tstat_frac\tname_frac\tnum_frac\n")
        for r in sorted(flagged, key=lambda r: -r[3]):
            f.write("\t".join(str(x) for x in r) + "\n")
    by_rule = Counter(r[2] for r in flagged)
    garble_by_rule = Counter()
    for r in flagged:
        garble_by_rule[r[2]] += r[3]
    print("\n  flagged-by-rule (pages):  ", dict(by_rule))
    print("  garble-excluded-by-rule:  ", dict(garble_by_rule),
          "  <- R2 ~0 garble => count-irrelevant; R1/R3/R4 carry the real exclusions")

    rows = sorted(vol_real.items(), key=lambda kv: -kv[1])
    with open(OUT_VOL, "w", encoding="utf-8") as f:
        f.write("vol\treal_garble\n")
        for vol, n in rows:
            f.write(f"{vol}\t{n}\n")
    print("\n=== TOP 12 VOLUMES by REAL garble (v2, garble-tolerant index excluded) ===")
    for vol, n in rows[:12]:
        print(f"  {vol:<34}{n:>8,}")

    # spot sample: 3 random flagged + 2 high-garble body, restricted to pre-1914 _Statutes (clean PDF/pk map)
    if SAMPLE_N:
        def early_stat(vol):
            m = re.match(r"production-(18\d\d|190\d|191[0-3])", vol)
            return m is not None and "code" not in vol and "vol" not in vol
        rnd = random.Random(20260613)
        flagged_e = [r for r in flagged if early_stat(r[0])]
        body_e    = [r for r in all_rows if r[2] == "-" and early_stat(r[0])]
        pick = rnd.sample(flagged_e, min(3, len(flagged_e))) + rnd.sample(body_e, min(2, len(body_e)))
        with open(OUT_SAMP, "w", encoding="utf-8") as f:
            f.write("vol\tpk\tdetector\trule\tgarble\tshort_line_ratio\tcounty_frac\tstat_frac\tfirst24tokens\n")
            for r in pick:
                vol, pk, rule = r[0], r[1], r[2]
                det = "INDEX/ROSTER" if rule != "-" else "BODY"
                fp = os.path.join(STAGE_OUT, vol + ".json")
                d = json.load(open(fp, encoding="utf-8", errors="replace"))
                flat = [t for toks in d[pk] for t in toks]
                f.write(f"{vol}\t{pk}\t{det}\t{rule}\t{r[3]}\t{r[4]}\t{r[5]}\t{r[6]}\t{' '.join(flat[:24])}\n")
        print(f"\nspot sample ({len(pick)} pages, pre-1914 _Statutes) -> {OUT_SAMP}")
        for r in pick:
            print(f"  {r[0]} pk={r[1]}  {'INDEX/ROSTER' if r[2]!='-' else 'BODY'} ({r[2]})  garble={r[3]}")

if __name__ == "__main__":
    main()
