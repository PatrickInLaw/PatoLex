"""
vocab_diff.py -- Corpus-wide "bad words" vocabulary diff
CPU-only. No GPU. Run on the 5090.

Reads all production-*/ocr_consensus/page_ocr_results.json files,
tokenises every page's consensus_text, diffs against an English dictionary,
and writes bad_words.tsv to C:\\Users\\patolex\\PatoLex-scratch\\_vocab\\

Usage:
    python vocab_diff.py [--scratch C:\\path\\to\\PatoLex-scratch] [--out C:\\path\\to\\_vocab]
                         [--log docs/80_PROJECT_HISTORY/run-logs/vocab-diff-run.log]
"""

import os
import sys
import json
import re
import glob
import unicodedata
import time
import argparse
from collections import defaultdict

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_SCRATCH = r"C:\Users\patolex\PatoLex-scratch"
DEFAULT_OUT     = r"C:\Users\patolex\PatoLex-scratch\_vocab"

LEGAL_SUPPLEMENT = {
    # Common legal/archaic terms that real dictionaries miss
    "hereinafter", "hereinbefore", "hereto", "hereunto", "heretofore",
    "hereunder", "herewith", "herein", "hereof", "thereof", "therein",
    "thereto", "thereunder", "therewith", "thereon", "therefor", "thereby",
    "thereat", "thereabout", "thereabouts", "therefrom", "thereupon",
    "whereof", "wherein", "whereto", "whereunder", "whereupon", "whereas",
    "wherefore", "aforesaid", "forthwith", "notwithstanding", "aforementioned",
    "hitherto", "thenceforth", "thenceforward", "suchlike",
    # California-specific / session-law boilerplate
    "chaptered", "uncodified", "appropriation", "appropriated",
    "statutes", "legislature", "legislative", "assemblyman", "assemblywoman",
    "assemblymen", "assemblymembers", "senate", "senator", "senators",
    "governor", "controller", "treasurer", "comptroller", "superintendent",
    "commissioners", "commissioner", "departmental", "subdivision",
    "subdivisions", "subparagraph", "subparagraphs", "subsection",
    "subsections", "enactment", "enactments", "reenactment", "reenactments",
    "codify", "codified", "codification", "uncodified", "recission",
    "rescission", "rescind", "rescinded",
}


# ---------------------------------------------------------------------------
# Run-logging
# ---------------------------------------------------------------------------
DEFAULT_LOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "80_PROJECT_HISTORY", "run-logs", "vocab-diff-run.log"
)

def _pt_label():
    """Return a Pacific-time timestamp string (best-effort; falls back to local)."""
    try:
        from datetime import datetime, timezone, timedelta
        # PT = UTC-7 (PDT) or UTC-8 (PST); use UTC-7 for simplicity (close enough)
        pt_offset = timedelta(hours=-7)
        now = datetime.now(timezone.utc).astimezone(timezone(pt_offset))
        return now.strftime("%Y-%m-%d %H:%M PT")
    except Exception:
        import datetime
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M local")


def run_log(log_path, phase, description, status="OK"):
    """Append a single timestamped line to the run-log file."""
    if not log_path:
        return
    line = f"[{_pt_label()}] {phase} | {description} | {status}\n"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"[WARN] run-log write failed ({log_path}): {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Vocabulary diff for OCR corpus")
    p.add_argument("--scratch", default=DEFAULT_SCRATCH)
    p.add_argument("--out",     default=DEFAULT_OUT)
    p.add_argument("--log",     default=DEFAULT_LOG,
                   help="Path to run-log file (appended). Pass empty string to disable.")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Dictionary building
