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
import os, sys, re, json, glob, time, bisect, threading
from collections import Counter
from datetime import datetime, timezone, timedelta
import multiprocessing as mp
from ocrcorrect.edits import edits1 as _edits1, is_prefix_frag as _e_is_prefix, is_suffix_frag as _e_is_suffix

os.environ["CUDA_VISIBLE_DEVICES"] = ""
import config  # SINGLE source of truth for data paths (the 3060 cutover knob); pipeline/ on sys.path
SCRATCH = config.path_for("data_root")
VOCAB   = config.path_for("vocab_dir")
CASCADE = config.path_for("cascade_dir")
CASCADE_FROM = os.environ.get("CASCADE_FROM", "reunify")
APPLY_SYMSPELL = os.environ.get("CASCADE_APPLY_SYMSPELL", "0") == "1"  # default OFF: SymSpell routes to adjudication, not auto-apply
# Gated heuristic post-autocorrect stage(s). Each only JOINS STAGES when its flag is ON, so the DEFAULT
# config == the golden-master deterministic floor (reunify->split->autocorrect). mojibake = constrained-
# position fix (the non-ASCII char MARKS the error span); high-precision -> auto-applyable. Runs AFTER the
# unifier, so a residual bad char is real damage (not a join seam reunify would have closed).
APPLY_MOJIBAKE = os.environ.get("CASCADE_APPLY_MOJIBAKE", "0") == "1"
STAGES  = ["reunify", "split", "autocorrect"] + (["mojibake"] if APPLY_MOJIBAKE else [])
for sub in ["audit", "counts"] + ["out_" + s for s in STAGES] + ["done_" + s for s in STAGES]:
    os.makedirs(os.path.join(CASCADE, sub), exist_ok=True)
LOG = os.path.join(CASCADE, "cascade-run.log")

WORD = re.compile(r"[A-Za-z\xc0-\xff]+")
HEAD_HYPHEN = re.compile(r"([A-Za-z\xc0-\xff]{2,})-[ \t\r]*$")
ALPHA = "abcdefghijklmnopqrstuvwxyz"
LOOKAHEAD = 6
MAXFRAG = 4
FRAG_WINDOW = 6      # A4 positional reunify: search +/- this many tokens (reading order) for a fragment's partner
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
_SYM = None                                   # corpus-aware SymSpell edit-2 index (None if freq file absent)
_NAMES = frozenset()                          # gazetteer names -- never autocorrect a token that IS a name
_GARBAGE_SHAPED = lambda t: False             # repeat4/cons5/novowel shape test (from symspell_e2)
_CORPUS_FREQ_PATH = os.path.join(CASCADE, "corpus_freq.json")
_GAZETTEER_PATH = os.path.join(SCRATCH, "name_gazetteer.txt")
_C_BC = {}; _C_E1 = {}; _C_AFF = {}; _C_SPLIT = {}
_CF = {}                                          # raw corpus_freq dict -- mojibake fix scoring target
_NONASCII_TOK = re.compile(r"[^\x00-\x7f]")        # token carries a mojibake / U+FFFD replacement char
from ocrcorrect.mojibake_fix import mojibake_candidates as _moji_cands, choose_fix as _moji_choose
def _init():
    global _WS, _HASWF, _WF, _ZIPF, _SORTED, _SORTED_REV, _SYM, _NAMES, _GARBAGE_SHAPED, _CF
    from ocrcorrect.dictionary import build_dictionary, build_sorted_common
    ws, _spell, has_wf, wf = build_dictionary()
    _WS = frozenset(ws); _HASWF = has_wf; _WF = wf
    from wordfreq import zipf_frequency
    _ZIPF = zipf_frequency
    _SORTED, _SORTED_REV = build_sorted_common(_WS, _ZIPF)
    from ocrcorrect.symspell_e2 import _garbage_shaped
    _GARBAGE_SHAPED = _garbage_shaped
    if os.path.exists(_GAZETTEER_PATH):       # protect real names/places from being "corrected"
        _NAMES = frozenset(l.strip() for l in open(_GAZETTEER_PATH, encoding="utf-8") if l.strip())
    if os.path.exists(_CORPUS_FREQ_PATH):     # build the edit-2 index from the corpus-native freq model
        from ocrcorrect.symspell_e2 import SymSpellE2, load_target_freq
        _SYM = SymSpellE2(load_target_freq(_CORPUS_FREQ_PATH))
        _CF = json.load(open(_CORPUS_FREQ_PATH, encoding="utf-8"))   # raw counts for mojibake scoring

