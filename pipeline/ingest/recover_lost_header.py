"""recover_lost_header.py -- GARBLED-NUMERAL / POSITION repair for the chaptered era.
================================================================================
PRECISION-FIRST. READ-ONLY w.r.t. the DB and every existing file. Writes ONLY a NEW
parsed_acts_lostheader.json per volume (if one already exists, writes .new -- never
clobbers). Never touches parsed_acts_certified.json / parsed_acts_chaptered_v2.json /
parsed_acts_recovered.json / parsed_acts_multiengine.json.

RUNS AFTER recover_multiengine_headers.py. This is NOT a general "header-independent"
recovery: it is the LAST, narrowest pass, and it targets ONLY the true post-multi-engine
RESIDUAL -- the chapters that are STILL missing after BOTH the certified floor AND the
multi-engine cross-engine recovery have run. multiengine already recovers every case where
SOME engine read the numeral cleanly; what is left for this pass is the harder subclass
where the PRINTED NUMERAL is garbled in ALL engines, but the act BOUNDARY is still visible.

PROBLEM (post-certification + post-multiengine residual, "garbled-numeral loss")
--------------------------------------------------------------------------------
After certify_chapters.py AND recover_multiengine_headers.py, some chapters in [1,N] are
STILL missing as confident/recovered acts. A large, addressable subclass is the
"garbled-numeral loss" act: the act boundary IS in the OCR (a "CHAPTER" header line and/or
an "An Act ..." title with an "[Approved ...]" / "Filed with Secretary of State" footer),
but the PRINTED NUMERAL is too OCR-garbled to read correctly in EVERY engine -- e.g. real
chapter 143 prints as "CHAPTER 148", real 213 prints as "CHAPTER 2138". Because the misread
numeral is in-range and disagrees with the true (positional) number, certify's
witness-guarded position_fill ABORTS the gap, and because no engine read it cleanly the
multi-engine pass cannot recover it either, so the act is left missing.

This pass recovers those acts by their act-BOUNDARY signal (NOT the numeral) and assigns the
chapter number by SEQUENCE/POSITION (the printed numeral is discarded as untrustworthy) --
but only in the UNAMBIGUOUS case: exactly ONE undetected act boundary sits, in correct page
order, between two CONFIDENT anchors that bracket exactly ONE open (residual) chapter slot.
Anything else (>1 candidate for the slot, >1 open slot, no detectable boundary) is LEFT for
a later re-OCR pass -- never guessed.

DO-NOT-FILL SET (post-multi-engine residual targeting -- KEY integration)
-------------------------------------------------------------------------
The "open slot" computation EXCLUDES every already-accounted chapter number so this pass can
only ever fill the residual and can never collide with an earlier pass:
  (a) the best-of floor's confident_acts AND flagged_acts (certified > chaptered_v2 >
      early_v2 > recovered), AND
  (b) the MULTI-ENGINE recoveries -- read parsed_acts_multiengine.json.new if present, else
      parsed_acts_multiengine.json (recovered_acts[].chapter_int).
A number in the do-not-fill set is NEVER an open slot and is NEVER emitted; the duplicate
self-check is run against the FULL do-not-fill set AND the set this pass recovers.

DETECTION (header-independent act boundary)
-------------------------------------------
A candidate act-start is a line where EITHER:
  (a) a line-head "CHAPTER <numeral>" header (recover_chaptered.is_header_line) -- the numeral
      may be garbled; we DO NOT trust it; OR
  (b) a near-top "An Act ..." title (recover_chaptered.find_title guards: not a quoted
      citation, not a body cross-reference)
AND within a forward lookahead window there is an "An Act" title (genuine) AND an approval
footer ([Approved ...] / Filed with Secretary of State / In effect). The An-Act + approval
pair is the boundary witness; the header glyph is optional.

GUARDS (reused from recover_chaptered, precision over recall)
  - RESOLUTION_RE: a window naming a Concurrent/Joint Resolution / Constitutional Amendment
    is excluded (resolutions renumber from 1 in a separate section).
  - quoted-title / body-ref head cue: an "An act" inside a quote or after "of an act"/"under
    an act" is a citation, not a boundary (find_title handles this).
  - SPILLOVER: a candidate boundary whose own buffer holds >1 header is ambiguous -> skipped.

POSITION ASSIGNMENT (sequence, the number is lost)
  Build the session's CONFIDENT anchor stream (parsed_acts_certified.json, page-ordered,
  numbers unique & in [1,N], strictly increasing). For each adjacent anchor pair (lo@p_lo,
  hi@p_hi) in the SAME volume with hi-lo open slots, collect candidate boundaries on pages
  (p_lo, p_hi) that are NOT already a confident act (page-distinct from both anchors). Fill
  ONLY when #candidates == #open_slots and pairs map in page order; the i-th candidate gets
  the i-th open slot. With 1 open slot and 1 candidate this is the dominant, safe case.

OUTPUT record (status="seq_assigned_no_header")
  chapter, chapter_int(_final), chapter_raw="(seq)", title, approved_date, iso_date, text,
  source_page, has_an_act, has_approval, printed_numeral (the untrusted misread, for audit),
  lo_anchor, hi_anchor, origin="lostheader", status.

Acts with a detectable boundary but NO safe positional slot are emitted to a separate
"needs_reocr" list (status="boundary_no_slot") so the re-OCR pass can be sized.

USAGE
  python -m ingest.recover_lost_header "1961 Regular Session"
  python -m ingest.recover_lost_header --all
  python -m ingest.recover_lost_header --score "1961 Regular Session"   (prints before/after)
"""
from __future__ import annotations
import sys, re, json, importlib.util
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline"))
sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
import config  # noqa

