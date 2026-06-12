"""
correction_passes.py -- Three deterministic correction passes on OCR corpus
CPU-only (CUDA_VISIBLE_DEVICES='').

Pass A: Dehyphenation / rejoin (line-break hyphens + adjacent token rejoins)
Pass B: De-merge (split run-together tokens into known words) -- freq>=2 only
         v3 TIGHTENED: three extra gates before accepting any de-merge split:
           Gate 1 (single-word-garble): if the token is within edit distance 1
             of ANY known word, skip -- it is a garble, leave for Pass C.
           Gate 2 (piece plausibility): both pieces >= 4 chars OR one piece is
             a common short stopword (of/the/in/to/and/for/by/an/as/at/or/on).
           Gate 3 (unique segmentation): for 2-splits, if more than one valid
             segmentation exists and none uses a stopword boundary, skip (ambiguous).
Pass C: Spell-correct high-frequency residuals (freq >= 10)

REDESIGN v3:
- ALL v2 features retained (heartbeat logging, freq>=2 bound, 2-3 segment DP)
- Pass B tightened with three conservative gates (see above)
- Heartbeat every ~20k types or ~15s inside the de-merge loop

Writes run log to C:/Users/patolex/PatoLex-scratch/_vocab/correction-pass-run.log
"""

import os, sys, json, re, glob, time, unicodedata, bisect
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
import random
import multiprocessing as mp

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["PYTORCH_NO_CUDA_MEMORY_CACHING"] = "1"

SCRATCH  = r"C:\Users\patolex\PatoLex-scratch"
OUT_DIR  = r"C:\Users\patolex\PatoLex-scratch\_vocab"
LOG_PATH = r"C:\Users\patolex\PatoLex-scratch\_vocab\correction-pass-run.log"

os.makedirs(OUT_DIR, exist_ok=True)

# ---- LEGAL SUPPLEMENT ----
LEGAL_SUPPLEMENT = {
    "hereinafter","hereinbefore","hereto","hereunto","heretofore",
    "hereunder","herewith","herein","hereof","thereof","therein",
    "thereto","thereunder","therewith","thereon","therefor","thereby",
    "thereat","thereabout","thereabouts","therefrom","thereupon",
    "whereof","wherein","whereto","whereunder","whereupon","whereas",
    "wherefore","aforesaid","forthwith","notwithstanding","aforementioned",
    "hitherto","thenceforth","thenceforward","suchlike",
    "chaptered","uncodified","appropriation","appropriated",
    "statutes","legislature","legislative","assemblyman","assemblywoman",
    "assemblymen","assemblymembers","senate","senator","senators",
    "governor","controller","treasurer","comptroller","superintendent",
    "commissioners","commissioner","departmental","subdivision",
    "subdivisions","subparagraph","subparagraphs","subsection",
    "subsections","enactment","enactments","reenactment","reenactments",
    "codify","codified","codification","recission",
    "rescission","rescind","rescinded",
    # --- v7: real legal/domain terms that were being FLAGGED-then-corrupted ---
    # (e.g. conservatee was "corrected" to conservative; habilitative was split).
    "conservatee","conservatees","conservator","conservators","conservatorship",
    "conservatorships","habilitative","habilitation","rehabilitative",
    "mobilehome","mobilehomes","twothirds","threefourths","threefifths",
    "nonunitary","nonconforming","noninstitutional","nonmotorized","nonvehicular",
    "nonambulatory","noncertificated","feepayer","feepayers","ratepayer","ratepayers",
    "taxpayer","taxpayers","materialmen","materialman","subcontainer","subcontainers",
    "preadoptive","postaudit","postadoption","disincorporated","disincorporation",
    "scholarshare","statemandated","weighmaster","weighmasters","retirant","retirants",
    "areawide","offstreet","permitholder","permitholders","schoolsite","schoolsites",
    "schoolbus","schoolbuses","winegrape","winegrapes","interindemnity","postclosure",
    "postconsumer","multicounty","trustline","disabilitant","disabilitants",
}

# --- CA proper-name supplement (counties/cities/features/legislators) ---
# Stops real CA names being false-flagged and protects them from mis-correction.
try:
    from ca_gazetteer import CA_NAME_TOKENS
    LEGAL_SUPPLEMENT |= CA_NAME_TOKENS
except Exception as _e:
    print(f"[WARN] ca_gazetteer not loaded: {_e}", file=sys.stderr)

# Short stopwords that make short-piece splits legitimate (e.g. ofthe -> of+the)
STOPWORDS = frozenset({"of","the","in","to","and","for","by","an","as","at","or","on"})

# ---- PLAUSIBILITY SCORING (v7) ----
# Dictionary *membership* is too blunt: nltk contains thousands of obscure short
# strings (reti, sech, pria, gian, etta, ...) so garbage fragments pass is_known().
# is_common() is a stricter gate -- a token is "common/plausible" only if it is a
# stopword, a curated legal term, OR has a Zipf frequency at/above MIN_ZIPF.
# Zipf scale: 0=absent, ~1-2=very rare, ~3=rare-but-real, ~5=common, ~7=("the").
try:
    from wordfreq import zipf_frequency as _ZIPF
except Exception:
    _ZIPF = None

# Tunables (env-overridable). MIN_ZIPF gates de-merge pieces; the Pass C corpus-
# frequency dominance check uses MIN_CORPUS_FREQ / CORR_DOMINANCE.
MIN_ZIPF        = float(os.environ.get("DEMERGE_MIN_ZIPF", "2.5"))
MIN_CORPUS_FREQ = int(os.environ.get("PASSC_MIN_CORPUS_FREQ", "50"))
CORR_DOMINANCE  = float(os.environ.get("PASSC_DOMINANCE", "3.0"))
PASSC_MIN_FREQ  = int(os.environ.get("PASSC_MIN_FREQ", "10"))  # Pass C frequency floor (lower to 2 to clean the 2-9 band)

