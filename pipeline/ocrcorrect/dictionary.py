"""
dictionary.py -- the canonical import surface for the correction dictionary. For now it re-exports
`build_dictionary` (whose body still lives in correction_passes.py; it physically moves here in the
package reorg, Step B) and provides `build_sorted_common`, the common-word sorted-list builder that was
copy-pasted into correction_cascade._init and recoverable_compose._init. De-duplication, not logic change.

`build_dictionary()` returns (word_set, spell, has_wordfreq, wf_fn):
  word_set      frozen-able set of known words (pyspellchecker + nltk + wordfreq-availability + LEGAL_SUPPLEMENT
                + CA gazetteer + validated corpus additions)
  spell         the pyspellchecker SpellChecker (or None)
  has_wordfreq  whether wordfreq is importable (per-token frequency available)
  wf_fn         wordfreq.word_frequency (or None)
"""
from ocrcorrect.correction_passes import build_dictionary, LEGAL_SUPPLEMENT  # noqa: F401 (re-export)

def build_sorted_common(word_set, zipf_fn, min_len=6, min_zipf=3.0):
    """The fragment-matcher reference lists: common alphabetic words >= min_len with zipf >= min_zipf,
    sorted forward and reversed. Used by reunify A4 + the affix guards. Returns (sorted, sorted_rev)."""
    common = [w for w in word_set if w.isalpha() and len(w) >= min_len and zipf_fn(w, "en") >= min_zipf]
    return sorted(common), sorted(w[::-1] for w in common)