def _load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

ROOT = Path(config.path_for("data_root"))
rc = _load_mod("recover_chaptered", REPO / "pipeline" / "ingest" / "recover_chaptered.py")
cc = _load_mod("certify_chapters", REPO / "pipeline" / "ingest" / "certify_chapters.py")
ing = rc.ing  # ingest_from_ocr predicates

PARSE_PREF = ("parsed_acts_certified.json", "parsed_acts_chaptered_v2.json",
              "parsed_acts_early_v2.json", "parsed_acts_recovered.json")

# Candidate boundary pages must sit STRICTLY between the two anchor pages: p_lo < pg < p_hi
# (fix #3). The anchors own their own pages; nothing on an anchor page is a candidate.


def assigned(a):
    v = a.get("chapter_int_final", a.get("chapter_int", 0))
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def best_parse(d):
    for n in PARSE_PREF:
        p = d / n
        if p.exists():
            return p, n
    return None, None


def floor_flagged_nums(p, N):
    """Numbers held by the best-of floor parse `p`: confident_acts AND flagged_acts.
    flagged_acts (dup_number / chapter_number_suspect) DO carry a real chapter_int that this
    pass must NEVER re-emit -- mirrors recover_multiengine_headers.floor_numbers (its MAJOR-1
    fix). Returns the in-range [1,N] set."""
    nums = set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return nums
    for bucket in ("confident_acts", "flagged_acts"):
        for a in data.get(bucket, []):
            n = assigned(a)
            if 1 <= n <= N:
                nums.add(n)
    return nums


def multiengine_nums(label, N):
    """Numbers recovered by recover_multiengine_headers.py for this volume -- read the .new
    file if present (the freshest, un-merged output), else the base file. recovered_acts[]
    carry chapter_int. KEY integration: these are added to the do-not-fill set so this pass
    targets ONLY the post-multi-engine residual and can never collide with a multi-engine
    number. Returns the in-range [1,N] set (empty if no multi-engine artifact exists)."""
    d = ROOT / ("production-" + label)
    nums = set()
    for fn in ("parsed_acts_multiengine.json.new", "parsed_acts_multiengine.json"):
        p = d / fn
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return nums
        for a in data.get("recovered_acts", []):
            n = a.get("chapter_int")
            if isinstance(n, int) and 1 <= n <= N:
                nums.add(n)
        return nums   # .new wins if present; do not also read the base file
    return nums


