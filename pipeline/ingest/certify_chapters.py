"""certify_chapters.py -- PRECISION-FIRST certification of parsed-but-flagged chapters.

Promote a flagged act -> CONFIDENT only when its chapter number is CERTAIN, by one of:
  R1 own-header clean in-range numeral, unique among real-act candidates, not already taken;
  R2 unambiguous position between two confident anchors filling exactly one open slot
     (renumber_repair rule -- reused directly for the 1880-1999 chaptered era).

Reads (read-only) the BEST per-volume parse:
    parsed_acts_chaptered_v2.json  >  parsed_acts_early_v2.json  >  parsed_acts_recovered.json
Writes NEW file per volume:  production-<label>/parsed_acts_certified.json
NEVER overrides a confident act. NEVER creates a duplicate chapter number. Writes nothing else.

Run:  python certify_chapters.py            (full run + write)
      python certify_chapters.py --dry      (measure only, no write)
"""
import sys, os, re, json, glob, importlib.util
from pathlib import Path
from collections import defaultdict, Counter

# REPO root = two levels up from this file (pipeline/ingest/certify_chapters.py).
REPO = Path(__file__).resolve().parents[2]
ORACLE_TSV = REPO / "docs" / "30_SYSTEM_DESIGN" / "sources" / "ca_chapter_counts.tsv"

def _load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

# ingest_from_ocr + renumber_repair import `config` (pipeline/ on sys.path) and build the
# data root from it (the 3060 cutover knob); ensure the path BEFORE loading either module.
sys.path.insert(0, str(REPO / "pipeline"))
sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
import config  # noqa: E402  -- single source of truth for the data-scratch root
ROOT = Path(config.path_for("data_root"))
OUT_AUDIT = ROOT / "_certify_audit"
# reuse production session map + the renumber_repair logic verbatim
ing = _load_mod("ingest_from_ocr", REPO / "pipeline" / "ingest" / "ingest_from_ocr.py")
rr = _load_mod("renumber_repair", REPO / "pipeline" / "ingest" / "renumber_repair.py")

LEG = ing.LEGISLATURE_MAP

# ---------- oracle ----------
def load_oracle():
    oracle = {}
    with open(ORACLE_TSV, encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 4 or not p[3].strip().isdigit():
                continue
            oracle[p[0].strip()] = int(p[3])
    return oracle

# ---------- header numeral reading (precision: roman or arabic, own act only) ----------
_HDR_RE = re.compile(r'^\s*[.,;:�\\\s]*CHAP(?:TER|T\.?|\.)?\s*([0-9IVXLCDM]{1,7})\b', re.I | re.M)
_ROMAN = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}

def roman_to_int(s):
    s = s.upper()
    if not s or not all(c in _ROMAN for c in s):
        return None
    t = p = 0
    for c in reversed(s):
        v = _ROMAN[c]
        t += -v if v < p else v
        p = max(p, v)
    return t if t > 0 else None

def header_numeral(text):
    """Clean chapter numeral printed in the act's OWN first header line, or None.
    Only looks at the first ~160 chars (the header region) so a SECOND chapter spilled
    into the body cannot be misread as this act's number."""
    if not text:
        return None
    m = _HDR_RE.search(text[:160])
    if not m:
        return None
    tok = m.group(1)
    if tok.isdigit():
        v = int(tok)
        return v if 0 < v < 10000 else None
    return roman_to_int(tok)

def raw_numeral(a):
    """Clean bare-digit chapter_raw, else None."""
    raw = str(a.get("chapter_raw", a.get("chapter", ""))).strip()
    if re.fullmatch(r'[1-9][0-9]{0,3}', raw):
        return int(raw)
    return None

# ---------- volume / best-parse selection ----------
def best_parse_path(d):
    for name in ("parsed_acts_chaptered_v2.json",
                 "parsed_acts_early_v2.json",
                 "parsed_acts_recovered.json"):
        p = d / name
        if p.exists():
            return p, name
    return None, None

def session_key(label):
    if label in LEG:
        return LEG[label][0]
    return None

_TYPE_WORDS = ("regular", "extra", "extraordinary", "adjourned", "prior")