# ---------------------------------------------------------------------------
def build_dictionary():
    """
    Return (word_set, spell_checker_or_None) where word_set is the UNION of:
      - pyspellchecker  (broad coverage, ~100k+ words with frequency data)
      - nltk words corpus (~236k words, including rare/archaic/technical terms)
      - wordfreq        (very broad coverage; any word with freq > 0 counts)
      - LEGAL_SUPPLEMENT
    A token is "known" if it appears in ANY of these sources.
    Returns (word_set, spell_obj) so the caller can also do per-token freq lookups.
    """
    word_set = set()
    source_desc = []
    spell = None

    # --- pyspellchecker ---
    try:
        from spellchecker import SpellChecker
        spell = SpellChecker()
        # spell.word_frequency contains all known words; iterate its keys
        spell_words = set(spell.word_frequency.dictionary.keys())
        word_set |= spell_words
        source_desc.append(f"pyspellchecker ({len(spell_words):,})")
    except Exception as e:
        print(f"[WARN] pyspellchecker not available: {e}", file=sys.stderr)

    # --- nltk words corpus (catches rare/archaic/technical real words) ---
    try:
        from nltk.corpus import words as nltk_words
        nltk_set = set(w.lower() for w in nltk_words.words())
        before = len(word_set)
        word_set |= nltk_set
        added = len(word_set) - before
        source_desc.append(f"nltk-words ({len(nltk_set):,} raw, +{added:,} new)")
        print(f"[DICT] nltk words corpus: {len(nltk_set):,} words loaded, {added:,} new after pyspellchecker union")
    except LookupError:
        print("[WARN] nltk 'words' corpus not downloaded; run: python -c \"import nltk; nltk.download('words')\"", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] nltk words corpus not available: {e}", file=sys.stderr)

    # --- wordfreq: add any token with nonzero frequency ---
    # We cannot enumerate all wordfreq tokens, so this source is applied
    # per-token in is_known_word() below.  Record it as a planned source.
    source_desc.append("wordfreq (per-token, word_frequency > 0)")

    # --- /usr/share/dict/words (Unix fallback) ---
    for dict_path in ["/usr/share/dict/words", "/usr/dict/words"]:
        if os.path.exists(dict_path):
            try:
                with open(dict_path, encoding="utf-8", errors="replace") as f:
                    extras = {line.strip().lower() for line in f if line.strip().isalpha()}
                before = len(word_set)
                word_set |= extras
                source_desc.append(f"{dict_path} (+{len(word_set)-before:,})")
            except Exception as e:
                print(f"[WARN] Could not read {dict_path}: {e}", file=sys.stderr)

    # --- Legal supplement ---
    word_set |= LEGAL_SUPPLEMENT
    source_desc.append(f"legal-supplement ({len(LEGAL_SUPPLEMENT)})")

    if not word_set:
        raise RuntimeError("No dictionary available — install pyspellchecker (pip install pyspellchecker)")

    print(f"[DICT] Static dictionary size: {len(word_set):,} words (wordfreq adds more per-token)")
    print(f"[DICT] Sources: {'; '.join(source_desc)}")
    return word_set, spell


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------
# Matches runs of ASCII/accented letters, optionally with interior hyphens
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ]+(?:-[A-Za-zÀ-ÿ]+)*")