def session_members(target, oracle):
    """All production volumes whose session_key == target, in volume order, with N."""
    members = []
    N = None
    for d in sorted(ROOT.glob("production-*")):
        if not d.is_dir():
            continue
        label = d.name[len("production-"):]
        if cc.session_key(label) != target:
            continue
        p, name = best_parse(d)
        if p is None:
            continue
        members.append((label, p, name))
        if N is None:
            N = cc.oracle_N(label, oracle)
    return members, N


def load_lines(label):
    """page-ordered [(page_1based, line_str, line_idx_in_page)]."""
    ocr = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    if not ocr.exists():
        return []
    raw = json.loads(ocr.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    out = []
    for pidx in sorted(pages):
        for k, ln in enumerate(pages[pidx].get("consensus_text", "").split("\n")):
            out.append((pidx + 1, ln, k))   # page is 1-based to match source_page
    return out


RES_CUE_WINDOW = 8   # lines below a header to scan for a resolution cue. The resolution
# heading often trails the "CHAPTER"/"An Act" line by a few lines in this corpus (the
# Concurrent/Joint Resolution / Constitutional Amendment naming sits in the title block, not
# always on line 1), so an over-tight 1-2 line window misses it. 8 lines covers the title
# block while staying inside the act head (well short of the body), matching the
# resolution-screen window recover_multiengine_headers.is_resolution_near uses.


def detect_boundaries(lines, volume_year=None):
    """Act-start boundaries in reading order; the printed numeral is NOT trusted.

    A boundary is anchored at a LINE-HEAD "CHAPTER ..." header (numeral untrusted) when that
    header's buffer (to the next header) carries a genuine "An Act" title AND an approval
    footer. This reuses recover_chaptered's segmentation (header stream) + title/approval/
    resolution guards, but DOES NOT trust or require a readable numeral.

    Returns list of dicts: {i, page, printed_numeral, title, has_an_act, has_approval,
                            has_enact, is_resolution, spillover, text}.
    """
    headers = rc.detect_headers(lines)   # [(i, num, raw)] line-head CHAPTER headers
    out = []
    for k, (si, num, raw) in enumerate(headers):
        ei = headers[k + 1][0] if k + 1 < len(headers) else len(lines)
        title, an_idx = rc.find_title(lines, si, ei)
        has_an_act = title is not None
        appr = rc.has_approval(lines, si, ei)
        buf = "\n".join(lines[j][1] for j in range(si, ei)).strip()
        has_enact = bool(ing.has_enact_marker(buf))
        win = "\n".join(lines[j][1] for j in range(si, min(ei, si + RES_CUE_WINDOW)))
        is_res = bool(rc.RESOLUTION_RE.search(win)) and not has_an_act
        # spillover: this buffer holds another line-head header beyond its own first line
        spillover = cc.chapter_header_count(buf) > 1
        iso_date, approved_str = ing.parse_act_date(buf, volume_year=volume_year)
        out.append({
            "i": si, "page": lines[si][0],
            "printed_numeral": num,
            "title": title or "",
            "has_an_act": has_an_act,
            "has_approval": appr,
            "has_enact": has_enact,
            "is_resolution": is_res,
            "spillover": spillover,
            "approved_date": approved_str,
            "iso_date": iso_date,
            "text": re.sub(r"[ \t]+", " ", buf)[:6000],
        })
    return out


def is_real_boundary(b):
    """A genuine act-start boundary: An-Act title present AND (approval footer OR enacting
    clause). Resolutions and spillover buffers are excluded."""
    if b["is_resolution"] or b["spillover"]:
        return False
    if not b["has_an_act"]:
        return False
    return b["has_approval"] or b["has_enact"]


def recover_session(target, oracle):
    members, N = session_members(target, oracle)
    result = {"session": target, "N": N, "members": [m[0] for m in members],
              "recovered": [], "needs_reocr": [], "meta": {}}
    if not members or N is None:
        result["meta"]["skipped"] = "no members or no oracle N"
        return result

    label_order = {lbl: i for i, (lbl, _, _) in enumerate(members)}

    # confident anchor stream + the set of confident (label,page) and numbers.
    # present_nums = ONLY confident_acts numbers (these and only these may be ANCHORS).
    conf = []   # (label, page, num)
    conf_pages = defaultdict(set)   # label -> set(pages with a confident act)
    present_nums = set()
    for label, p, name in members:
        data = json.loads(p.read_text(encoding="utf-8"))
        for a in data.get("confident_acts", []):
            n = assigned(a)
            if 1 <= n <= N:
                pg = a.get("source_page", 0)
                conf.append((label, pg, n))
                conf_pages[label].add(pg)
                present_nums.add(n)
    conf.sort(key=lambda t: (label_order[t[0]], t[1]))

    # DO-NOT-FILL SET (fix #2 -- post-multi-engine residual targeting). A number here is
    # NEVER an open slot and is NEVER emitted. It is the UNION of:
    #   (a) the best-of floor's confident_acts AND flagged_acts (every member volume), AND
    #   (b) the MULTI-ENGINE recoveries (.new if present else base) for every member volume.
    # This guarantees this pass fills ONLY the residual left after multi-engine, and can
    # never collide with a confident, flagged, or multi-engine number.
    do_not_fill = set(present_nums)
    multiengine_present = set()
    for label, p, name in members:
        do_not_fill |= floor_flagged_nums(p, N)   # confident + flagged (in-range)
        me = multiengine_nums(label, N)
        multiengine_present |= me
        do_not_fill |= me

    # unique-number anchors with strictly-increasing position
    pos_of = {}   # num -> (label, page) first occurrence
    for label, pg, n in conf:
        pos_of.setdefault(n, (label, pg))
    # count number occurrences; a number held by >1 confident act is NOT a clean anchor
    num_count = defaultdict(int)
    for _, _, n in conf:
        num_count[n] += 1

    # per-volume boundary detection
    vol_boundaries = {}
    for label, p, name in members:
        lines = load_lines(label)
        m = re.match(r"(\d{4})", label)
        vol_year = int(m.group(1)) if m else None
        vol_boundaries[label] = detect_boundaries(lines, volume_year=vol_year)

    recovered = []
    recovered_labels = []   # parallel to `recovered`: routing label per record (out-of-band)
    needs = []
    used_pages = set()   # (label, page) already claimed by a recovered act this pass
    # seed seen_numbers with the FULL do-not-fill set (confident + flagged + multi-engine),
    # NOT just confident_acts -- so a flagged or already-multi-engine-recovered number is
    # never treated as an open slot (fix #2).
    seen_numbers = set(do_not_fill)

    # build the ordered list of CLEAN anchors (unique number, in-range), page-ordered
    clean_anchors = [(label, pg, n) for (label, pg, n) in conf if num_count[n] == 1]
    # enforce strictly increasing number along the page order; drop inversions
    mono = []
    for label, pg, n in clean_anchors:
        if mono and n <= mono[-1][2]:
            continue
        mono.append((label, pg, n))
    clean_anchors = mono

    # iterate adjacent anchor pairs; only consider pairs in the SAME volume
    n_pairs_examined = 0
    n_multi_cand = n_zero_cand = n_filled = 0
    boundary_no_slot_pages = set()

    for (l_lo, p_lo, lo), (l_hi, p_hi, hi) in zip(clean_anchors, clean_anchors[1:]):
        if l_lo != l_hi:
            continue
        open_slots = [s for s in range(lo + 1, hi) if s not in seen_numbers]
        if not open_slots:
            continue
        n_pairs_examined += 1
        bnds = vol_boundaries.get(l_lo, [])
        # candidates: real boundaries strictly between the anchor pages, not on an anchor
        # page, not already used, page-ordered.
        cands = []
        for b in bnds:
            if not is_real_boundary(b):
                continue
            pg = b["page"]
            # STRICTLY between the anchor pages (fix #3): p_lo < pg < p_hi. The anchors
            # themselves own their pages; a candidate sharing an anchor's page is excluded
            # both here and by the conf_pages guard below.
            if not (p_lo < pg < p_hi):
                continue
            if pg in conf_pages[l_lo]:
                continue          # an anchor already lives on this page
            if (l_lo, pg) in used_pages:
                continue
            cands.append(b)
        cands.sort(key=lambda b: (b["page"], b["i"]))
        # collapse multiple boundary lines on the SAME page into one (page granularity):
        # interior loss is one missing act per gap; if two distinct pages -> two candidates.
        cand_pages = []
        seen_pg = set()
        for b in cands:
            if b["page"] in seen_pg:
                continue
            seen_pg.add(b["page"])
            cand_pages.append(b)

        if len(cand_pages) == len(open_slots) and len(open_slots) >= 1:
            # unambiguous: pair i-th candidate (page order) to i-th open slot
            for b, slot in zip(cand_pages, open_slots):
                rec = {
                    "chapter": str(slot), "chapter_int": slot, "chapter_int_final": slot,
                    "chapter_raw": "(seq)",
                    "title": b["title"],
                    "approved_date": b["approved_date"], "iso_date": b["iso_date"],
                    "text": b["text"], "source_page": b["page"],
                    "has_an_act": b["has_an_act"], "has_approval": b["has_approval"],
                    "has_enact": b["has_enact"],
                    "printed_numeral": b["printed_numeral"],
                    "lo_anchor": lo, "hi_anchor": hi,
                    "gap_open_slots": len(open_slots),
                    "label": l_lo,            # provenance: which volume this act lives in
                    "origin": "lostheader",
                    "status": "seq_assigned_no_header",
                }
                # fix #5: routing label is carried OUT-OF-BAND (parallel list), never inside
                # the emitted record (no internal `_label` leaks into the JSON).
                recovered.append(rec)
                recovered_labels.append(l_lo)
                used_pages.add((l_lo, b["page"]))
                seen_numbers.add(slot)
                n_filled += 1
        else:
            # ambiguous: record the candidate boundaries (if any) as needs_reocr context,
            # and the open slots that could not be safely filled.
            if len(cand_pages) > len(open_slots):
                n_multi_cand += 1
            else:
                n_zero_cand += 1
            for b in cand_pages:
                if (l_lo, b["page"]) in boundary_no_slot_pages:
                    continue
                boundary_no_slot_pages.add((l_lo, b["page"]))
                needs.append({
                    "session": target, "label": l_lo, "source_page": b["page"],
                    "title": b["title"][:200],
                    "printed_numeral": b["printed_numeral"],
                    "lo_anchor": lo, "hi_anchor": hi,
                    "open_slots": open_slots,
                    "n_candidates": len(cand_pages),
                    "status": "boundary_no_slot",
                    "reason": ("multi_candidate_one_or_more_slots"
                               if len(cand_pages) > len(open_slots)
                               else "more_slots_than_candidates"),
                })

    # PRECISION CHECK (fix #2): no recovered number may duplicate ANYTHING in the full
    # do-not-fill set (confident + flagged + multi-engine) OR another recovered number.
    dup = []
    rec_nums = defaultdict(int)
    for r in recovered:
        rec_nums[r["chapter_int"]] += 1
    for n, c in rec_nums.items():
        if c > 1 or n in do_not_fill:
            dup.append(n)

    result["recovered"] = recovered
    result["recovered_labels"] = recovered_labels
    result["needs_reocr"] = needs
    result["meta"] = {
        "N": N, "confident_before": len(present_nums),
        "multiengine_recovered_before": len(multiengine_present),
        "do_not_fill_count": len(do_not_fill),
        "anchor_pairs_examined": n_pairs_examined,
        "recovered": n_filled,
        "gaps_multi_candidate": n_multi_cand,
        "gaps_no_candidate": n_zero_cand,
        "needs_reocr_boundaries": len(needs),
        "duplicate_numbers_introduced": dup,
        "accounted_after": len(do_not_fill) + n_filled,
    }
    return result


def write_session(target, oracle):
    """Recover one session and write per-volume parsed_acts_lostheader.json (or .new if a
    prior file exists -- fix #1, never silently clobbers)."""
    res = recover_session(target, oracle)
    by_label = defaultdict(lambda: {"recovered_acts": [], "needs_reocr": []})
    # route via the out-of-band parallel label list (fix #5: no internal `_label` in records)
    for r, lbl in zip(res["recovered"], res.get("recovered_labels", [])):
        by_label[lbl]["recovered_acts"].append(r)
    for nd in res["needs_reocr"]:
        by_label[nd["label"]]["needs_reocr"].append(nd)
    written = []
    # write for every member (even empty) so the artifact is complete
    for lbl in res["members"]:
        d = by_label.get(lbl, {"recovered_acts": [], "needs_reocr": []})
        for b in ("recovered_acts", "needs_reocr"):
            d[b].sort(key=lambda a: a.get("source_page", 0))
        base = ROOT / ("production-" + lbl) / "parsed_acts_lostheader.json"
        # CRITICAL (fix #1): NEVER overwrite a prior parsed_acts_lostheader.json. If one
        # exists, write the .new sibling instead (mirrors recover_multiengine_headers.py).
        outp = base
        clobber_guard = ""
        if base.exists():
            outp = ROOT / ("production-" + lbl) / "parsed_acts_lostheader.json.new"
            clobber_guard = " (existing file present -> wrote .new)"
        outp.write_text(json.dumps({
            "recovered_acts": d["recovered_acts"],
            "needs_reocr": d["needs_reocr"],
            "_lostheader_meta": {
                "session": target, "label": lbl,
                "session_meta": res["meta"],
                "detector": ("recover_lost_header.py (garbled-numeral/position repair, "
                             "runs AFTER multi-engine; fills residual gaps only)"),
            },
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append((lbl, outp.name + clobber_guard))
    return res, written


def all_sessions(oracle):
    sks = set()
    for d in sorted(ROOT.glob("production-*")):
        if not d.is_dir():
            continue
        label = d.name[len("production-"):]
        sk = cc.session_key(label)
        if sk and cc.oracle_N(label, oracle):
            sks.add(sk)
    return sorted(sks)


def main():
    args = sys.argv[1:]
    score = "--score" in args
    if score:
        args.remove("--score")
    oracle = cc.load_oracle()
    if "--all" in args:
        targets = all_sessions(oracle)
    else:
        targets = args
    if not targets:
        raise SystemExit('usage: recover_lost_header.py "<session>" | --all [--score]')
    grand = {"recovered": 0, "needs_reocr": 0, "dups": 0, "sessions": 0,
             "multiengine_before": 0}
    rows = []
    for t in targets:
        res, written = write_session(t, oracle)
        m = res["meta"]
        grand["recovered"] += m.get("recovered", 0)
        grand["needs_reocr"] += m.get("needs_reocr_boundaries", 0)
        grand["dups"] += len(m.get("duplicate_numbers_introduced", []))
        grand["multiengine_before"] += m.get("multiengine_recovered_before", 0)
        grand["sessions"] += 1
        rows.append((t, m))
        print(f"{t:<32} N={m.get('N')} conf_before={m.get('confident_before')} "
              f"me_before={m.get('multiengine_recovered_before')} "
              f"do_not_fill={m.get('do_not_fill_count')} "
              f"recovered={m.get('recovered')} needs_reocr={m.get('needs_reocr_boundaries')} "
              f"multi_cand_gaps={m.get('gaps_multi_candidate')} "
              f"dups={len(m.get('duplicate_numbers_introduced', []))}")
    out = ROOT / "_lostheader_summary.json"
    if out.exists():
        out = ROOT / "_lostheader_summary.json.new"   # no-clobber (fix #1 spirit)
    out.write_text(json.dumps({"grand": grand,
                               "rows": [{"session": t, **m} for t, m in rows]},
                              indent=2), encoding="utf-8")
    print("\nGRAND:", json.dumps(grand))
    print("wrote", out)


if __name__ == "__main__":
    main()
