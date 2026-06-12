"""
compare_adjudications.py -- compare the LOCAL (gemma3:27b) vs SONNET adjudication
of the Pass C review tier (2,655 tokens). Verdict scheme: FIX/NAME/GARBAGE/KEEP.

Reads (all under docs/80_PROJECT_HISTORY/run-logs/):
  review_local_gemma3.json        {token: {freq,candidates,verdict,value}}
  review_sonnet_part1..5.json     {token: {verdict,value}}
Writes a console report + review_comparison.tsv (per-token side-by-side).
"""
import os, json, glob

RUNLOGS = os.path.join(os.path.dirname(__file__), "..", "docs", "80_PROJECT_HISTORY", "run-logs")
RUNLOGS = os.path.abspath(RUNLOGS)
CATS = ["FIX", "NAME", "GARBAGE", "KEEP"]

def norm(v):
    return (v or "").strip().lower()

def load_local():
    with open(os.path.join(RUNLOGS, "review_local_gemma3.json"), encoding="utf-8") as f:
        return json.load(f)

def load_sonnet():
    merged = {}
    for p in sorted(glob.glob(os.path.join(RUNLOGS, "review_sonnet_part*.json"))):
        with open(p, encoding="utf-8") as f:
            merged.update(json.load(f))
    return merged

def main():
    local = load_local()
    sonnet = load_sonnet()
    toks = [t for t in local if t in sonnet]
    print(f"local={len(local)} sonnet={len(sonnet)} common={len(toks)}")

    def tally(d, keys):
        out = {c: 0 for c in CATS}; other = 0
        for t in keys:
            v = (d[t].get("verdict") or "").upper()
            if v in out: out[v] += 1
            else: other += 1
        return out, other
    lt, lo = tally(local, toks)
    st, so = tally(sonnet, toks)
    print("\nVERDICT TALLY (common tokens):")
    print(f"  {'cat':9} {'local':>7} {'sonnet':>7}")
    for c in CATS:
        print(f"  {c:9} {lt[c]:>7} {st[c]:>7}")
    print(f"  {'other/ERR':9} {lo:>7} {so:>7}")

    # verdict agreement
    same = sum(1 for t in toks if (local[t].get('verdict') or '').upper() == (sonnet[t].get('verdict') or '').upper())
    print(f"\nVERDICT AGREEMENT: {same}/{len(toks)} = {100.0*same/max(len(toks),1):.1f}%")

    # cross-tab
    print("\nCROSS-TAB (rows=local, cols=sonnet):")
    print("           " + "".join(f"{c[:4]:>8}" for c in CATS))
    for lc in CATS:
        row = []
        for sc in CATS:
            n = sum(1 for t in toks
                    if (local[t].get('verdict') or '').upper() == lc
                    and (sonnet[t].get('verdict') or '').upper() == sc)
            row.append(n)
        print(f"  {lc:9}" + "".join(f"{n:>8}" for n in row))

    # FIX value agreement (both FIX)
    both_fix = [t for t in toks if (local[t].get('verdict') or '').upper()=="FIX"
                and (sonnet[t].get('verdict') or '').upper()=="FIX"]
    fix_same = sum(1 for t in both_fix if norm(local[t].get('value')) == norm(sonnet[t].get('value')))
    print(f"\nBOTH 'FIX': {len(both_fix)} | same correction: {fix_same} ({100.0*fix_same/max(len(both_fix),1):.1f}%)")

    # write side-by-side TSV
    out = os.path.join(RUNLOGS, "review_comparison.tsv")
    with open(out, "w", encoding="utf-8") as f:
        f.write("token\tfreq\tcandidates\tlocal_verdict\tlocal_value\tsonnet_verdict\tsonnet_value\tagree\n")
        for t in sorted(toks, key=lambda x: -local[x].get("freq", 0)):
            lv = (local[t].get('verdict') or '').upper(); sv = (sonnet[t].get('verdict') or '').upper()
            agree = "Y" if lv == sv else "N"
            cands = ",".join(local[t].get("candidates", []))
            f.write(f"{t}\t{local[t].get('freq',0)}\t{cands}\t{lv}\t{local[t].get('value','')}\t{sv}\t{sonnet[t].get('value','')}\t{agree}\n")
    print(f"\nside-by-side -> {out}")

    # sample disagreements (high freq)
    disagree = [t for t in toks if (local[t].get('verdict') or '').upper() != (sonnet[t].get('verdict') or '').upper()]
    disagree.sort(key=lambda x: -local[x].get("freq", 0))
    print(f"\nTOP 30 VERDICT DISAGREEMENTS (by freq):")
    print(f"  {'token':16}{'freq':>7}  {'local':24}{'sonnet':24}")
    for t in disagree[:30]:
        lstr = f"{(local[t].get('verdict') or '')}:{local[t].get('value','')}"
        sstr = f"{(sonnet[t].get('verdict') or '')}:{sonnet[t].get('value','')}"
        print(f"  {t:16}{local[t].get('freq',0):>7}  {lstr:24}{sstr:24}")

if __name__ == "__main__":
    main()