def is_common(tok):
    """Stricter than is_known(): is this a *plausible* real word, not just present
    somewhere in a huge union dictionary? Stopwords and curated legal terms always
    pass; everything else must clear the Zipf frequency floor."""
    if tok in STOPWORDS or tok in LEGAL_SUPPLEMENT:
        return True
    if _ZIPF is not None and _ZIPF(tok, "en") >= MIN_ZIPF:
        return True
    return False

# ---- RUN LOG ----
def pt_label():
    try:
        pt = timezone(timedelta(hours=-7))
        return datetime.now(timezone.utc).astimezone(pt).strftime("%Y-%m-%d %H:%M PT")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M local")

def rlog(phase, desc, status="OK"):
    line = f"[{pt_label()}] {phase} | {desc} | {status}\n"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
    except Exception as e:
        print(f"[WARN] log write failed: {e}", file=sys.stderr)
    print(line.rstrip())
    sys.stdout.flush()

# ---- DICTIONARY BUILD ----
def build_dictionary():
    word_set = set()
    spell = None
    has_wordfreq = False
    wf_fn = None

    try:
        from spellchecker import SpellChecker
        spell = SpellChecker()
        word_set |= set(spell.word_frequency.dictionary.keys())
        print(f"[DICT] pyspellchecker: {len(word_set):,} words")
        sys.stdout.flush()
    except Exception as e:
        print(f"[WARN] pyspellchecker: {e}", file=sys.stderr)

    try:
        from nltk.corpus import words as nltk_words
        nltk_set = set(w.lower() for w in nltk_words.words())
        before = len(word_set)
        word_set |= nltk_set
        print(f"[DICT] nltk words: {len(nltk_set):,} raw, +{len(word_set)-before:,} new")
        sys.stdout.flush()
    except Exception as e:
        print(f"[WARN] nltk words: {e}", file=sys.stderr)

    try:
        from wordfreq import word_frequency as _wf
        wf_fn = _wf
        has_wordfreq = True
        print("[DICT] wordfreq available (per-token check)")
        sys.stdout.flush()
    except ImportError:
        print("[WARN] wordfreq not available; using static dict only", file=sys.stderr)

    word_set |= LEGAL_SUPPLEMENT

    # VALIDATED corpus-vocabulary layer (Patrick: start from the corpus's own words). Names that
    # are corpus-attested + matched a real name list, plus genuine-novel corpus terms that are NOT
    # within edit-2 of a common English word (so systematic OCR errors like secrion/sball are
    # excluded). Built by build_dict_additions.py -> _vocab/dict_additions.txt. Loaded if present.
    _add_path = os.path.join(OUT_DIR, "dict_additions.txt") if "OUT_DIR" in globals() else \
                r"C:\Users\patolex\PatoLex-scratch\_vocab\dict_additions.txt"
    try:
        if os.path.exists(_add_path):
            with open(_add_path, encoding="utf-8") as _f:
                _adds = set(w.strip().lower() for w in _f if w.strip())
            before = len(word_set)
            word_set |= _adds
            print(f"[DICT] corpus-vocab additions: {len(_adds):,} loaded (+{len(word_set)-before:,} new)")
        else:
            print("[DICT] no dict_additions.txt (corpus-vocab layer absent)")
    except Exception as _e:
        print(f"[WARN] dict_additions load failed: {_e}", file=sys.stderr)

    print(f"[DICT] Static dict size: {len(word_set):,}")
    sys.stdout.flush()
    return word_set, spell, has_wordfreq, wf_fn

def make_is_known(word_set, has_wordfreq, wf_fn):
    def is_known(tok):
        if tok in word_set:
            return True
        if has_wordfreq and wf_fn(tok, "en") > 0:
            return True
        return False
    return is_known

# ---- TOKENISER (no hyphen splitting, preserves stream order) ----
_TOKEN_RE = re.compile(r"[A-Za-z\xc0-\xff]+(?:-[A-Za-z\xc0-\xff]+)*")

def tokenise_raw(text):
    """Yield (start, end, orig, low) for each token. Min length 2. No hyphen expansion."""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", text)
    for m in _TOKEN_RE.finditer(text):
        orig = m.group(0)
        low = orig.lower()
        if len(low) >= 2:
            yield (m.start(), m.end(), orig, low)

# ---- BASELINE TOKENISER (with hyphen expansion, for counting) ----
def tokenise_baseline(text):
    """Like tokenise_raw but also yields hyphen-split components (matches vocab_diff.py)."""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", text)
    for m in _TOKEN_RE.finditer(text):
        orig = m.group(0)
        low = orig.lower()
        if len(low) >= 2:
            yield low
            if "-" in low:
                for part in low.split("-"):
                    if len(part) >= 2:
                        yield part

def measure_counter(freq_counter, is_known):
    """Returns (total_occ, bad_types, bad_occ, pct)."""
    total_occ = sum(freq_counter.values())
    bad_occ   = 0
    bad_types = 0
    for tok, cnt in freq_counter.items():
        if not is_known(tok):
            bad_types += 1
            bad_occ   += cnt
    pct = 100.0 * bad_occ / total_occ if total_occ else 0
    return total_occ, bad_types, bad_occ, pct

# ================================================================
# PASS B: TIGHTENED DE-MERGE (v3)
# Three gates added on top of v2's basic DP approach.
#
# Gate 1 -- Single-word-garble gate:
#   If the bad token is within edit distance 1 of ANY known dictionary word,
#   it is almost certainly a garbled real word (e.g. publie -> public).
#   DO NOT split it -- leave it for Pass C spell-correction.
#   Implementation: pyspellchecker's .candidates(tok) returns the set of
#   edit-1 known neighbors. If that set is non-empty (and contains something
#   other than the token itself corrected), the token passes the garble gate
#   and we SKIP the split.
#   Fallback (if spell is None): generate all edit-1 variants and test
#   set membership against word_set directly.
#
# Gate 2 -- Piece plausibility:
#   Only accept a 2-piece split where BOTH pieces are >= 4 chars, OR at least
#   one piece is a recognised short stopword (of/the/in/to/and/for/by/an/as/at/or/on).
#   This kills coincidental short splits like pub+lie while keeping ofthe, inthe, etc.
#
# Gate 3 -- Unique segmentation:
#   For 2-splits: collect ALL valid 2-splits that pass Gate 2.
#   If exactly one exists, accept it.
#   If more than one exists and none uses a stopword boundary, skip (ambiguous).
#   If more than one exists but one uses a stopword boundary, prefer that one.
#
# For 3-splits: only attempt if no 2-split was accepted; same piece-plausibility
# rule (all pieces >= 4 OR stopword); take the first found (conservative).
# ================================================================