def known(t): return (t in _WS) or (_HASWF and _WF(t, "en") > 0)
def zipf(t): return _ZIPF(t, "en")
def strong_known(t): return (t in _WS) or zipf(t) >= 2.8
_ROMAN = re.compile(r"^[ivxlcdm]+$")
def is_roman(t): return bool(_ROMAN.match(t)) and len(t) >= 2

# ---- garbage classification (refined per Patrick) ----
_REPEAT4 = re.compile(r"(.)\1\1\1")                        # 4+ same char in a row -> guaranteed garbage
_REPEAT3 = re.compile(r"(.)\1\1")                          # 3+ same char -> recoverability-checked
_CONS5   = re.compile(r"[bcdfghjklmnpqrstvwxz]{5,}")       # 5+ consonants in a row
_RUN3    = re.compile(r"(.)\1\1+")
_VOWELS  = set("aeiouy")
def _collapse(t): return _RUN3.sub(r"\1\1", t)            # collapse any 3+ run to 2 (addresss->address)

def classify_residual(t):
    """Classify an already-FLAGGED (unknown) token: roman | garbage_<rule> | recoverable.
    LONG run-ons are handled by the splitter upstream; a long token still here = unsplittable."""
    if _ROMAN.match(t) and len(t) >= 2:
        return "roman"
    nonascii = sum(1 for c in t if ord(c) > 127)
    if nonascii:                                          # single mojibake in a word-ish token = recoverable
        return "recoverable" if (nonascii <= 1 and len(t) <= 16) else "garbage_mojibake"
    if _REPEAT4.search(t):
        return "garbage_repeat4"                          # 4+ same char (>3) -- guaranteed
    if _REPEAT3.search(t):                                # exactly-3: garbage ONLY if not recoverable
        if known(_collapse(t)) or _edit1_known(t):
            return "recoverable"                          # fianeee->fiancee, addresss->address
        if _CONS5.search(t) or (len(t) >= 5 and not (set(t) & _VOWELS)):
            return "garbage_repeat3"
        return "recoverable"                             # benefit of the doubt (rare real word)
    if _CONS5.search(t): return "garbage_cons5"
    if len(t) >= 5 and not (set(t) & _VOWELS): return "garbage_novowel"
    if len(t) >= 25: return "garbage_toolong"            # long + unsplittable (split ran upstream)
    return "recoverable"

def _edit1_known(w):
    v = _C_E1.get(w)
    if v is None:
        v = any(known(c) for c in _edits1(w)); _C_E1[w] = v
    return v
def _is_prefix_frag(s): return _e_is_prefix(s, _SORTED)        # edits.py logic, over this worker's _SORTED
def _is_suffix_frag(s): return _e_is_suffix(s, _SORTED_REV)
def _affix_of_common(s):
    v = _C_AFF.get(s)
    if v is None:
        v = _is_prefix_frag(s) or _is_suffix_frag(s)
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
    if res is None and APPLY_SYMSPELL and _SYM is not None and len(tok) >= 5:
        # corpus-aware edit-2 fallback. DECISION 2026-06-12: SymSpell precision (es1 ~83%, es2 ~75-80%)
        # is below legal-grade, so it is NOT auto-applied -- it routes to LLM context adjudication.
        # This path is OFF by default; set CASCADE_APPLY_SYMSPELL=1 only to reproduce the experiment.
        res = _SYM.lookup(tok)                # -> (word, 's1'|'s2') or None
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

