"""
build_corpus_freq.py -- one-time precompute of the CORPUS-NATIVE frequency model that drives the
edit-2 SymSpell corrector. Counts KNOWN tokens across the persisted out_split stage (the input to
autocorrect) -> _cascade/corpus_freq.json = {word: count} for words attested >= MIN_TARGET_COUNT.
Run this ONCE on the 5090 before re-running the cascade from autocorrect.
"""
import os, time
SCRATCH = r"C:\Users\patolex\PatoLex-scratch"
CASCADE = os.path.join(SCRATCH, "_cascade")
OUT_SPLIT = os.path.join(CASCADE, "out_split")
FREQ_PATH = os.path.join(CASCADE, "corpus_freq.json")
LOG = os.path.join(CASCADE, "corpus-freq-run.log")

def _log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.rstrip(), flush=True)

def main():
    t0 = time.time()
    _log("building dictionary...")
    from ocrcorrect.dictionary import build_dictionary
    ws, _spell, has_wf, wf = build_dictionary()
    WS = frozenset(ws)
    # STRICT membership only (the 334k static dict: pyspell + nltk + validated additions/names).
    # NOT wordfreq>0 -- that path admits OCR-error/misspelled words as bogus correction targets.
    def strong(t):
        return t in WS
    _log("aggregating strong-dict corpus frequency from out_split...")
    from ocrcorrect.symspell_e2 import build_corpus_freq, MIN_TARGET_COUNT
    tgt = build_corpus_freq(OUT_SPLIT, strong, FREQ_PATH)
    _log(f"DONE: {len(tgt):,} target words (count >= {MIN_TARGET_COUNT}) -> {FREQ_PATH}  | {time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
