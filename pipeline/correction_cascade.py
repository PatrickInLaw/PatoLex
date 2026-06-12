"""
correction_cascade.py -- run the OCR text-correction passes as an ORDERED CASCADE, each stage on
the PREVIOUS stage's PERSISTED output. Produces a defensible per-stage flagged-rate progression
and a fully re-runnable, auditable pipeline (sequence is the architecture -- see
docs/30_SYSTEM_DESIGN/CORRECTION_AND_DISPLAY_LAYER.md).

ORDER (per volume):
  reunify    rejoin OCR-split fragments (same-line multi-fragment + line-break + cross-page)
  split      guarded 2-piece over-merge (BEFORE autocorrect); skip typos [edit-1 of a word] and
             fragments [affix of a word]
  autocorrect edit-1 typo -> dominant COMMON word (zipf-ranked, tightened). GUARDED: skip Roman
             numerals and affix-of-a-real-word tokens (orphaned fragments)
  (sonnet)   applied LATER, once the deterministic cascade is tuned (APPLY_SONNET / separate)

PER-STAGE PERSISTENCE + RESUME (Patrick): each stage reads the prior stage's saved output, writes
its OWN output text + per-stage audit + per-stage flagged measurement + a done marker. Set
CASCADE_FROM={reunify|split|autocorrect} to re-run from a stage (reading the prior stage's cached
output) -- so tuning one stage does NOT re-run the earlier ones.

PRINCIPLES: immutable source never touched (reads ocr_consensus, writes only _cascade/); per-stage
DONE markers + counts for AUDIT and RESUME; heartbeated run log; per-stage audit TSV. Parallel.

_cascade/
  out_reunify/{vol}.json  out_split/{vol}.json  out_autocorrect/{vol}.json   (token stream per page)
  audit/{vol}.{stage}.tsv      per-stage changes (page, before, after)
  counts/{vol}.json            per-stage flagged/total + correction counts
  done_{stage}/{vol}.marker
  cascade-run.log  cascade_report.json
"""
import os, sys, re, json, glob, time, bisect
from collections import Counter
from datetime import datetime, timezone, timedelta
import multiprocessing as mp

os.environ["CUDA_VISIBLE_DEVICES"] = ""
SCRATCH = r"C:\Users\patolex\PatoLex-scratch"
VOCAB   = os.path.join(SCRATCH, "_vocab")
CASCADE = os.path.join(SCRATCH, "_cascade")
STAGES  = ["reunify", "split", "autocorrect"]
CASCADE_FROM = os.environ.get("CASCADE_FROM", "reunify")
for sub in ["audit", "counts"] + ["out_" + s for s in STAGES] + ["done_" + s for s in STAGES]:
    os.makedirs(os.path.join(CASCADE, sub), exist_ok=True)
LOG = os.path.join(CASCADE, "cascade-run.log")

WORD = re.compile(r"[A-Za-z\xc0-\xff]+")
HEAD_HYPHEN = re.compile(r"([A-Za-z\xc0-\xff]{2,})-[ \t\r]*$")
ALPHA = "abcdefghijklmnopqrstuvwxyz"
LOOKAHEAD = 6
MAXFRAG = 4
_DIGITS = re.compile(r"(\d+)")

def pt():
    try:
        z = timezone(timedelta(hours=-7))
        return datetime.now(timezone.utc).astimezone(z).strftime("%Y-%m-%d %H:%M PT")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M")
def rlog(phase, desc, status="OK"):
    line = f"[{pt()}] {phase} | {desc} | {status}\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line); f.flush()
    print(line.rstrip()); sys.stdout.flush()

# ---- worker dict / helpers ----
_WS = None; _HASWF = False; _WF = None; _ZIPF = None; _SORTED = None; _SORTED_REV = None
_C_BC = {}; _C_E1 = {}; _C_AFF = {}; _C_SPLIT = {}
def _init():
    global _WS, _HASWF, _WF, _ZIPF, _SORTED, _SORTED_REV
    from correction_passes import build_dictionary
    ws, _spell, has_wf, wf = build_dictionary()
    _WS = frozenset(ws); _HASWF = has_wf; _WF = wf
    from wordfreq import zipf_frequency
    _ZIPF = zipf_frequency
    common = [w for w in _WS if w.isalpha() and len(w) >= 6 and _ZIPF(w, "en") >= 3.0]
    _SORTED = sorted(common); _SORTED_REV = sorted(w[::-1] for w in common)

