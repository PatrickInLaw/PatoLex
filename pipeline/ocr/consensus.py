"""
consensus.py -- Token-aligned multi-engine OCR consensus (Phase B, F1/F2 fix).
===============================================================================
Replaces production_pipeline.three_engine_consensus(), which committed
Tesseract-only text and reported a bag-of-words set-overlap ratio (Hans F1/F2).

This module produces:
  * committed text built by **per-aligned-token majority vote** of the engines,
  * a **real, position-aware per-token confidence** = the fraction of engines
    that agree (after alignment) on the committed token at each position.

It operates purely on banked per-page engine text (tess_text / doctr_text /
surya_text from page_ocr_results.json, or the bakeoff per-engine .txt files).
No OCR, no GPU, no DB, no network.

--------------------------------------------------------------------------------
ALGORITHM (deterministic — same input always yields the same output)
--------------------------------------------------------------------------------
Input: 2 or 3 engine strings for ONE page, each tagged with a stable engine id.

1. NORMALIZE FOR ALIGNMENT ONLY (committed tokens keep their original surface):
   - rejoin end-of-line hyphens ("hap-\npiness" -> "happiness"),
   - split each engine's text into lines, then into whitespace tokens,
   - we DO NOT lowercase or strip punctuation off the committed token surface;
     a separate casefold key is used only for the vote/agreement comparison so
     that "The" and "the" are counted as agreeing while the committed surface
     stays faithful.

2. PICK A REFERENCE SPINE (deterministic, FRAGMENTATION-ROBUST — Hans S1-A):
   The spine is the engine whose token count is CLOSEST TO THE MEDIAN token
   count across engines (ties broken toward more content, then char length,
   then fixed engine priority tesseract < doctr < surya). This is deliberately
   NOT "the engine with the most tokens": OCR word-splitting ("Weights" ->
   "W eights") inflates an engine's token count, so the old most-tokens rule
   privileged the WORST-segmented engine and committed its fragments ("W",
   "eights") as separate positions. The median is robust to a single
   over-segmenter (far above median) or word-dropper (far below).

   2b. SPINE-MERGE PASS (Hans S1-A): before alignment, any two ADJACENT spine
   tokens whose casefold keys concatenate to a single token that >= 2 OTHER
   engines carry as ONE whole word are collapsed into one faithful whole-word
   token (surface taken verbatim from a real engine). This repairs any residual
   word-split the chosen spine still carries, so no phantom fragment is
   committed. Majority vote then corrects the spine's own misreads token-by-token.

3. ALIGN EACH NON-SPINE ENGINE TO THE SPINE:
   difflib.SequenceMatcher(autojunk=False) on the casefold token lists gives
   opcodes (equal / replace / delete / insert). For every spine position we
   record what each other engine "says" at that position:
     - equal/replace -> the other engine's aligned token (surface kept),
     - delete (spine has token, other doesn't) -> GAP for that engine,
     - insert (other has extra tokens spine lacks) -> those tokens are attached
       to the *following* spine position as candidate insertions; if two engines
       agree on the same insertion and the spine lacks it, the inserted token is
       committed (majority restores content the spine dropped).
   SequenceMatcher is deterministic; we additionally sort all tie-affected
   structures so the result never depends on dict/set iteration order.

4. PER-POSITION MAJORITY VOTE:
   At each spine position we have up to N votes (N = number of engines present
   at that position, 2 or 3). Votes are compared on a casefold+punctuation-
   trimmed key. The winning key is the one with the most votes; ties are broken
   deterministically by (a) preferring a non-empty/non-GAP token, then (b) the
   fixed engine-priority order of the engines that cast that vote. The committed
   surface is the *original* surface of the highest-priority engine that voted
   for the winning key (so casing/punctuation come from a real engine, never
   synthesised).

5. PER-TOKEN CONFIDENCE (position-aware, NOT set overlap):
   confidence[pos] = (# engines whose aligned token matches the committed key)
                     / (# engines present at this position).
   So a token all three engines read identically -> 1.0; a 2-of-3 token -> ~0.67;
   a token only the spine had (others GAP) -> 1/1 present but flagged low via
   the `engines_present` count. We also emit `n_agree` and `n_present` so the
   ingest layer can apply its own thresholds honestly.

6. PAGE AGGREGATES:
   page_confidence  = mean of per-token confidence weighted by n_present,
   token_agreement_ratio = fraction of committed tokens with n_agree >= majority,
   method tag        = "token_majority_3" or "token_majority_2" (honest: never
                       label it "consensus" when only one engine was present).

Two-engine pages: the same machinery runs with N=2; a token is "agreed" only
when both engines match (no majority possible with 2 — agreement is unanimity),
which the confidence (0.5 vs 1.0) reflects honestly.

--------------------------------------------------------------------------------
OUTPUT (per page): a ConsensusResult dataclass with:
  committed_text   : str   -- faithful, full UTF-8, majority-voted
  tokens           : list[CommittedToken]  (surface, key, n_agree, n_present,
                                            confidence, voters)
  page_confidence  : float
  token_agreement_ratio : float
  method           : str   ("token_majority_3" | "token_majority_2" | "single")
  engines_used     : list[str]  (sorted, the engines actually present)
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import re
import difflib
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

# Fixed engine priority for deterministic tie-breaks (lower index = higher prio).
# Order chosen from the bakeoff ranking (Tesseract lowest CER on this corpus),
# then docTR, then Surya. This ONLY breaks exact ties; it never overrides a vote.
ENGINE_PRIORITY = ["tesseract", "doctr", "surya"]

GAP = None  # sentinel for "this engine has no token at this position"

# Single-engine pages have ZERO corroboration: only one engine read the page,
# so NOTHING can vouch for any token. Honest confidence for such tokens is the
# 1/N_MAX_ENGINES floor (one of the three pipeline engines agreed — itself —
# and no other), NEVER 1.0 (Hans M3: 1.0 falsely asserts full agreement when
# there is none). N_MAX_ENGINES is the corpus engine ceiling (tesseract+doctr+
# surya). Deterministic constant: same input -> same value.
N_MAX_ENGINES = 3
SINGLE_ENGINE_CONFIDENCE = round(1.0 / N_MAX_ENGINES, 4)  # 0.3333


def _priority(engine: str) -> int:
    try:
        return ENGINE_PRIORITY.index(engine)
    except ValueError:
        return len(ENGINE_PRIORITY)


# --------------------------------------------------------------------------- #
# Tokenization / keys
# --------------------------------------------------------------------------- #

_HYPHEN_WRAP = re.compile(r"-\s*\n\s*")
_WS = re.compile(r"\s+")
# punctuation trimmed from the comparison key (NOT from the committed surface)
_KEY_STRIP = " \t\r\n.,;:!?\"'`()[]{}<>"


def _dehyphenate(text: str) -> str:
    """Rejoin words split across a line by a trailing hyphen."""
    return _HYPHEN_WRAP.sub("", text)


def tokenize(text: str) -> List[str]:
    """Whitespace tokenization preserving original token surfaces (UTF-8 intact)."""
    text = _dehyphenate(text)
    return [t for t in _WS.split(text) if t]


def vote_key(token: Optional[str]) -> str:
    """
    Comparison key for the vote: casefold + strip surrounding punctuation.
    Two engines that wrote 'The,' and 'the' both map to 'the' and so AGREE,
    while the committed *surface* still comes verbatim from a real engine.
    GAP maps to '' (the empty key) so it can never win a non-empty position.
    """
    if token is GAP or token is None:
        return ""
    return token.strip(_KEY_STRIP).casefold()


# --------------------------------------------------------------------------- #
# Alignment
# --------------------------------------------------------------------------- #

def _align_to_spine(
    spine_keys: List[str], other_keys: List[str]
) -> Tuple[List[Optional[int]], Dict[int, List[int]]]:
    """
    Align `other` token list to the `spine` by casefold key.

    Returns:
      aligned[i] = index into `other` that maps to spine position i, or GAP(None)
                   if the other engine has no token at spine position i.
      insertions = {spine_pos: [other_idx, ...]} for tokens `other` has that the
                   spine lacks; attached to the spine position they precede.
    SequenceMatcher is deterministic. We attach inserts to the *following* spine
    position (or the last position if at end) so they can be majority-voted in.
    """
    sm = difflib.SequenceMatcher(None, spine_keys, other_keys, autojunk=False)
    aligned: List[Optional[int]] = [GAP] * len(spine_keys)
    insertions: Dict[int, List[int]] = {}
    for op, s0, s1, o0, o1 in sm.get_opcodes():
        if op == "equal":
            for si, oi in zip(range(s0, s1), range(o0, o1)):
                aligned[si] = oi
        elif op == "replace":
            pairs = min(s1 - s0, o1 - o0)
            for k in range(pairs):
                aligned[s0 + k] = o0 + k
            # extra `other` tokens in a replace block become insertions at s1
            if (o1 - o0) > pairs:
                insertions.setdefault(s1, []).extend(range(o0 + pairs, o1))
        elif op == "delete":
            # spine has tokens other lacks -> those spine positions stay GAP
            pass
        elif op == "insert":
            insertions.setdefault(s0, []).extend(range(o0, o1))
    return aligned, insertions


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #

@dataclass
class CommittedToken:
    surface: str            # faithful committed surface (UTF-8)
    key: str                # vote key that won
    n_agree: int            # engines agreeing on the winning key
    n_present: int          # engines with a (non-GAP) token at this position
    confidence: float       # n_agree / n_present
    voters: List[str]       # engine ids that voted for the winning key (sorted)
    # Phase C substrate (capture-ALL-signals): the per-engine candidate tokens
    # at this position — what EACH present engine actually read here, including
    # the DISAGREEING reads. Populated ONLY when build_consensus(...,
    # capture_candidates=True); left None otherwise so the default ConsensusResult
    # / to_dict() output is byte-identical to the pre-capture behaviour (the live
    # pipeline path is unchanged). Each entry: {"engine": str, "token": str}.
    candidates: Optional[List[Dict[str, str]]] = None


@dataclass
class ConsensusResult:
    committed_text: str
    tokens: List[CommittedToken]
    page_confidence: float
    token_agreement_ratio: float
    method: str
    engines_used: List[str]
    n_tokens: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #

def _median(values: List[int]) -> float:
    """Deterministic median of a small int list (no numpy)."""
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


def _choose_spine(engine_tokens: Dict[str, List[str]]) -> str:
    """
    Choose the reference spine by a FRAGMENTATION-ROBUST criterion (Hans S1-A).

    The old rule ("engine with the MOST tokens") privileged the WORST-segmented
    engine: OCR word-splitting ("Weights" -> "W eights") inflates an engine's
    token count, so the engine that mangled words most became the spine and its
    fragments ("W", "eights") got committed as separate positions.

    The robust criterion:
      1. Prefer the engine whose token count is CLOSEST to the MEDIAN token count
         across engines (an over-segmenter sits far above the median; a
         word-dropper sits far below — both are penalised). Distance ties are
         broken toward the LARGER token count only as a last resort (we still
         want to minimise dropped content), then by char length, then priority.
    This is deterministic and never privileges a single mis-segmenting engine.
    The downstream spine-merge pass (see build_consensus) additionally repairs
    any residual split the chosen spine still carries.
    """
    engines = list(engine_tokens.keys())
    counts = [len(engine_tokens[e]) for e in engines]
    med = _median(counts)
    return min(
        engines,
        key=lambda e: (
            abs(len(engine_tokens[e]) - med),  # closeness to median (robust)
            -len(engine_tokens[e]),            # tie: prefer more content
            -sum(len(t) for t in engine_tokens[e]),  # tie: more characters
            _priority(e), e,                    # final deterministic tie-break
        ),
    )


def _merge_spine_splits(
    spine_tokens: List[str],
    engine_tokens: Dict[str, List[str]],
    engine_key_sets: Dict[str, set],
    spine_engine: str,
) -> List[str]:
    """
    Collapse adjacent SPINE tokens that are an OCR word-split (Hans S1-A).

    For each adjacent spine pair (i, i+1), if their casefold keys CONCATENATE to
    a single token that >= 2 OTHER engines (engines other than the spine) carry
    as ONE whole token, the spine split is spurious: merge the two spine
    positions into one, using the concatenated surface FROM A REAL ENGINE that
    has the whole word (faithful — never a synthesised join). Deterministic:
    a single left-to-right pass, merged tokens are not re-examined.

    `engine_key_sets[e]` is the set of vote_keys engine e has (whole-token keys).
    Merging only fires when a non-spine MAJORITY (>=2) actually read the whole
    word, so we never fabricate a join the engines do not support.
    """
    others = [e for e in engine_tokens if e != spine_engine]
    if len(others) < 2:
        return list(spine_tokens)  # need >=2 corroborating engines to merge

    # Map whole-word key -> a faithful surface from some engine that has it.
    # Prefer the spine_engine's own surface if it (somehow) also has the whole
    # word; otherwise the highest-priority other engine that does.
    def whole_word_surface(key: str) -> Optional[str]:
        for e in sorted(engine_tokens, key=lambda x: (_priority(x), x)):
            for tok in engine_tokens[e]:
                if vote_key(tok) == key:
                    return tok
        return None

    out: List[str] = []
    i = 0
    n = len(spine_tokens)
    while i < n:
        if i + 1 < n:
            k1 = vote_key(spine_tokens[i])
            k2 = vote_key(spine_tokens[i + 1])
            if k1 and k2:
                joined_key = k1 + k2
                corroborating = sum(
                    1 for e in others if joined_key in engine_key_sets[e]
                )
                if corroborating >= 2:
                    surf = whole_word_surface(joined_key)
                    if surf is not None:
                        out.append(surf)   # faithful whole-word surface
                        i += 2
                        continue
        out.append(spine_tokens[i])
        i += 1
    return out


def _vote(
    candidates: List[Tuple[str, Optional[str]]]
) -> Tuple[str, str, int, int, List[str]]:
    """
    candidates: list of (engine_id, token-or-GAP) at one position.
    Returns (committed_surface, winning_key, n_agree, n_present, voters_sorted).

    Majority by vote_key. Ties broken deterministically:
      1. prefer a non-empty key (real token over GAP),
      2. higher total votes,
      3. the key whose highest-priority engine has the smallest priority index.
    Committed surface = original surface of the highest-priority engine that
    voted for the winning key (never synthesised).
    """
    present = [(e, t) for e, t in candidates if t is not GAP and t is not None]
    n_present = len(present)

    # group by key
    groups: Dict[str, List[Tuple[str, str]]] = {}
    for e, t in present:
        k = vote_key(t)
        if k == "":
            continue  # token was pure punctuation/empty after stripping
        groups.setdefault(k, []).append((e, t))

    if not groups:
        # everything was GAP/empty here; nothing to commit
        return "", "", 0, n_present, []

    def group_rank(item):
        key, voters = item
        best_prio = min(_priority(e) for e, _ in voters)
        # sort: more votes first (neg), then better engine priority, then key text
        return (-len(voters), best_prio, key)

    winning_key, winning_voters = sorted(groups.items(), key=group_rank)[0]
    # committed surface: highest-priority engine that voted for the winning key
    winning_voters_sorted = sorted(winning_voters, key=lambda ev: (_priority(ev[0]), ev[0]))
    committed_surface = winning_voters_sorted[0][1]
    voters_ids = sorted(e for e, _ in winning_voters)
    n_agree = len(winning_voters)
    return committed_surface, winning_key, n_agree, n_present, voters_ids


def build_consensus(
    engine_texts: Dict[str, str],
    _legacy_spine_no_merge: bool = False,
    capture_candidates: bool = False,
) -> ConsensusResult:
    """
    engine_texts: {engine_id: page_text}. Engine ids should be canonical
    ('tesseract','doctr','surya'); unknown ids work but sort last in tie-breaks.
    Empty / missing engines should simply be omitted by the caller.

    Returns a ConsensusResult. Handles 1, 2, or 3 engines.

    _legacy_spine_no_merge: PRODUCTION MUST LEAVE THIS FALSE. It reproduces the
      pre-S1A-fix behaviour (most-tokens spine, NO spine-merge pass) and exists
      ONLY so the A/B harness (ab_compare.py) can measure the corruption the fix
      removed. It is never used by the real pipeline.
    """
    # keep only engines with non-empty text, sorted for determinism
    engines = sorted(
        (e for e, t in engine_texts.items() if t and t.strip()),
        key=lambda e: (_priority(e), e),
    )

    if not engines:
        return ConsensusResult("", [], 0.0, 0.0, "empty", [], 0)

    engine_tokens: Dict[str, List[str]] = {e: tokenize(engine_texts[e]) for e in engines}
    engine_keys: Dict[str, List[str]] = {
        e: [vote_key(t) for t in engine_tokens[e]] for e in engines
    }

    if len(engines) == 1:
        # ZERO corroboration: one engine, nothing to agree with it. Hans M3:
        # emit an honest low confidence (SINGLE_ENGINE_CONFIDENCE), NEVER 1.0.
        # n_present stays 1 (one engine truly present); n_agree stays 1 (the
        # token trivially agrees with itself) — but confidence (and the page
        # aggregates) reflect that NO independent engine vouched for the read.
        e = engines[0]
        toks = [
            CommittedToken(
                t, vote_key(t), 1, 1, SINGLE_ENGINE_CONFIDENCE, [e],
                candidates=([{"engine": e, "token": t}] if capture_candidates else None),
            )
            for t in engine_tokens[e]
        ]
        text = " ".join(t.surface for t in toks)
        # page_confidence / token_agreement_ratio honestly reflect zero
        # corroboration (not 1.0): a single-engine page is uncorroborated.
        return ConsensusResult(
            text, toks,
            SINGLE_ENGINE_CONFIDENCE,   # page_confidence (was dishonest 1.0)
            0.0,                        # token_agreement_ratio: no >=2 agreement possible
            "single", engines, len(toks),
        )

    if _legacy_spine_no_merge:
        # Pre-S1A-fix path (A/B measurement only): most-tokens spine, NO merge.
        spine = min(
            engine_tokens.keys(),
            key=lambda e: (-len(engine_tokens[e]), _priority(e), e),
        )
        others = [e for e in engines if e != spine]
        spine_tokens = list(engine_tokens[spine])
        spine_keys = list(engine_keys[spine])
    else:
        spine = _choose_spine(engine_tokens)
        others = [e for e in engines if e != spine]

        # ---- S1-A spine-merge: repair OCR word-splits the spine still carries --
        # If the chosen spine split a word ("Weights" -> "W eights") but >=2 OTHER
        # engines read the whole word, collapse those adjacent spine positions
        # into one faithful whole-word token BEFORE alignment/voting, so no
        # phantom fragment ("eights") can ever be committed.
        engine_key_sets: Dict[str, set] = {e: set(engine_keys[e]) for e in engines}
        spine_tokens = _merge_spine_splits(
            engine_tokens[spine], engine_tokens, engine_key_sets, spine
        )
        spine_keys = [vote_key(t) for t in spine_tokens]

    # align each other engine to the (de-fragmented) spine
    aligned_map: Dict[str, List[Optional[int]]] = {}
    insertions_map: Dict[str, Dict[int, List[int]]] = {}
    for e in others:
        aligned, ins = _align_to_spine(spine_keys, engine_keys[e])
        aligned_map[e] = aligned
        insertions_map[e] = ins

    committed: List[CommittedToken] = []
    n_engines = len(engines)

    def commit_insertions_before(pos: int):
        """Commit any tokens that >=2 engines inserted (and the spine lacked) at pos.

        Only majority-agreed insertions are committed, so we never invent content
        a single engine hallucinated. Surfaces come verbatim from the engines.
        """
        # collect inserted tokens by key across the other engines at this pos
        cand: Dict[str, List[Tuple[str, str]]] = {}
        for e in others:
            for oi in insertions_map[e].get(pos, []):
                surf = engine_tokens[e][oi]
                k = engine_keys[e][oi]
                if k == "":
                    continue
                cand.setdefault(k, []).append((e, surf))
        for k in sorted(cand.keys()):
            voters = cand[k]
            if len(voters) >= 2:  # >=2 engines independently inserted it -> commit
                voters_sorted = sorted(voters, key=lambda ev: (_priority(ev[0]), ev[0]))
                surface = voters_sorted[0][1]
                cands = None
                if capture_candidates:
                    # the inserting engines' surfaces at this position (sorted)
                    cands = [
                        {"engine": e, "token": s}
                        for e, s in sorted(voters, key=lambda ev: (_priority(ev[0]), ev[0]))
                    ]
                committed.append(
                    CommittedToken(
                        surface, k, len(voters), n_engines,
                        round(len(voters) / n_engines, 4),
                        sorted(e for e, _ in voters),
                        candidates=cands,
                    )
                )

    for i, spine_surface in enumerate(spine_tokens):
        commit_insertions_before(i)
        candidates: List[Tuple[str, Optional[str]]] = [(spine, spine_surface)]
        for e in others:
            oi = aligned_map[e][i]
            candidates.append((e, engine_tokens[e][oi] if oi is not None else GAP))
        surface, key, n_agree, n_present, voters = _vote(candidates)
        if surface == "":
            # nothing votable (all GAP/punct) — keep the spine surface faithfully,
            # flagged as low confidence (only the spine present)
            surface = spine_surface
            key = vote_key(spine_surface)
            n_agree = 1
            n_present = 1
            voters = [spine]
        conf = round(n_agree / n_present, 4) if n_present else 0.0
        cands = None
        if capture_candidates:
            # what EACH engine read at this spine position (incl. disagreements);
            # GAP -> token null. Sorted by engine priority for determinism.
            cands = [
                {"engine": e, "token": (t if t is not GAP and t is not None else None)}
                for e, t in sorted(candidates, key=lambda ev: (_priority(ev[0]), ev[0]))
            ]
        committed.append(
            CommittedToken(surface, key, n_agree, n_present, conf, voters,
                           candidates=cands)
        )
    commit_insertions_before(len(spine_tokens))  # trailing inserts

    # aggregates
    if committed:
        total_present = sum(t.n_present for t in committed)
        weighted_conf = sum(t.confidence * t.n_present for t in committed)
        page_conf = round(weighted_conf / total_present, 4) if total_present else 0.0
        # majority threshold: with 3 engines need >=2 agree; with 2 need ==2
        maj = 2
        agreed = sum(1 for t in committed if t.n_agree >= maj)
        agreement_ratio = round(agreed / len(committed), 4)
    else:
        page_conf = 0.0
        agreement_ratio = 0.0

    method = f"token_majority_{n_engines}"
    text = " ".join(t.surface for t in committed)
    return ConsensusResult(
        committed_text=text,
        tokens=committed,
        page_confidence=page_conf,
        token_agreement_ratio=agreement_ratio,
        method=method,
        engines_used=engines,
        n_tokens=len(committed),
    )


# A committed token is "low confidence" (a Phase C review candidate) when fewer
# engines agreed on it than the page's engines would allow at full agreement —
# i.e. confidence < 1.0 OR not every present engine was even present. We expose
# the threshold as a module constant so ingest and the review queue agree.
LOW_CONFIDENCE_THRESHOLD = 1.0  # confidence < this  -> flagged for review


def consensus_from_page_record(
    page: dict, capture_candidates: bool = False
) -> ConsensusResult:
    """
    Adapter for a page_ocr_results.json record. Pulls tess_text/doctr_text/
    surya_text (any may be missing/empty) and builds the consensus.

    capture_candidates: when True, each CommittedToken carries the per-engine
    candidate reads (the Phase C disagreement substrate). Left False for the
    quality-estimate-only callers so their output is unchanged.
    """
    texts = {}
    if page.get("tess_text"):
        texts["tesseract"] = page["tess_text"]
    if page.get("doctr_text"):
        texts["doctr"] = page["doctr_text"]
    if page.get("surya_text"):
        texts["surya"] = page["surya_text"]
    return build_consensus(texts, capture_candidates=capture_candidates)


if __name__ == "__main__":
    # tiny self-test (no I/O dependencies) demonstrating determinism + 2/3 engine
    demo = {
        "tesseract": "AN ACT fixing the time for Acts and Joint Resolutions.",
        "doctr": "AN ACT firing the lime for Acts and Joint Resolutions.",
        "surya": "AN ACT fixing the time for Acts and Joint Resolutions.",
    }
    r = build_consensus(demo)
    print("method:", r.method, "engines:", r.engines_used)
    print("committed:", r.committed_text)
    print("page_confidence:", r.page_confidence, "agreement_ratio:", r.token_agreement_ratio)
    for t in r.tokens:
        flag = "" if t.confidence == 1.0 else "  <-- dissent"
        print(f"  {t.surface!r:30} agree={t.n_agree}/{t.n_present} conf={t.confidence}{flag}")
    # run twice -> identical
    r2 = build_consensus(demo)
    assert r2.committed_text == r.committed_text, "NON-DETERMINISTIC!"
    print("determinism check: OK")
