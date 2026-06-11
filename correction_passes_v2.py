"""
correction_passes.py -- Three deterministic correction passes on OCR corpus
CPU-only (CUDA_VISIBLE_DEVICES='').

Pass A: Dehyphenation / rejoin (line-break hyphens + adjacent token rejoins)
Pass B: De-merge (split run-together tokens into known words) -- freq>=2 only
Pass C: Spell-correct high-frequency residuals (freq >= 10)

REDESIGN v2:
- PERIODIC HEARTBEAT logging inside every long loop (never silent >~15s)
- Pass B bounded: only bad-word types with corpus_freq >= 2 (skip singletons)
- Pass B DP capped at 2-3 segments, each piece >= 3 chars (iterative, fast)
- All pass-boundary summaries retained
- Final accounting: baseline -> after A -> after B -> after C with ~20 residual examples

Writes run log to C:/Users/patolex/PatoLex-scratch/_vocab/correction-pass-run.log
"""

import os, sys, json, re, glob, time, unicodedata
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
import random

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
}

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

# ---- PASS B: DE-MERGE DP (fast: 2-3 segments max, each piece >= 3 chars) ----
# BOUNDED: only processes types with corpus_freq >= 2 (caller filters singletons)
def _try_split_2(tok, is_known):
    """Try all 2-segment splits. Returns list of 2 pieces or None."""
    n = len(tok)
    for i in range(3, n - 2):        # each piece >= 3 chars
        left  = tok[:i]
        right = tok[i:]
        if len(right) >= 3 and is_known(left) and is_known(right):
            return [left, right]
    return None

def _try_split_3(tok, is_known):
    """Try all 3-segment splits. Returns list of 3 pieces or None."""
    n = len(tok)
    for i in range(3, n - 5):        # left >= 3, leaves >= 6 for mid+right
        for j in range(i + 3, n - 2):  # mid >= 3, right >= 3
            left  = tok[:i]
            mid   = tok[i:j]
            right = tok[j:]
            if len(right) >= 3 and is_known(left) and is_known(mid) and is_known(right):
                return [left, mid, right]
    return None

