"""recover_multiengine_headers.py -- ADDITIVE, PRECISION-FIRST recovery of MODERN-format
chapter headers (1910+) that the token-majority `consensus_text` parse MISSED because the
clean header survives only in a per-engine field (surya_text / doctr_text / tess_text).

CONTEXT (verified 2026-06-17, see docs run-log multiengine-headers-run.md):
  The production parse reads ONE text per page -- the majority-vote `consensus_text`. When
  two engines garble the numeral on a "CHAPTER N." header line, the consensus inherits the
  garble and the header is lost. But the OTHER engine read it cleanly. Measured on 1915:
  surya alone has 450 clean standalone "CHAPTER N." headers, the 3-engine union 498, yet the
  certified floor holds only 278 distinct chapter numbers. The headers ARE in the OCR; the
  single-text parse missed them. Same pattern in 1911 (production-1910-11) and 1941.

WHAT THIS DOES -- ADDITIVE ONLY, NEVER MUTATES AN EXISTING PARSE:
  * FLOOR = the best-of current parse's confident chapter numbers (certified > chaptered_v2 >
    early_v2 > recovered), read read-only. We ONLY recover numbers NOT already in the floor.
  * For each page, scan EACH engine field for STANDALONE line-head "CHAPTER <arabic>." headers
    (the modern format). Record (chapter_number, engine, page, line_index).
  * Accept a recovered number for a page ONLY when, for a candidate header occurrence:
      (in-range) 1 <= n <= oracle_N, AND
      a REAL-ACT BODY WITNESS is present in BOTH cases (an `An act` title + an approval/enact
        marker + a minimum body length -- NOT a one-line TOC entry), AND the numeral is trusted:
      (A) >= 2 INDEPENDENT engines (surya/doctr/tess -- NOT consensus, which is their token
          majority) read the SAME clean number at a line-head position on that page, OR
      (B) exactly one INDEPENDENT engine reads it cleanly AND the body witness corroborates.
    The body witness is MANDATORY for emission in EITHER case: numeral agreement alone never
    emits an act (a two-engine TOC line is not an act). consensus_text is read only for body /
    resolution screening -- it gets NO numeral-agreement vote.
    This mirrors recover_chaptered.py's keep-gate. Its guard helpers (quoted-title exclusion,
    body-ref head cue, resolution exclusion, the line-head header predicate, approval/an-act
    detectors) are IMPORTED and reused -- recover_chaptered.py is NOT modified.

PRECISION INVARIANTS (hard -- enforced + self-checked in meta):
  * never emit a number already held by a confident floor act;
  * never emit the same number twice (intra-pass dedup);
  * never emit out of [1, oracle_N];
  * if a page's engines disagree on the number with NO >=2 majority and no single-engine
    body witness -> SKIP (do not guess) -> routed to needs_review;
  * exclude resolutions, TOC/front-matter (require a real act body), quoted titles, body
    cross-references.

OUTPUT: a NEW file production-<label>/parsed_acts_multiengine.json (NOT overwritten -- if it
  exists, writes parsed_acts_multiengine.json.new). Contains recovered_acts[], needs_review[],
  and _multiengine_meta with floor_count / recovered_count / oracle_N /
  duplicate_numbers_introduced (MUST be 0).

SCOPE: MODERN standalone "CHAPTER <arabic>." era only. The early-italic ROMAN "CHAP. <ROMAN>"
  era is intentionally NOT covered here (left for a later pass).

USAGE:  python -m ingest.recover_multiengine_headers 1915-vol1-chapters 1910-11 1941-vol1-41chapters
"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # pipeline/ on path
import config

ROOT = Path(config.path_for("data_root"))

# ---- reuse recover_chaptered.py guards (which itself reuses ingest_from_ocr) -- READ ONLY ----
_RC = Path(__file__).resolve().parent / "recover_chaptered.py"
_spec = importlib.util.spec_from_file_location("recover_chaptered_ro", str(_RC))
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

AN_ACT_RE = rc.AN_ACT_RE
APPROVAL_RE = rc.APPROVAL_RE
RESOLUTION_RE = rc.RESOLUTION_RE
BODYREF_HEAD_CUE = rc.BODYREF_HEAD_CUE
_quoted_before = rc._quoted_before

# consensus_text is the token-majority of the three independent engines -- it is NOT an
# independent witness. It must NEVER count toward the ">=2 engines agree" vote (CRITICAL-1):
# counting it manufactures a false "2-engine agreement" out of a single real read. The THREE
# INDEPENDENT engines below are the ONLY votes for numeral agreement. consensus_text is still
# scanned (ENGINES) for body-witness / resolution screening, never for the agreement vote.
INDEPENDENT_ENGINES = ("surya_text", "doctr_text", "tess_text")
ENGINES = INDEPENDENT_ENGINES + ("consensus_text",)

# MODERN standalone header: the line is essentially JUST "CHAPTER <arabic>." with at most a
# little leading noise and a trailing punctuation. A clean unambiguous arabic numeral is
# REQUIRED (no embedded garble glyph -- precision). A run-on tail (a sentence after the
# number) disqualifies it: that is a body line, not a standalone header.
MODERN_HEAD_RE = re.compile(
    r"^[^A-Za-z0-9]{0,3}"
    r"CHAPTER"
    r"[.\s]+"
    r"([0-9]{1,4})"           # clean arabic numeral, NO trailing garble glyph allowed
    r"\s*[.,]?\s*$")          # end of line (optional terminal . or ,)

AN_ACT_LOOKAHEAD = 8          # lines after header to find the "An Act" title (engine-local)
APPROVAL_LOOKAHEAD = 60       # lines after header to find the approval/enact footer
MIN_BODY_CHARS = 200          # a real act body is long; a TOC line is short -> excludes TOC


def floor_numbers(label):
    """Best-of current parse's CONFIDENT chapter numbers + (acts, source_file, oracle_N).
    Priority: certified > chaptered_v2 > early_v2 > recovered. Read-only."""
    d = ROOT / ("production-" + label)
    order = ("parsed_acts_certified.json", "parsed_acts_chaptered_v2.json",
             "parsed_acts_early_v2.json", "parsed_acts_recovered.json")
    src = None
    j = None
    for fn in order:
        p = d / fn
        if p.exists():
            src = fn
            j = json.loads(p.read_text(encoding="utf-8"))
            break
    if j is None:
        return set(), [], None, None
    acts = j.get("confident_acts", [])
    # MAJOR-1: the dedup FLOOR must include flagged_acts numbers too -- recover_chaptered's
    # _load_before (its "CRITICAL-B1" fix) unions confident AND flagged chapter_ints, because
    # flagged_acts (dup_number / chapter_number_suspect) DO carry a real chapter_int that this
    # pass must never re-emit. We mirror that exactly: scan confident_acts AND flagged_acts,
    # taking chapter_int_final if present else chapter_int.
    flagged = j.get("flagged_acts", [])

    def _add_nums(seq, dest):
        for a in seq:
            n = a.get("chapter_int_final")
            if not isinstance(n, int):
                n = a.get("chapter_int")
            if isinstance(n, int) and n > 0:
                dest.add(n)

    nums = set()
    _add_nums(acts, nums)        # confident floor numbers
    _add_nums(flagged, nums)     # + flagged (dup/suspect) numbers -- never re-emit these
    oracle_N = None
    for mk in ("_certify_meta", "_chaptered_meta", "_recovery_meta", "_meta"):
        if isinstance(j.get(mk), dict) and isinstance(j[mk].get("oracle_N"), int):
            oracle_N = j[mk]["oracle_N"]
            break
    return nums, acts, src, oracle_N


def page_engine_lines(pg, engine):
    return (pg.get(engine) or "").split("\n")


def scan_page_headers(pg):
    """Return {chapter_number: {engine: line_index}} for clean standalone headers on a page,
    across all engines. A number may be read by several engines (cross-engine agreement)."""
    hits = {}
    for e in ENGINES:
        lines = page_engine_lines(pg, e)
        for i, ln in enumerate(lines):
            m = MODERN_HEAD_RE.match(ln.strip())
            if not m:
                continue
            n = int(m.group(1))
            hits.setdefault(n, {})
            # keep the FIRST line-index this engine read the number at
            hits[n].setdefault(e, i)
    return hits


def body_witness(pg, engine, header_line_idx, chapter_num):
    """Single-engine body witness (gate B). In `engine`'s own text, starting at the header
    line, find within lookahead a genuine `An act` title (not quoted / not body-ref) AND an
    approval/enact footer, with a real (long) body. Returns (ok, title, witness_str)."""
    lines = page_engine_lines(pg, engine)
    n = len(lines)
    # title search
    title = None
    title_idx = -1
    lim = min(n, header_line_idx + 1 + AN_ACT_LOOKAHEAD)
    for j in range(header_line_idx, lim):
        seg = lines[j]
        am = AN_ACT_RE.search(seg)
        if not am:
            continue
        if _quoted_before(seg, am):
            continue
        if BODYREF_HEAD_CUE.search(seg):
            continue
        head = seg[:am.start()].strip(" \t.,:;\"'`-")
        if head and len(head) > 14 and not re.match(
                r"^(?:Stats?\.?\s*\d{0,4}[.,]?|[A-Z][a-zA-Z]{0,9}\.?)$", head):
            continue
        title = re.sub(r"\s+", " ", seg).strip()[:500]
        title_idx = j
        break
    if title is None:
        return False, None, None
    # approval / enact witness
    witness = None
    alim = min(n, header_line_idx + APPROVAL_LOOKAHEAD)
    body_chunk = "\n".join(lines[header_line_idx:alim])
    am2 = APPROVAL_RE.search(body_chunk)
    if am2:
        witness = body_chunk[max(0, am2.start() - 5): am2.start() + 40].strip()
    elif rc.ing.has_enact_marker(body_chunk):
        witness = "do enact"
    if witness is None:
        return False, None, None
    # min body length (exclude one-line TOC entries)
    body_len = len(re.sub(r"\s+", " ", "\n".join(lines[header_line_idx:alim])).strip())
    if body_len < MIN_BODY_CHARS:
        return False, None, None
    return True, title, witness


def is_resolution_near(pg, header_line_idx):
    """Resolution exclusion: scan a small window across ALL THREE independent engines
    (surya_text, doctr_text, tess_text) for a resolution cue (MAJOR-3). Previously only
    consensus_text + surya_text were scanned, so a resolution that one of the other
    independent engines read (and consensus garbled) slipped through."""
    for e in INDEPENDENT_ENGINES:
        lines = page_engine_lines(pg, e)
        win = "\n".join(lines[header_line_idx: header_line_idx + 8])
        if RESOLUTION_RE.search(win):
            return True
    return False


def best_excerpt(pg, engine, header_line_idx):
    lines = page_engine_lines(pg, engine)
    chunk = "\n".join(lines[header_line_idx: header_line_idx + 6])
    return re.sub(r"[ \t]+", " ", chunk).strip()[:400]


def _skipped_meta(label, reason):
    """DEFECT-B: a SKIPPED meta for a volume that could not be processed -- batch continues."""
    return {
        "label": label,
        "detector": "recover_multiengine_headers.py v1 (modern CHAPTER N. cross-engine, additive)",
        "SKIPPED": True,
        "skip_reason": reason,
        "floor_source": None,
        "floor_count": 0,
        "oracle_N": None,
        "oracle_N_source": "none",
        "recovered_count": 0,
        "range_gated_count": 0,
        "needs_review_count": 0,
        "duplicate_numbers_introduced": 0,
    }


def process_label(label):
    # DEFECT-B: isolate the ENTIRE per-volume body in try/except. A missing/corrupt
    # page_ocr_results.json (FileNotFoundError, JSONDecodeError, etc.) on ONE volume must
    # NEVER abort the whole batch -- record a SKIPPED meta and let the caller continue.
    try:
        return _process_label_inner(label)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: one bad vol can't kill the run
        reason = "%s: %s" % (type(exc).__name__, str(exc)[:300])
        return [], [], _skipped_meta(label, reason)


def _process_label_inner(label):
    d = ROOT / ("production-" + label)
    raw = json.loads((d / "ocr_consensus" / "page_ocr_results.json").read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}

    floor, floor_acts, floor_src, oracle_N = floor_numbers(label)
    # MAJOR-2: NEVER fall back to a blind 9999 -- that silently disables the range gate and
    # lets garbled page/section/year numerals (up to 9999) pass as chapter numbers.
    #   * oracle_N resolved          -> use it (oracle).
    #   * oracle_N None, floor non-empty -> use max(floor), recorded as floor_max_fallback so
    #                                       it is auditable (still a real range gate).
    #   * oracle_N None, floor empty -> REFUSE: skip the volume entirely with a loud meta note.
    oracle_N_source = "oracle"
    if oracle_N is None:
        if floor:
            oracle_N = max(floor)
            oracle_N_source = "floor_max_fallback"
        else:
            # No way to range-gate at all. Recover NOTHING from this volume; emit a loud meta.
            meta = {
                "label": label,
                "detector": "recover_multiengine_headers.py v1 (modern CHAPTER N. cross-engine, additive)",
                "SKIPPED": True,
                "skip_reason": ("oracle_N unresolved AND floor empty -- cannot range-gate; "
                                "refusing to recover (would let garble up to 9999 pass)."),
                "floor_source": floor_src,
                "floor_count": 0,
                "oracle_N": None,
                "oracle_N_source": "none",
                "recovered_count": 0,
                "needs_review_count": 0,
                "duplicate_numbers_introduced": 0,
            }
            return [], [], meta

    recovered = []
    needs_review = []
    emitted_numbers = set()        # numbers we have RECOVERED this pass (intra-pass dedup)
    range_gated_count = 0          # DEFECT-A: how many candidates the range gate dropped

    for pidx in sorted(pages):
        pg = pages[pidx]
        page_1 = pg.get("page_1indexed", pidx + 1)
        hits = scan_page_headers(pg)
        for n in sorted(hits):
            # range gate (kills garbled page-number / citation numerals like 5828)
            if not (1 <= n <= oracle_N):
                # DEFECT-A: always count the drop, and when the range ceiling is only a
                # floor_max_fallback (NOT the real oracle), make the drop AUDITABLE by routing
                # the out-of-range candidate to needs_review instead of silently dropping it.
                # We still NEVER emit it -- precision is intact. When oracle_N is the real
                # oracle value, a plain continue is fine (just count it).
                range_gated_count += 1
                if oracle_N_source == "floor_max_fallback":
                    eng_read = hits[n]
                    needs_review.append({
                        "chapter_int": n,
                        "source_page": page_1,
                        "engines_read": sorted(eng_read),
                        "reason": "out_of_range_floor_max_fallback",
                        "oracle_N": oracle_N,
                        "oracle_N_source": oracle_N_source,
                        "excerpt": best_excerpt(pg, sorted(eng_read)[0], min(eng_read.values())),
                    })
                continue
            # FLOOR exclusion: only recover numbers NOT already confident
            if n in floor:
                continue
            engines_read = hits[n]                 # {engine: line_idx} (ALL engines, incl. consensus)
            # CRITICAL-1: the engine-AGREEMENT vote must use ONLY the three INDEPENDENT engines.
            # consensus_text is the token-majority of those three -- counting it would fabricate
            # a false "2-engine agreement" from a single independent read. consensus may still
            # corroborate the body witness below, but it gets NO vote here.
            indep_read = {e: engines_read[e] for e in INDEPENDENT_ENGINES if e in engines_read}
            if not indep_read:
                # only consensus_text read this number at a line-head -> not an independent
                # signal at all -> never emit (consensus inherits whatever the engines read).
                continue
            # resolution exclusion (use the earliest header line idx among independent engines)
            min_idx = min(indep_read.values())
            if is_resolution_near(pg, min_idx):
                continue

            multi = len(indep_read) >= 2            # gate A numeral test: >=2 INDEPENDENT engines agree

            # CRITICAL-2: a real-act body witness is REQUIRED for EVERY emitted act -- numeral
            # agreement alone is NOT enough (a TOC line "CHAPTER 5. An act to..." read by two
            # engines must NOT become an act). body_witness() requires an `An act` title (not
            # quoted, not a body cross-ref) AND an approval/enact marker AND >= MIN_BODY_CHARS
            # of following body -- a TOC one-liner fails the length guard. We look for the body
            # witness in the independent engines first, then allow consensus_text to corroborate.
            witness = None
            title = None
            wit_engine = None
            for e in INDEPENDENT_ENGINES + ("consensus_text",):
                if e not in engines_read:
                    continue
                ok, t, w = body_witness(pg, e, engines_read[e], n)
                if ok:
                    witness, title, wit_engine = w, t, e
                    break

            body_ok = witness is not None
            # NUMERAL is trusted when (>=2 independent engines agree) OR (exactly one
            # independent engine reads it cleanly AND the body witness corroborates). In the
            # single-engine case the body witness IS the corroboration, so require body_ok.
            numeral_trusted = multi or (len(indep_read) == 1 and body_ok)
            # ...AND in BOTH cases a real-act body is REQUIRED before emitting.
            accept = numeral_trusted and body_ok
            if not accept:
                # detected but not safely numbered/witnessed -> needs_review, NEVER emitted
                if not body_ok:
                    reason = ("no real-act body witness (no An-act title / no approval-enact "
                              "marker / body shorter than %d chars -- likely TOC or stub)"
                              % MIN_BODY_CHARS)
                else:
                    reason = "single independent engine read with no corroborating body witness"
                needs_review.append({
                    "chapter_int": n,
                    "source_page": page_1,
                    "engines_read": sorted(engines_read),
                    "independent_engines_read": sorted(indep_read),
                    "multi_engine_agreement": multi,
                    "body_witness_found": body_ok,
                    "reason": reason,
                    "excerpt": best_excerpt(pg, sorted(indep_read)[0], min_idx),
                })
                continue

            # intra-pass dedup: the SAME number must never be emitted twice. If a later page
            # also yields this number, the first wins; the second is routed to needs_review.
            if n in emitted_numbers:
                needs_review.append({
                    "chapter_int": n,
                    "source_page": page_1,
                    "engines_read": sorted(engines_read),
                    "independent_engines_read": sorted(indep_read),
                    "reason": "duplicate of an already-recovered number (kept first occurrence)",
                    "excerpt": best_excerpt(pg, sorted(indep_read)[0], min_idx),
                })
                continue

            # choose a display engine + title/excerpt: prefer the witness engine, else an
            # independent engine that read the header.
            disp_engine = wit_engine or next(
                (e for e in INDEPENDENT_ENGINES if e in indep_read),
                sorted(indep_read)[0])
            disp_idx = engines_read[disp_engine]
            if title is None:
                _ok, title, _w = body_witness(pg, disp_engine, disp_idx, n)
            # MINOR-1: provenance must truthfully record HOW the act was accepted -- which
            # INDEPENDENT engines agreed on the numeral, whether consensus also read it, and
            # which engine supplied the corroborating body witness.
            rec = {
                "chapter": str(n),
                "chapter_int": n,
                "source_page": page_1,
                "engines_read": sorted(engines_read),
                "independent_engines_agreed": sorted(indep_read),
                "n_independent_agreed": len(indep_read),
                "consensus_also_read": "consensus_text" in engines_read,
                "agreement": "multi_engine" if multi else "single_engine_body_witness",
                "body_witness_engine": wit_engine,
                "body_witness_found": True,
                "witness": witness,
                "title": title or "",
                "text_excerpt": best_excerpt(pg, disp_engine, disp_idx),
                "origin": "multiengine_v1",
            }
            recovered.append(rec)
            emitted_numbers.add(n)

    # ---- self-checked precision invariants ----
    rec_nums = [r["chapter_int"] for r in recovered]
    dup_in_pass = len(rec_nums) - len(set(rec_nums))
    dup_vs_floor = len(set(rec_nums) & floor)
    out_of_range = sum(1 for x in rec_nums if not (1 <= x <= oracle_N))
    duplicate_numbers_introduced = dup_in_pass + dup_vs_floor + out_of_range

    after = len(floor) + len(set(rec_nums))
    meta = {
        "label": label,
        "detector": "recover_multiengine_headers.py v1 (modern CHAPTER N. cross-engine, additive)",
        "scope": "MODERN standalone 'CHAPTER <arabic>.' only; early roman CHAP. era NOT covered",
        "floor_source": floor_src,
        "floor_count": len(floor),
        "oracle_N": oracle_N,
        "oracle_N_source": oracle_N_source,    # "oracle" | "floor_max_fallback" (MAJOR-2)
        "recovered_count": len(recovered),
        "recovered_multi_engine": sum(1 for r in recovered if r["agreement"] == "multi_engine"),
        "recovered_single_witness": sum(1 for r in recovered if r["agreement"] == "single_engine_body_witness"),
        "range_gated_count": range_gated_count,   # DEFECT-A: candidates dropped by the range gate
        "needs_review_count": len(needs_review),
        "after_distinct_floor_plus_recovered": after,
        "implied_completeness_before": round(len(floor) / oracle_N, 4) if oracle_N else None,
        "implied_completeness_after": round(after / oracle_N, 4) if oracle_N else None,
        "missing_before": (oracle_N - len(floor)) if oracle_N else None,
        "fraction_of_missing_recovered": (
            round(len(set(rec_nums)) / (oracle_N - len(floor)), 4)
            if oracle_N and (oracle_N - len(floor)) > 0 else None),
        "duplicate_numbers_introduced": duplicate_numbers_introduced,   # MUST be 0
        "_invariant_breakdown": {
            "dup_within_pass": dup_in_pass,
            "dup_vs_floor": dup_vs_floor,
            "out_of_range": out_of_range,
        },
    }
    return recovered, needs_review, meta


def write_label(label):
    recovered, needs_review, meta = process_label(label)
    d = ROOT / ("production-" + label)
    out = d / "parsed_acts_multiengine.json"
    suffix = ""
    if out.exists():
        out = d / "parsed_acts_multiengine.json.new"
        suffix = " (existing file present -> wrote .new)"
    out.write_text(json.dumps({
        "recovered_acts": recovered,
        "needs_review": needs_review,
        "_multiengine_meta": meta,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta, out, suffix


def main():
    args = sys.argv[1:]
    if not args:
        raise SystemExit("usage: python -m ingest.recover_multiengine_headers <label> ...")
    for label in args:
        # DEFECT-B backstop: isolate each label at the driver level too -- even a failure in
        # write_label (e.g. an unwritable output dir) must not abort the rest of the batch.
        try:
            meta, out, suffix = write_label(label)
        except Exception as exc:  # noqa: BLE001
            print(f"{label}: SKIPPED (write_label error) -- "
                  f"{type(exc).__name__}: {str(exc)[:200]}")
            continue
        if meta.get("SKIPPED"):
            print(f"{label}: SKIPPED -- {meta.get('skip_reason')} -> {out.name}{suffix}")
            continue
        print(f"{label}: floor={meta['floor_count']} "
              f"(src={meta['floor_source']}) +recovered={meta['recovered_count']} "
              f"(multi={meta['recovered_multi_engine']} "
              f"single_witness={meta['recovered_single_witness']}) "
              f"-> after={meta['after_distinct_floor_plus_recovered']} / N={meta['oracle_N']} "
              f"| completeness {meta['implied_completeness_before']}->{meta['implied_completeness_after']} "
              f"| dup_introduced={meta['duplicate_numbers_introduced']} "
              f"| range_gated={meta.get('range_gated_count')} "
              f"| needs_review={meta['needs_review_count']} "
              f"-> {out.name}{suffix}")


if __name__ == "__main__":
    main()
