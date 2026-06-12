"""
correction_cascade.py -- run the OCR text-correction passes as an ORDERED CASCADE, each on the
PREVIOUS pass's output, and measure the flagged-token rate before vs after. This is the pass
that produces a defensible post-correction number (sequence is the architecture -- see
docs/30_SYSTEM_DESIGN/CORRECTION_AND_DISPLAY_LAYER.md).

ORDER (per volume, on the progressively-corrected token stream):
  A. REUNIFY   rejoin OCR-split fragments  (same-line multi-fragment + line-break + cross-page)
  B. AUTOCORRECT  edit-1 then edit-2 typo -> dominant COMMON word (zipf-ranked: avoids correcting
                  one OCR error into another)
  C. SPLIT     guarded 2-piece over-merge (only tokens that survived A+B and are neither a typo
               [edit-1 of a word] nor a fragment [affix of a word])
  D. SONNET    apply the validated freq>=10 adjudication map (token -> fix)
Then count flagged tokens (alpha, len>=2, not is_known) BEFORE (raw) and AFTER (cascaded), same dict.

PRINCIPLES: immutable source never touched (reads ocr_consensus, writes only _cascade/); per-volume
DONE markers + counts for AUDIT and RESUME; run log with heartbeats + stage/volume boundaries;
per-volume audit TSV of every change. Parallel per-volume.

Output dir: _cascade/
  corrected/{vol}.json   final corrected token stream (per page)
  audit/{vol}.tsv        every change: stage, before, after, page
  counts/{vol}.json      per-volume before/after flagged + per-stage counts
  done/{vol}.marker
  cascade-run.log        heartbeated run log
  cascade_report.json    aggregate result
"""
import os, sys, re, json, glob, time, bisect
from collections import Counter
from datetime import datetime, timezone, timedelta
import multiprocessing as mp

os.environ["CUDA_VISIBLE_DEVICES"] = ""
SCRATCH = r"C:\Users\patolex\PatoLex-scratch"
VOCAB   = os.path.join(SCRATCH, "_vocab")
CASCADE = os.path.join(SCRATCH, "_cascade")
for sub in ("corrected", "audit", "counts", "done"):
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

# ---- worker globals ----
_WS = None; _HASWF = False; _WF = None; _ZIPF = None; _SORTED = None; _SORTED_REV = None; _SONNET = {}
def _init():
    global _WS, _HASWF, _WF, _ZIPF, _SORTED, _SORTED_REV, _SONNET
    from correction_passes import build_dictionary
    ws, _spell, has_wf, wf = build_dictionary()
    _WS = frozenset(ws); _HASWF = has_wf; _WF = wf
    from wordfreq import zipf_frequency
    _ZIPF = zipf_frequency
    common = [w for w in _WS if w.isalpha() and len(w) >= 6 and _ZIPF(w, "en") >= 3.0]
    _SORTED = sorted(common); _SORTED_REV = sorted(w[::-1] for w in common)
    # Sonnet freq>=10 adjudication: token -> fix (REAL/NAME with a corrected value)
    import glob as _g
    for p in _g.glob(os.path.join(VOCAB, "review_sonnet_part*.json")):
        try:
            for tok, v in json.load(open(p, encoding="utf-8")).items():
                val = (v.get("value") or "").strip()
                if v.get("verdict") in ("FIX", "NAME") and val and val.lower() != tok.lower():
                    _SONNET[tok.lower()] = val.lower()
        except Exception:
            pass

def known(t): return (t in _WS) or (_HASWF and _WF(t, "en") > 0)
def zipf(t): return _ZIPF(t, "en")
def strong_known(t): return (t in _WS) or zipf(t) >= 2.8

# per-worker memo caches (workers reused across volumes -> compute each token once)
_C_BC = {}; _C_E1 = {}; _C_AFF = {}; _C_SPLIT = {}

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
    """edit-1 -> dominant COMMON word, or None. (correction, edit_distance). Memoized.
    EDIT-1 ONLY in the cascade: edit-2 brute-force is intractable corpus-wide; it is a deferred
    follow-up (needs a SymSpell deletion index). edit-1 is the high-precision bulk anyway."""
    if tok in _C_BC: return _C_BC[tok]
    res = None
    e1 = [c for c in _edits1(tok) if known(c)]
    if e1:
        sc = sorted(((c, zipf(c)) for c in e1), key=lambda x: -x[1])
        tz = sc[0][1]; mg = tz - (sc[1][1] if len(sc) > 1 else 0.0)
        res = (sc[0][0], 1) if (tz >= 3.0 and mg >= 0.4) else None
    _C_BC[tok] = res
    return res