def known(t): return (t in _WS) or (_HASWF and _WF(t, "en") > 0)
def zipf(t): return _ZIPF(t, "en")
def strong_known(t): return (t in _WS) or zipf(t) >= 2.8
_ROMAN = re.compile(r"^[ivxlcdm]+$")
def is_roman(t): return bool(_ROMAN.match(t)) and len(t) >= 2

def _edits1(w):
    sp = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    out = set()
    for a, b in sp:
        if b: out.add(a + b[1:])
        if len(b) > 1: out.add(a + b[1] + b[0] + b[2:])
        for c in ALPHA:
            if b: out.add(a + c + b[1:])
            out.add(a + c + b)
    out.discard(w); return out
def _edit1_known(w):
    v = _C_E1.get(w)
    if v is None:
        v = any(known(c) for c in _edits1(w)); _C_E1[w] = v
    return v
def _affix_of_common(s):
    v = _C_AFF.get(s)
    if v is None:
        i = bisect.bisect_left(_SORTED, s)
        v = (i < len(_SORTED) and _SORTED[i].startswith(s) and len(_SORTED[i]) >= len(s) + 2)
        if not v:
            r = s[::-1]; j = bisect.bisect_left(_SORTED_REV, r)
            v = j < len(_SORTED_REV) and _SORTED_REV[j].startswith(r) and len(_SORTED_REV[j]) >= len(s) + 2
        _C_AFF[s] = v
    return v
def _best_correction(tok):
    if tok in _C_BC: return _C_BC[tok]
    res = None
    e1 = [c for c in _edits1(tok) if known(c)]
    if e1:
        sc = sorted(((c, zipf(c)) for c in e1), key=lambda x: -x[1])
        tz = sc[0][1]; mg = tz - (sc[1][1] if len(sc) > 1 else 0.0)
        res = (sc[0][0], 1) if (tz >= 3.3 and mg >= 0.5) else None
    _C_BC[tok] = res
    return res
def _split(tok):
    if tok in _C_SPLIT: return _C_SPLIT[tok]
    n = len(tok); best = None
    for i in range(4, n - 3):
        a, b = tok[:i], tok[i:]
        if zipf(a) >= 3.2 and zipf(b) >= 3.2:
            mz = min(zipf(a), zipf(b))
            if best is None or mz > best[0]: best = (mz, a + " " + b)
    res = best[1] if best else None
    _C_SPLIT[tok] = res
    return res

def _measure(vol_pages):
    f = t = 0
    for pk, lines in vol_pages:
        for ln in lines:
            for tok in ln[0]:
                if len(tok) >= 2:
                    t += 1
                    if not known(tok): f += 1
    return f, t

def _pk_key(k):
    m = _DIGITS.search(str(k)); return (int(m.group(1)) if m else 0, str(k))

# ---- I/O of the per-volume structured token stream: vol_pages = [(pk, [[toks, hyphen|None], ...])] ----
def _load_raw(path):
    data = json.load(open(path, encoding="utf-8", errors="replace"))
    vol_pages = []
    for pk in sorted(data.keys(), key=_pk_key):
        txt = data[pk].get("consensus_text") or ""
        lines = []
        for ln in txt.split("\n"):
            toks = [t.lower() for t in WORD.findall(ln)]
            if not toks: continue
            m = HEAD_HYPHEN.search(ln)
            lines.append([toks, (m.group(1).lower() if m else None)])
        vol_pages.append((pk, lines))
    return vol_pages
def _load_stage(stage, vol):
    d = json.load(open(os.path.join(CASCADE, "out_" + stage, vol + ".json"), encoding="utf-8"))
    return [(pk, [[list(toks), None] for toks in d[pk]]) for pk in sorted(d.keys(), key=_pk_key)]
def _persist(stage, vol, vol_pages):
    out = {pk: [ln[0] for ln in lines] for pk, lines in vol_pages}
    json.dump(out, open(os.path.join(CASCADE, "out_" + stage, vol + ".json"), "w", encoding="utf-8"))

