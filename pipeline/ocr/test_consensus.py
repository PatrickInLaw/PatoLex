"""
test_consensus.py -- Unit tests for pipeline/consensus.py (Phase B Hans 2nd pass).
===============================================================================
Reproduces Hans's S1-A corruption case and confirms the fix.

S1-A (CRITICAL): the old spine = "engine with most tokens" privileged the
WORST-segmented engine, because OCR word-splitting ("Weights" -> "W eights")
inflates the token count. With docTR as the (bad) spine, the consensus committed
both fragments -> "Sealer of Weights eights and Measures": a phantom "eights"
token that no engine actually read as a word.

The fix:
  (a) choose the spine by a fragmentation-ROBUST criterion (median token count
      across engines, tie-broken by char length then engine priority), so a
      single over-segmented engine cannot become the spine; AND
  (b) a spine-merge pass: when two ADJACENT spine tokens concatenate to a token
      that >=2 engines agree on as a single word, collapse them into one
      committed token (faithful surface from a real engine).

Run:  python -m pytest pipeline/test_consensus.py -q
  or: python pipeline/test_consensus.py   (built-in runner, no pytest needed)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# cc019: also put pipeline/ on the path. One test in this file reaches code that
# does `import config` at module level, and without this it errored with
# ModuleNotFoundError (8/9 passing) -- reported as a "known failure" for long
# enough that it stopped being read as a bug. Same rot class that left
# test_date_parser_fix.py dead for a month.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from consensus import (  # noqa: E402
    build_consensus, _choose_spine, tokenize, SINGLE_ENGINE_CONFIDENCE,
)


# --------------------------------------------------------------------------- #
# Hans's exact reproduction case
# --------------------------------------------------------------------------- #
# tesseract + surya read "Weights" as one token; docTR splits it "W eights".
# docTR therefore has the MOST tokens (the word-split inflates its count), so
# under the OLD rule docTR became the spine and the consensus committed the
# split as two positions -> phantom "eights".
HANS_TESS = "Sealer of Weights and Measures"
HANS_SURYA = "Sealer of Weights and Measures"
HANS_DOCTR = "Sealer of W eights and Measures"


def test_hans_word_split_no_phantom_fragment():
    """FIXED consensus must commit 'Weights' once, with no phantom 'eights'."""
    r = build_consensus(
        {"tesseract": HANS_TESS, "doctr": HANS_DOCTR, "surya": HANS_SURYA}
    )
    committed = r.committed_text
    surfaces = [t.surface for t in r.tokens]

    # The corruption signature: a standalone 'eights' fragment, or 'W' as its
    # own token, must NOT appear.
    assert "eights" not in surfaces, (
        f"phantom fragment 'eights' was committed: {surfaces!r}"
    )
    assert "W" not in surfaces, f"orphan 'W' fragment committed: {surfaces!r}"

    # 'Weights' must appear exactly once as a whole word.
    assert surfaces.count("Weights") == 1, (
        f"expected exactly one whole 'Weights', got {surfaces!r}"
    )

    # Whole committed text is the faithful phrase, no duplication/garble.
    assert committed == "Sealer of Weights and Measures", (
        f"committed text corrupted: {committed!r}"
    )


def test_hans_spine_not_the_oversegmented_engine():
    """The over-segmented engine (docTR, most tokens) must NOT be chosen spine."""
    engine_tokens = {
        "tesseract": tokenize(HANS_TESS),
        "doctr": tokenize(HANS_DOCTR),
        "surya": tokenize(HANS_SURYA),
    }
    spine = _choose_spine(engine_tokens)
    assert spine != "doctr", (
        f"over-segmented docTR was chosen as spine (the S1-A bug): {spine!r}"
    )


def test_determinism():
    """Same input -> identical committed text on repeat runs."""
    inp = {"tesseract": HANS_TESS, "doctr": HANS_DOCTR, "surya": HANS_SURYA}
    r1 = build_consensus(inp)
    r2 = build_consensus(inp)
    assert r1.committed_text == r2.committed_text


def test_faithful_surface_from_real_engine():
    """Every committed surface must come from some engine's actual token."""
    inp = {"tesseract": HANS_TESS, "doctr": HANS_DOCTR, "surya": HANS_SURYA}
    r = build_consensus(inp)
    engine_surfaces = set()
    for t in (HANS_TESS, HANS_SURYA, HANS_DOCTR):
        engine_surfaces.update(tokenize(t))
    for tok in r.tokens:
        assert tok.surface in engine_surfaces, (
            f"committed surface {tok.surface!r} not from any engine "
            f"(synthesised?): engine surfaces {sorted(engine_surfaces)!r}"
        )


def test_majority_vote_still_corrects_misreads():
    """Regression guard: the normal 2-of-3 majority correction still works."""
    inp = {
        "tesseract": "AN ACT fixing the time for Acts and Joint Resolutions.",
        "doctr": "AN ACT firing the lime for Acts and Joint Resolutions.",
        "surya": "AN ACT fixing the time for Acts and Joint Resolutions.",
    }
    r = build_consensus(inp)
    assert "fixing" in r.committed_text
    assert "firing" not in r.committed_text
    assert "lime" not in r.committed_text