def _split(tok):
    """guarded 2-piece over-merge (both halves >=4 & common). Memoized. caller ensures not typo/fragment."""
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

def _flagged(tokens):
    """count (flagged, total) content tokens: alpha len>=2; flagged = not known."""
    f = t = 0
    for tok in tokens:
        if len(tok) >= 2:
            t += 1
            if not known(tok): f += 1
    return f, t

def _process_volume(path):
    vol = os.path.basename(os.path.dirname(os.path.dirname(path)))
    done_marker = os.path.join(CASCADE, "done", vol + ".marker")
    if os.path.exists(done_marker):
        try:
            return json.load(open(os.path.join(CASCADE, "counts", vol + ".json"), encoding="utf-8"))
        except Exception:
            pass  # re-run if counts missing
    try:
        data = json.load(open(path, encoding="utf-8", errors="replace"))
    except Exception:
        return None
    # page order
    def pk_key(k):
        m = _DIGITS.search(str(k)); return (int(m.group(1)) if m else 0, str(k))
    pages = sorted(data.keys(), key=pk_key)
    # per page: list of lines; each line: list of tokens (lower). keep last-hyphen flag per line.
    vol_pages = []   # [(pk, [ (toks, head_hyphen) ... ]) ]
    raw_tokens = []
    for pk in pages:
        txt = data[pk].get("consensus_text") or ""
        lines = []
        for ln in txt.split("\n"):
            toks = [t.lower() for t in WORD.findall(ln)]
            if not toks: continue
            m = HEAD_HYPHEN.search(ln)
            lines.append([toks, (m.group(1).lower() if m else None)])
            raw_tokens.extend(toks)
        vol_pages.append((pk, lines))
    raw_flag, raw_tot = _flagged(raw_tokens)

    audit = []   # (page, stage, before, after)
    cnt = Counter()

    # ---------- STAGE A: REUNIFY ----------
    # A1 same-line multi-fragment (greedy longest-first)
    for pk, lines in vol_pages:
        for li in range(len(lines)):
            low = lines[li][0]; i = 0; out = []
            while i < len(low):
                if i == len(low) - 1:
                    out.append(low[i]); i += 1; continue
                emitted = False
                maxL = min(MAXFRAG, len(low) - i)
                for L in range(maxL, 1, -1):
                    run = low[i:i + L]
                    if any(len(c) < 2 for c in run): continue
                    j = "".join(run)
                    if len(j) < 5 or all(known(c) for c in run): continue
                    if any((not known(c)) and len(c) < 3 for c in run): continue
                    if strong_known(j):
                        out.append(j); audit.append((pk, "reunify_space", " ".join(run), j))
                        cnt["reunify_space"] += 1; i += L; emitted = True; break
                if not emitted:
                    out.append(low[i]); i += 1
            lines[li][0] = out
    # A2 line-break joins within a page (last tok of line + first tok of a nearby line)
    for pk, lines in vol_pages:
        li = 0
        while li < len(lines) - 1:
            toks = lines[li][0]; hh = lines[li][1]
            if not toks: li += 1; continue
            head = hh if hh else (toks[-1] if (not known(toks[-1]) and len(toks[-1]) >= 3) else None)
            if head is None: li += 1; continue
            joined_done = False
            for k in range(1, min(LOOKAHEAD + 1, len(lines) - li)):
                nt = lines[li + k][0]
                if not nt: continue
                tail = nt[0]; j = head + tail
                if known(j) and not (known(head) and known(tail)):
                    if hh: lines[li][0][-1] = j  # head was hyphen-stem == last token stem; replace last
                    else:  lines[li][0][-1] = j
                    lines[li + k][0] = nt[1:]
                    audit.append((pk, "reunify_break", head + "|" + tail, j)); cnt["reunify_break"] += 1
                    joined_done = True; break
            li += 1
    # A3 cross-page: last token of a page + first token of next page
    for pidx in range(len(vol_pages) - 1):
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

    # flatten to token stream for B/C/D (formatting not needed for measurement)
    def all_tokens():
        for pk, lines in vol_pages:
            for ln in lines:
                for t in ln[0]:
                    yield pk, ln, t

    # ---------- STAGE B: AUTOCORRECT ----------
    for pk, lines in vol_pages:
        for ln in lines:
            toks = ln[0]
            for ti in range(len(toks)):
                t = toks[ti]
                if len(t) < 3 or known(t): continue
                r = _best_correction(t)
                if r:
                    toks[ti] = r[0]; audit.append((pk, f"autocorrect_e{r[1]}", t, r[0]))
                    cnt[f"autocorrect_e{r[1]}"] += 1

    # ---------- STAGE C: SPLIT ----------
    for pk, lines in vol_pages:
        for ln in lines:
            toks = ln[0]; newtoks = []
            for t in toks:
                if len(t) >= 8 and not known(t) and not _edit1_known(t) and not _affix_of_common(t):
                    s = _split(t)
                    if s:
                        newtoks.extend(s.split(" ")); audit.append((pk, "split", t, s)); cnt["split"] += 1
                        continue
                newtoks.append(t)
            ln[0] = newtoks

    # ---------- STAGE D: SONNET overlay ----------
    if _SONNET:
        for pk, lines in vol_pages:
            for ln in lines:
                toks = ln[0]
                for ti in range(len(toks)):
                    fix = _SONNET.get(toks[ti])
                    if fix:
                        audit.append((pk, "sonnet", toks[ti], fix)); toks[ti] = fix; cnt["sonnet"] += 1

    # ---------- MEASURE AFTER ----------
    final_tokens = [t for _, _, t in all_tokens()]
    aft_flag, aft_tot = _flagged(final_tokens)

    # persist
    corrected = {pk: [ln[0] for ln in lines] for pk, lines in vol_pages}
    json.dump(corrected, open(os.path.join(CASCADE, "corrected", vol + ".json"), "w", encoding="utf-8"))
    with open(os.path.join(CASCADE, "audit", vol + ".tsv"), "w", encoding="utf-8") as f:
        f.write("page\tstage\tbefore\tafter\n")
        for r in audit: f.write("\t".join(str(x) for x in r) + "\n")
    res = {"vol": vol, "raw_flagged": raw_flag, "raw_total": raw_tot,
           "after_flagged": aft_flag, "after_total": aft_tot, "stages": dict(cnt)}
    json.dump(res, open(os.path.join(CASCADE, "counts", vol + ".json"), "w", encoding="utf-8"))
    open(done_marker, "w").write(pt())
    return res