_C_DEC = {}
def _decompose_long(tok):
    """For a LONG token (a possible multi-word run-on): greedily segment into >=2 common words
    (each >=3 chars, zipf>=3.0). Char salad won't fully cover -> None -> it falls to garbage."""
    if tok in _C_DEC: return _C_DEC[tok]
    n = len(tok); pieces = []; i = 0
    while i < n:
        matched = False
        for L in range(min(15, n - i), 2, -1):
            p = tok[i:i + L]
            if len(p) >= 3 and (p in _WS or zipf(p) >= 3.0):
                pieces.append(p); i += L; matched = True; break
        if not matched:
            _C_DEC[tok] = None; return None
    res = " ".join(pieces) if len(pieces) >= 2 else None
    _C_DEC[tok] = res; return res

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
    # A4 positional within-window fragment reunify (the RANGE matcher: partner anywhere within FRAG_WINDOW
    # tokens in reading order, not just at a line/page boundary). Suffix-frags look BACK for a head; prefix-
    # frags look FORWARD for a tail. Join only if strong_known and partner is itself a non-word; a real word
    # between the two halves stops the search (won't bridge across a legitimate word).
    flat = []                                          # reading-order refs into the live token lists
    for pk, lines in vol_pages:
        for ln in lines:
            toks = ln[0]
            for idx in range(len(toks)):
                flat.append((pk, toks, idx))
    n = len(flat)
    for i in range(n):
        pk_i, toks_i, idx_i = flat[i]
        t = toks_i[idx_i]
        if t is None or len(t) < 3 or known(t): continue
        joined = False
        if _is_suffix_frag(t):                         # t is a TAIL -> scan back for a head
            for d in range(1, FRAG_WINDOW + 1):
                j = i - d
                if j < 0: break
                _pj, tj, ij = flat[j]
                h = tj[ij]
                if h is None: continue                 # consumed slot -> treat as gap, keep scanning
                if len(h) >= 2 and strong_known(h + t):  # the partner may itself be a real word (re|store)
                    tj[ij] = h + t; toks_i[idx_i] = None
                    audit.append((pk_i, "reunify_window", h + "+" + t, h + t)); cnt["reunify_window"] += 1
                    joined = True; break
                if known(h): break                     # join failed AND it's a real word -> boundary, stop
        if joined: continue
        if _is_prefix_frag(t):                         # t is a HEAD -> scan forward for a tail
            for d in range(1, FRAG_WINDOW + 1):
                k = i + d
                if k >= n: break
                _pk, tk, ik = flat[k]
                tail = tk[ik]
                if tail is None: continue
                if len(tail) >= 2 and strong_known(t + tail):  # tail half is commonly a real word (incorpo|rated)
                    toks_i[idx_i] = t + tail; tk[ik] = None
                    audit.append((pk_i, "reunify_window", t + "+" + tail, t + tail)); cnt["reunify_window"] += 1
                    break
                if known(tail): break                  # join failed AND it's a real word -> boundary, stop
    for pk, lines in vol_pages:                        # drop the consumed (None) slots
        for ln in lines:
            ln[0] = [x for x in ln[0] if x is not None]

def stage_split(vol_pages, audit, cnt):
    for pk, lines in vol_pages:
        for ln in lines:
            newtoks = []
            for t in ln[0]:
                if len(t) >= 8 and not known(t) and not _edit1_known(t) and not _affix_of_common(t):
                    s = _split(t)
                    if not s and len(t) >= 15:          # long run-on: try multi-word decomposition
                        s = _decompose_long(t)
                        if s: cnt["split_long"] += 1
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
                if t in _NAMES or _GARBAGE_SHAPED(t): continue   # don't "fix" a real name or guaranteed garbage
                r = _best_correction(t)
                if r:
                    toks[ti] = r[0]; audit.append((pk, f"autocorrect_e{r[1]}", t, r[0])); cnt[f"autocorrect_e{r[1]}"] += 1

def _moji_score(w): return _CF.get(w, 0) * 100.0 + zipf(w)   # corpus count dominates; zipf breaks ties

