"""recover_acts.py -- ADDITIVE completion + chapter-renumber pass for the noisy
mid-century OCR era. Recovers acts the production parser (ingest_from_ocr.py) misses
because the printed "CHAPTER NN" header was dropped or OCR-garbled, even though the
act body ("An act to ..." + enactment/approval marker) is fully present in the text.

DIAGNOSIS (see analysis/diagnose_misses.py + inspect_pagetop.py):
  CA session laws print each act as  "CHAPTER NN" / "An act to ..." / body / "[Approved
  ...19xx]". The production parser only STARTS an act when HEADER_RE matches the CHAPTER
  line AND "An Act" follows within 4 lines. The dominant miss (1957: ~313 of ~744) is a
  real act whose CHAPTER header landed in a page header / on the prior page / as garbled
  glyphs -- so header_starts_act never fires. The act text itself is fully present; this
  is recoverable-from-text, not re-OCR work. A smaller mode is OCR-misread chapter
  NUMBERS (e.g. "13879", "24138") that inflate the sequence.

WHAT THIS DOES (precision-first):
  1. Re-runs the EXACT production walk to get baseline act-starts (where header_starts_act
     fires), each with a token (the printed chapter numeral) and a line index.
  2. Independently finds MISSED act-starts with a tolerant, body-reference-safe detector:
       * line matches AN_ACT_RE ("An act ...")
       * "An act" is at the START of the line (not mid-sentence)
       * the line is at the TOP of its OCR page OR a fuzzy CHAPTER header is within 8
         lines above (the real act-start layout signal)
       * an enactment OR approval marker appears within ENACT_LOOKAHEAD lines after
       * it is NOT a body title-reference (rejected on "of an act"/"entitled"/quote cues)
       * not already within +/-2 lines of a baseline start (no dup)
  3. Builds act buffers for the merged set in reading order across ALL physical volumes
     of the session (so a session split into vol1/vol2 is one continuous sequence), and
     extracts the same fields production flush_act produces.
  4. RENUMBERS BY SEQUENCE over the whole session: acts are page-ordered and chapters run
     1..N. It selects a longest STRICTLY-INCREASING chain of confident, plausibly-numbered
     acts as ANCHORS (robust to a single misread number), then between two adjacent anchors
     A(=a) and B(=b) it deterministically numbers the intervening acts a+1..b-1 IFF the
     count of intervening acts equals (b-a-1) -- i.e. sequence and page order AGREE. The
     leading run before the first anchor is filled only when its count matches the first
     anchor's number. The trailing run is filled only when an explicit true_total is given
     and the arithmetic closes; otherwise trailing acts are left ambiguous (no guessing).

  Output: ONE parsed_acts_recovered.json PER physical volume (NEW FILE -- never overwrites
  parsed_acts_fixed.json), with the session-renumbered acts split back to their origin
  volume. Same schema as parsed_acts_fixed.json plus per-act keys:
     origin            : "baseline" | "recovered"
     renumber_status   : "anchor" | "filled" | "kept_parsed" | "ambiguous"
     chapter_int_final : chosen chapter number (0 if undetermined)

Read-only w.r.t. the DB and w.r.t. all existing files.

Usage (pass ALL physical volumes of a session together so renumbering is session-wide):
  python -m ingest.recover_acts 1957-vol1-57chapters 1957-vol2-57chapters
  python -m ingest.recover_acts --true 2424 1957-vol1-57chapters 1957-vol2-57chapters
  python -m ingest.recover_acts 1893
"""
import sys, re, json
from pathlib import Path
import importlib.util
import config

# ---- load the production parser module so we reuse its EXACT regexes / predicates ----
_ING = Path(__file__).resolve().parent / "ingest_from_ocr.py"
_spec = importlib.util.spec_from_file_location("ingest_from_ocr", str(_ING))
ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ing)

ROOT = Path(config.path_for("data_root"))

ENACT_LOOKAHEAD = 14      # lines after "An act" to look for an enact/approval marker
PAGE_TOP_MAX = 2          # line index <= this counts as page-top
CA_HARD_CEILING = 2500    # 1957 reached ch. 2424 (its true max); 2500 keeps real
                          # high chapters while still rejecting OCR-garble (3000+)