# ---- STAGE TRANSFORMS (mutate vol_pages in place; append audit rows; bump cnt) ----
def stage_reunify(vol_pages, audit, cnt):
    for pk, lines in vol_pages:           # A1 same-line multi-fragment (greedy longest-first)
        for li in range(len(lines)):
            low = lines[li][0]; i = 0; out = []
            while i < len(low):
                if i == len(low) - 1: out.append(low[i]); i += 1; continue
                emitted = False
                for L in range(min(MAXFRAG, len(low) - i), 1, -1):
                    run = low[i:i + L]
                    if any(len(c) < 2 for c in run): continue
                    j = "".join(run)
                    if len(j) < 5 or all(known(c) for c in run): continue
                    if any((not known(c)) and len(c) < 3 for c in run): continue
                    if strong_known(j):
                        out.append(j); audit.append((pk, "reunify_space", " ".join(run), j)); cnt["reunify_space"] += 1
                        i += L; emitted = True; break
                if not emitted: out.append(low[i]); i += 1
            lines[li][0] = out
    for pk, lines in vol_pages:           # A2 line-break within page
        li = 0
        while li < len(lines) - 1:
            toks = lines[li][0]; hh = lines[li][1]
            if not toks: li += 1; continue
            head = hh if hh else (toks[-1] if (not known(toks[-1]) and len(toks[-1]) >= 3) else None)
            if head is None: li += 1; continue
            for k in range(1, min(LOOKAHEAD + 1, len(lines) - li)):
                nt = lines[li + k][0]
                if not nt: continue
                tail = nt[0]; j = head + tail
                if known(j) and not (known(head) and known(tail)):
                    lines[li][0][-1] = j; lines[li + k][0] = nt[1:]
                    audit.append((pk, "reunify_break", head + "|" + tail, j)); cnt["reunify_break"] += 1
                    break
            li += 1
    for pidx in range(len(vol_pages) - 1):  # A3 cross-page
        pk, lines = vol_pages[pidx]
        if not lines or not lines[-1][0]: continue
        last = lines[-1][0][-1]
        if known(last) or len(last) < 3: continue
        for j2 in range(pidx + 1, min(pidx + 1 + LOOKAHEAD, len(vol_pages))):
            nlines = vol_pages[j2][1]
            if nlines and nlines[0][0]:
                tail = nlines[0][0][0]; j = last + tail
                if known(j) and not (known(last) and known(tail)):
                    lines[-1][0][-1] = j; nlines[0][0] = nlines[0][0][1:]
                    audit.append((pk, "reunify_xpage", last + "|" + tail, j)); cnt["reunify_xpage"] += 1
                break

def stage_split(vol_pages, audit, cnt):
    for pk, lines in vol_pages:
        for ln in lines:
            newtoks = []
            for t in ln[0]:
                if len(t) >= 8 and not known(t) and not _edit1_known(t) and not _affix_of_common(t):
                    s = _split(t)
                    if s:
                        newtoks.extend(s.split(" ")); audit.append((pk, "split", t, s)); cnt["split"] += 1; continue
                newtoks.append(t)
            ln[0] = newtoks

def stage_autocorrect(vol_pages, audit, cnt):
    for pk, lines in vol_pages:
        for ln in lines:
            toks = ln[0]
            for ti in range(len(toks)):
                t = toks[ti]
                if len(t) < 3 or known(t) or is_roman(t) or _affix_of_common(t): continue
                r = _best_correction(t)
                if r:
                    toks[ti] = r[0]; audit.append((pk, f"autocorrect_e{r[1]}", t, r[0])); cnt[f"autocorrect_e{r[1]}"] += 1

_TRANSFORM = {"reunify": stage_reunify, "split": stage_split, "autocorrect": stage_autocorrect}
_STAGE_KEYS = {"reunify": ("reunify_space", "reunify_break", "reunify_xpage"),
               "split": ("split",), "autocorrect": ("autocorrect_e1", "autocorrect_e2")}

def _process_volume(arg):
    path, from_stage = arg
    vol = os.path.basename(os.path.dirname(os.path.dirname(path)))
    cfp = os.path.join(CASCADE, "counts", vol + ".json")
    prior = json.load(open(cfp, encoding="utf-8")) if os.path.exists(cfp) else {}
    meas = dict(prior.get("meas", {}))          # {"raw":[f,t], "reunify":[f,t], "split":[f,t], "autocorrect":[f,t]}
    stage_cnt = Counter(prior.get("stages", {}))

    timings = dict(prior.get("timings", {}))    # per-stage wall seconds for THIS volume
    start = STAGES.index(from_stage)
    t_load = time.time()
    # load the input to the first stage we run; fall back to full run if the prior output is missing
    if start > 0 and os.path.exists(os.path.join(CASCADE, "out_" + STAGES[start - 1], vol + ".json")):
        vol_pages = _load_stage(STAGES[start - 1], vol)
    else:
        start = 0
        vol_pages = _load_raw(path)
        f, t = _measure(vol_pages); meas["raw"] = [f, t]
    timings["load"] = round(time.time() - t_load, 3)

    for idx in range(start, len(STAGES)):
        st = STAGES[idx]
        audit = []; cnt = Counter()
        ts = time.time()
        _TRANSFORM[st](vol_pages, audit, cnt)
        f, t = _measure(vol_pages)
        timings[st] = round(time.time() - ts, 3)
        for k in _STAGE_KEYS[st]: stage_cnt[k] = cnt.get(k, 0)   # idempotent replace on re-run
        meas[st] = [f, t]
        _persist(st, vol, vol_pages)
        with open(os.path.join(CASCADE, "audit", f"{vol}.{st}.tsv"), "w", encoding="utf-8") as fh:
            fh.write("page\tkind\tbefore\tafter\n")
            for r in audit: fh.write("\t".join(str(x) for x in r) + "\n")
        open(os.path.join(CASCADE, "done_" + st, vol + ".marker"), "w").write(pt())

    res = {"vol": vol, "meas": meas, "stages": dict(stage_cnt), "timings": timings}
    json.dump(res, open(cfp, "w", encoding="utf-8"))
    return res