def _norm_session_label(label):
    """Normalize a volume label to candidate oracle keys. The early era (pre-1880) uses
    LEGISLATURE_MAP keys that DON'T match the oracle's '<year> Regular Session' form, so
    we derive the oracle key from the label directly. Strip non-session suffixes
    (-code/-regular/-vol*/-NNchapters/-statutes) and append the session-type phrase."""
    base = label.lower()
    # drop volume / printing-variant suffixes that are not part of the session identity
    base = re.sub(r"-(?:code|statutes|reg-session|regular)$", "", base)
    base = re.sub(r"-vol\d.*$", "", base)
    base = re.sub(r"-\d+chapters$", "", base)
    base = re.sub(r"-chapters$", "", base)
    # session type
    if "firstextra" in base or "1stextra" in base or "extra1" in base:
        typ = "First Extra Session"
    elif "secondextra" in base or "extra2" in base:
        typ = "Second Extra Session"
    elif "prior" in base:
        typ = "Regular Session"   # 'prior' handled separately if oracle has it
    elif "extra" in base:
        typ = "First Extra Session"
    else:
        typ = "Regular Session"
    # year token = leading 4-digit, plus optional -NN biennial second half
    m = re.match(r"(\d{4})(?:-(\d{2}))?", base)
    if not m:
        return []
    y = m.group(1); half = m.group(2)
    cands = []
    if half:
        cands.append(f"{y}-{half} {typ}")
    cands.append(f"{y} {typ}")
    return cands


def oracle_N(label, oracle):
    # 1) production session map (correct for the chaptered era 1880+)
    sk = session_key(label)
    if sk and sk in oracle:
        return oracle[sk]
    # 2) fallback: derive the oracle key from the label (needed for pre-1880 early era)
    for cand in _norm_session_label(label):
        if cand in oracle:
            return oracle[cand]
    return None

def year_of(label):
    m = re.match(r"(\d{4})", label)
    return int(m.group(1)) if m else 0


def assigned(a):
    v = a.get("chapter_int_final", a.get("chapter_int", 0))
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def is_real_act(a):
    """A real act body (not a TOC/index fragment). Enactment clause is the strong signal."""
    # BODY-SUBSTANCE GUARD: a TOC/index line can spuriously carry has_enact (or the
    # an-act+approved pair), so require a non-trivial body. 200 chars is far below any
    # real act body yet well above a single TOC/index fragment line -> precision-safe.
    if len((a.get("text") or "").strip()) < 200:
        return False
    return bool(a.get("has_enact")) or (bool(a.get("has_an_act")) and bool(a.get("has_approved")))


# count CHAPTER headers in an act body. >1 means two acts were merged into one buffer
# (the printed second header spilled in), so the act's number is NOT cleanly determined
# from position/witness -- the buffer is ambiguous. Match both "CHAPTER" and the common
# OCR forms "Cuap./Cuar./Car./Chap." plus a following numeral-ish token.
_BODY_CHAP_RE = re.compile(
    r'(?:CHAP(?:TER|T\.?|\.)?|C[UH]A[PR]\.?|CAR\.)\s*'
    r'[.,;:�\\\s]*([0-9IVXLCDM]{1,8}|X[TVIL]{1,7})\b', re.I)

def chapter_header_count(text):
    if not text:
        return 0
    return len(_BODY_CHAP_RE.findall(text))


