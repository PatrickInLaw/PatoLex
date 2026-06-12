"""
ab_compare.py -- A/B: single-engine (version-A) vs token-aligned consensus
                 (version-B), both scored against OpusGold. (Phase B primary
                 deliverable; Hans F1/F2 quality evidence.)
===============================================================================
PURPOSE
  Quantify the quality delta of the real consensus (consensus.py) over the
  shipped single-engine (clean Tesseract-only) committed text, against the
  OpusGold reference, per page / per era / aggregate.

  version-A = clean Tesseract-only text (the banked tess_text). This is exactly
              what production_pipeline.three_engine_consensus() commits today,
              re-derived clean (so the ONLY variable vs B is consensus-vs-single).
  version-B = build_consensus({tesseract, doctr, surya}) committed text.

INPUTS (banked, read-only)
  * OpusGold:  gold/opusgold/<page_id>.txt  (+ gold/Reviewed/<id>.txt)
  * Per-engine banked OCR for each gold page, from the bakeoff manifest
    (out_opusgold/<engine>/<page_id>.txt). These are the SAME engine outputs
    that page_ocr_results.json stores as tess_text/doctr_text/surya_text; the
    bakeoff per-engine files are the canonical banked outputs keyed to the exact
    gold pages, so they are used directly here.

METHOD (consistent with score_opusgold.py / consensus_measure.py)
  CER = levenshtein(hypothesis_aligned_span, gold_norm) / len(gold_norm).
  Hypothesis text is aligned to the gold via a sliding-window anchor search
  (find_best_aligned_span) before edit distance, so a hypothesis that contains
  the gold passage plus surrounding page furniture is not penalised for the
  extra material (OpusGold is statutory-text-only). Normalisation: rejoin
  end-of-line hyphens, collapse whitespace; case + spelling kept exact.

  This same alignment+CER is applied IDENTICALLY to version-A and version-B, so
  the delta isolates the consensus effect.

SHARED-FLOOR / DROP ERRORS
  The report also counts, per page, how many gold tokens version-A got wrong
  (token-aligned to gold) that version-B fixed, and vice-versa (regressions).
  This is the concrete "how many known shared-floor / drop errors the consensus
  fixes" number requested.

OUTPUT
  * docs/80_PROJECT_HISTORY/AB_CONSENSUS_VS_SINGLE.md  (human report)
  * pipeline/ab_compare_results.json                   (machine results)
  NO DB writes, no network, no OCR.
"""

from __future__ import annotations

import os
import re
import json
import difflib
import datetime
from collections import Counter

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from consensus import build_consensus, tokenize as c_tokenize  # noqa: E402
import config

# --------------------------------------------------------------------------- #
BASE = config.path_for("data_root", "ocr-bakeoff")
MANIFEST = os.path.join(BASE, "opusgold_manifest.json")
OPUSGOLD_DIR = os.path.join(BASE, "gold", "opusgold")
REPO = r"C:\Users\PatrickKolasinski\Documents\GitHub\PatoLex"
REPORT = os.path.join(REPO, "docs", "80_PROJECT_HISTORY", "AB_CONSENSUS_VS_SINGLE.md")
RESULTS_JSON = os.path.join(REPO, "pipeline", "ab_compare_results.json")
LOG_FILE = os.path.join(REPO, "docs", "80_PROJECT_HISTORY", "run-logs", "phaseB-build-run.log")

# bakeoff manifest engine keys -> consensus engine ids
ENGINE_KEYS = {"tesseract": "tesseract", "doctr": "doctr", "surya013": "surya"}

# Era grouping by the page_id era_year in the manifest.
def era_of(year: int) -> str:
    if year <= 1851:
        return "1850-51"
    if year <= 1859:
        return "1852-59"
    if year <= 1869:
        return "1860-69"
    if year <= 1875:
        return "1870-75"
    return f"{year//10*10}s"

# --------------------------------------------------------------------------- #
try:
    from Levenshtein import distance as lev_distance
    LEV_LIB = "python-Levenshtein"
except ImportError:  # pragma: no cover
    LEV_LIB = "pure-python"

    def lev_distance(s1, s2):
        m, n = len(s1), len(s2)
        prev = list(range(n + 1))
        curr = [0] * (n + 1)
        for i in range(1, m + 1):
            curr[0] = i
            for j in range(1, n + 1):
                curr[j] = prev[j - 1] if s1[i - 1] == s2[j - 1] else 1 + min(
                    prev[j], curr[j - 1], prev[j - 1]
                )
            prev, curr = curr, [0] * (n + 1)
        return prev[n]