def stage_mojibake(vol_pages, audit, cnt):
    """Constrained-position mojibake fix: substitute ONLY the non-ASCII span and keep a fix only when it
    yields a KNOWN, UNAMBIGUOUS word (the bad char marks exactly where the damage is, so far higher
    precision than blind edit-1). Pure core lives in mojibake_fix.py (unit-tested)."""
    for pk, lines in vol_pages:
        for ln in lines:
            toks = ln[0]
            for ti in range(len(toks)):
                t = toks[ti]
                if not _NONASCII_TOK.search(t) or known(t):
                    continue
                cs = _moji_cands(t, known)
                if not cs:
                    continue
                fix, _amb = _moji_choose(cs, _moji_score)
                if fix is not None and fix != t:
                    toks[ti] = fix; audit.append((pk, "mojibake", t, fix)); cnt["mojibake"] += 1

_TRANSFORM = {"reunify": stage_reunify, "split": stage_split, "autocorrect": stage_autocorrect,
              "mojibake": stage_mojibake}
_STAGE_KEYS = {"reunify": ("reunify_space", "reunify_break", "reunify_xpage", "reunify_window"),
               "split": ("split",), "autocorrect": ("autocorrect_e1", "autocorrect_es1", "autocorrect_es2"),
               "mojibake": ("mojibake",)}

def _process_volume(arg):
    path, from_stage = arg
    vol = os.path.basename(os.path.dirname(os.path.dirname(path)))
    cfp = os.path.join(CASCADE, "counts", vol + ".json")
    prior = json.load(open(cfp, encoding="utf-8")) if os.path.exists(cfp) else {}
    start = STAGES.index(from_stage)
    meas = dict(prior.get("meas", {}))          # {"raw":[f,t], "reunify":[f,t], "split":[f,t], "autocorrect":[f,t]}
    # Keep correction counts ONLY for stages BEFORE the resume point; re-run stages recompute fresh.
    # (A full re-run from "reunify" starts the counter clean -- fixes the stale-count-merge double-count.)
    _keep = set().union(*[set(_STAGE_KEYS[s]) for s in STAGES[:start]]) if start else set()
    stage_cnt = Counter({k: v for k, v in prior.get("stages", {}).items() if k in _keep})

    timings = dict(prior.get("timings", {}))    # per-stage wall seconds for THIS volume
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

    # FINAL garbage classification of the post-cascade flagged tokens (in-cascade, not standalone)
    gc = Counter()
    for pk, lines in vol_pages:
        for ln in lines:
            for t in ln[0]:
                if len(t) >= 2 and not known(t):
                    c = classify_residual(t)
                    gc["roman" if c == "roman" else ("garbage" if c.startswith("garbage") else "recoverable")] += 1
                    if c.startswith("garbage"): gc[c] += 1   # keep per-rule breakdown too
    classify = {"roman": gc["roman"], "garbage": gc["garbage"], "recoverable": gc["recoverable"],
                "by_rule": {k: v for k, v in gc.items() if k.startswith("garbage_")}}

    res = {"vol": vol, "meas": meas, "stages": dict(stage_cnt), "timings": timings, "classify": classify}
    json.dump(res, open(cfp, "w", encoding="utf-8"))
    return res