def build_demerge_splits(bad_token_freq, is_known):
    """
    bad_token_freq: dict {tok: corpus_freq} -- ONLY types with freq >= 2.
    Returns splits dict {tok: [piece, ...] or None}.

    Uses fast 2-then-3 segment approach (no full DP), each piece >= 3 chars.
    Logs heartbeat every 20,000 types.
    """
    splits = {}
    total = len(bad_token_freq)
    t_start = time.time()
    last_hb = time.time()

    for i, tok in enumerate(bad_token_freq):
        n = len(tok)
        if n < 6:
            splits[tok] = None
        else:
            result = _try_split_2(tok, is_known)
            if result is None and n >= 9:
                result = _try_split_3(tok, is_known)
            splits[tok] = result

        # Heartbeat every 20,000 types OR if >15 seconds have passed
        now = time.time()
        if (i + 1) % 20_000 == 0 or (now - last_hb >= 15.0 and i > 0):
            done_so_far = sum(1 for v in splits.values() if v is not None)
            rate = (i + 1) / max(now - t_start, 0.001)
            rlog("PASS-B",
                 f"{i+1:,}/{total:,} types | splittable_so_far={done_so_far:,} | "
                 f"elapsed={now-t_start:.0f}s | rate={rate:.0f}/s",
                 status="HEARTBEAT")
            last_hb = now

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
    rlog("START", "correction_passes.py v2  CUDA_VISIBLE_DEVICES=''  CPU-only  heartbeat+bounded-PassB")

    # -- Build dictionary --
    rlog("DICT", "Building union dictionary ...")
    word_set, spell, has_wordfreq, wf_fn = build_dictionary()
    is_known = make_is_known(word_set, has_wordfreq, wf_fn)
    rlog("DICT", f"ready  static={len(word_set):,}  wordfreq={has_wordfreq}")

    # -- Find JSON files --
    pattern = os.path.join(SCRATCH, "production-*", "ocr_consensus", "page_ocr_results.json")
    json_files = sorted(glob.glob(pattern))
    rlog("SCAN", f"Found {len(json_files)} consensus JSON files")

    # -- Load all page texts (heartbeat every 50 files) --
    rlog("LOAD", f"Loading {len(json_files)} JSON files ...")
    all_pages = []   # list of (label, page_key, raw_text)
    files_done = 0
    t_load = time.time()
    last_hb = time.time()

    for jf in json_files:
        label = os.path.basename(os.path.dirname(os.path.dirname(jf)))
        try:
            with open(jf, encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[WARN] {jf}: {e}", file=sys.stderr)
            continue
        for pk, po in data.items():
            txt = (po.get("consensus_text") or "").strip()
            if txt:
                all_pages.append((label, pk, txt))
        files_done += 1
        now = time.time()
        if files_done % 50 == 0 or (now - last_hb >= 15.0):
            rlog("LOAD",
                 f"{files_done}/{len(json_files)} files | pages={len(all_pages):,} | "
                 f"elapsed={now-t_load:.0f}s",
                 status="HEARTBEAT")
            last_hb = now

    rlog("LOAD", f"pages={len(all_pages):,}  files={files_done}  t={time.time()-t0:.0f}s")

    total_pages = len(all_pages)

    # ================================================================
    # BASELINE: vocab_diff.py-compatible tokenisation (with hyphen expansion)
    # ================================================================
    rlog("BASELINE", "Tokenising corpus (with hyphen expansion) ...")
    baseline_freq = Counter()
    t_base = time.time()
    last_hb = time.time()

    for idx, (_, _, text) in enumerate(all_pages):
        for tok in tokenise_baseline(text):
            baseline_freq[tok] += 1
        now = time.time()
        if (idx + 1) % 25_000 == 0 or (now - last_hb >= 15.0 and idx > 0):
            rlog("BASELINE",
                 f"{idx+1:,}/{total_pages:,} pages | unique_so_far={len(baseline_freq):,} | "
                 f"elapsed={now-t_base:.0f}s",
                 status="HEARTBEAT")
            last_hb = now

    total_base, bad_types_base, bad_occ_base, pct_base = measure_counter(baseline_freq, is_known)
    rlog("BASELINE", f"total={total_base:,}  unique={len(baseline_freq):,}  bad_types={bad_types_base:,}  bad_occ={bad_occ_base:,}  pct={pct_base:.4f}%")

    # ================================================================
    # PASS A: Dehyphenation / adjacent-token rejoin
    # HEARTBEAT every 25,000 pages
    # ================================================================
    rlog("PASS-A", f"Starting dehyphenation + adjacent-pair rejoin over {total_pages:,} pages ...")
    passA_freq = Counter()
    passA_lbh_counter = Counter()
    passA_adj_counter = Counter()
    t_A = time.time()
    last_hb = time.time()
    rejoin_count = 0

    for idx, (_, _, text) in enumerate(all_pages):
        # Step 1: collapse line-break hyphens
        def _lbh_sub(m):
            left = m.group(1)
            right_start = m.group(2)
            joined = left + right_start
            passA_lbh_counter[joined.lower()] += 1
            return joined
        text2 = re.sub(r'([A-Za-z\xc0-\xff]+)-[ \t]*\r?\n[ \t]*([A-Za-z\xc0-\xff])', _lbh_sub, text)

        # Step 2: tokenise and do adjacent-pair rejoin
        tokens = list(tokenise_raw(text2))
        i = 0
        while i < len(tokens):
            if i + 1 < len(tokens):
                low0 = tokens[i][3]
                low1 = tokens[i+1][3]
                joined = low0 + low1
                if (len(joined) >= 4
                        and is_known(joined)
                        and (not is_known(low0) or not is_known(low1))):
                    passA_freq[joined] += 1
                    passA_adj_counter[joined] += 1
                    rejoin_count += 1
                    i += 2
                    continue
            passA_freq[tokens[i][3]] += 1
            i += 1

        # Heartbeat every 25,000 pages OR every 15 seconds
        now = time.time()
        if (idx + 1) % 25_000 == 0 or (now - last_hb >= 15.0 and idx > 0):
            lbh_so_far = sum(passA_lbh_counter.values())
            adj_so_far = sum(passA_adj_counter.values())
            rlog("PASS-A",
                 f"{idx+1:,}/{total_pages:,} pages | lbh_so_far={lbh_so_far:,} | "
                 f"adj_rejoins={adj_so_far:,} | elapsed={now-t_A:.0f}s",
                 status="HEARTBEAT")
            last_hb = now

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
    # ================================================================
    passA_bad_all = {tok: passA_freq[tok] for tok in passA_freq if not is_known(tok)}
    passA_bad_freq2 = {tok: cnt for tok, cnt in passA_bad_all.items() if cnt >= 2}
    passA_singleton_count = len(passA_bad_all) - len(passA_bad_freq2)
    passA_singleton_occ   = sum(cnt for cnt in passA_bad_all.values() if cnt < 2)

    rlog("PASS-B",
         f"bad_types_total={len(passA_bad_all):,}  "
         f"freq>=2={len(passA_bad_freq2):,}  "
         f"singletons_skipped={passA_singleton_count:,}({passA_singleton_occ:,} occ)")

    t_dm = time.time()
    splits = build_demerge_splits(passA_bad_freq2, is_known)
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
    freq10 = {tok: cnt for tok, cnt in passB_bad_freq.items() if cnt >= 10}
    freq10_occ_total = sum(freq10.values())
    rlog("PASS-C", f"freq10_types={len(freq10):,}  freq10_occ={freq10_occ_total:,}  starting spell-correct ...")

    corrections = pass_c_correct(freq10, spell, t0)
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
    print(f"  After Pass B (demerge freq>=2):  bad_occ={bad_occ_B:>11,}  types={bad_types_B:>7,}  {pct_B:.4f}%   recovered={demerge_recovered:,}")
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
