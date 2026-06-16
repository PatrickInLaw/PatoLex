"""renumber_repair.py -- CONSERVATIVE chapter-number REPAIR for the chaptered era
(1880-1999). Extends recover_acts.py's idea: where recover_acts already RENUMBERED a
session by page-order anchors+fill, a residual set of acts still carry a chapter number
that is provably wrong -- it is OUT-OF-RANGE for the session (outside [1, N], N from the
authoritative oracle) or it is an in-range DUPLICATE of another act's number. The act
body is present; only the numeral is garbled. These are recoverable from page-order
position between the nearest CONFIDENT, in-range, unique anchors -- WITHOUT trusting the
garbled numeral.

PRECISION-FIRST. A confidently-wrong chapter number is worse than a flagged one. We
assign a repaired number ONLY when the position + gap-arithmetic agree UNAMBIGUOUSLY:
there is exactly ONE open chapter slot in the gap between the bracketing anchors for the
candidate to occupy, AND assigning it keeps strict page-order monotonicity. Anything
short of that stays flagged (status 'left_flagged'). We NEVER renumber an act that
already has a valid confident number, and we NEVER create a duplicate.

INPUT  (read-only): per-volume production-<label>/parsed_acts_recovered.json
                    (confident_acts/flagged_acts; each act has chapter_int_final,
                     renumber_status, source_page, _volume, ...)
ORACLE (read-only): docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv
                    keyed by session_label == LEGISLATURE_MAP[label][0]
OUTPUT (NEW file) : production-<label>/parsed_acts_repaired.json
                    same schema as parsed_acts_recovered.json (the transient grouping keys
                    _label / _listname_in are stripped before write); repaired acts get
                    renumber_status 'repaired_position' and a _repair audit sub-record.

NOTE (maintenance, audit MINOR-4): _HDR_RE here mirrors WITNESS_CHAP_RE in recover_acts.py.
If either header pattern is tightened, update BOTH; they are intentionally kept in sync.

Grouping: acts are grouped into a single page-ordered stream PER LEGISLATIVE SESSION,
keyed by LEGISLATURE_MAP[label][0] (the specific-session name -- the SAME key
recover_acts.py uses; NOT the biennium and NOT the leading-4-digit label, which mis-files
biennial spanning labels). Co-session volumes (e.g. 1957 vol1+vol2) are stitched in
volume order then source_page order.

Run-only-analysis (Step 1, no output):   python -m ingest.renumber_repair --analyze-only
Full repair + write parsed_acts_repaired:  python -m ingest.renumber_repair
"""
import sys, re, json
from pathlib import Path
import importlib.util
from collections import defaultdict
import config

ROOT = Path(config.path_for("data_root"))
REPO = Path(__file__).resolve().parents[2]
ORACLE_TSV = REPO / "docs" / "30_SYSTEM_DESIGN" / "sources" / "ca_chapter_counts.tsv"

# reuse the production parser's LEGISLATURE_MAP for the session key
_ING = Path(__file__).resolve().parent / "ingest_from_ocr.py"
_spec = importlib.util.spec_from_file_location("ingest_from_ocr", str(_ING))
ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ing)

# Chaptered era only. The OCR/renumber regime applies to the scanned chaptered volumes
# (~1880-1999). Earlier "act"-numbered sessions (1850s-1870s) are a different numbering
# regime and are handled by recover_early.py; born-digital (2000+) is not OCR.
CHAPTERED_MIN_YEAR = 1880
CHAPTERED_MAX_YEAR = 1999

# a CLEAN, readable own-header CHAPTER numeral the act itself prints. If present and
# in-range, it is AUTHORITATIVE for that act -- the repair must NEVER assign a positional
# number that contradicts it (that is exactly the confidently-wrong outcome the brief
# forbids; recover_acts already DEMOTED such acts on witness-disagreement).
_HDR_RE = re.compile(r"^\s*CHAP(?:TER|T\.?|\.)?\s*([0-9]{1,4})\s*[.,;:]?\s*$",
                     re.I | re.M)