# =========================================================================
# CERTIFY RULE 1 (own clean header, unique, not taken) -- applied within a
# single volume's act set (early era) or a session's set (chaptered era).
# =========================================================================
def certify_rule1(acts, N, taken_confident):
    """Mutate: certify flagged acts whose OWN clean numeral is in-range, agrees across
    available witnesses, is UNIQUE among real-act candidates claiming it, and is not
    already held by a confident act. Returns list of (act, number) certified."""
    # candidate number for each flagged real act = a number ALL available clean witnesses
    # agree on. Witnesses: chapter_int (Surya), raw_numeral (bare-digit raw), header_numeral.
    cand = {}      # id(act) -> number
    for a in acts:
        if a.get("confident"):
            continue
        if not is_real_act(a):
            continue
        # SPILLOVER GUARD: if two (or more) chapter headers are present in the body, the
        # buffer merged two acts -> this act's number is NOT cleanly determined. Skip.
        if chapter_header_count(a.get("text", "")) > 1:
            continue
        witnesses = []
        ci = a.get("chapter_int")
        if isinstance(ci, int) and ci > 0:
            witnesses.append(ci)
        rn = raw_numeral(a)
        if rn:
            witnesses.append(rn)
        hn = header_numeral(a.get("text", ""))
        if hn:
            witnesses.append(hn)
        if not witnesses:
            continue
        # all witnesses must agree (no OCR disagreement) -> certain numeral
        if len(set(witnesses)) != 1:
            continue
        n = witnesses[0]
        if N is not None and not (1 <= n <= N):
            continue
        if N is None:
            # No oracle range bound for this volume -> require CORROBORATION (>=2 agreeing
            # witnesses) and a sane absolute cap. Single-Surya certification is only
            # allowed when an oracle N bounds the range.
            if len(witnesses) < 2 or not (1 <= n <= 2500):
                continue
        cand[id(a)] = n
    # uniqueness: a number claimed by >1 real-act candidate is NOT certain for either
    num_claims = Counter(cand.values())
    certified = []
    for a in acts:
        n = cand.get(id(a))
        if n is None:
            continue
        if n in taken_confident:
            continue                     # already held by a confident act
        if num_claims[n] != 1:
            continue                     # ambiguous: two bodies claim same number
        # certify
        a["chapter_int"] = n
        a["chapter_int_final"] = n
        a["chapter"] = str(n)
        a["confident"] = True
        a["_certify"] = {"rule": "R1_own_clean_header", "to": n,
                         "witnesses": "agree"}
        a["renumber_status"] = "certified_self"
        taken_confident.add(n)
        certified.append((a, n))
    return certified