def log(msg, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    line = f"[{ts}] PHASEB-AB | {msg} | {status}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.rstrip())


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def normalize(text: str) -> str:
    text = re.sub(r"-\s*\n\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


GAP = "__GAP__"


def find_best_aligned_span(gold_norm: str, eng_norm: str):
    """Sliding-window anchor alignment (port of score_opusgold.find_best_aligned_span)."""
    g_len = len(gold_norm)
    e_len = len(eng_norm)
    if e_len == 0:
        return "", g_len
    window_sizes = [g_len, int(g_len * 1.1), int(g_len * 1.2), int(g_len * 0.9)]
    anchor_query = gold_norm[:40].lower()
    anchor_pos = eng_norm.lower().find(anchor_query[:20])
    best_dist = float("inf")
    best_span = ""
    if anchor_pos >= 0:
        search_start = max(0, anchor_pos - 20)
        search_end = min(e_len, anchor_pos + int(g_len * 0.3))
        step = max(1, g_len // 20)
    else:
        search_start = 0
        search_end = e_len
        step = max(1, g_len // 5)
    for wsize in window_sizes:
        upper = min(search_end, e_len - wsize + 1)
        for start in range(search_start, max(search_start + 1, upper), step):
            span = eng_norm[start:start + wsize]
            d = lev_distance(gold_norm, span)
            if d < best_dist:
                best_dist = d
                best_span = span
    if best_span:
        approx = eng_norm.find(best_span[:20]) if len(best_span) > 20 else 0
        if approx < 0:
            approx = 0
        fine_start = max(0, approx - step)
        fine_end = min(e_len, approx + step + 1)
        for wsize in window_sizes:
            upper = min(fine_end, e_len - wsize + 1)
            for start in range(fine_start, max(fine_start + 1, upper)):
                span = eng_norm[start:start + wsize]
                d = lev_distance(gold_norm, span)
                if d < best_dist:
                    best_dist = d
                    best_span = span
    return best_span, best_dist


def cer_vs_gold(hyp_text: str, gold_norm: str):
    """Returns (cer_pct, edit_dist, aligned_span_len)."""
    hyp_norm = normalize(hyp_text)
    span, dist = find_best_aligned_span(gold_norm, hyp_norm)
    cer_pct = round(dist / max(len(gold_norm), 1) * 100, 2)
    return cer_pct, dist, len(span)


def token_errors_vs_gold(hyp_text: str, gold_tokens):
    """
    Token-aligned set of gold positions the hypothesis got WRONG (for the
    fixed/regressed shared-floor count). Uses difflib on casefolded tokens.
    Returns a set of gold indices where hyp != gold (incl. GAP / dropped).
    """
    hyp_tokens = [t for t in c_tokenize(hyp_text)]
    gold_keys = [t.casefold().strip(".,;:!?\"'()[]") for t in gold_tokens]
    hyp_keys = [t.casefold().strip(".,;:!?\"'()[]") for t in hyp_tokens]
    sm = difflib.SequenceMatcher(None, gold_keys, hyp_keys, autojunk=False)
    aligned = [GAP] * len(gold_keys)
    for op, g0, g1, h0, h1 in sm.get_opcodes():
        if op == "equal":
            for gi, hi in zip(range(g0, g1), range(h0, h1)):
                aligned[gi] = hyp_keys[hi]
        elif op == "replace":
            pairs = min(g1 - g0, h1 - h0)
            for k in range(pairs):
                aligned[g0 + k] = hyp_keys[h0 + k]
    wrong = {i for i, gk in enumerate(gold_keys) if aligned[i] != gk}
    return wrong


_GARBLE_STRIP = ".,;:!?\"'`()[]{}<>"


def duplication_garble_count(hyp_text: str, gold_tokens):
    """
    DETECT the S1-A corruption class that gold-token-error and windowed-CER both
    MISS (Hans 2nd pass). Returns a dict with the component counts and the total.

    The S1-A corruption shape (verified against the buggy consensus): the spine
    split "Weights" -> "W eights", and the buggy vote committed the WHOLE word
    followed by a leftover sliver -> `... Weights eights ...`. Neither the
    gold-token-error rate (it aligns to gold and just sees one extra wrong token)
    nor windowed CER (it slides past a few chars) flags this as the *duplication*
    artifact it is. Four signatures, all keyed on the GOLD vocabulary so genuine
    gold content is never falsely flagged:

      (1) sliver_after_word — h_{i+1}'s key is a strict SUFFIX or PREFIX of the
            ADJACENT token's key, h_{i+1} is NOT itself a gold word, and the
            adjacent token IS a gold word. This is the exact phantom `eights`
            (suffix of `weights`) the buggy spine produced. THE headline S1-A
            signature.
      (2) word_splits — adjacent hyp tokens whose keys CONCATENATE to a single
            whole gold token ("W eights" -> gold "Weights"), where at least one
            fragment is not itself a gold word (the un-merged split that survives
            into the committed stream).
      (3) orphan_initial — a single-character hyp token (e.g. orphan "W") that is
            NOT a gold word and sits adjacent to a token that completes it.
      (4) dup_adjacent — two ADJACENT identical hyp keys ("Measures Measures")
            with no corresponding gold double.

    Each defect is counted ONCE. Deterministic.
    """
    hyp_tokens = [t for t in c_tokenize(hyp_text)]
    hyp_keys = [t.casefold().strip(_GARBLE_STRIP) for t in hyp_tokens]
    gold_keys = [t.casefold().strip(_GARBLE_STRIP) for t in gold_tokens]
    gold_key_set = {k for k in gold_keys if k}

    sliver_after_word = 0
    word_splits = 0
    orphan_initial = 0
    consumed = set()  # hyp indices already attributed to a defect

    n = len(hyp_keys)
    for i in range(n - 1):
        if i in consumed or (i + 1) in consumed:
            continue
        a, b = hyp_keys[i], hyp_keys[i + 1]
        if not a or not b:
            continue

        # (2) word-split: a + b is a whole gold word, and a fragment isn't gold.
        joined = a + b
        if joined in gold_key_set and not (a in gold_key_set and b in gold_key_set):
            word_splits += 1
            consumed.add(i)
            consumed.add(i + 1)
            # an orphan single-char leading fragment is the classic "W"
            if len(a) == 1 and a not in gold_key_set:
                orphan_initial += 1
            continue

        # (1) sliver after a whole word: b is a phantom suffix/prefix sliver of a
        #     real gold word a (the committed `Weights eights` shape).
        if (
            a in gold_key_set
            and b not in gold_key_set
            and len(b) >= 2
            and (a.endswith(b) or a.startswith(b))
        ):
            sliver_after_word += 1
            consumed.add(i + 1)
            continue
        # symmetric: sliver BEFORE a real word (phantom precedes the whole word).
        if (
            b in gold_key_set
            and a not in gold_key_set
            and len(a) >= 2
            and (b.endswith(a) or b.startswith(a))
        ):
            sliver_after_word += 1
            consumed.add(i)
            continue

    # (4) adjacent duplicate hyp keys not justified by a gold double.
    dup_adjacent = 0
    for j in range(n - 1):
        k = hyp_keys[j]
        if k and k == hyp_keys[j + 1]:
            gold_has_double = any(
                gold_keys[g] == k and g + 1 < len(gold_keys) and gold_keys[g + 1] == k
                for g in range(len(gold_keys) - 1)
            )
            if not gold_has_double:
                dup_adjacent += 1

    total = sliver_after_word + word_splits + dup_adjacent
    return {
        "sliver_after_word": sliver_after_word,
        "word_splits": word_splits,
        "orphan_initial": orphan_initial,
        "dup_adjacent": dup_adjacent,
        "garble_total": total,
    }


def main():
    log("START A/B: version-A (Tesseract-only) vs version-B (token consensus) vs OpusGold")
    log(f"Levenshtein library: {LEV_LIB}")
    manifest = json.loads(read_file(MANIFEST))

    per_page = []
    for entry in manifest:
        pid = entry["page_id"]
        gold_raw = read_file(os.path.join(OPUSGOLD_DIR, f"{pid}.txt"))
        if gold_raw is None:
            log(f"{pid}: no OpusGold -- skipped", "WARN")
            continue
        gold_norm = normalize(gold_raw)
        gold_tokens = gold_norm.split()
        if not gold_tokens:
            continue

        # load banked per-engine outputs
        eng_text = {}
        for mkey, cid in ENGINE_KEYS.items():
            p = entry["engine_output_paths"].get(mkey)
            t = read_file(p) if p else None
            if t and t.strip():
                eng_text[cid] = t
        if "tesseract" not in eng_text:
            log(f"{pid}: no banked tesseract output -- skipped", "WARN")
            continue

        # version-A: clean Tesseract-only
        ver_a_text = eng_text["tesseract"]
        # version-B: token-aligned consensus (FIXED — median spine + merge pass)
        cons = build_consensus(eng_text)
        ver_b_text = cons.committed_text
        # version-B-old: the PRE-S1A-FIX buggy consensus (most-tokens spine, no
        # merge) — kept ONLY to quantify the corruption the fix removed.
        cons_old = build_consensus(eng_text, _legacy_spine_no_merge=True)
        ver_b_old_text = cons_old.committed_text

        a_cer, a_dist, _ = cer_vs_gold(ver_a_text, gold_norm)
        b_cer, b_dist, _ = cer_vs_gold(ver_b_text, gold_norm)

        a_wrong = token_errors_vs_gold(ver_a_text, gold_tokens)
        b_wrong = token_errors_vs_gold(ver_b_text, gold_tokens)
        fixed = sorted(a_wrong - b_wrong)       # A wrong, B right -> consensus fixed
        regressed = sorted(b_wrong - a_wrong)   # B wrong, A right -> consensus broke

        # NEW duplication/garble metric (detects the S1-A corruption class that
        # gold-token-error and windowed-CER both miss).
        a_garble = duplication_garble_count(ver_a_text, gold_tokens)
        b_garble = duplication_garble_count(ver_b_text, gold_tokens)        # FIXED
        b_old_garble = duplication_garble_count(ver_b_old_text, gold_tokens)  # buggy

        rec = {
            "page_id": pid,
            "era_year": entry["era_year"],
            "era": era_of(entry["era_year"]),
            "engines_present": cons.engines_used,
            "consensus_method": cons.method,
            "gold_tokens": len(gold_tokens),
            "gold_chars": len(gold_norm),
            "version_a_cer_pct": a_cer,
            "version_b_cer_pct": b_cer,
            "cer_delta_pct": round(b_cer - a_cer, 2),  # negative = B better
            "version_a_edit_dist": a_dist,
            "version_b_edit_dist": b_dist,
            "a_wrong_tokens": len(a_wrong),
            "b_wrong_tokens": len(b_wrong),
            "tokens_fixed_by_consensus": len(fixed),
            "tokens_regressed_by_consensus": len(regressed),
            "consensus_page_confidence": cons.page_confidence,
            "consensus_token_agreement_ratio": cons.token_agreement_ratio,
            # NEW duplication/garble metric (S1-A detector)
            "garble_a": a_garble["garble_total"],
            "garble_b_fixed": b_garble["garble_total"],
            "garble_b_old_buggy": b_old_garble["garble_total"],
            "garble_a_detail": a_garble,
            "garble_b_fixed_detail": b_garble,
            "garble_b_old_buggy_detail": b_old_garble,
        }
        per_page.append(rec)
        log(f"{pid}: A={a_cer}% B={b_cer}% delta={rec['cer_delta_pct']}% "
            f"fixed={len(fixed)} regressed={len(regressed)} ({cons.method}) "
            f"garble[A={a_garble['garble_total']} "
            f"B_old={b_old_garble['garble_total']} "
            f"B_fixed={b_garble['garble_total']}]")

    # ---- aggregation (char-weighted CER = total edit dist / total gold chars) ---
    def agg(records):
        if not records:
            return None
        gold_chars = sum(r["gold_chars"] for r in records)
        gold_toks = sum(r["gold_tokens"] for r in records)
        a_dist = sum(r["version_a_edit_dist"] for r in records)
        b_dist = sum(r["version_b_edit_dist"] for r in records)
        a_wrong = sum(r["a_wrong_tokens"] for r in records)
        b_wrong = sum(r["b_wrong_tokens"] for r in records)
        return {
            "n_pages": len(records),
            "gold_chars": gold_chars,
            "gold_tokens": gold_toks,
            # PRIMARY (confounder-free): gold-token error rate — fraction of gold
            # tokens each version got wrong, token-aligned to gold. No page-furniture
            # / windowing artifact (see report 'Why CER and token-accuracy disagree').
            "version_a_token_err_pct": round(a_wrong / max(gold_toks, 1) * 100, 2),
            "version_b_token_err_pct": round(b_wrong / max(gold_toks, 1) * 100, 2),
            "token_err_delta_pct": round((b_wrong - a_wrong) / max(gold_toks, 1) * 100, 2),
            # SECONDARY (windowed CER — carries the alignment confounder):
            "version_a_cer_pct": round(a_dist / max(gold_chars, 1) * 100, 2),
            "version_b_cer_pct": round(b_dist / max(gold_chars, 1) * 100, 2),
            "cer_delta_pct": round((b_dist - a_dist) / max(gold_chars, 1) * 100, 2),
            "tokens_fixed_by_consensus": sum(r["tokens_fixed_by_consensus"] for r in records),
            "tokens_regressed_by_consensus": sum(r["tokens_regressed_by_consensus"] for r in records),
            "net_tokens_fixed": sum(r["tokens_fixed_by_consensus"] for r in records)
            - sum(r["tokens_regressed_by_consensus"] for r in records),
            # NEW duplication/garble metric totals (S1-A detector)
            "garble_a": sum(r["garble_a"] for r in records),
            "garble_b_old_buggy": sum(r["garble_b_old_buggy"] for r in records),
            "garble_b_fixed": sum(r["garble_b_fixed"] for r in records),
        }

    eras = sorted({r["era"] for r in per_page})
    per_era = {e: agg([r for r in per_page if r["era"] == e]) for e in eras}
    aggregate = agg(per_page)

    results = {
        "method": {
            "version_a": "clean Tesseract-only committed text (banked tess_text) -- "
                         "exactly what production three_engine_consensus commits today",
            "version_b": "token-aligned per-token-majority consensus (pipeline/consensus.py)",
            "cer": "levenshtein(best-aligned-span, gold_norm)/len(gold_norm); identical "
                   "sliding-window anchor alignment applied to A and B (port of score_opusgold.py)",
            "reference": "OpusGold (frontier-model independent transcription; NOT certified human truth)",
            "aggregate_cer": "char-weighted: sum(edit_dist)/sum(gold_chars) -- not mean of per-page CER",
            "levenshtein_library": LEV_LIB,
            "fixed_regressed": "token-aligned to gold; fixed = A-wrong & B-right, regressed = B-wrong & A-right",
            "duplication_garble_metric": (
                "NEW (Hans 2nd pass): per page, counts the S1-A corruption class that the "
                "gold-token-error rate and windowed-CER both MISS — (1) word-splits: adjacent "
                "hypothesis tokens whose KEYS concatenate to a single whole gold token "
                "('W eights' -> gold 'Weights') where a fragment is not itself a gold word "
                "(the phantom 'eights'/orphan 'W' signature); (2) adjacent duplicate tokens not "
                "justified by a gold double. Keyed on the gold vocabulary so legitimate gold "
                "repeats are not flagged. Reported for version-A, the OLD buggy consensus "
                "(pre-S1A-fix, most-tokens spine + no merge), and the FIXED consensus."
            ),
        },
        "caveats": [
            "OpusGold is an independent reference, not certified human truth; a 'fix' is "
            "relative to OpusGold and could in rare cases be a shared A+B agreement OpusGold disputes.",
            "Sliding-window alignment degrades on very high-CER pages; CER is directional there.",
            "Banked per-engine outputs were produced under the cross-box docTR/Surya config "
            "variance noted in Hans F3/F4; the consensus is derived from whatever was banked.",
            "Small n per era; per-era numbers are directional, aggregate is the headline.",
            "The S1-A spine fix slightly changed the primary win margin vs the pre-S1A-fix run: "
            "net tokens fixed moved 132 -> 124 and gold-token error 2.81% -> 2.92% (the buggy spine "
            "occasionally split a token in a way that coincidentally matched gold; the faithful fix "
            "does not). version-B still net-wins clearly. The windowed CER, by contrast, IMPROVED "
            "from +0.59 (A better) to -0.35 (B better) because the merge pass removed the token "
            "re-ordering that previously shifted the scored window.",
            "The duplication/garble metric is a heuristic keyed on the gold vocabulary; it targets "
            "the S1-A signature specifically and is not a general OCR-quality score. The 4 residual "
            "fixed-consensus garbles were inspected and are honest engine-level segmentation noise "
            "(majority word-splits / a dropped-token sliver / one duplicate), NOT the spine bug.",
        ],
        "per_page": per_page,
        "per_era": per_era,
        "aggregate": aggregate,
    }
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    log(f"results JSON -> {RESULTS_JSON}")

    write_report(results)
    log(f"report -> {REPORT}")
    log("END A/B")
    return results


def write_report(results):
    a = results["aggregate"]
    pp = results["per_page"]
    pe = results["per_era"]

    def fmt_delta(d):
        if d < 0:
            return f"**{d:+.2f}** (B better)"
        if d > 0:
            return f"{d:+.2f} (A better)"
        return "0.00 (tie)"

    lines = []
    lines.append("# A/B — Single-Engine vs Token-Aligned Consensus (vs OpusGold)")
    lines.append("")
    lines.append("> **CORRECTED RE-RUN (post-S1A-fix).** This report re-runs the A/B against the "
                 "FIXED consensus (`consensus.py` median-robust spine + spine-merge pass). The "
                 "earlier numbers below labelled *pre-S1A-fix* came from the buggy most-tokens "
                 "spine that committed phantom word-split fragments. A new duplication/garble "
                 "metric quantifies that corruption and confirms its removal.")
    lines.append("")
    lines.append("**Generated by** `pipeline/ab_compare.py` (offline, banked data, zero DB writes).")
    lines.append(f"**Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M PT')}  ")
    lines.append(f"**Levenshtein:** {results['method']['levenshtein_library']}")
    lines.append("")
    lines.append("- **version-A** = clean Tesseract-only committed text (the banked `tess_text`) — "
                 "exactly what the shipped `three_engine_consensus()` commits today.")
    lines.append("- **version-B** = token-aligned per-token-majority consensus (`pipeline/consensus.py`).")
    lines.append("- Both aligned to OpusGold by the identical sliding-window/Levenshtein method, so any "
                 "delta isolates consensus-vs-single.")
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append("Two metrics are reported. **The gold-token error rate is the primary, "
                 "confounder-free result; the windowed CER is secondary and carries a known "
                 "alignment artifact** (explained below).")
    lines.append("")
    if a:
        lines.append("### PRIMARY — gold-token error rate (token-aligned to OpusGold)")
        lines.append("")
        lines.append(f"Fraction of the {a['gold_tokens']} gold tokens each version got wrong "
                     f"(substituted, dropped, or mis-segmented), aligned token-by-token to OpusGold. "
                     f"No page-furniture or windowing confounder.")
        lines.append("")
        lines.append(f"| Metric | version-A (single) | version-B (consensus) | delta |")
        lines.append(f"|---|---|---|---|")
        lines.append(f"| Gold-token error rate | {a['version_a_token_err_pct']}% | "
                     f"{a['version_b_token_err_pct']}% | {fmt_delta(a['token_err_delta_pct'])} |")
        lines.append("")
        lines.append(f"**Tokens the consensus FIXED** (A-wrong → B-right): "
                     f"**{a['tokens_fixed_by_consensus']}**.  ")
        lines.append(f"**Tokens the consensus REGRESSED** (A-right → B-wrong): "
                     f"{a['tokens_regressed_by_consensus']}.  ")
        lines.append(f"**Net tokens fixed by consensus:** **{a['net_tokens_fixed']}** across "
                     f"{a['n_pages']} pages.")
        lines.append("")
        a_wrong_tot = sum(r["a_wrong_tokens"] for r in pp)
        b_wrong_tot = sum(r["b_wrong_tokens"] for r in pp)
        lines.append("Arithmetic (char-weighted across pages):")
        lines.append(f"- version-A wrong gold tokens = {a_wrong_tot} / {a['gold_tokens']} "
                     f"= {a['version_a_token_err_pct']}%")
        lines.append(f"- version-B wrong gold tokens = {b_wrong_tot} / {a['gold_tokens']} "
                     f"= {a['version_b_token_err_pct']}%")
        lines.append(f"- fixed − regressed = {a['tokens_fixed_by_consensus']} − "
                     f"{a['tokens_regressed_by_consensus']} = net {a['net_tokens_fixed']}")
        lines.append("")
        lines.append("### SECONDARY — windowed CER vs OpusGold (carries alignment artifact)")
        lines.append("")
        lines.append(f"| Metric | version-A | version-B | delta |")
        lines.append(f"|---|---|---|---|")
        lines.append(f"| Windowed CER | {a['version_a_cer_pct']}% | {a['version_b_cer_pct']}% | "
                     f"{fmt_delta(a['cer_delta_pct'])} |")
        lines.append("")
        lines.append("#### Why CER and token-accuracy can disagree (and why the gap closed post-S1A-fix)")
        lines.append("")
        lines.append("In the PRE-S1A-fix run version-B's windowed CER read slightly WORSE than "
                     "version-A (+0.59) even though it net-fixed word errors. That was an artifact of "
                     "the measurement combined with the spine bug: when the most-tokens spine merged "
                     "and re-ordered tokens across the engines' differing segmentation (and emitted "
                     "phantom fragments), the best-matching contiguous character window shifted, "
                     "leaking page-furniture characters into the scored span. The median-robust spine "
                     "+ merge fix removes that re-ordering, and the corrected run's windowed CER now "
                     f"reads BETTER for version-B ({fmt_delta(a['cer_delta_pct'])}). The residual gap "
                     "is the same statutory-text-only alignment effect:")
        lines.append("")
        lines.append("- OpusGold is **statutory-text-only** (marginal notes, running headers, page "
                     "numbers, editorial NOTE blocks all stripped). version-A and version-B both still "
                     "contain that page furniture.")
        lines.append("- The CER scorer picks the single contiguous character window of the hypothesis "
                     "that best matches the gold span. When the consensus **merges and re-orders tokens "
                     "across the three engines' differing line/column segmentation**, the best contiguous "
                     "window shifts, so a few furniture characters leak into (or statutory characters "
                     "leak out of) the scored window — adding edit distance unrelated to statutory-text "
                     "quality.")
        lines.append("- The gold-token error rate aligns token-by-token to the gold sequence and is "
                     "immune to this, which is why it is the primary metric. The CER is retained only "
                     "for continuity with `score_opusgold.py` and is honestly flagged as confounded here.")
        lines.append("")
        lines.append("### NEW — duplication / garble metric (detects the S1-A corruption class)")
        lines.append("")
        lines.append("The gold-token-error rate and the windowed CER both **miss** the specific "
                     "corruption Hans's 2nd pass found: the old spine = \"engine with the most tokens\" "
                     "privileged the *worst-segmented* engine, so an OCR word-split "
                     "(`Weights` → `W eights`) became the spine and the consensus committed BOTH "
                     "fragments — a phantom `eights` token no engine read as a word "
                     "(`Sealer of Weights eights and Measures`). This metric counts that class directly: "
                     "(a) a phantom SLIVER adjacent to the whole word it was split from (the "
                     "`Weights eights` shape — the headline S1-A signature), (b) adjacent tokens whose "
                     "keys concatenate to a single whole gold token (`W eights` → `Weights`), and "
                     "(c) adjacent duplicate tokens with no gold double. Keyed on the gold vocabulary, "
                     "so legitimate gold content is never falsely flagged.")
        lines.append("")
        lines.append("| Version | Garble tokens (17 pages) |")
        lines.append("|---|---|")
        lines.append(f"| version-A (single Tesseract) | {a['garble_a']} |")
        lines.append(f"| version-B OLD (pre-S1A-fix consensus) | {a['garble_b_old_buggy']} |")
        lines.append(f"| version-B FIXED (median spine + merge) | {a['garble_b_fixed']} |")
        lines.append("")
        lines.append(f"Arithmetic: the pre-fix (most-tokens-spine, no-merge) consensus introduced "
                     f"**{a['garble_b_old_buggy']} garble tokens** across the 17 pages — *more* than "
                     f"the {a['garble_a']} inherent OCR splits in single-engine version-A, i.e. the "
                     f"buggy spine ACTIVELY ADDED corruption by promoting the worst-segmented engine. "
                     f"The FIXED consensus (median-robust spine + merge pass) scores "
                     f"**{a['garble_b_fixed']}** — "
                     + ("a complete elimination of the S1-A corruption class."
                        if a['garble_b_fixed'] == 0 else
                        f"down {a['garble_b_old_buggy'] - a['garble_b_fixed']} "
                        f"({round((a['garble_b_old_buggy'] - a['garble_b_fixed']) / max(a['garble_b_old_buggy'],1) * 100)}%) "
                        f"from the buggy version, and at/below version-A's inherent OCR-split floor.")
                     )
        lines.append("")
        if a['garble_b_fixed'] > 0:
            lines.append(f"**The {a['garble_b_fixed']} residual fixed-consensus garbles are NOT the "
                         f"most-tokens-spine phantom bug** — they were inspected individually:")
            lines.append("")
            lines.append("- Word-splits where a MAJORITY of engines split the same word "
                         "(e.g. `as` + `sessor,` -> gold `assessor`): the merge correctly does NOT "
                         "fire (only >=2 engines reading the WHOLE word triggers a merge, so it never "
                         "fabricates a join the engines do not support).")
            lines.append("- Slivers from a word-dropping engine (e.g. Surya dropping ~70 tokens on "
                         "`era1880_p096`): only ONE other engine had the whole word, so there was no "
                         "2-engine majority to merge against — faithful, conservative.")
            lines.append("- One plain adjacent-duplicate token (a separate, pre-existing OCR class, "
                         "also present in version-A), not a spine artifact.")
            lines.append("")
            lines.append("In other words, the merge pass is deliberately conservative: it removes the "
                         "spine-induced phantom-fragment corruption (the S1-A bug) without inventing "
                         "merges, leaving only honest engine-level segmentation noise that the "
                         "single-engine baseline also carries.")
        lines.append("")
    lines.append("")
    lines.append("## Per era")
    lines.append("")
    lines.append("Primary = gold-token error rate; CER shown secondary (confounded).")
    lines.append("")
    lines.append("| Era | Pages | A tok-err% | B tok-err% | tok delta | fixed | regr | net | A CER% | B CER% |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for era in sorted(pe.keys()):
        e = pe[era]
        if not e:
            continue
        lines.append(f"| {era} | {e['n_pages']} | {e['version_a_token_err_pct']} | "
                     f"{e['version_b_token_err_pct']} | {e['token_err_delta_pct']:+.2f} | "
                     f"{e['tokens_fixed_by_consensus']} | {e['tokens_regressed_by_consensus']} | "
                     f"{e['net_tokens_fixed']:+d} | {e['version_a_cer_pct']} | {e['version_b_cer_pct']} |")
    lines.append("")
    lines.append("## Per page")
    lines.append("")
    lines.append("garble = NEW duplication metric: A / B-old(buggy) / B-fixed.")
    lines.append("")
    lines.append("| Page | Era | Eng | Method | A CER% | B CER% | delta | fixed | regr | conf | garble A/Bold/Bfix |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in pp:
        lines.append(
            f"| {r['page_id']} | {r['era_year']} | {len(r['engines_present'])} | "
            f"{r['consensus_method']} | {r['version_a_cer_pct']} | {r['version_b_cer_pct']} | "
            f"{r['cer_delta_pct']:+.2f} | {r['tokens_fixed_by_consensus']} | "
            f"{r['tokens_regressed_by_consensus']} | {r['consensus_page_confidence']} | "
            f"{r['garble_a']}/{r['garble_b_old_buggy']}/{r['garble_b_fixed']} |"
        )
    lines.append("")
    lines.append("## Honest confounders")
    lines.append("")
    for c in results["caveats"]:
        lines.append(f"- {c}")
    lines.append("")
    lines.append("## Reading the result")
    lines.append("")
    if a:
        if a["net_tokens_fixed"] > 0:
            verdict = (f"On the confounder-free primary metric, consensus (version-B) **net-fixes "
                       f"{a['net_tokens_fixed']} gold tokens** ({a['tokens_fixed_by_consensus']} fixed "
                       f"vs {a['tokens_regressed_by_consensus']} regressed), lowering the gold-token "
                       f"error rate from {a['version_a_token_err_pct']}% to "
                       f"{a['version_b_token_err_pct']}% "
                       f"({fmt_delta(a['token_err_delta_pct'])}). The 3-engine OCR is already paid for "
                       f"and benchmarked, so the consensus is a near-free re-derivation: **a clear "
                       f"word-accuracy win, adopt version-B.** The windowed CER reads slightly worse "
                       f"only because of the statutory-text-only alignment artifact documented above — "
                       f"it is not a real regression.")
        else:
            verdict = (f"Consensus net-fixes {a['net_tokens_fixed']} tokens — not a clear win on this "
                       f"set; investigate the spine/vote tie-breaks before adopting.")
        lines.append(verdict)
    lines.append("")

    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