def main():
    rlog("START", f"cascade from '{CASCADE_FROM}' (reunify -> split -> autocorrect; sonnet held out)")
    files = sorted(glob.glob(os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json")))
    rlog("SCAN", f"{len(files)} volumes")
    nw = max(2, min(12, (os.cpu_count() or 4) - 2))
    keys = ["raw", "reunify", "split", "autocorrect"]
    F = {k: 0 for k in keys}; T = {k: 0 for k in keys}; agg = Counter(); tim = Counter(); cls = Counter()
    state = {"done": 0}
    lock = threading.Lock()
    t0 = time.time()
    n_files = len(files)

    # TRUE time-based heartbeat: a daemon thread fires every 15s on a wall clock, independent of
    # volume completion (so a single slow volume can't silence it), with per-stage flagged counts+rates.
    hb_stop = threading.Event()
    def _heartbeat():
        while not hb_stop.wait(15):
            with lock:
                seg = " | ".join(
                    f"{('raw' if k=='raw' else 'aft-'+k[:4])} {F[k]:,}={100.0*F[k]/max(1,T[k]):.3f}%"
                    for k in keys if T[k])
                tstr = " ".join(f"{s}={tim[s]:.0f}s" for s in STAGES if tim[s])
                d = state["done"]
            rlog("HEARTBEAT", f"{d}/{n_files} vols | {seg} | stage-cpu[{tstr}] | wall={time.time()-t0:.0f}s")
    hb = threading.Thread(target=_heartbeat, daemon=True); hb.start()

    ctx = mp.get_context("spawn")
    args = [(p, CASCADE_FROM) for p in files]
    with ctx.Pool(nw, initializer=_init) as pool:
        for res in pool.imap_unordered(_process_volume, args, chunksize=1):
            with lock:
                state["done"] += 1
                if res:
                    for k in keys:
                        if k in res["meas"]:
                            F[k] += res["meas"][k][0]; T[k] += res["meas"][k][1]
                    for k, v in res["stages"].items(): agg[k] += v
                    for k, v in res.get("timings", {}).items(): tim[k] += v
                    c = res.get("classify", {})
                    cls["garbage"] += c.get("garbage", 0); cls["roman"] += c.get("roman", 0)
                    cls["recoverable"] += c.get("recoverable", 0)
                    for k, v in c.get("by_rule", {}).items(): cls[k] += v
    hb_stop.set(); hb.join(timeout=2)
    done = state["done"]
    def rate(k): return round(100.0 * F[k] / max(1, T[k]), 4)
    prog = {("raw" if k == "raw" else "after_" + k): {"flagged": F[k], "total": T[k], "rate_pct": rate(k)} for k in keys}
    fl = F["autocorrect"]; ga = cls["garbage"]; ro = cls["roman"]; rc = cls["recoverable"]
    corpus_tot = T["autocorrect"]
    classification = {
        "flagged": fl, "garbage": ga, "roman": ro, "recoverable": rc,
        "garbage_pct_of_corpus": round(100.0 * ga / max(1, corpus_tot), 4),
        "recoverable_pct_of_corpus": round(100.0 * rc / max(1, corpus_tot), 4),
        "garbage_pct_of_flagged": round(100.0 * ga / max(1, fl), 1),
        "by_rule": {k: cls[k] for k in cls if k.startswith("garbage_")}}
    report = {"generated": pt(), "from_stage": CASCADE_FROM, "volumes": done, "sonnet_applied": False,
              "stage_progression": prog,
              "pre_sonnet_rate_pct": rate("autocorrect"),
              "reduction_pct_relative": round(100.0 * (F["raw"] - F["autocorrect"]) / max(1, F["raw"]), 1),
              "residual_classification": classification,
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
    cz = report["residual_classification"]
    rlog("CLASSIFY", f"of {cz['flagged']:,} flagged: garbage={cz['garbage']:,} ({cz['garbage_pct_of_corpus']}% corpus) | roman={cz['roman']:,} | recoverable={cz['recoverable']:,} ({cz['recoverable_pct_of_corpus']}% corpus)")
    rlog("CLASSIFY", f"garbage by rule: {cz['by_rule']}")
    rlog("TIMING", f"stage cpu-seconds: {dict(report['stage_cpu_seconds'])}  | wall={report['wall_seconds']}s")
    rlog("STAGES", json.dumps(dict(agg)))
    try:
        from ocrcorrect.cascade_summary import build_summary
        sp, srows = build_summary(CASCADE)
        rlog("SUMMARY", f"per-volume summary ({len(srows)} vols) -> {sp}")
    except Exception as _e:
        rlog("SUMMARY", f"per-volume summary failed: {_e}", "WARN")
    rlog("DONE", f"-> {os.path.join(CASCADE, 'cascade_report.json')}")

if __name__ == "__main__":
    main()