def position_fill(stream, N, certify_log):
    """CERTIFY RULE 2 -- conservative position-between-confident-anchors fill, reimplemented
    from renumber_repair's core (robust to PRE-EXISTING source duplicates, which we never
    demote). stream is the session's page-ordered act list.

    Anchors = CONFIDENT acts whose chapter number is in [1,N] and UNIQUE among confident
    acts (a number held by >1 confident act is NOT a trustworthy anchor -> excluded from
    the frame, but those acts are left untouched). Anchor numbers + positions must be
    strictly increasing; inversions are dropped from the frame.

    A repair candidate = a FLAGGED real act (has_an_act) that is not an anchor. In each gap
    between consecutive anchors we assign open slots ONLY when #candidates == #open_slots
    and >=1, pairing the i-th page-ordered candidate to the i-th open slot. WITNESS GUARD:
    if any candidate prints a clean in-range own numeral != its slot, abort the WHOLE gap.
    SPILLOVER GUARD: a candidate whose body holds >1 chapter header is never filled.
    Returns count certified.

    RESIDUAL RISK (MAJOR-5B -- stale-N / R2 tail-fill):
    -------------------------------------------------------------------------------
    R2 fills open slots between confident anchors. The frame's TAIL bound is the oracle
    N: the synthetic high anchor is (len(stream), N+1), so the gap between the LAST real
    anchor and N+1 is framed entirely by the oracle. If the oracle N is STALE or WRONG
    for a session, that tail gap could fill candidates into slots that do not correspond
    to real chapters (slots N_real+1 .. N_stale would be fabricated). The same staleness
    also affects the in-range test (1<=v<=N) elsewhere. This risk is BOUNDED by, in order:
      (a) the WITNESS GUARD below -- any candidate that prints a clean in-range own
          numeral contradicting its assigned slot (or witnesses that disagree among
          themselves) aborts the WHOLE gap, so a fabricated tail run is killed the moment
          one real numeral is read;
      (b) the EXACT #candidates == #open_slots (and >=1) requirement -- a partial/loose
          match never fills, so a tail with the wrong count is skipped entirely;
      (c) the oracle itself having been AUDITED 2026-06-16 (ca_chapter_counts.tsv), so a
          stale N is unlikely for the covered sessions.
    No further code change for 5B -- the tail frame behavior is as described above.
    -------------------------------------------------------------------------------"""
    if N is None:
        return 0
    # 1) anchors from confident acts, unique in-range numbers
    conf_num_positions = defaultdict(list)
    for i, a in enumerate(stream):
        if a.get("confident"):
            n = assigned(a)
            if 1 <= n <= N:
                conf_num_positions[n].append(i)
    anchor_pos = {}
    for n, positions in conf_num_positions.items():
        if len(positions) == 1:
            anchor_pos[positions[0]] = n
    anchors_sorted = sorted(anchor_pos.items())
    # enforce strict monotonic numbers
    mono = []
    for pos, num in anchors_sorted:
        if mono and num <= mono[-1][1]:
            continue
        mono.append((pos, num))
    anchors_sorted = mono
    taken = {num for _, num in anchors_sorted}      # monotonic-unique anchors -> position FRAME only
    anchor_positions = {pos for pos, _ in anchors_sorted}
    # FIX (b): the position frame uses only monotonic-unique anchors, but an OPEN slot must
    # never reuse a chapter number held by ANY confident act in the session -- including a
    # confident act that is NOT a clean monotonic anchor (e.g. a number R1 just certified
    # on a real body, while a separate TOC line carrying the same number is still flagged).
    # Without this, that held number looks "open" in the gap and R2 would fill the duplicate.
    all_taken = set()
    for a in stream:
        if a.get("confident"):
            n = assigned(a)
            if 1 <= n <= N:
                all_taken.add(n)

    def is_cand(i):
        if i in anchor_positions:
            return False
        a = stream[i]
        if a.get("confident"):
            return False                       # never touch a confident act
        # FIX (a): a fill candidate must be a REAL act body (enacting/approval evidence +
        # the 200-char body guard), NOT merely an `has_an_act` line. A TOC / index title
        # line ("Chapter 105 .- An Act for...") carries has_an_act=True but is_real_act=False,
        # so it must never be eligible to fill an open slot.
        if not is_real_act(a):
            return False
        if chapter_header_count(a.get("text", "")) > 1:
            return False                       # spillover -> ambiguous
        return True

    frame = [(-1, 0)] + anchors_sorted + [(len(stream), N + 1)]
    certified = 0
    for (lo_pos, lo_num), (hi_pos, hi_num) in zip(frame, frame[1:]):
        cand = [i for i in range(lo_pos + 1, hi_pos) if is_cand(i)]
        if not cand:
            continue
        # open slots = numbers in the gap NOT used by the frame anchors AND not held by
        # ANY confident act in the session (FIX (b): all_taken, not just the anchor `taken`).
        open_slots = [n for n in range(lo_num + 1, hi_num)
                      if n not in taken and n not in all_taken]
        if len(cand) != len(open_slots) or len(open_slots) < 1:
            continue
        # witness guard: ALL clean in-range own numerals must agree with each other AND
        # with the slot. Collect every clean in-range witness (not just the first) so a
        # second witness contradicting the slot -- or two witnesses disagreeing among
        # themselves -- aborts the gap (mirrors R1's all-witnesses-agree logic).
        conflict = False
        for i, slot in zip(cand, open_slots):
            a = stream[i]
            rn = raw_numeral(a)
            hn = header_numeral(a.get("text", ""))
            ci = a.get("chapter_int") if isinstance(a.get("chapter_int"), int) else None
            wits = [cw for cw in (rn, hn, ci) if cw and 1 <= cw <= N]
            if wits and (len(set(wits)) > 1 or any(w != slot for w in wits)):
                conflict = True
                break
        if conflict:
            continue
        # close the gap: assign each candidate its slot
        for i, slot in zip(cand, open_slots):
            a = stream[i]
            a["chapter_int"] = slot
            a["chapter_int_final"] = slot
            a["chapter"] = str(slot)
            a["confident"] = True
            a["renumber_status"] = "certified_position"
            a["_certify"] = {"rule": "R2_position_fill", "to": slot,
                             "lo_anchor": lo_num, "hi_anchor": hi_num,
                             "gap_open_slots": len(open_slots)}
            taken.add(slot)
            all_taken.add(slot)
            certify_log.append((a, slot, "R2"))
            certified += 1
    return certified


def confident_taken(acts, N):
    s = set()
    for a in acts:
        if a.get("confident"):
            n = assigned(a)
            if (N is None and 1 <= n) or (N is not None and 1 <= n <= N):
                s.add(n)
    return s


def distinct_confident_in_range(acts, N):
    s = set()
    for a in acts:
        if not a.get("confident"):
            continue
        n = assigned(a)
        if N is not None and 1 <= n <= N:
            s.add(n)
        elif N is None and 1 <= n:
            s.add(n)
    return s


def verify_no_dups(acts, N):
    seen = {}
    probs = []
    for a in acts:
        if not a.get("confident"):
            continue
        n = assigned(a)
        if N is not None and not (1 <= n <= N):
            probs.append(("oor_confident", n, a.get("source_page")))
            continue
        if n in seen:
            probs.append(("dup_confident", n, a.get("source_page")))
        seen[n] = True
    return probs