def main():
    rlog("START", f"cascade from '{CASCADE_FROM}' (reunify -> split -> autocorrect; sonnet held out)")
    files = sorted(glob.glob(os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json")))
    rlog("SCAN", f"{len(files)} volumes")
    nw = max(2, min(12, (os.cpu_count() or 4) - 2))
    keys = ["raw", "reunify", "split", "autocorrect"]
    F = {k: 0 for k in keys}; T = {k: 0 for k in keys}; agg = Counter(); tim = Counter(); done = 0
    t0 = time.time(); last = time.time()
    ctx = mp.get_context("spawn")
    args = [(p, CASCADE_FROM) for p in files]
    with ctx.Pool(nw, initializer=_init) as pool:
        for res in pool.imap_unordered(_process_volume, args, chunksize=1):
            done += 1
            if res:
                for k in keys:
                    if k in res["meas"]:
                        F[k] += res["meas"][k][0]; T[k] += res["meas"][k][1]
                for k, v in res["stages"].items(): agg[k] += v
                for k, v in res.get("timings", {}).items(): tim[k] += v
            now = time.time()
            if now - last >= 15 or done == len(files):
                rr = 100.0 * F["raw"] / max(1, T["raw"]); ar = 100.0 * F["autocorrect"] / max(1, T["autocorrect"])
                tstr = " ".join(f"{s}={tim[s]:.0f}s" for s in STAGES if tim[s])
                rlog("CASCADE", f"{done}/{len(files)} vols | raw {rr:.3f}% -> pre-sonnet {ar:.3f}% | stage-cpu[{tstr}] | wall={now-t0:.0f}s", "HEARTBEAT")
                last = now
    def rate(k): return round(100.0 * F[k] / max(1, T[k]), 4)
    prog = {("raw" if k == "raw" else "after_" + k): {"flagged": F[k], "total": T[k], "rate_pct": rate(k)} for k in keys}
    report = {"generated": pt(), "from_stage": CASCADE_FROM, "volumes": done, "sonnet_applied": False,
              "stage_progression": prog,
              "pre_sonnet_rate_pct": rate("autocorrect"),
              "reduction_pct_relative": round(100.0 * (F["raw"] - F["autocorrect"]) / max(1, F["raw"]), 1),
              "stage_corrections": dict(agg),
              "stage_cpu_seconds": {k: round(v, 1) for k, v in tim.items()},
              "wall_seconds": round(time.time() - t0, 1)}
    json.dump(report, open(os.path.join(CASCADE, "cascade_report.json"), "w", encoding="utf-8"), indent=2)
    rlog("==== STAGE PROGRESSION (flagged rate + cpu time per stage) ====", "")
    for k in keys:
        lab = "raw" if k == "raw" else "after_" + k
        ts = f"  [{tim[k]:.0f}s cpu]" if k in tim else ""
        rlog("RATE", f"{lab:18s} = {F[k]:,}/{T[k]:,} = {rate(k)}%{ts}")
    rlog("RATE", f"total reduction = {report['reduction_pct_relative']}% relative  (pre-sonnet)")
    rlog("TIMING", f"stage cpu-seconds: {dict(report['stage_cpu_seconds'])}  | wall={report['wall_seconds']}s")
    rlog("STAGES", json.dumps(dict(agg)))
    rlog("DONE", f"-> {os.path.join(CASCADE, 'cascade_report.json')}")

if __name__ == "__main__":
    main()