def clean_own_witness(a):
    """The act's OWN printed chapter numeral if cleanly readable, else None.
    Source 1: chapter_raw when it is a bare 1-4 digit numeral.
    Source 2: a leading 'CHAPTER NN' header line in the first 400 chars of text."""
    raw = str(a.get("chapter_raw", "")).strip()
    if re.fullmatch(r"[1-9][0-9]{0,3}", raw):   # 1-4 digits, no zero / leading-zero
        return int(raw)
    m = _HDR_RE.search((a.get("text") or "")[:400])
    if m:
        return int(m.group(1))
    return None


# determined statuses from recover_acts: these acts have a number we should TRUST as an
# anchor candidate (subject to in-range + uniqueness checks below).
DETERMINED_STATUSES = ("anchor", "filled", "self_numbered")


def load_oracle():
    """session_label -> total_chapters (N). Keyed exactly as LEGISLATURE_MAP[label][0]."""
    oracle = {}
    with open(ORACLE_TSV, encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 4 or not p[3].strip().isdigit():
                continue
            oracle[p[0].strip()] = int(p[3])
    return oracle


def session_year(label):
    m = re.match(r"(\d{4})", label)
    return int(m.group(1)) if m else 0


def discover_labels():
    """All production-<label> dirs that have parsed_acts_recovered.json AND map to a
    known legislative session in the chaptered year window."""
    labels = []
    for d in sorted(ROOT.glob("production-*")):
        if not (d / "parsed_acts_recovered.json").exists():
            continue
        label = d.name[len("production-"):]
        if label not in ing.LEGISLATURE_MAP:
            continue
        yr = session_year(label)
        if not (CHAPTERED_MIN_YEAR <= yr <= CHAPTERED_MAX_YEAR):
            continue
        labels.append(label)
    return labels


def load_recovered(label):
    p = ROOT / ("production-" + label) / "parsed_acts_recovered.json"
    return json.loads(p.read_text(encoding="utf-8"))


def session_key(label):
    return ing.LEGISLATURE_MAP[label][0]


def build_sessions(labels):
    """Return {session_name: [act, ...]} where each act-list is in page reading order
    (volume order, then source_page). Each act keeps an injected '_label' (its origin
    volume) and '_listname' (which list it came from)."""
    by_session = defaultdict(list)
    label_order = {}  # session -> [labels in stitch order]
    for label in labels:
        sess = session_key(label)
        label_order.setdefault(sess, [])
        if label not in label_order[sess]:
            label_order[sess].append(label)
    # preserve the discover order (already sorted) as the volume stitch order
    for label in labels:
        sess = session_key(label)
        data = load_recovered(label)
        for listname in ("confident_acts", "flagged_acts"):
            for a in data.get(listname, []):
                a = dict(a)
                a["_label"] = label
                a["_listname_in"] = listname
                by_session[sess].append(a)
    # sort each session by (volume stitch index, source_page)
    for sess, acts in by_session.items():
        order = {lbl: i for i, lbl in enumerate(label_order[sess])}
        acts.sort(key=lambda a: (order.get(a["_label"], 9999),
                                 a.get("source_page", 0)))
    return by_session


def assigned_num(a):
    """The number recover_acts settled on for this act."""
    v = a.get("chapter_int_final", a.get("chapter_int", 0))
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def classify(by_session, oracle):
    """Per session: identify anchors (trustworthy, in-range, unique determined numbers)
    and repair candidates (out-of-range or duplicate). Returns a stats dict and annotates
    nothing yet."""
    stats = {}
    for sess, acts in by_session.items():
        N = oracle.get(sess)
        # count how many DETERMINED acts hold each number (to find duplicates)
        num_count = defaultdict(int)
        for a in acts:
            if a.get("renumber_status") in DETERMINED_STATUSES:
                num_count[assigned_num(a)] += 1
        out_of_range = dup = 0
        for a in acts:
            det = a.get("renumber_status") in DETERMINED_STATUSES
            n = assigned_num(a)
            if not det:
                continue
            if N is not None and not (1 <= n <= N):
                out_of_range += 1
            elif num_count[n] > 1:
                dup += 1
        # the real "misnumbered-but-present" recovery pool = present acts that LACK a
        # confident number (recover_acts already declined to number them, OR numbered
        # them out-of-range / as a dup). These are flagged acts with an act body plus any
        # determined act whose number is bad. raw_oor/raw_dup measure the bad RAW numeral.
        flagged_present = sum(1 for a in acts
                              if not a.get("confident") and a.get("has_an_act"))
        raw_oor = raw_dup = 0
        raw_count = defaultdict(int)
        for a in acts:
            r = a.get("chapter_int") or 0
            try:
                r = int(r)
            except (TypeError, ValueError):
                r = 0
            if r:
                raw_count[r] += 1
        for a in acts:
            r = a.get("chapter_int") or 0
            try:
                r = int(r)
            except (TypeError, ValueError):
                r = 0
            if not r:
                continue
            if N is not None and not (1 <= r <= N):
                raw_oor += 1
            elif raw_count[r] > 1:
                raw_dup += 1
        stats[sess] = {
            "N": N, "acts": len(acts),
            "determined": sum(1 for a in acts
                              if a.get("renumber_status") in DETERMINED_STATUSES),
            "out_of_range": out_of_range, "dup": dup,
            "flagged_present": flagged_present,
            "raw_oor": raw_oor, "raw_dup": raw_dup,
            "has_oracle": N is not None,
        }
    return stats


def repair_session(acts, N):
    """CONSERVATIVE position-based repair within ONE session's page-ordered act list.

    Anchors = determined acts whose number is in [1,N] and UNIQUE among determined acts.
    These anchor numbers are FIXED and never reassigned. We then walk the gaps between
    consecutive anchors (and the leading/trailing runs). A 'slot' is a chapter number in
    (lo_anchor_num, hi_anchor_num) that is NOT already taken by ANY act's anchor number.
    A repair candidate (an act in that gap that is NOT itself a valid unique anchor) is
    assigned a slot ONLY when:
        * there is exactly ONE repair candidate in the gap AND exactly ONE open slot, OR
        * the number of repair candidates in the gap == number of open slots AND each
          candidate maps to a slot by strict page-order (the i-th candidate by page gets
          the i-th open slot) -- i.e. position and arithmetic close exactly.
    Anything else: every candidate in that gap stays 'left_flagged'. No guessing, no
    duplicate creation (slots are drawn only from open, untaken numbers).

    Returns counts dict; mutates acts in place adding _repair audit + new status.
    """
    if N is None:
        # No oracle bound -> we cannot define out-of-range; do not repair (precision).
        for a in acts:
            a.setdefault("_repair", None)
        return {"anchors": 0, "candidates": 0, "repaired": 0, "left_flagged": 0,
                "no_oracle": True}

    # 1) anchors: determined, in-range, unique number
    det_num = defaultdict(list)  # number -> [positions] among determined acts
    for i, a in enumerate(acts):
        if a.get("renumber_status") in DETERMINED_STATUSES:
            n = assigned_num(a)
            if 1 <= n <= N:
                det_num[n].append(i)
    anchor_pos = {}  # position -> number  (unique in-range determined)
    taken = set()    # all numbers occupied by an anchor (never reassign these)
    for n, positions in det_num.items():
        if len(positions) == 1:
            anchor_pos[positions[0]] = n
            taken.add(n)
        # if a number is held by >1 determined act, NEITHER is a trustworthy anchor
        # (it is the duplicate problem); both become repair candidates below.

    anchors_sorted = sorted(anchor_pos.items())  # (position, number), page-ordered

    # sanity: anchors must be strictly increasing in BOTH position and number (they are,
    # by construction position-sorted; verify number monotonic, drop any inversion to
    # stay safe). A non-monotone anchor would corrupt the gap arithmetic.
    mono = []
    for pos, num in anchors_sorted:
        if mono and num <= mono[-1][1]:
            # inversion -> this "anchor" is unreliable; demote it (do not use as bound).
            # Leave it determined for output but exclude from the anchor frame.
            taken.discard(num)
            continue
        mono.append((pos, num))
    anchors_sorted = mono
    taken = {num for _, num in anchors_sorted}

    # repair candidate = any act that is NOT a current frame-anchor position and whose
    # number is out-of-range OR duplicate (or it's a determined dup we just demoted).
    anchor_positions = {pos for pos, _ in anchors_sorted}
    repaired = left = candidates = 0

    def is_candidate(i):
        if i in anchor_positions:
            return False
        a = acts[i]
        if a.get("renumber_status") not in DETERMINED_STATUSES:
            # already-flagged acts: only treat as repair candidates if they have a body
            # and could plausibly slot in. We DO try to place these (they are present
            # acts missing a confident number) -- but conservatively, same gap rules.
            return bool(a.get("has_an_act"))
        n = assigned_num(a)
        if not (1 <= n <= N):
            return True              # out-of-range determined
        # in-range determined act that is NOT a frame anchor. By construction it can only
        # reach here if its number is NOT a unique-anchor number: a UNIQUE in-range number
        # makes the act its own anchor (caught above at `i in anchor_positions`), and a
        # number held by >1 determined act is never added to anchor_pos. So `n not in
        # taken` always holds here -- the act is (or shares) a demoted duplicate, hence a
        # repair candidate. (Audit MAJOR-1: the old `if n not in taken: return True` +
        # trailing `return True` had an unreachable branch with a misleading comment.)
        assert n not in taken, (
            "unreachable: in-range determined non-anchor act carries an anchor number")
        return True

    # build gap frame: boundaries are anchor positions with anchor numbers; plus virtual
    # bounds (pos=-1,num=0) at the start and (pos=len,num=N+1) at the end.
    frame = [(-1, 0)] + anchors_sorted + [(len(acts), N + 1)]

    for (lo_pos, lo_num), (hi_pos, hi_num) in zip(frame, frame[1:]):
        # candidate positions strictly between the two anchor positions, page-ordered
        cand = [i for i in range(lo_pos + 1, hi_pos) if is_candidate(i)]
        if not cand:
            continue
        candidates += len(cand)
        # open slots = numbers in (lo_num, hi_num) not already taken by an anchor
        open_slots = [n for n in range(lo_num + 1, hi_num) if n not in taken]
        # CONSERVATIVE close condition: exactly as many candidates as open slots, AND
        # (slots are contiguous OR there is exactly one). With #cand == #slots and slots
        # drawn from the open range in increasing order, the i-th page-ordered candidate
        # takes the i-th slot -- strict monotone, no collision. We additionally require
        # the assignment to keep each candidate strictly between its bracketing anchors
        # (guaranteed since slots are within (lo_num,hi_num)).
        # WITNESS GUARD (precision-first): if ANY candidate in this gap prints a CLEAN,
        # in-range own-header chapter numeral that does NOT equal the slot the positional
        # arithmetic would give it, the positional assignment for this gap is NOT
        # trustworthy -- the printer's numeral overrides our guess. recover_acts already
        # demotes on witness-disagreement; we must not re-impose the contradicted number.
        # Because the fill is a strict 1:1 cand<->slot pairing, a single conflict makes
        # the whole pairing suspect, so we abort the fill for the ENTIRE gap and leave
        # every candidate in it flagged. (A clean witness that AGREES with its slot is
        # fine -- that is a confirmation, not an override.)
        witness_conflict = False
        if len(cand) == len(open_slots) and len(open_slots) >= 1:
            for i, slot in zip(cand, open_slots):
                w = clean_own_witness(acts[i])
                if w is not None and 1 <= w <= N and w != slot:
                    witness_conflict = True
                    break
        if len(cand) == len(open_slots) and len(open_slots) >= 1 and not witness_conflict:
            for i, slot in zip(cand, open_slots):
                a = acts[i]
                old = assigned_num(a)
                a["_repair"] = {
                    "from": old, "to": slot,
                    "prev_status": a.get("renumber_status"),
                    "lo_anchor": lo_num, "hi_anchor": hi_num,
                    "gap_open_slots": len(open_slots),
                    "own_witness": clean_own_witness(a),
                }
                a["renumber_status"] = "repaired_position"
                a["chapter_int_final"] = slot
                a["chapter_int"] = slot
                a["chapter"] = str(slot)
                a["confident"] = True
                taken.add(slot)
                repaired += 1
        else:
            # ambiguous gap: leave every candidate flagged (do not guess)
            for i in cand:
                a = acts[i]
                reason = (f"witness conflict in gap ({lo_num},{hi_num})"
                          if witness_conflict else
                          f"ambiguous gap: {len(cand)} candidates vs "
                          f"{len(open_slots)} open slots in ({lo_num},{hi_num})")
                a["_repair"] = {
                    "from": assigned_num(a), "to": None,
                    "reason": reason,
                    "prev_status": a.get("renumber_status"),
                    "own_witness": clean_own_witness(a),
                }
                if a.get("renumber_status") in DETERMINED_STATUSES:
                    a["renumber_status"] = "left_flagged"
                    a["confident"] = False
                left += 1

    # ensure every act has _repair key for clean output
    for a in acts:
        a.setdefault("_repair", None)
    return {"anchors": len(anchors_sorted), "candidates": candidates,
            "repaired": repaired, "left_flagged": left, "no_oracle": False}


def verify_no_dups(acts, N):
    """Adversarial post-check: no two CONFIDENT acts may share an in-range number."""
    seen = {}
    dups = []
    for a in acts:
        if not a.get("confident"):
            continue
        n = assigned_num(a)
        if N is not None and not (1 <= n <= N):
            dups.append(("out_of_range_confident", n, a.get("_label")))
            continue
        if n in seen:
            dups.append(("duplicate_confident", n, a.get("_label")))
        seen[n] = True
    return dups


def distinct_in_range(acts, N, only_confident=True):
    """Set of distinct chapter numbers in [1,N] held by (confident) acts."""
    s = set()
    for a in acts:
        if only_confident and not a.get("confident"):
            continue
        n = assigned_num(a)
        if N is not None and 1 <= n <= N:
            s.add(n)
    return s


def write_outputs(by_session):
    """Split each session's (now-repaired) acts back to per-volume parsed_acts_repaired."""
    by_label = defaultdict(lambda: {"confident_acts": [], "flagged_acts": []})
    for sess, acts in by_session.items():
        for a in acts:
            lbl = a["_label"]
            cf = bool(a.get("confident"))
            # strip transient grouping keys (_label and _listname_in are injected by
            # build_sessions for grouping ONLY -- not part of the parsed_acts schema;
            # audit MAJOR-2). KEEP _repair audit + renumber_status + the pre-existing
            # _volume key that recover_acts already writes.
            out = {k: v for k, v in a.items() if k not in ("_listname_in", "_label")}
            bucket = "confident_acts" if cf else "flagged_acts"
            by_label[lbl][bucket].append(out)
    written = []
    for lbl, d in by_label.items():
        # restore origin order within each list by source_page for stable output
        for b in ("confident_acts", "flagged_acts"):
            d[b].sort(key=lambda a: a.get("source_page", 0))
        meta = {
            "label": lbl, "session": session_key(lbl),
            "confident": len(d["confident_acts"]),
            "flagged": len(d["flagged_acts"]),
            "repaired_here": sum(1 for a in d["confident_acts"]
                                 if a.get("renumber_status") == "repaired_position"),
            "source": "renumber_repair.py over parsed_acts_recovered.json",
        }
        out_path = ROOT / ("production-" + lbl) / "parsed_acts_repaired.json"
        out_path.write_text(json.dumps({
            "confident_acts": d["confident_acts"],
            "flagged_acts": d["flagged_acts"],
            "_repair_meta": meta,
        }, indent=2), encoding="utf-8")
        written.append((lbl, meta["confident"], meta["flagged"], meta["repaired_here"]))
    return written


def main():
    analyze_only = "--analyze-only" in sys.argv
    oracle = load_oracle()
    labels = discover_labels()
    by_session = build_sessions(labels)
    stats = classify(by_session, oracle)

    # Step 1 report: per-session repair-candidate counts.
    # raw_oor/raw_dup = acts whose RAW chapter_int numeral is out-of-range / duplicate
    #   (the "misnumbered-but-present" the brief describes).
    # flagged = present acts lacking a confident number (the recovery POOL).
    print("=== STEP 1: misnumbered/flagged per session ===")
    print(f"{'session':<34}{'N':>6}{'acts':>6}{'flag':>6}{'rawOOR':>7}{'rawDUP':>7}")
    tot_oor = tot_dup = tot_flag = 0
    no_oracle_sessions = []
    for sess in sorted(stats):
        s = stats[sess]
        if not s["has_oracle"]:
            no_oracle_sessions.append(sess)
        nstr = str(s["N"]) if s["N"] is not None else "?"
        print(f"{sess:<34}{nstr:>6}{s['acts']:>6}{s['flagged_present']:>6}"
              f"{s['raw_oor']:>7}{s['raw_dup']:>7}")
        tot_oor += s["raw_oor"]; tot_dup += s["raw_dup"]
        tot_flag += s["flagged_present"]
    print(f"\nTOTAL raw out-of-range numerals: {tot_oor}")
    print(f"TOTAL raw in-range duplicate numerals: {tot_dup}")
    print(f"TOTAL raw misnumbered (oor+dup): {tot_oor + tot_dup}")
    print(f"TOTAL flagged-but-present acts (recovery pool): {tot_flag}")
    if no_oracle_sessions:
        print(f"\nsessions with NO oracle N ({len(no_oracle_sessions)}): "
              + ", ".join(no_oracle_sessions))

    if analyze_only:
        return

    # Step 2: conservative repair. Capture BEFORE distinct-in-range (confident) per
    # session, run repair, then capture AFTER for the before/after completeness report.
    print("\n=== STEP 2: conservative position repair ===")
    rtot = {"anchors": 0, "candidates": 0, "repaired": 0, "left_flagged": 0}
    dup_problems = []
    before_present = {}
    after_present = {}
    for sess in sorted(by_session):
        N = oracle.get(sess)
        before_present[sess] = len(distinct_in_range(by_session[sess], N))
        r = repair_session(by_session[sess], N)
        for k in rtot:
            rtot[k] += r.get(k, 0)
        after_present[sess] = len(distinct_in_range(by_session[sess], N))
        d = verify_no_dups(by_session[sess], N)
        if d:
            dup_problems.append((sess, d))
    print(f"anchors={rtot['anchors']} candidates={rtot['candidates']} "
          f"repaired={rtot['repaired']} left_flagged={rtot['left_flagged']}")
    if dup_problems:
        print(f"\n*** PRECISION FAILURE: {len(dup_problems)} sessions have confident "
              f"dups/out-of-range AFTER repair ***")
        for sess, d in dup_problems[:20]:
            print(f"  {sess}: {d[:10]}")
    else:
        print("PRECISION OK: 0 confident duplicates / out-of-range after repair.")

    # before/after completeness vs oracle (biennium-correct: keyed by true session name)
    print("\n=== before/after completeness (distinct-in-[1,N] confident) ===")
    tb = ta = tN = 0
    for sess in sorted(by_session):
        N = oracle.get(sess)
        if N is None:
            continue
        b = before_present[sess]; a = after_present[sess]
        tb += b; ta += a; tN += N
        if a != b:
            print(f"  {sess:<34} N={N:>5} before={b:>5} after={a:>5} (+{a-b})")
    print(f"\nCORPUS chaptered (sessions with oracle N): authoritative {tN:,}, "
          f"before {tb:,} ({100.0*tb/max(1,tN):.2f}%), "
          f"after {ta:,} ({100.0*ta/max(1,tN):.2f}%), recovered +{ta-tb}")

    # Step 3: write NEW outputs
    print("\n=== STEP 3: write parsed_acts_repaired.json ===")
    written = write_outputs(by_session)
    print(f"wrote {len(written)} parsed_acts_repaired.json files")
    print(f"total repaired-here across files: {sum(w[3] for w in written)}")


if __name__ == "__main__":
    main()