def test_no_double_split_when_two_engines_split():
    """If a MAJORITY split the word, we do NOT force a merge against them."""
    # Here tess+doctr both split "Weights" -> "W eights"; only surya has it whole.
    # The robust spine + merge must NOT fabricate; majority (2 of 3) split it,
    # so the faithful committed result reflects what the majority read. We only
    # require: no crash, deterministic, and surfaces are all real engine tokens.
    inp = {
        "tesseract": "Sealer of W eights and Measures",
        "doctr": "Sealer of W eights and Measures",
        "surya": "Sealer of Weights and Measures",
    }
    r = build_consensus(inp)
    surfaces = [t.surface for t in r.tokens]
    engine_surfaces = set()
    for t in inp.values():
        engine_surfaces.update(tokenize(t))
    for s in surfaces:
        assert s in engine_surfaces
    # deterministic
    assert build_consensus(inp).committed_text == r.committed_text


def test_garble_metric_detects_phantom_fragment():
    """The NEW duplication metric flags the buggy output, zero for the fixed."""
    from ab_compare import duplication_garble_count  # noqa: PLC0415

    gold = "Sealer of Weights and Measures".split()
    inp = {"tesseract": HANS_TESS, "doctr": HANS_DOCTR, "surya": HANS_SURYA}
    old = build_consensus(inp, _legacy_spine_no_merge=True).committed_text
    new = build_consensus(inp).committed_text

    g_old = duplication_garble_count(old, gold)
    g_new = duplication_garble_count(new, gold)
    g_single = duplication_garble_count(HANS_TESS, gold)

    assert old == "Sealer of Weights eights and Measures", old
    assert g_old["garble_total"] == 1, f"buggy garble should be 1: {g_old}"
    assert g_old["sliver_after_word"] == 1, g_old
    assert g_new["garble_total"] == 0, f"fixed garble should be 0: {g_new}"
    assert g_single["garble_total"] == 0, f"clean single garble should be 0: {g_single}"


# --------------------------------------------------------------------------- #
# Hans M2: capture_candidates must NOT change the committed text
# --------------------------------------------------------------------------- #
# The production path runs build_consensus(..., capture_candidates=True) (it
# banks the per-engine candidate disagreement substrate). capture_candidates
# MUST be purely additive: the committed_text it produces has to be BYTE-
# IDENTICAL to the default (False) path, or production would commit different
# law than the tests verify. This locks that invariant for the multi-engine
# cases (the paths production actually runs).
_M2_CASES = [
    # 3-engine: word-split repair case
    {"tesseract": HANS_TESS, "doctr": HANS_DOCTR, "surya": HANS_SURYA},
    # 3-engine: majority misread correction
    {
        "tesseract": "AN ACT fixing the time for Acts and Joint Resolutions.",
        "doctr": "AN ACT firing the lime for Acts and Joint Resolutions.",
        "surya": "AN ACT fixing the time for Acts and Joint Resolutions.",
    },
    # 2-engine: unanimity machinery
    {
        "tesseract": "Sealer of Weights and Measures",
        "surya": "Sealer of Weights and Measures",
    },
    # 3-engine: two engines split (no forced merge)
    {
        "tesseract": "Sealer of W eights and Measures",
        "doctr": "Sealer of W eights and Measures",
        "surya": "Sealer of Weights and Measures",
    },
]


def test_capture_candidates_committed_text_identical():
    """capture_candidates=True must yield byte-identical committed_text to False."""
    for i, case in enumerate(_M2_CASES):
        plain = build_consensus(case).committed_text
        captured = build_consensus(case, capture_candidates=True).committed_text
        assert plain == captured, (
            f"M2 case {i}: capture_candidates changed committed_text:\n"
            f"  False -> {plain!r}\n  True  -> {captured!r}"
        )


def test_single_engine_confidence_not_one():
    """Hans M3: a single-engine page must NOT report confidence 1.0."""
    r = build_consensus({"tesseract": "AN ACT to do a thing."})
    assert r.method == "single"
    assert r.page_confidence == SINGLE_ENGINE_CONFIDENCE, r.page_confidence
    assert r.page_confidence < 1.0
    assert r.token_agreement_ratio == 0.0
    for t in r.tokens:
        assert t.confidence == SINGLE_ENGINE_CONFIDENCE, t.confidence
        assert t.confidence < 1.0
    # committed surfaces are still faithful (verbatim engine tokens)
    assert r.committed_text == "AN ACT to do a thing."
    # and capture_candidates doesn't change the single-engine committed text
    assert build_consensus(
        {"tesseract": "AN ACT to do a thing."}, capture_candidates=True
    ).committed_text == r.committed_text


# --------------------------------------------------------------------------- #
# Built-in runner (no pytest dependency required)
# --------------------------------------------------------------------------- #
def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_all())