def _edit1_is_known_fast(tok, word_set):
    """
    Return True if any edit-distance-1 neighbour of tok is in word_set.
    Covers: deletions, substitutions, insertions, transpositions.
    Fast enough for short tokens (< 20 chars), skips longer tokens.
    """
    # For tokens > 20 chars the garble-gate is less relevant and this is slow
    if len(tok) > 20:
        return False
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    n = len(tok)

    # deletions (length n-1)
    for i in range(n):
        cand = tok[:i] + tok[i+1:]
        if len(cand) >= 2 and cand in word_set:
            return True

    # substitutions
    for i in range(n):
        for c in alphabet:
            if c == tok[i]:
                continue
            cand = tok[:i] + c + tok[i+1:]
            if cand in word_set:
                return True

    # insertions (length n+1)
    for i in range(n + 1):
        for c in alphabet:
            cand = tok[:i] + c + tok[i:]
            if cand in word_set:
                return True

    # transpositions
    for i in range(n - 1):
        cand = tok[:i] + tok[i+1] + tok[i] + tok[i+2:]
        if cand in word_set:
            return True

    return False


def _piece_ok(piece):
    """Gate 2 check on a single piece: >= 4 chars OR is a stopword."""
    return len(piece) >= 4 or piece in STOPWORDS


def _find_2splits(tok, is_known=None):
    """
    Return list of all 2-piece splits [left, right] where:
      - Both pieces are COMMON words (is_common: Zipf>=MIN_ZIPF or stopword/legal)
        -- v7: was is_known(), which let garbage fragments (reti, treet, ...) pass
      - Both pieces pass _piece_ok (Gate 2)
      - Each piece is >= 2 chars (minimum meaningful token)
    """
    n = len(tok)
    results = []
    for i in range(2, n - 1):
        left  = tok[:i]
        right = tok[i:]
        if len(right) >= 2 and _piece_ok(left) and _piece_ok(right):
            if is_common(left) and is_common(right):
                results.append([left, right])
    return results


def _find_3splits(tok, is_known=None):
    """
    Return the first valid 3-piece split [left, mid, right] where:
      - All three pieces are COMMON words (is_common) -- v7 (was is_known)
      - All three pieces pass _piece_ok (Gate 2)
    """
    n = len(tok)
    for i in range(2, n - 3):
        for j in range(i + 2, n - 1):
            left  = tok[:i]
            mid   = tok[i:j]
            right = tok[j:]
            if (len(right) >= 2
                    and _piece_ok(left) and _piece_ok(mid) and _piece_ok(right)):
                if is_common(left) and is_common(mid) and is_common(right):
                    return [left, mid, right]
    return None