def tokenise(text):
    """
    Yield (lowercase_token, original_token) pairs.
    - Strips Unicode control chars first
    - Keeps hyphenated forms AND each component separately
    - Drops pure-numeric and pure-punctuation tokens
    """
    # Normalise: NFC, drop control characters
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", text)

    for m in _TOKEN_RE.finditer(text):
        orig = m.group(0)
        low  = orig.lower()

        # Must be at least 2 characters to be worth indexing
        if len(low) < 2:
            continue

        yield low, orig

        # Also yield hyphen-split components (if hyphenated)
        if "-" in low:
            for part in low.split("-"):
                if len(part) >= 2:
                    yield part, part


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = parse_args()

    log = args.log if args.log else None

    t0 = time.time()

    # Ensure no GPU is touched — set CUDA_VISIBLE_DEVICES to empty
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["PYTORCH_NO_CUDA_MEMORY_CACHING"] = "1"

    print(f"[START] vocab_diff.py  scratch={args.scratch}  out={args.out}")
    print(f"[ENV]   CUDA_VISIBLE_DEVICES=''  (GPU disabled)")
    run_log(log, "START", f"vocab_diff.py  scratch={args.scratch}  out={args.out}")

    # -----------------------------------------------------------------------
    # 1. Find all consensus files
    # -----------------------------------------------------------------------
    pattern = os.path.join(args.scratch, "production-*", "ocr_consensus", "page_ocr_results.json")
    json_files = sorted(glob.glob(pattern))
    print(f"[SCAN]  Found {len(json_files)} consensus JSON files")

    run_log(log, "SCAN", f"Found {len(json_files)} consensus JSON files  scratch={args.scratch}")
    if not json_files:
        print("[ERROR] No files found. Check --scratch path.", file=sys.stderr)
        run_log(log, "SCAN", f"No files found at {args.scratch} -- check path", "FAIL")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # 2. Build vocab maps
    #    corpus_freq[tok]  = total occurrences across all pages
    #    doc_freq[tok]     = number of distinct labels (volumes) containing tok
    #    examples[tok]     = (label, page_key)  — first seen
    # -----------------------------------------------------------------------
    corpus_freq  = defaultdict(int)
    doc_freq     = defaultdict(set)   # value = set of labels
    examples     = {}                 # tok -> (label, page_key)
    total_tokens = 0
    files_processed = 0

    for jf in json_files:
        # Derive label from path: production-XXXX
        label = os.path.basename(os.path.dirname(os.path.dirname(jf)))

        try:
            with open(jf, encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[WARN] Could not load {jf}: {e}", file=sys.stderr)
            continue

        for page_key, page_obj in data.items():
            text = page_obj.get("consensus_text") or ""
            if not text:
                continue
            for low, orig in tokenise(text):
                corpus_freq[low] += 1
                doc_freq[low].add(label)
                if low not in examples:
                    examples[low] = (label, page_key)
                total_tokens += 1

        files_processed += 1
        if files_processed % 20 == 0:
            elapsed = time.time() - t0
            print(f"[PROG]  {files_processed}/{len(json_files)} files  "
                  f"{total_tokens:,} tokens  {elapsed:.0f}s elapsed")
            run_log(log, "PROGRESS",
                    f"{files_processed}/{len(json_files)} files  "
                    f"{total_tokens:,} tokens  {elapsed:.0f}s elapsed")

    t1 = time.time()
    print(f"[DONE]  Processed {files_processed} files in {t1-t0:.1f}s")
    print(f"[STATS] Total tokens scanned : {total_tokens:,}")
    print(f"[STATS] Unique tokens        : {len(corpus_freq):,}")
    run_log(log, "SCAN-DONE",
            f"Processed {files_processed} files in {t1-t0:.1f}s  "
            f"total_tokens={total_tokens:,}  unique={len(corpus_freq):,}")

    # -----------------------------------------------------------------------
    # 3. Build dictionary (union: pyspellchecker + wordfreq + legal supplement)
    # -----------------------------------------------------------------------
    dictionary, spell = build_dictionary()

    try:
        from wordfreq import word_frequency
        has_wordfreq = True
        print("[DICT] wordfreq available (membership check + frequency signal)")
    except ImportError:
        has_wordfreq = False
        print("[DICT] wordfreq not available; using static dictionary only")

    def is_known(tok):
        """True if token is in any source of the union dictionary."""
        if tok in dictionary:
            return True
        # wordfreq per-token check: nonzero frequency = known word
        if has_wordfreq and word_frequency(tok, "en") > 0:
            return True
        return False

    # -----------------------------------------------------------------------
    # 4. Diff: tokens NOT in the union dictionary = bad-word candidates
    #    Keep ALL — do not filter on frequency
    # -----------------------------------------------------------------------
    good = []
    bad  = []
    for tok, freq in corpus_freq.items():
        # A token is "good" if it passes the union check.
        # Hyphenated tokens were split into components during tokenisation
        # and those appear separately in corpus_freq, so we just check as-is.
        if is_known(tok):
            good.append(tok)
        else:
            bad.append(tok)

    print(f"[STATS] Dictionary match (good) : {len(good):,}")
    print(f"[STATS] Bad-word candidates     : {len(bad):,}")
    print(f"[STATS] Dict source size        : {len(dictionary):,}")
    run_log(log, "DIFF",
            f"dict_size={len(dictionary):,}  good={len(good):,}  bad_candidates={len(bad):,}")

    # -----------------------------------------------------------------------
    # 5. Sort bad words by corpus_freq descending
    # -----------------------------------------------------------------------
    bad.sort(key=lambda t: -corpus_freq[t])

    # -----------------------------------------------------------------------
    # 6. Write output
    # -----------------------------------------------------------------------
    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "bad_words.tsv")

    with open(out_path, "w", encoding="utf-8") as f:
        # Header
        if has_wordfreq:
            f.write("token\tcorpus_freq\tdoc_freq\texternal_wordfreq\texample_label\texample_page\n")
        else:
            f.write("token\tcorpus_freq\tdoc_freq\texample_label\texample_page\n")

        for tok in bad:
            cf  = corpus_freq[tok]
            df  = len(doc_freq[tok])
            ex_label, ex_page = examples.get(tok, ("?", "?"))
            if has_wordfreq:
                wf = word_frequency(tok, "en")
                f.write(f"{tok}\t{cf}\t{df}\t{wf:.2e}\t{ex_label}\t{ex_page}\n")
            else:
                f.write(f"{tok}\t{cf}\t{df}\t{ex_label}\t{ex_page}\n")

    print(f"[OUT]   Written: {out_path}")
    print(f"[OUT]   Rows: {len(bad):,}")
    run_log(log, "OUTPUT", f"Written {len(bad):,} bad-word rows to {out_path}")

    # -----------------------------------------------------------------------
    # 7. Print sample rows for the report
    # -----------------------------------------------------------------------
    print("\n=== SAMPLE: TOP 15 BY CORPUS FREQ (likely real words / place names) ===")
    header = "token\tcorpus_freq\tdoc_freq" + ("\texternal_wordfreq" if has_wordfreq else "") + "\texample"
    print(header)
    for tok in bad[:15]:
        cf = corpus_freq[tok]
        df = len(doc_freq[tok])
        ex = f"{examples[tok][0]}:p{examples[tok][1]}"
        if has_wordfreq:
            wf = word_frequency(tok, "en")
            print(f"{tok}\t{cf}\t{df}\t{wf:.2e}\t{ex}")
        else:
            print(f"{tok}\t{cf}\t{df}\t{ex}")

    print("\n=== SAMPLE: BOTTOM 15 BY CORPUS FREQ (likely OCR garbage / singletons) ===")
    print(header)
    for tok in bad[-15:]:
        cf = corpus_freq[tok]
        df = len(doc_freq[tok])
        ex = f"{examples[tok][0]}:p{examples[tok][1]}"
        if has_wordfreq:
            wf = word_frequency(tok, "en")
            print(f"{tok}\t{cf}\t{df}\t{wf:.2e}\t{ex}")
        else:
            print(f"{tok}\t{cf}\t{df}\t{ex}")

    t2 = time.time()
    print(f"\n[TOTAL] Wall time: {t2-t0:.1f}s")
    print(f"[CPU]   CUDA_VISIBLE_DEVICES was '' (no GPU used)")
    run_log(log, "DONE",
            f"wall_time={t2-t0:.1f}s  total_tokens={total_tokens:,}  "
            f"unique={len(corpus_freq):,}  dict_matched={len(good):,}  "
            f"bad_words={len(bad):,}  out={out_path}")


if __name__ == "__main__":
    main()