def era_of(year):
    if year < 1880:
        return "early_1850_1879"
    if year < 1900:
        return "late19c_1880_1899"
    if year < 1950:
        return "early20c_1900_1949"
    if year < 1989:
        return "mid20c_1950_1988"
    return "modern_1989_1999"


# =========================================================================
# MAIN
# =========================================================================
def discover_volumes():
    """Return list of (label, best_path, best_name) for every production-* volume that
    has at least one parse file and maps to a known session (so the oracle key resolves)."""
    vols = []
    for d in sorted(ROOT.glob("production-*")):
        label = d.name[len("production-"):]
        p, name = best_parse_path(d)
        if p is None:
            continue
        vols.append((label, p, name))
    return vols


def load_acts(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    conf = data.get("confident_acts", []) or []
    flag = data.get("flagged_acts", []) or []
    out = []
    for a in conf:
        a = dict(a); a.setdefault("confident", True); out.append(a)
    for a in flag:
        a = dict(a); a.setdefault("confident", False); out.append(a)
    # normalize fields needed by rr / certify
    for a in out:
        a.setdefault("chapter_int_final", a.get("chapter_int", 0))
        a.setdefault("renumber_status", "anchor" if a.get("confident") else "ambiguous")
    return out, data


def main():
    dry = "--dry" in sys.argv
    oracle = load_oracle()
    vols = discover_volumes()

    # group volumes by session (None session => its own singleton group keyed by label)
    by_session = defaultdict(list)   # session_or_label -> [(label, path, name, acts, raw)]
    vol_meta = {}
    for label, path, name in vols:
        acts, raw = load_acts(path)
        sk = session_key(label) or ("__noleg__" + label)
        by_session[sk].append((label, path, name, acts))
        vol_meta[label] = {"path": str(path), "name": name, "session": sk,
                           "year": year_of(label)}

    # BEFORE metrics (per volume + per session)
    before_conf = {}   # label -> (#confident, #total)
    for label, path, name in vols:
        acts, _ = load_acts(path)
        c = sum(1 for a in acts if a.get("confident"))
        before_conf[label] = (c, len(acts))

    # CERTIFY per session
    cert_counts = defaultdict(int)   # label -> #newly certified
    rule_counts = Counter()
    precision_problems = []
    sacred_violations = []
    session_after = {}   # sk -> (distinct_before, distinct_after, N)

    audit_examples = []

    for sk, members in by_session.items():
        # build page-ordered stream across the session's volumes (volume order, then page)
        label_order = {lbl: i for i, (lbl, _, _, _) in enumerate(members)}
        stream = []
        for lbl, _, _, acts in members:
            for a in acts:
                a["_label"] = lbl
                # snapshot the ORIGINAL confident state + number. Originally-confident
                # acts are SACRED: certification must never demote them or change their
                # number (prompt: "NEVER override a confident act").
                a["_orig_confident"] = bool(a.get("confident"))
                a["_orig_num"] = assigned(a)
                a["_orig_status"] = a.get("renumber_status")
                stream.append(a)
        stream.sort(key=lambda a: (label_order.get(a["_label"], 9999),
                                   a.get("source_page", 0)))

        # N: take the oracle for any member label (all share session)
        N = None
        for lbl, _, _, _ in members:
            N = oracle_N(lbl, oracle)
            if N is not None:
                break

        before_distinct = len(distinct_confident_in_range(stream, N))

        # iterate R1 (own clean header) and R2 (position fill) to fixpoint
        prev_conf = -1
        for _ in range(6):
            taken = confident_taken(stream, N)
            newly = certify_rule1(stream, N, taken)
            for a, n in newly:
                cert_counts[a["_label"]] += 1
                rule_counts["R1_own_clean_header"] += 1
                if len(audit_examples) < 100000:
                    audit_examples.append({
                        "label": a["_label"], "rule": "R1", "to": n,
                        "page": a.get("source_page"),
                        "head": (a.get("text", "") or "")[:90].replace("\n", " ")})
            # R2 position fill -- only meaningful with oracle N. Our own conservative
            # implementation (never demotes a confident act; robust to source dups).
            if N is not None:
                r2log = []
                position_fill(stream, N, r2log)
                for a, slot, _ in r2log:
                    cert_counts[a["_label"]] += 1
                    rule_counts["R2_position_fill"] += 1
                    if len(audit_examples) < 100000:
                        audit_examples.append({
                            "label": a["_label"], "rule": "R2", "to": slot,
                            "page": a.get("source_page"),
                            "head": (a.get("text", "") or "")[:90].replace("\n", " ")})
            cur_conf = sum(1 for a in stream if a.get("confident"))
            if cur_conf == prev_conf:
                break
            prev_conf = cur_conf

        after_distinct = len(distinct_confident_in_range(stream, N))
        session_after[sk] = (before_distinct, after_distinct, N)

        # PRECISION INVARIANTS:
        #  (a) no originally-confident act was demoted or had its number changed
        #  (b) no NEW duplicate or out-of-range confident number was introduced by certify
        for a in stream:
            if a.get("_orig_confident"):
                if not a.get("confident"):
                    sacred_violations.append((sk, "demoted", a.get("source_page"), a["_orig_num"]))
                elif assigned(a) != a["_orig_num"]:
                    sacred_violations.append((sk, "renumbered", a.get("source_page"),
                                              a["_orig_num"], assigned(a)))
        # duplicates/oor among confident: classify each as pre-existing vs introduced.
        seen = {}
        for a in stream:
            if not a.get("confident"):
                continue
            n = assigned(a)
            introduced = bool(a.get("_certify"))     # this act became confident in this run
            if N is not None and not (1 <= n <= N):
                bucket = "introduced_oor" if introduced else "preexisting_oor"
                precision_problems.append((sk, bucket, n, a.get("source_page")))
                continue
            if n in seen:
                # a dup: introduced if EITHER of the colliding acts was certified here
                intro = introduced or seen[n][1]
                bucket = "introduced_dup" if intro else "preexisting_dup"
                precision_problems.append((sk, bucket, n, a.get("source_page")))
            else:
                seen[n] = (a.get("source_page"), introduced)

    # PRECISION WRITE-GATE (CRITICAL-3B): compute the PASS condition from the fully
    # populated evidence lists BEFORE writing anything. If precision fails, we must NOT
    # write certified outputs -- a wrong chapter number must never reach disk.
    pp_counts = Counter(p[1] for p in precision_problems)
    precision_pass = (pp_counts.get("introduced_dup", 0) == 0
                      and pp_counts.get("introduced_oor", 0) == 0
                      and len(sacred_violations) == 0)

    if not precision_pass:
        # Emit the audit report so the failure is inspectable, then abort WITHOUT writing
        # any certified per-volume outputs.
        print("PRECISION GATE FAILED -- no certified outputs written.", file=sys.stderr)
        print("  introduced_dup = %d" % pp_counts.get("introduced_dup", 0), file=sys.stderr)
        print("  introduced_oor = %d" % pp_counts.get("introduced_oor", 0), file=sys.stderr)
        print("  sacred_violations = %d" % len(sacred_violations), file=sys.stderr)
        for sv in sacred_violations[:10]:
            print("    sacred_violation: %r" % (sv,), file=sys.stderr)
        report = {"precision": {
            "PASS": False,
            "introduced_duplicate_confident": pp_counts.get("introduced_dup", 0),
            "introduced_out_of_range_confident": pp_counts.get("introduced_oor", 0),
            "sacred_violations_confident_demoted_or_renumbered": len(sacred_violations),
            "sacred_violation_examples": sacred_violations[:10],
            "introduced_examples": [p for p in precision_problems
                                    if p[1].startswith("introduced")][:10],
        }, "totals": {"volumes_written": 0}, "GATE": "FAILED"}
        OUT_AUDIT.mkdir(exist_ok=True)
        (OUT_AUDIT / ("report_dry.json" if dry else "report.json")).write_text(
            json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        sys.exit(2)

    # WRITE certified outputs per volume (split stream back by _label)
    written = []
    if not dry:
        OUT_AUDIT.mkdir(exist_ok=True)
        by_label = defaultdict(lambda: {"confident_acts": [], "flagged_acts": []})
        for sk, members in by_session.items():
            for lbl, _, _, acts in members:
                for a in acts:
                    out = {k: v for k, v in a.items()
                           if k not in ("_label", "_orig_confident", "_orig_num",
                                        "_orig_status", "_repair")}
                    bucket = "confident_acts" if a.get("confident") else "flagged_acts"
                    by_label[lbl][bucket].append(out)
        for lbl, d in by_label.items():
            for b in ("confident_acts", "flagged_acts"):
                d[b].sort(key=lambda a: a.get("source_page", 0))
            meta = {
                "label": lbl,
                "session": vol_meta[lbl]["session"],
                "source_parse": vol_meta[lbl]["name"],
                "oracle_N": oracle_N(lbl, oracle),
                "confident": len(d["confident_acts"]),
                "flagged": len(d["flagged_acts"]),
                "newly_certified": cert_counts.get(lbl, 0),
                "source": "certify_chapters.py (R1 own-header + R2 position-fill)",
            }
            outp = ROOT / ("production-" + lbl) / "parsed_acts_certified.json"
            outp.write_text(json.dumps({
                "confident_acts": d["confident_acts"],
                "flagged_acts": d["flagged_acts"],
                "_certify_meta": meta,
            }, indent=2), encoding="utf-8")
            written.append(lbl)

    # ---------- REPORT ----------
    report = {"by_era": {}, "totals": {}, "precision": {}, "sessions_changed": []}

    # per-era before/after distinct-confident vs oracle N (only volumes w/ oracle)
    era_N = defaultdict(int); era_b = defaultdict(int); era_a = defaultdict(int)
    tot_cert = sum(cert_counts.values())
    for sk, (b, a, N) in session_after.items():
        if N is None:
            continue
        # era by the min year among member volumes
        yrs = [vol_meta[lbl]["year"] for (lbl, _, _, _) in by_session[sk]]
        era = era_of(min(yrs)) if yrs else "unknown"
        era_N[era] += N; era_b[era] += b; era_a[era] += a
        if a != b:
            report["sessions_changed"].append({"session": sk, "N": N,
                                               "before": b, "after": a, "gain": a - b})
    for era in sorted(era_N):
        report["by_era"][era] = {
            "oracle_N": era_N[era], "before_distinct": era_b[era],
            "after_distinct": era_a[era],
            "before_pct": round(100.0 * era_b[era] / max(1, era_N[era]), 2),
            "after_pct": round(100.0 * era_a[era] / max(1, era_N[era]), 2),
            "gain": era_a[era] - era_b[era],
        }
    TN = sum(era_N.values()); TB = sum(era_b.values()); TA = sum(era_a.values())
    report["totals"] = {
        "oracle_N": TN, "before_distinct": TB, "after_distinct": TA,
        "before_pct": round(100.0 * TB / max(1, TN), 2),
        "after_pct": round(100.0 * TA / max(1, TN), 2),
        "distinct_gain": TA - TB,
        "acts_newly_certified": tot_cert,
        "by_rule": dict(rule_counts),
        "volumes_written": len(written),
    }
    pp_counts = Counter(p[1] for p in precision_problems)
    report["precision"] = {
        # the ONLY values that may be non-zero for a PASS are the 'preexisting_*' ones
        # (data issues already present in the source parse, which certification leaves
        # untouched). All 'introduced_*' and sacred violations MUST be zero.
        "introduced_duplicate_confident": pp_counts.get("introduced_dup", 0),
        "introduced_out_of_range_confident": pp_counts.get("introduced_oor", 0),
        "sacred_violations_confident_demoted_or_renumbered": len(sacred_violations),
        "preexisting_duplicate_confident": pp_counts.get("preexisting_dup", 0),
        "preexisting_out_of_range_confident": pp_counts.get("preexisting_oor", 0),
        "PASS": (pp_counts.get("introduced_dup", 0) == 0
                 and pp_counts.get("introduced_oor", 0) == 0
                 and len(sacred_violations) == 0),
        "sacred_violation_examples": sacred_violations[:10],
        "introduced_examples": [p for p in precision_problems
                                if p[1].startswith("introduced")][:10],
        "preexisting_examples": [p for p in precision_problems
                                 if p[1].startswith("preexisting")][:8],
    }

    # always emit the audit artifacts (report + examples) so spot-checks work on a dry run
    OUT_AUDIT.mkdir(exist_ok=True)
    (OUT_AUDIT / ("report_dry.json" if dry else "report.json")).write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    (OUT_AUDIT / "audit_examples.json").write_text(
        json.dumps(audit_examples, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
