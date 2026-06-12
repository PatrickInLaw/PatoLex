"""
autocorrect_pass.py -- spell-correction overlay for the residual unknown tokens (the typo bulk,
incl. the singletons the freq>=2 passes skipped). Reversible overlay; nothing destructively edited.

Method (Patrick's idea + the guard that avoids the frequent-corpus-error trap):
  - For each residual token that is NOT a known word, generate edit-1 then edit-2 candidates that
    ARE known words (dict now includes validated corpus vocab).
  - Rank candidates by GENERAL-ENGLISH commonness (wordfreq zipf). This is the key guard: a
    frequent CORPUS error like "cither" has LOW general zipf, so a genuinely common word
    ("either") always outranks it -> we never "correct" one OCR error into another.
  - Accept only a DOMINANT common candidate; tier by edit distance:
      AUTO_E1  edit-1, top zipf >= 3.0, margin over 2nd >= 0.4   (high precision -> auto-apply)
      AUTO_E2  edit-2, top zipf >= 3.6, margin >= 0.7            (stricter -> auto-apply)
      FLAG     a candidate exists but not dominant/common enough  (-> LLM/human review, not applied)
      NONE     no edit<=2 candidate (deep garbage / over-merge / fragment -> other passes)
Runs on the 5090 (dict + wordfreq). Operates on residual_triage types (token, freq).

Output: _vocab/autocorrect_corrections.tsv  (token, freq, correction, edit, tier, top_zipf, margin)
"""
import os, sys, re, time
from collections import Counter
import multiprocessing as mp

VOCAB = r"C:\Users\patolex\PatoLex-scratch\_vocab"
RESID = os.path.join(VOCAB, "residual_triage.tsv")
OUT   = os.path.join(VOCAB, "autocorrect_corrections.tsv")
LOG   = os.path.join(VOCAB, "autocorrect-run.log")
ALPHA = "abcdefghijklmnopqrstuvwxyz"

def rlog(msg, status="OK"):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{msg} | {status}\n")
    print(msg, flush=True)

_WS = None; _HASWF = False; _WF = None; _ZIPF = None
def _init():
    global _WS, _HASWF, _WF, _ZIPF
    from correction_passes import build_dictionary
    ws, _spell, has_wf, wf = build_dictionary()
    _WS = frozenset(ws); _HASWF = has_wf; _WF = wf
    from wordfreq import zipf_frequency
    _ZIPF = zipf_frequency

def _known(t):
    return (t in _WS) or (_HASWF and _WF(t, "en") > 0)
def _zipf(t):
    return _ZIPF(t, "en")

def _edits1(w):
    sp = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    out = set()
    for a, b in sp:
        if b: out.add(a + b[1:])
        if len(b) > 1: out.add(a + b[1] + b[0] + b[2:])
        for c in ALPHA:
            if b: out.add(a + c + b[1:])
            out.add(a + c + b)
    out.discard(w)
    return out

def _best(cands):
    """rank known candidates by general-English zipf; return (top, top_zipf, margin)."""
    scored = sorted(((c, _zipf(c)) for c in cands), key=lambda x: -x[1])
    if not scored:
        return None
    top, tz = scored[0]
    second = scored[1][1] if len(scored) > 1 else 0.0
    return top, tz, tz - second

def _classify(tok):
    if _known(tok) or len(tok) < 3:
        return None
    e1 = [c for c in _edits1(tok) if _known(c)]
    b = _best(e1)
    if b:
        top, tz, margin = b
        if tz >= 3.0 and margin >= 0.4:
            return (top, 1, "AUTO_E1", tz, margin)
        return (top, 1, "FLAG", tz, margin)
    # edit-2 only if no edit-1 candidate; bounded
    if len(tok) <= 16:
        e2 = set()
        for c1 in _edits1(tok):
            for c2 in _edits1(c1):
                if _known(c2):
                    e2.add(c2)
        b = _best(e2)
        if b:
            top, tz, margin = b
            if tz >= 3.6 and margin >= 0.7:
                return (top, 2, "AUTO_E2", tz, margin)
            return (top, 2, "FLAG", tz, margin)
    return None

def _work(batch):
    rows = []; counts = Counter()
    for tok, freq in batch:
        r = _classify(tok)
        if r is None:
            counts["NONE"] += 1
            continue
        top, ed, tier, tz, margin = r
        counts[tier] += 1
        rows.append((tok, freq, top, ed, tier, f"{tz:.2f}", f"{margin:.2f}"))
    return (counts, rows)

def main():
    rlog("START autocorrect_pass")
    toks = []
    for i, ln in enumerate(open(RESID, encoding="utf-8")):
        if i == 0: continue
        p = ln.rstrip("\n").split("\t")
        if len(p) >= 2 and p[0].isalpha():
            try: f = int(p[1])
            except Exception: f = 0
            toks.append((p[0].lower(), f))
    rlog(f"{len(toks):,} residual tokens to classify")
    nw = max(2, min(12, (os.cpu_count() or 4) - 2))
    bs = 2000
    batches = [toks[i:i+bs] for i in range(0, len(toks), bs)]
    totals = Counter(); allrows = []
    t0 = time.time(); last = time.time(); done = 0
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw, initializer=_init) as pool:
        for counts, rows in pool.imap_unordered(_work, batches, chunksize=1):
            totals.update(counts); allrows.extend(rows); done += 1
            if time.time() - last >= 15 or done == len(batches):
                rlog(f"{done}/{len(batches)} batches | rows={len(allrows):,} | {time.time()-t0:.0f}s", "HEARTBEAT")
                last = time.time()
    allrows.sort(key=lambda r: -r[1])
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("token\tfreq\tcorrection\tedit\ttier\ttop_zipf\tmargin\n")
        for r in allrows:
            f.write("\t".join(str(x) for x in r) + "\n")
    auto1 = totals["AUTO_E1"]; auto2 = totals["AUTO_E2"]; flag = totals["FLAG"]; none = totals["NONE"]
    occ = Counter()
    for r in allrows:
        occ[r[4]] += r[1]
    rlog("==== RESULT ====")
    rlog(f"AUTO_E1 = {auto1:,} types / {occ['AUTO_E1']:,} occ")
    rlog(f"AUTO_E2 = {auto2:,} types / {occ['AUTO_E2']:,} occ")
    rlog(f"FLAG    = {flag:,} types / {occ['FLAG']:,} occ  (review/LLM, not auto-applied)")
    rlog(f"NONE    = {none:,} types  (no edit<=2 -> split/garbage/other passes)")
    print("\n[AUTO_E1 sample]")
    for r in [x for x in allrows if x[4] == "AUTO_E1"][:25]:
        print(f"   {r[1]:5d}  {r[0]} -> {r[2]}  (zipf {r[5]}, margin {r[6]})")
    print("\n[AUTO_E2 sample]")
    for r in [x for x in allrows if x[4] == "AUTO_E2"][:15]:
        print(f"   {r[1]:5d}  {r[0]} -> {r[2]}  (zipf {r[5]}, margin {r[6]})")
    rlog(f"DONE -> {OUT}")

if __name__ == "__main__":
    main()