ANCHOR_SLACK = 60         # max numeric gap allowed between adjacent anchors (vs positions)

FUZZY_CHAP = re.compile(
    r"^[^A-Za-z0-9]{0,6}"
    r"(?:c[hilou][\w]{0,2}p\w{0,4}|cilap\w{0,4}|ohap\w{0,4}|ghap\w{0,4})"
    r"\.?\s*[ivxlcdm0-9]", re.I)
APPROVAL_PROBE = re.compile(
    r"Approved\s+by\s+(?:the\s+)?Governor"
    r"|Filed\s+with\s+Secretary\s+of\s+State"
    r"|In\s+effe[ce]t\b"
    r"|\[Approved", re.I)
BODYREF_CUE = re.compile(
    r"of\s+an\s+act\b"
    r"|an\s+act\s+of\s+congress"
    r"|entitled\b"
    r"|\bsaid\s+act\b"
    r"|provisions?\s+of\s+(?:the\s+|an\s+)?act"
    r"|under\s+an\s+act"
    r"|performance.*of\s+an\s+act"
    r"|doing\s+of\s+an\s+act", re.I)
# Opening-quote characters: an "An act" preceded by one of these is the quoted
# TITLE of an act being amended/cited, not a new act start (MAJOR-1).
_OPEN_QUOTES = "\"'“‘„‚«‹`’”›»"   # incl. right-curly/guillemet variants some OCR emits for an opener
# Witness header: a readable, ARABIC "CHAPTER <n>" / "CHAP. <n>" numeral that the
# printer set as the act's OWN leading header line. Anchored to the START of the line
# (^) on purpose -- a CHAPTER token mid-line is a BODY reference ("...to amend Chapter
# 2 of the Code...") and is NOT a witness of the act's own number. Arabic-only:
# roman/garbled numerals are not a trustworthy disagreement witness.
WITNESS_CHAP_RE = re.compile(r"^\s*CHAP(?:TER|T\.?|\.)?\s*([0-9]{1,4})\s*[.,;:]?\s*$", re.I)


def own_header_witness(lines, start_i, buf, n_above=4):
    """Return the int CHAPTER number from this act's OWN leading printed header, or
    None if no clean header line is readable. The witness must be a line that IS a
    chapter header (anchored '^CHAPTER NN$'), NOT a mid-sentence body reference.
      * baseline acts begin at the 'CHAPTER NN' line  -> buf[0] is the header.
      * recovered acts begin at the 'An act' line     -> header sits just ABOVE.
    We take the CLOSEST such header line at-or-above the start (the act's own), so a
    prior act's header bleeding in from far above is not mistaken for this one."""
    # the act's own first line (baseline case: 'CHAPTER NN')
    if buf:
        m = WITNESS_CHAP_RE.match(buf[0])
        if m:
            return int(m.group(1))
    # otherwise scan UP from the start; first header line found is the closest one
    lo = max(0, start_i - n_above)
    for j in range(start_i - 1, lo - 1, -1):
        seg = lines[j][1]
        m = WITNESS_CHAP_RE.match(seg)
        if m:
            return int(m.group(1))
    return None