def _select_split(candidates):
    """
    Gate 3: given a list of 2-split candidates (each a [left, right] list),
    apply uniqueness / stopword preference.

    Rules:
      1. If exactly one candidate, accept it.
      2. If multiple candidates, prefer any that uses a stopword boundary
         (left or right is a stopword). If exactly one stopword-boundary
         split exists, accept it. If more than one, return None (ambiguous).
      3. If no stopword-boundary split and multiple candidates, return None.
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Multiple candidates -- look for stopword-boundary ones
    sw_candidates = [c for c in candidates if c[0] in STOPWORDS or c[1] in STOPWORDS]
    if len(sw_candidates) == 1:
        return sw_candidates[0]
    # None or multiple stopword splits -- too ambiguous
    return None


# ================================================================
# PARALLEL PASS B (v5)
# Windows uses 'spawn', so worker state must be rebuilt per process via an
# initializer (closures/connections are NOT inherited). Each worker rebuilds
# the union dictionary once, then classifies tokens independently. The MAIN
# process consumes results via imap_unordered and emits the heartbeat -- so we
# keep full parallelism AND a live run log.
#
# Gate 1 here uses _edit1_is_known_fast (EARLY-EXIT: returns True on the first
# edit-1 known neighbour) against the SAME union word_set the rest of the
# pipeline uses -- not pyspellchecker.candidates() (which builds + frequency-
# ranks the entire edit-1 set). Semantics: "is this token within edit-1 of any
# known word?" -- identical intent to v3's garble gate, slightly more
# conservative because the union dict is larger than pyspellchecker's alone.
# ================================================================
_W_WORD_SET = None
_W_HAS_WF = False
_W_WF_FN = None
_W_SPELL = None

# Line-break-hyphen pattern (module-level so workers can use it under spawn).
# v8: captures the FULL second word so the join can be GUARDED (only collapse if the
# result is a known word) -- otherwise marginalia/gutter-note text glued across a line
# break manufactures garbage merges (appropria-\ndollars -> appropriadollars).
LBH_RE = re.compile(r'([A-Za-z\xc0-\xff]+)-[ \t]*\r?\n[ \t]*([A-Za-z\xc0-\xff]+)')

def _worker_is_known(tok):
    if tok in _W_WORD_SET:
        return True
    if _W_HAS_WF and _W_WF_FN(tok, "en") > 0:
        return True
    return False

def _init_worker_full():
    """
    Rebuild the union dictionary AND the SpellChecker inside each worker process
    (spawn-safe). Used by every pool (file-scan, de-merge, Pass C) so any worker
    can answer is_known() and run spell.correction(). Building the dict costs a
    few seconds per worker, done once at pool startup.
    """
    global _W_WORD_SET, _W_HAS_WF, _W_WF_FN, _W_SPELL
    ws, spell, has_wf, wf_fn = build_dictionary()
    _W_WORD_SET = frozenset(ws)
    _W_HAS_WF = has_wf
    _W_WF_FN = wf_fn
    _W_SPELL = spell

# Back-compat alias (older call sites)
_init_demerge_worker = _init_worker_full

def _scan_file(path):
    """
    PARALLEL file-scan worker (v6): load one consensus JSON file and compute,
    in a single read, both the BASELINE token frequencies (hyphen-expanded) and
    the PASS-A (dehyphenation + adjacent-pair rejoin) frequencies, plus the
    line-break-hyphen and adjacent-rejoin op counters. Returns four Counters.
    Workers read their own files, so no large text is pickled across processes.
    """
    bf = Counter(); pf = Counter(); lbh = Counter(); adj = Counter()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception:
        return (bf, pf, lbh, adj)

    def _lbh_sub(m):
        joined = m.group(1) + m.group(2)
        # GUARD: only collapse the line-break hyphen if the join is a real word.
        # Otherwise it's likely a margin/gutter-note word glued to a body word -- leave
        # the original text untouched (don't manufacture a bad merge).
        if _worker_is_known(joined.lower()):
            lbh[joined.lower()] += 1
            return joined
        return m.group(0)

    for _pk, po in data.items():
        txt = (po.get("consensus_text") or "").strip()
        if not txt:
            continue
        # BASELINE: hyphen-expanded tokenisation (matches vocab_diff.py)
        for tok in tokenise_baseline(txt):
            bf[tok] += 1
        # PASS A: collapse line-break hyphens, then adjacent-pair rejoin
        text2 = LBH_RE.sub(_lbh_sub, txt)
        tokens = list(tokenise_raw(text2))
        i = 0
        n = len(tokens)
        while i < n:
            if i + 1 < n:
                low0 = tokens[i][3]
                low1 = tokens[i + 1][3]
                joined = low0 + low1
                if (len(joined) >= 4
                        and _worker_is_known(joined)
                        and (not _worker_is_known(low0) or not _worker_is_known(low1))):
                    pf[joined] += 1
                    adj[joined] += 1
                    i += 2
                    continue
            pf[tokens[i][3]] += 1
            i += 1
    return (bf, pf, lbh, adj)

def _passC_candidates(tok):
    """
    PARALLEL Pass C worker (v7): return the edit-distance candidate SET for one
    freq>=10 token (the slow part). The MAIN process then picks among candidates
    by CORPUS frequency -- because general-English frequency is the wrong language
    model for statutes (it would pick 'small' over 'shall' for 'sball'). Returns
    (tok, tuple_of_candidates).
    """
    try:
        cands = _W_SPELL.candidates(tok)
        if cands:
            return (tok, tuple(sorted(cands)))
    except Exception:
        pass
    return (tok, ())


def _select_correction(tok, cands, corpus_freq):
    """
    Score candidates by CORPUS frequency and accept only a confident correction.
    Returns (correction_or_None, reason).
      - 0 candidates           -> reject (no_candidate)
      - 1 candidate            -> accept iff it appears >= MIN_CORPUS_FREQ in corpus
      - >=2 candidates         -> rank by corpus freq; accept the top only if it is
                                  frequent AND dominates the runner-up by CORR_DOMINANCE
                                  (a clear winner). Otherwise it's genuinely ambiguous
                                  (e.g. cight -> right/eight) -> leave for review.
    """
    cands = [c for c in cands if c != tok]
    if not cands:
        return None, "no_candidate"
    if len(cands) == 1:
        c = cands[0]
        cf = corpus_freq.get(c, 0)
        if cf >= MIN_CORPUS_FREQ:
            return c, f"unique({c}:{cf})"
        return None, f"weak_unique({c}:{cf})"
    ranked = sorted(cands, key=lambda c: corpus_freq.get(c, 0), reverse=True)
    best, second = ranked[0], ranked[1]
    bf, sf = corpus_freq.get(best, 0), corpus_freq.get(second, 0)
    if bf >= MIN_CORPUS_FREQ and bf >= CORR_DOMINANCE * max(sf, 1):
        return best, f"dominant({best}:{bf}>>{second}:{sf})"
    return None, f"ambiguous({best}:{bf}/{second}:{sf})"

def _demerge_one(tok):
    """Classify a single bad token. Returns (tok, result_or_None, gate_tag)."""
    n = len(tok)
    if n < 4:
        return (tok, None, "short")
    # ---- Gates 2 + 3 (cheap): segmentation ----
    two_splits = _find_2splits(tok, _worker_is_known)
    selected = _select_split(two_splits)
    if selected is not None:
        result = selected
    elif len(two_splits) > 1:
        return (tok, None, "gate3")
    else:
        result = _find_3splits(tok, _worker_is_known) if n >= 8 else None
    if result is None:
        return (tok, None, "nosplit")
    # ---- Gate 1 (early-exit garble veto) ----
    if _edit1_is_known_fast(tok, _W_WORD_SET):
        return (tok, None, "gate1")
    return (tok, result, "accepted")


def build_demerge_splits_parallel(bad_token_freq, word_set, has_wordfreq, wf_fn, n_workers):
    """
    Parallel de-merge classification over bad tokens (freq>=2). Spawns n_workers
    processes, each rebuilding the dictionary once, then streams results back to
    the main process which writes heartbeats. Returns splits dict {tok: pieces|None}.
    """
    toks = list(bad_token_freq)
    total = len(toks)
    splits = {}
    gate1_skipped = 0
    gate3_skipped = 0
    accepted = 0
    t_start = time.time()
    last_hb = time.time()

    rlog("PASS-B", f"Parallel de-merge: {total:,} types across {n_workers} workers (each builds dict once) ...")

    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=n_workers, initializer=_init_demerge_worker) as pool:
        for i, (tok, result, tag) in enumerate(
                pool.imap_unordered(_demerge_one, toks, chunksize=500)):
            splits[tok] = result
            if tag == "gate1":
                gate1_skipped += 1
            elif tag == "gate3":
                gate3_skipped += 1
            elif tag == "accepted":
                accepted += 1
            now = time.time()
            if (i + 1) % 20_000 == 0 or (now - last_hb >= 15.0 and i > 0):
                rate = (i + 1) / max(now - t_start, 0.001)
                rlog("PASS-B",
                     f"{i+1:,}/{total:,} types | splittable_so_far={accepted:,} | "
                     f"gate1_garble_skipped={gate1_skipped:,} | gate3_ambig_skipped={gate3_skipped:,} | "
                     f"elapsed={now-t_start:.0f}s | rate={rate:.0f}/s | PARALLEL",
                     status="HEARTBEAT")
                last_hb = now

    rlog("PASS-B",
         f"GATE SUMMARY (parallel): total_bad_types={total:,} | accepted_splits={accepted:,} | "
         f"gate1_garble_blocked={gate1_skipped:,} | gate3_ambig_blocked={gate3_skipped:,} | "
         f"workers={n_workers} | elapsed={time.time()-t_start:.1f}s")
    return splits


def build_demerge_splits(bad_token_freq, is_known, word_set, spell):
    """
    bad_token_freq: dict {tok: corpus_freq} -- ONLY types with freq >= 2.
    Returns splits dict {tok: [piece, ...] or None}.

    v3 TIGHTENED: applies all three gates before accepting any split.
    Logs heartbeat every 20,000 types or every ~15s.

    gate1_skipped: count of tokens rejected by the garble gate
    gate2_skipped: rolled into the _find_2splits / _find_3splits logic (piece plausibility)
    gate3_skipped: count of tokens with multiple ambiguous splits
    """
    splits = {}
    total = len(bad_token_freq)
    t_start = time.time()
    last_hb = time.time()
    gate1_skipped = 0
    gate3_skipped = 0

    for i, tok in enumerate(bad_token_freq):
        n = len(tok)

        if n < 4:
            # Too short to split into two meaningful pieces even with stopwords
            splits[tok] = None
        else:
            # ---- Gates 2 + 3 FIRST (cheap): piece plausibility + uniqueness ----
            # Reordered v4: segment first. If a token produces no candidate split,
            # there is nothing to de-merge and Gate 1 (the expensive edit-distance
            # garble check) is irrelevant -- skip it entirely. Gate 1 only matters
            # as a VETO on an actual split, so we run it ONLY on the few thousand
            # tokens that actually segment. Output is identical to the v3 order.
            result = None
            two_splits = _find_2splits(tok, is_known)
            selected = _select_split(two_splits)

            if selected is not None:
                result = selected
            elif len(two_splits) > 1:
                # Multiple ambiguous 2-splits with no clear stopword winner
                gate3_skipped += 1
                result = None
            else:
                # No valid 2-split -- try 3-split if token is long enough
                if n >= 8:
                    result = _find_3splits(tok, is_known)

            if result is None:
                # No candidate split -> nothing for Gate 1 to veto; skip the
                # expensive edit-distance check entirely.
                splits[tok] = None
            else:
                # ---- Gate 1 (expensive): single-word-garble veto ----
                # The token DID segment. Only now do we ask: is it more likely a
                # garbled single word than a genuine merge? If within edit-1 of a
                # known word, veto the split and leave it for Pass C.
                is_garble = False
                if spell is not None:
                    try:
                        candidates_set = spell.candidates(tok)
                        if candidates_set and len(candidates_set) > 0:
                            is_garble = True
                    except Exception:
                        pass
                else:
                    is_garble = _edit1_is_known_fast(tok, word_set)

                if is_garble:
                    gate1_skipped += 1
                    splits[tok] = None
                else:
                    splits[tok] = result

        # Heartbeat every 20,000 types OR if >15 seconds have passed
        now = time.time()
        if (i + 1) % 20_000 == 0 or (now - last_hb >= 15.0 and i > 0):
            done_so_far = sum(1 for v in splits.values() if v is not None)
            rate = (i + 1) / max(now - t_start, 0.001)
            rlog("PASS-B",
                 f"{i+1:,}/{total:,} types | splittable_so_far={done_so_far:,} | "
                 f"gate1_garble_skipped={gate1_skipped:,} | gate3_ambig_skipped={gate3_skipped:,} | "
                 f"elapsed={now-t_start:.0f}s | rate={rate:.0f}/s",
                 status="HEARTBEAT")
            last_hb = now

    # Final summary log for the gate stats
    accepted = sum(1 for v in splits.values() if v is not None)
    rlog("PASS-B",
         f"GATE SUMMARY: total_bad_types={total:,} | accepted_splits={accepted:,} | "
         f"gate1_garble_blocked={gate1_skipped:,} | gate3_ambig_blocked={gate3_skipped:,} | "
         f"elapsed={time.time()-t_start:.1f}s")

    return splits

# ---- PASS C: SPELL-CORRECT ----
def pass_c_correct(freq10_dict, spell, t0_global):
    if spell is None:
        return {}
    corrections = {}
    total = len(freq10_dict)
    t_start = time.time()
    last_hb = time.time()
    done = 0

    for tok in freq10_dict:
        try:
            corr = spell.correction(tok)
            if corr and corr != tok:
                corrections[tok] = corr
        except Exception:
            pass
        done += 1

        now = time.time()
        if done % 2_000 == 0 or (now - last_hb >= 15.0 and done > 0):
            rate = done / max(now - t_start, 0.001)
            rlog("PASS-C",
                 f"{done:,}/{total:,} types | corrections_so_far={len(corrections):,} | "
                 f"elapsed={now-t_start:.0f}s | rate={rate:.0f}/s",
                 status="HEARTBEAT")
            last_hb = now

    return corrections

# ================================================================
# MAIN
# ================================================================
def main():
    t0 = time.time()
    rlog("START", f"correction_passes.py v8  +LBH-guard +PassC-fragment-gate +CA-gazetteer  (de-merge Zipf>={MIN_ZIPF}; PassC dominance>={CORR_DOMINANCE}; min_freq={PASSC_MIN_FREQ})  CPU-only")

    # -- Build dictionary --
    rlog("DICT", "Building union dictionary ...")
    word_set, spell, has_wordfreq, wf_fn = build_dictionary()
    is_known = make_is_known(word_set, has_wordfreq, wf_fn)
    rlog("DICT", f"ready  static={len(word_set):,}  wordfreq={has_wordfreq}")

    # ---- parallel worker count (shared by scan, de-merge, Pass C) ----
    try:
        cpu = os.cpu_count() or 4
    except Exception:
        cpu = 4
    n_workers = int(os.environ.get("DEMERGE_WORKERS", max(2, min(cpu - 2, 12))))

    # -- Find JSON files --
    pattern = os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json")
    json_files = sorted(glob.glob(pattern))
    rlog("SCAN", f"Found {len(json_files)} consensus JSON files")

    # ================================================================
    # PARALLEL FILE-SCAN (v6): each worker reads its OWN files and computes the
    # BASELINE (hyphen-expanded) + PASS-A (rejoin) counters in a single read.
    # No raw text crosses the process boundary -- only file paths out, Counters
    # back -- so memory stays low and there is no giant pickle. Main never holds
    # all_pages. Heartbeats are emitted from the main process as files merge.
    # ================================================================
    rlog("SCAN", f"Parallel scan of {len(json_files)} files across {n_workers} workers (baseline + Pass A in one read) ...")
    baseline_freq = Counter()
    passA_freq = Counter()
    passA_lbh_counter = Counter()
    passA_adj_counter = Counter()
    t_scan = time.time()
    last_hb = time.time()
    files_done = 0

    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=n_workers, initializer=_init_worker_full) as pool:
        for bf, pf, lbh, adj in pool.imap_unordered(_scan_file, json_files, chunksize=1):
            baseline_freq.update(bf)
            passA_freq.update(pf)
            passA_lbh_counter.update(lbh)
            passA_adj_counter.update(adj)
            files_done += 1
            now = time.time()
            if files_done % 20 == 0 or now - last_hb >= 15.0 or files_done == len(json_files):
                rlog("SCAN",
                     f"{files_done}/{len(json_files)} files merged | "
                     f"baseline_unique={len(baseline_freq):,} | elapsed={now-t_scan:.0f}s",
                     status="HEARTBEAT")
                last_hb = now
    rlog("SCAN", f"scan complete  files={files_done}  t={time.time()-t0:.0f}s")

    # ---- BASELINE measure ----
    total_base, bad_types_base, bad_occ_base, pct_base = measure_counter(baseline_freq, is_known)
    rlog("BASELINE", f"total={total_base:,}  unique={len(baseline_freq):,}  bad_types={bad_types_base:,}  bad_occ={bad_occ_base:,}  pct={pct_base:.4f}%")

    # ---- PASS A measure (counters already built by the parallel scan) ----
    total_A, bad_types_A, bad_occ_A, pct_A = measure_counter(passA_freq, is_known)
    rejoin_recovered = bad_occ_base - bad_occ_A
    lbh_ops = sum(passA_lbh_counter.values())
    adj_ops  = sum(passA_adj_counter.values())
    rlog("PASS-A", f"lbh_ops={lbh_ops:,}  adj_ops={adj_ops:,}  bad_occ={bad_occ_A:,}  pct={pct_A:.4f}%  recovered={rejoin_recovered:,}")
    print(f"[PASS-A] bad_occ_after={bad_occ_A:,}  pct={pct_A:.4f}%  recovered={rejoin_recovered:,}")
    print(f"[PASS-A] Top 25 rejoined words (adj-pair):")
    for w, c in passA_adj_counter.most_common(25):
        print(f"         {w}: {c:,}")
    print(f"[PASS-A] Top 10 LBH rejoined words:")
    for w, c in passA_lbh_counter.most_common(10):
        print(f"         {w}: {c:,}")
    sys.stdout.flush()

    # ================================================================
    # PASS B: De-merge -- BOUNDED: freq >= 2 only (skip singletons)
    #         + v3 TIGHTENED GATES (garble, piece plausibility, uniqueness)
    # ================================================================
    passA_bad_all = {tok: passA_freq[tok] for tok in passA_freq if not is_known(tok)}
    passA_bad_freq2 = {tok: cnt for tok, cnt in passA_bad_all.items() if cnt >= 2}
    passA_singleton_count = len(passA_bad_all) - len(passA_bad_freq2)
    passA_singleton_occ   = sum(cnt for cnt in passA_bad_all.values() if cnt < 2)

    rlog("PASS-B",
         f"bad_types_total={len(passA_bad_all):,}  "
         f"freq>=2={len(passA_bad_freq2):,}  "
         f"singletons_skipped={passA_singleton_count:,}({passA_singleton_occ:,} occ)")
    rlog("PASS-B", "Gate 1=garble(edit1), Gate 2=piece-plausibility(>=4 or stopword), Gate 3=unique-segmentation -- starting DP ...")

    t_dm = time.time()
    try:
        cpu = os.cpu_count() or 4
    except Exception:
        cpu = 4
    n_workers = int(os.environ.get("DEMERGE_WORKERS", max(2, min(cpu - 2, 12))))
    if n_workers > 1:
        splits = build_demerge_splits_parallel(
            passA_bad_freq2, word_set, has_wordfreq, wf_fn, n_workers)
    else:
        splits = build_demerge_splits(passA_bad_freq2, is_known, word_set, spell)
    splittable = {tok: v for tok, v in splits.items() if v is not None}
    rlog("PASS-B", f"DP done: {len(splittable):,} splittable types  elapsed={time.time()-t_dm:.1f}s")

    passB_freq = Counter()
    passB_demerge_occ = Counter()

    for tok, cnt in passA_freq.items():
        if not is_known(tok) and tok in splittable:
            for piece in splittable[tok]:
                passB_freq[piece] += cnt
            passB_demerge_occ[tok] = cnt
        else:
            passB_freq[tok] += cnt

    total_B, bad_types_B, bad_occ_B, pct_B = measure_counter(passB_freq, is_known)
    demerge_recovered = bad_occ_A - bad_occ_B
    demerge_total_occ = sum(passB_demerge_occ.values())
    rlog("PASS-B", f"demerge_ops_occ={demerge_total_occ:,}  splittable_types={len(splittable):,}  bad_occ={bad_occ_B:,}  pct={pct_B:.4f}%  recovered={demerge_recovered:,}")
    print(f"[PASS-B] demerge_ops_occ={demerge_total_occ:,}  splittable_types={len(splittable):,}  bad_occ_after={bad_occ_B:,}  pct={pct_B:.4f}%  recovered={demerge_recovered:,}")
    print(f"[PASS-B] Top 25 de-merged tokens (token -> pieces : occ):")
    for tok, cnt in sorted(passB_demerge_occ.items(), key=lambda kv: -kv[1])[:25]:
        print(f"         '{tok}' -> {splittable[tok]} : {cnt:,}")
    sys.stdout.flush()

    # ================================================================
    # PASS C: Spell-correct freq >= 10 residual
    # HEARTBEAT every 2,000 types
    # ================================================================
    passB_bad_freq = {tok: passB_freq[tok] for tok in passB_freq if not is_known(tok)}
    freq10 = {tok: cnt for tok, cnt in passB_bad_freq.items() if cnt >= PASSC_MIN_FREQ}
    freq10_occ_total = sum(freq10.values())
    rlog("PASS-C", f"min_freq={PASSC_MIN_FREQ}  freq_types={len(freq10):,}  freq_occ={freq10_occ_total:,}  PARALLEL candidate-gen + corpus-freq scoring across {n_workers} workers ...")

    # FRAGMENT GATE (v8): a token that is a prefix/suffix of a LONGER common word is
    # likely a line-break piece (ablished=established, acility=facility), NOT a typo --
    # its coincidental edit-1 to a complete word would be a wrong "correction". Route
    # such tokens to review instead of correcting. Common-word reference = wordfreq top-N.
    try:
        from wordfreq import top_n_list as _tnl
        _frag_set = set(_tnl("en", 60000)) | set(LEGAL_SUPPLEMENT)
    except Exception:
        _frag_set = set(LEGAL_SUPPLEMENT)
    _frag_sorted = sorted(_frag_set)
    _frag_rev = sorted(w[::-1] for w in _frag_set)
    def _is_fragment(tok):
        if len(tok) < 4:
            return False
        i = bisect.bisect_left(_frag_sorted, tok)
        if i < len(_frag_sorted):
            w = _frag_sorted[i]
            if len(w) > len(tok) and w.startswith(tok):
                return True
        r = tok[::-1]
        j = bisect.bisect_left(_frag_rev, r)
        if j < len(_frag_rev):
            w = _frag_rev[j]
            if len(w) > len(tok) and w.startswith(r):
                return True
        return False

    # PARALLEL Pass C (v7): workers generate edit-distance candidate SETS (slow);
    # the MAIN process scores them against the CORPUS frequency distribution
    # (baseline_freq) and accepts only confident corrections. Ambiguous calls are
    # captured to a review TSV instead of being silently mis-corrected.
    corrections = {}
    accepted_reason = {}   # tok -> selection reason (provenance for the reversible layer)
    review_rows = []   # (tok, freq, best_guess, reason)
    if freq10 and n_workers > 1:
        toks = list(freq10)
        total_pc = len(toks)
        t_pc = time.time()
        last_hb = time.time()
        done = 0
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=n_workers, initializer=_init_worker_full) as pool:
            for tok, cands in pool.imap_unordered(_passC_candidates, toks, chunksize=200):
                corr, reason = _select_correction(tok, cands, baseline_freq)
                if corr is not None and _is_fragment(tok):
                    review_rows.append((tok, freq10[tok], f"fragment_gate({corr})"))
                elif corr is not None:
                    corrections[tok] = corr
                    accepted_reason[tok] = reason
                else:
                    review_rows.append((tok, freq10[tok], reason))
                done += 1
                now = time.time()
                if done % 2_000 == 0 or now - last_hb >= 15.0 or done == total_pc:
                    rate = done / max(now - t_pc, 0.001)
                    rlog("PASS-C",
                         f"{done:,}/{total_pc:,} types | accepted={len(corrections):,} | "
                         f"review={len(review_rows):,} | elapsed={now-t_pc:.0f}s | rate={rate:.0f}/s | PARALLEL",
                         status="HEARTBEAT")
                    last_hb = now
    else:
        corrections = pass_c_correct(freq10, spell, t0)

    # Capture the ambiguous/rejected freq>=10 corrections for human/LLM review
    if review_rows:
        review_path = os.path.join(OUT_DIR, "passC_review.tsv")
        try:
            with open(review_path, "w", encoding="utf-8") as f:
                f.write("token\tcorpus_freq\treason\n")
                for tok, fr, reason in sorted(review_rows, key=lambda r: -r[1]):
                    f.write(f"{tok}\t{fr}\t{reason}\n")
            rlog("PASS-C", f"review TSV: {len(review_rows):,} ambiguous/rejected -> {review_path}")
        except Exception as e:
            print(f"[WARN] passC_review write failed: {e}", file=sys.stderr)
    # PERSIST the accepted corrections (the artifact to feed the reversible layer).
    # token -> correction, with original frequency + selection provenance.
    corr_path = os.path.join(OUT_DIR, "passC_corrections.tsv")
    try:
        with open(corr_path, "w", encoding="utf-8") as f:
            f.write("token\tfreq\tcorrection\treason\n")
            for tok, corr in sorted(corrections.items(), key=lambda kv: -freq10.get(kv[0], 0)):
                f.write(f"{tok}\t{freq10.get(tok,0)}\t{corr}\t{accepted_reason.get(tok,'')}\n")
        rlog("PASS-C", f"corrections TSV: {len(corrections):,} accepted -> {corr_path}")
    except Exception as e:
        print(f"[WARN] passC_corrections write failed: {e}", file=sys.stderr)

    corrected_occ = sum(freq10[tok] for tok in corrections)

    passC_freq = Counter(passB_freq)
    for tok, corr in corrections.items():
        cnt = passC_freq.pop(tok, 0)
        passC_freq[corr] += cnt

    total_C, bad_types_C, bad_occ_C, pct_C = measure_counter(passC_freq, is_known)
    spell_recovered = bad_occ_B - bad_occ_C
    rlog("PASS-C", f"corrections={len(corrections):,}  corrected_occ={corrected_occ:,}  bad_occ={bad_occ_C:,}  pct={pct_C:.4f}%  recovered={spell_recovered:,}")

    corr_sorted = sorted(corrections.items(), key=lambda kv: -freq10.get(kv[0], 0))
    print("[PASS-C] Top 25 spell corrections (bad -> correction : freq):")
    for tok, corr in corr_sorted[:25]:
        print(f"         '{tok}' -> '{corr}' : {freq10[tok]:,}")
    sys.stdout.flush()

    no_corr_freq10 = {tok: cnt for tok, cnt in freq10.items() if tok not in corrections}
    print(f"[PASS-C] freq>=10 with no correction: {len(no_corr_freq10):,} types  ({sum(no_corr_freq10.values()):,} occ)")
    print("[PASS-C] Top 20 uncorrectable freq>=10 tokens:")
    for tok, cnt in sorted(no_corr_freq10.items(), key=lambda kv: -kv[1])[:20]:
        print(f"         '{tok}': {cnt:,}")
    sys.stdout.flush()

    # ================================================================
    # RESIDUAL ANALYSIS
    # ================================================================
    passC_bad_freq = {tok: passC_freq[tok] for tok in passC_freq if not is_known(tok)}
    singletons  = {tok: cnt for tok, cnt in passC_bad_freq.items() if cnt == 1}
    low_freq_2  = {tok: cnt for tok, cnt in passC_bad_freq.items() if 2 <= cnt <= 9}
    high_freq10 = {tok: cnt for tok, cnt in passC_bad_freq.items() if cnt >= 10}

    print("\n[RESIDUAL] True residual breakdown:")
    print(f"  singletons (freq=1): {len(singletons):,} types  {sum(singletons.values()):,} occ")
    print(f"  low-freq  (2-9):     {len(low_freq_2):,} types  {sum(low_freq_2.values()):,} occ")
    print(f"  high-freq (>=10):    {len(high_freq10):,} types  {sum(high_freq10.values()):,} occ")

    print("\n[RESIDUAL] Top 30 residual tokens by frequency:")
    for tok, cnt in sorted(passC_bad_freq.items(), key=lambda kv: -kv[1])[:30]:
        print(f"         '{tok}': {cnt:,}")

    print("\n[RESIDUAL] 20 sample singleton tokens (OCR garbage):")
    random.seed(42)
    sample_s = random.sample(list(singletons.keys()), min(20, len(singletons)))
    for tok in sample_s:
        print(f"         '{tok}'")
    sys.stdout.flush()

    # ================================================================
    # FINAL SUMMARY TABLE
    # ================================================================
    total_recovered = rejoin_recovered + demerge_recovered + spell_recovered
    print("\n" + "=" * 72)
    print("FINAL BEFORE / AFTER ACCOUNTING")
    print("=" * 72)
    print(f"  Total corpus tokens (baseline):  {total_base:>14,}")
    print(f"  Unique token types (baseline):   {len(baseline_freq):>14,}")
    print()
    print(f"  BASELINE (no correction):        bad_occ={bad_occ_base:>11,}  types={bad_types_base:>7,}  {pct_base:.4f}%")
    print(f"  After Pass A (rejoin):           bad_occ={bad_occ_A:>11,}  types={bad_types_A:>7,}  {pct_A:.4f}%   recovered={rejoin_recovered:,}")
    print(f"  After Pass B (demerge v3):       bad_occ={bad_occ_B:>11,}  types={bad_types_B:>7,}  {pct_B:.4f}%   recovered={demerge_recovered:,}")
    print(f"  After Pass C (spell >= 10):      bad_occ={bad_occ_C:>11,}  types={bad_types_C:>7,}  {pct_C:.4f}%   recovered={spell_recovered:,}")
    print()
    print(f"  Total recovered (A+B+C):         {total_recovered:>14,} occurrences")
    print(f"  TRUE RESIDUAL:                   bad_occ={bad_occ_C:>11,}  types={bad_types_C:>7,}  {pct_C:.4f}%")
    print("=" * 72)
    print()
    print(f"  ~20 residual examples (top by freq):")
    for tok, cnt in sorted(passC_bad_freq.items(), key=lambda kv: -kv[1])[:20]:
        print(f"    '{tok}': {cnt:,}")
    print("=" * 72)
    sys.stdout.flush()

    rlog("SUMMARY", (
        f"baseline={bad_occ_base:,}  "
        f"after_A={bad_occ_A:,}(recovered={rejoin_recovered:,})  "
        f"after_B={bad_occ_B:,}(recovered={demerge_recovered:,})  "
        f"after_C={bad_occ_C:,}(recovered={spell_recovered:,})  "
        f"true_residual_pct={pct_C:.4f}%  "
        f"residual_types={bad_types_C:,}"
    ))

    # Write residual TSV
    residual_path = os.path.join(OUT_DIR, "residual_bad_words.tsv")
    with open(residual_path, "w", encoding="utf-8") as f:
        f.write("token\tfreq\tcategory\n")
        for tok, cnt in sorted(passC_bad_freq.items(), key=lambda kv: -kv[1]):
            cat = "singleton" if cnt == 1 else ("low_freq" if cnt < 10 else "high_freq")
            f.write(f"{tok}\t{cnt}\t{cat}\n")
    print(f"[OUT] residual TSV: {residual_path}  ({len(passC_bad_freq):,} rows)")

    wall = time.time() - t0
    rlog("DONE", f"wall_time={wall:.0f}s  true_residual_pct={pct_C:.4f}%  residual_types={bad_types_C:,}  residual_occ={bad_occ_C:,}")
    print(f"\n[DONE] Wall time: {wall:.0f}s")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