def main():
    rlog("START", "correction cascade (reunify -> autocorrect -> split -> sonnet), resumable")
    files = sorted(glob.glob(os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json")))
    rlog("SCAN", f"{len(files)} volumes")
    nw = max(2, min(12, (os.cpu_count() or 4) - 2))
    agg = Counter(); raw_f = raw_t = aft_f = aft_t = 0; done = 0
    t0 = time.time(); last = time.time()
    ctx = mp.get_context("spawn")
    with ctx.Pool(nw, initializer=_init) as pool:
        for res in pool.imap_unordered(_process_volume, files, chunksize=1):
            done += 1
            if res:
                raw_f += res["raw_flagged"]; raw_t += res["raw_total"]
                aft_f += res["after_flagged"]; aft_t += res["after_total"]
                for k, v in res["stages"].items(): agg[k] += v
            now = time.time()
            if now - last >= 15 or done == len(files):
                rr = 100.0 * raw_f / max(1, raw_t); ar = 100.0 * aft_f / max(1, aft_t)
                rlog("CASCADE", f"{done}/{len(files)} vols | raw {rr:.3f}% -> after {ar:.3f}% | elapsed={now-t0:.0f}s", "HEARTBEAT")
                last = now
    rr = 100.0 * raw_f / max(1, raw_t); ar = 100.0 * aft_f / max(1, aft_t)
    report = {"generated": pt(), "volumes": done,
              "raw_flagged": raw_f, "raw_total": raw_t, "raw_rate_pct": round(rr, 4),
              "after_flagged": aft_f, "after_total": aft_t, "after_rate_pct": round(ar, 4),
              "reduction_pct_relative": round(100.0 * (raw_f - aft_f) / max(1, raw_f), 1),
              "stage_corrections": dict(agg)}
    json.dump(report, open(os.path.join(CASCADE, "cascade_report.json"), "w", encoding="utf-8"), indent=2)
    rlog("==== RESULT ====", "")
    rlog("RATE", f"raw flagged = {raw_f:,}/{raw_t:,} = {rr:.4f}%")
    rlog("RATE", f"after cascade = {aft_f:,}/{aft_t:,} = {ar:.4f}%  (down {report['reduction_pct_relative']}% relative)")
    rlog("STAGES", json.dumps(dict(agg)))
    rlog("DONE", f"-> {os.path.join(CASCADE, 'cascade_report.json')}  wall={time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