def load_pages_lines(label):
    ocr_path = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(ocr_path.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    lines = []   # (page_index, text, line_pos_within_page)
    for pidx in sorted(pages.keys()):
        txt = pages[pidx].get("consensus_text", "").split("\n")
        for k, line in enumerate(txt):
            lines.append((pidx, line, k))
    return pages, lines


def baseline_starts(lines):
    """Indices into `lines` where the PRODUCTION header_starts_act fires, with token."""
    starts = []
    plain = [(p, t) for (p, t, k) in lines]
    for i in range(len(plain)):
        is_hdr, token = ing.header_starts_act(plain, i)
        if is_hdr:
            starts.append((i, token))
    return starts


def is_real_act_start(lines, i):
    """Precision filter: True only if the 'An act' at line i is a genuine act header,
    not a body citation. (1) 'An act' must begin the line; (2) no body-ref cue on it."""
    cur = lines[i][1]
    m = ing.AN_ACT_RE.search(cur)
    if not m:
        return False
    # MAJOR-1: if the char immediately before "An act" (ignoring spaces, BEFORE any
    # stripping) is an opening quotation mark, this is a quoted title of an act being
    # amended/cited, not a new act start. Check the raw preceding non-space char.
    raw_head = cur[:m.start()]
    raw_head_nospace = raw_head.rstrip(" \t")
    if raw_head_nospace and raw_head_nospace[-1] in _OPEN_QUOTES:
        return False
    head = cur[:m.start()].strip(" \t.,:;\"'`-")
    if head:                       # text before "An act" -> a citation, not a start
        return False
    if BODYREF_CUE.search(cur):
        return False
    return True


def fuzzy_header_above(lines, i, n=8):
    for j in range(i - 1, max(-1, i - 1 - n), -1):
        if FUZZY_CHAP.match(lines[j][1].strip()):
            return True
    return False


def has_marker_ahead(lines, i, n=ENACT_LOOKAHEAD):
    for j in range(i, min(len(lines), i + n)):
        seg = lines[j][1]
        if ing.ENACT_MARKER_RE.search(seg) or APPROVAL_PROBE.search(seg):
            return True
    return False


def recovered_starts(lines, baseline_idx_set):
    """Indices of MISSED act-starts the tolerant detector finds (precision-first)."""
    out = []
    for i, (pidx, line, kpos) in enumerate(lines):
        if not ing.AN_ACT_RE.search(line):
            continue
        if i in baseline_idx_set:
            continue
        if any((i + d) in baseline_idx_set for d in (-2, -1, 0, 1, 2)):
            continue
        if not (kpos <= PAGE_TOP_MAX or fuzzy_header_above(lines, i)):
            continue
        if not is_real_act_start(lines, i):
            continue
        if not has_marker_ahead(lines, i):
            continue
        out.append(i)
    return out


def build_act(lines, start_i, end_i, token, volume_year, label):
    buf = [lines[j][1] for j in range(start_i, end_i)]
    start_page = lines[start_i][0]
    full = "\n".join(buf).strip()
    chap_int = ing.parse_chapter_number(token) if token else 0
    if chap_int > CA_HARD_CEILING:     # OCR-inflated numeral -> treat as unknown
        chap_int = 0
    title = ""
    for line in buf:
        if ing.AN_ACT_RE.search(line):
            title = re.sub(r"\s+", " ", line).strip()[:500]
            break
    if not title and buf:
        title = re.sub(r"\s+", " ", buf[0]).strip()[:300]
    iso_date, approved_str = ing.parse_act_date(full, volume_year=volume_year)
    body_text = re.sub(r"[ \t]+", " ", full)
    # CRITICAL-1 witness: the act's OWN printed CHAPTER numeral (scanned at/above the
    # source start). Used after renumber to DEMOTE acts whose assigned number disagrees
    # with a readable printed header. Internal (_-prefixed) -> stripped before write.
    own_witness = own_header_witness(lines, start_i, buf)
    return {
        "chapter": str(chap_int), "chapter_int": chap_int,
        "chapter_raw": token or "", "title": title,
        "approved_date": approved_str, "iso_date": iso_date,
        "text": body_text[:6000], "source_page": start_page + 1,
        "confident": False,                      # decided after renumber
        "has_enact": bool(ing.has_enact_marker(full)),
        "has_an_act": bool(ing.AN_ACT_RE.search(full)),
        "_volume": label,
        "_own_header_witness": own_witness,
    }


def _longest_increasing_chain(acts, cand):
    """Return indices (subset of cand, in order) forming the longest strictly-increasing
    chapter-number chain, so a few OCR-misread numbers can't derail the anchors.
    Classic O(k^2) LIS on chapter_int over candidate positions (k ~ #candidates)."""
    if not cand:
        return []
    vals = [acts[i]["chapter_int"] for i in cand]
    m = len(cand)
    dp = [1] * m
    prev = [-1] * m
    for x in range(m):
        for y in range(x):
            if vals[y] < vals[x] and dp[y] + 1 > dp[x]:
                dp[x] = dp[y] + 1
                prev[x] = y
    best = max(range(m), key=lambda z: dp[z])
    chain = []
    while best != -1:
        chain.append(cand[best])
        best = prev[best]
    chain.reverse()
    return chain


def renumber_by_sequence(acts, true_total=None):
    n = len(acts)
    for a in acts:
        a["chapter_int_final"] = a.get("chapter_int", 0)
        a["renumber_status"] = "kept_parsed"

    # anchor candidates: An Act + a date + plausible parsed number
    cand = [idx for idx, a in enumerate(acts)
            if a.get("has_an_act") and a.get("iso_date") is not None
            and 1 <= a.get("chapter_int", 0) <= CA_HARD_CEILING]
    chain = _longest_increasing_chain(acts, cand)
    # drop adjacent anchors whose numeric gap is implausibly larger than position gap
    pruned = []
    for idx in chain:
        if not pruned:
            pruned.append(idx); continue
        last = pruned[-1]
        if (acts[idx]["chapter_int"] - acts[last]["chapter_int"]) <= (idx - last) + ANCHOR_SLACK:
            pruned.append(idx)
    chain = pruned
    for idx in chain:
        acts[idx]["renumber_status"] = "anchor"
        acts[idx]["chapter_int_final"] = acts[idx]["chapter_int"]

    filled = ambiguous = 0

    def set_filled(j, num):
        nonlocal filled
        acts[j]["chapter_int_final"] = num
        acts[j]["chapter"] = str(num)
        acts[j]["renumber_status"] = "filled"
        filled += 1

    def set_amb(j):
        nonlocal ambiguous
        if acts[j]["renumber_status"] != "anchor":
            acts[j]["renumber_status"] = "ambiguous"
            ambiguous += 1

    # between consecutive anchors -- deterministic fill only when counts agree
    for ai, bi in zip(chain, chain[1:]):
        a, b = acts[ai]["chapter_int"], acts[bi]["chapter_int"]
        between = list(range(ai + 1, bi))
        if not between:
            continue
        if (b - a - 1) == len(between):
            num = a + 1
            for j in between:
                set_filled(j, num); num += 1
        else:
            for j in between:
                set_amb(j)

    if chain:
        # leading run before the first anchor
        first = chain[0]; a = acts[first]["chapter_int"]
        lead = list(range(0, first))
        if a - 1 == len(lead):
            num = 1
            for j in lead:
                set_filled(j, num); num += 1
        else:
            for j in lead:
                set_amb(j)
        # trailing run after the last anchor -- only fill if a true_total closes it
        last = chain[-1]; b = acts[last]["chapter_int"]
        tail = list(range(last + 1, n))
        if true_total is not None and (true_total - b) == len(tail):
            num = b + 1
            for j in tail:
                set_filled(j, num); num += 1
        else:
            for j in tail:
                set_amb(j)
    else:
        for j in range(n):
            set_amb(j)

    return {"anchors": len(chain), "filled": filled, "ambiguous": ambiguous}


def process_session(labels, true_total=None):
    """Process ALL physical volumes of one session as a single page-ordered stream,
    renumber session-wide, then write one parsed_acts_recovered.json per volume."""
    # CRITICAL-2 cross-session guard: renumber-by-sequence is only valid WITHIN a
    # single legislative session, because CA numbers chapters 1..N PER SESSION and
    # EVERY session -- each Regular AND each Extraordinary session -- restarts at 1.
    # Key each label by LEGISLATURE_MAP[label][0], the SPECIFIC-SESSION name (e.g.
    # "1957 Regular Session", "1950 3rd Extraordinary Session") -- NOT the year prefix
    # ("1957-vol1-56chapters" is the 1956 session). Do NOT use [1] (the biennium, e.g.
    # "1949-50"): a biennium holds SEVERAL independent chapter sequences (1949 Regular,
    # 1950 Regular, 1950 3rd Extra ...), and keying on it would MERGE them and corrupt
    # the renumber. Co-session volumes (1957 vol1+vol2) share [0] and are allowed.
    # Reject loudly on >1 distinct session or any unmapped label.
    # (Audit note 2026-06-14: a 2nd-pass auditor claimed [1] was the correct key. It is
    #  NOT -- verified against LEGISLATURE_MAP + the chapter-count oracle; [0] is right.)
    if not labels:
        raise SystemExit("recover_acts: no volume labels given")
    sess_of = {}
    for label in labels:
        if label not in ing.LEGISLATURE_MAP:
            raise SystemExit(
                f"recover_acts: label {label!r} is not in LEGISLATURE_MAP -- "
                f"cannot verify its session; refusing to run.")
        sess_of[label] = ing.LEGISLATURE_MAP[label][0]
    distinct_sessions = sorted(set(sess_of.values()))
    if len(distinct_sessions) > 1:
        detail = ", ".join(f"{lbl} -> {sess_of[lbl]}" for lbl in labels)
        raise SystemExit(
            "recover_acts: refusing to renumber across MORE THAN ONE legislative "
            f"session. Labels map to {len(distinct_sessions)} sessions "
            f"{distinct_sessions}: {detail}. Run each session separately.")
    acts = []
    per_vol_meta = {}
    for label in labels:
        pages, lines = load_pages_lines(label)
        volume_year = int(re.match(r"(\d{4})", label).group(1))
        bstarts = baseline_starts(lines)
        bidx = {i for i, _ in bstarts}
        rstarts = recovered_starts(lines, bidx)
        per_vol_meta[label] = {"baseline_starts": len(bstarts),
                               "recovered_starts": len(rstarts)}
        merged = [(i, tok, "baseline") for (i, tok) in bstarts]
        merged += [(i, None, "recovered") for i in rstarts]
        merged.sort(key=lambda x: x[0])
        for k, (si, tok, origin) in enumerate(merged):
            ei = merged[k + 1][0] if k + 1 < len(merged) else len(lines)
            rec = build_act(lines, si, ei, tok, volume_year, label)
            if len(rec["text"]) < 60 or not rec["has_enact"]:
                continue
            hdr0 = re.sub(r"\s+", " ", lines[si][1]).strip()
            if re.search(r"\b(?:Approved|Passed)\b", hdr0, re.I) and origin == "baseline":
                continue
            rec["origin"] = origin
            acts.append(rec)
    # acts are already in (volume order, line order); that IS session reading order
    rstats = renumber_by_sequence(acts, true_total=true_total)

    # RESCUE PASS (conservative): an act left 'ambiguous' but carrying its OWN plausible
    # printed chapter number is self-evidencing -- we trust the numeral the printer set,
    # NOT a positional guess. Promote it to 'self_numbered' ONLY when that number does not
    # collide with any already-determined (anchor/filled) number AND is monotonically
    # consistent with its page-order neighbors (strictly between the nearest determined
    # number before and after it). This rescues real baseline acts that fell in an
    # inter-anchor gap with a still-missing neighbor, without inventing anything.
    determined = {}  # position -> number, for anchor/filled (grows as we rescue)
    for idx, a in enumerate(acts):
        if a["renumber_status"] in ("anchor", "filled"):
            determined[idx] = a["chapter_int_final"]
    det_nums = set(determined.values())
    det_positions = sorted(determined.keys())
    import bisect
    rescued = 0
    # MAJOR-2: sweep ambiguous candidates in PAGE (position) order, and after EVERY
    # promotion fold the new (position, number) into determined / det_positions /
    # det_nums. This keeps the neighbor lookup correct for later candidates in the
    # SAME gap -- so two ambiguous acts in one gap cannot end up out-of-order or
    # duplicated: the second is bounded below by the first's just-assigned number.
    amb_positions = [idx for idx, a in enumerate(acts)
                     if a["renumber_status"] == "ambiguous"]
    for idx in amb_positions:
        a = acts[idx]
        own = a.get("chapter_int", 0)
        if not (1 <= own <= CA_HARD_CEILING):
            continue
        if own in det_nums:
            continue
        # nearest determined number strictly before / after this position
        p = bisect.bisect_left(det_positions, idx)
        lo_num = determined[det_positions[p - 1]] if p > 0 else 0
        hi_num = determined[det_positions[p]] if p < len(det_positions) else CA_HARD_CEILING + 1
        if lo_num < own < hi_num:
            a["renumber_status"] = "self_numbered"
            a["chapter_int_final"] = own
            a["chapter"] = str(own)
            det_nums.add(own)
            determined[idx] = own
            bisect.insort(det_positions, idx)
            rescued += 1
    rstats["self_numbered"] = rescued

    # CRITICAL-1 post-fill disagreement demotion: after fill/renumber assigns a
    # number, if the act's OWN readable printed CHAPTER header (scanned at/above its
    # source start in build_act) DISAGREES with the assigned number, DEMOTE the act
    # to flagged (do not emit as confident). This guards against fill-from-a-false-
    # split assigning a wrong number to an act that actually shows its true number.
    # 'anchor'/'self_numbered' acts already ARE their own printed number, so a witness
    # match is guaranteed for them; the real guard target is 'filled' (positional)
    # acts -- but we apply it to any determined status for safety.
    witness_demoted = 0
    for a in acts:
        if a["renumber_status"] not in ("anchor", "filled", "self_numbered"):
            continue
        wit = a.get("_own_header_witness")
        if wit is None or not (1 <= wit <= CA_HARD_CEILING):
            continue
        assigned = a.get("chapter_int_final", 0)
        if wit != assigned:
            a["renumber_status"] = "demoted_witness_disagree"
            a["_witness_disagree"] = {"assigned": assigned, "header_says": wit}
            witness_demoted += 1
    rstats["witness_demoted"] = witness_demoted

    # finalize confidence + split back per volume.
    # An act is CONFIDENT on its chapter number when it has an "An Act" body AND a
    # deterministically-determined number (an anchor, or a fill where sequence+page
    # order agree). A parseable approval DATE is NOT required for confidence: the
    # production ingest already defaults a missing date to <year>-01-01, and the
    # renumber proof is independent of the date. Requiring a date here needlessly
    # demoted 379 page-order-proven acts in 1957 whose "[Approved ...]" footer simply
    # failed to OCR-parse. iso_date is preserved on the record either way.
    out_by_vol = {label: {"confident_acts": [], "flagged_acts": []} for label in labels}
    for a in acts:
        cf = (a.get("has_an_act")
              and 1 <= a.get("chapter_int_final", 0) <= CA_HARD_CEILING
              and a.get("renumber_status") in ("anchor", "filled", "self_numbered"))
        a["confident"] = bool(cf)
        a["chapter_int"] = a.get("chapter_int_final", a.get("chapter_int", 0))
        a["chapter"] = str(a["chapter_int"])
        a.pop("_own_header_witness", None)   # internal scan result -- not persisted
        bucket = "confident_acts" if cf else "flagged_acts"
        out_by_vol[a["_volume"]][bucket].append(a)

    for label in labels:
        d = out_by_vol[label]
        meta = dict(per_vol_meta[label])
        meta.update({"label": label, "session": labels,
                     "confident": len(d["confident_acts"]),
                     "flagged": len(d["flagged_acts"]),
                     "renumber_session": rstats})
        out_path = ROOT / ("production-" + label) / "parsed_acts_recovered.json"
        out_path.write_text(json.dumps({
            "confident_acts": d["confident_acts"],
            "flagged_acts": d["flagged_acts"],
            "_recovery_meta": meta,
        }, indent=2), encoding="utf-8")
        print(f"{label}: baseline={meta['baseline_starts']} recovered={meta['recovered_starts']} "
              f"-> confident={meta['confident']} flagged={meta['flagged']} | wrote {out_path.name}")
    print(f"SESSION {labels}: anchors={rstats['anchors']} filled={rstats['filled']} "
          f"ambiguous={rstats['ambiguous']} total_acts={len(acts)}")


def main():
    args = sys.argv[1:]
    true_total = None
    if "--true" in args:
        k = args.index("--true"); true_total = int(args[k + 1]); del args[k:k + 2]
    process_session(args, true_total=true_total)


if __name__ == "__main__":
    main()
