"""merge_passes.py -- ADDITIVE, PRECISION-FILTERED best-of merge of the existing parse passes.
TRUSTED passes (certified > chaptered_v2 > repaired > recovered) define the chapter->page
order. LOW passes (multiengine, lostheader, fixed) add only chapters they uniquely have AND
that pass a sanity gate: the chapter's source_page must be page-monotonic vs the trusted
anchors (chapters are page-ordered), OR it must carry a real "An act ..." title. This drops
the engine-union's page-misassigned garbage (e.g. 1915 ch22 @ p1807) while keeping real
recovered acts. One act per chapter, no dups, capped at the session's oracle N. NEW file
parsed_acts_merged.json; never touches inputs.

Usage: python merge_passes.py <glob>   e.g. "production-1915*"  or  "production-19*"
"""
import os, json, glob, sys, re, csv, bisect
from collections import defaultdict

SCRATCH = r"C:\PatoLex-scratch"
ORACLE_TSV = r"C:\GitHub\PatoLex\docs\30_SYSTEM_DESIGN\sources\ca_chapter_counts.tsv"
TRUSTED = ["parsed_acts_certified.json", "parsed_acts_chaptered_v2.json", "parsed_acts_repaired.json",
           "parsed_acts_recovered.json"]
LOW = ["parsed_acts_multiengine.json", "parsed_acts_lostheader.json", "parsed_acts_fixed.json"]
FALLBACK_CAP, PAGE_TOL = 2500, 12

ORACLE = {}
with open(ORACLE_TSV, encoding="utf-8") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        try:
            y = int(row["session_year"]); ORACLE[y] = max(ORACLE.get(y, 0), int(row["total_chapters"]))
        except Exception:
            pass

def n_for(name):
    m = re.search(r"production-(\d{4})", name)
    return (ORACLE[int(m.group(1))], int(m.group(1))) if m and int(m.group(1)) in ORACLE else (FALLBACK_CAP, None)

def acts_of(d):
    out = []
    for v in (d.values() if isinstance(d, dict) else [d]):
        if isinstance(v, list):
            out += [a for a in v if isinstance(a, dict)]
    return out

def cn(a, N):
    n = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
    return n if isinstance(n, int) and 1 <= n <= N else None

def page(a):
    p = a.get("source_page")
    return p if isinstance(p, int) else None

def real_anact(a):
    t = (a.get("an_act_title_snippet") or a.get("title") or a.get("text") or "")
    return bool(re.match(r"\s*An\s+act\b", t, re.I))

def load(D, f):
    p = os.path.join(D, f)
    if not os.path.exists(p):
        return []
    try:
        return acts_of(json.load(open(p, encoding="utf-8")))
    except Exception:
        return []

def page_ok(c, sp, anchors):
    if sp is None:
        return False  # low-pass act with no page AND no real title -> can't trust
    below = [p for ch, p in anchors if ch < c]
    above = [p for ch, p in anchors if ch > c]
    lo, hi = (max(below) if below else None), (min(above) if above else None)
    if lo is not None and sp < lo - PAGE_TOL:
        return False
    if hi is not None and sp > hi + PAGE_TOL:
        return False
    return True

# ---- OCR page-header ground truth (fuzzy: tolerates "UHAPTER", "CIIAPTER", garbled digits) ----
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_HDR_LINE = re.compile(r"^[^A-Za-z0-9]{0,4}([A-Za-z][A-Za-z]{4,8})[^A-Za-z0-9]{0,3}([0-9OoIlij]{1,4})\b")
_DIGIT_FIX = str.maketrans("OoIlij", "001111")

def _editle2(a, b):
    """True iff Levenshtein(a, b) <= 2 (bounded; a,b short uppercase tokens)."""
    if abs(len(a) - len(b)) > 2:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            best = min(best, cur[j])
        if best > 2:
            return False
        prev = cur
    return prev[-1] <= 2

_XREF = re.compile(r"\s*\.?\s+of\b", re.I)  # "CHAPTER N of [the Statutes/title/code]" = cross-ref

def fuzzy_headers(txt, N):
    """Returns (anchored, raw): `anchored` = arabic chapter numbers in [1,N] whose 'CHAPTER N.'
    header physically appears on the page (the volume's own ground truth for which chapter occupies
    the page); `raw` = the uncapped cleaned digit-strings of those headers (so an extra-digit garble
    like '2338'=>chapter 238 can be matched back later). Fuzzy on the word CHAPTER (<=2 edits) so OCR
    garbles ('UHAPTER','CIIAPTER') still anchor. Rejects: body cross-references ('chapter 877 OF the
    statutes of 1921'); roman/letter-only tokens ('CHAPTER II.' -> code-chapter heading, not a
    statute chapter -- 1900-1999 statute chapters are arabic). Caps anchors at oracle N (a 4-digit
    'header' is OCR noise)."""
    anchored, raw = set(), []
    for ln in txt.splitlines():
        m = _HDR_LINE.match(ln)
        if not m:
            continue
        if not _editle2(m.group(1).upper(), "CHAPTER"):
            continue
        tok = m.group(2)
        if not any(ch.isdigit() for ch in tok):  # all-letter token (roman 'II'/'III' or garbage)
            continue
        if _XREF.match(ln[m.end():]):  # number followed by "of ..." -> body cross-reference, not a header
            continue
        num = tok.translate(_DIGIT_FIX)
        if not num.isdigit():
            continue
        raw.append(num)
        v = int(num)
        if 1 <= v <= N:
            anchored.add(v)
    return anchored, raw

def load_headers(D, N):
    """page_1indexed -> (anchored:set[int], raw:list[str])."""
    p = os.path.join(D, "ocr_consensus", "page_ocr_results.json")
    if not os.path.exists(p):
        return {}
    try:
        ocr = json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for v in (ocr.values() if isinstance(ocr, dict) else []):
        pg = v.get("page_1indexed")
        if isinstance(pg, int):
            out[pg] = fuzzy_headers(v.get("consensus_text") or "", N)
    return out

def _has_own_garbled_header(c, raw_tokens):
    """True iff chapter c has its OWN header on the page, allowing an extra-digit OCR garble
    (e.g. raw '2338' is chapter 238 -- one inserted/doubled digit). Distinguishes a real chapter
    whose header digit-garbled (keep) from a bodyless stub of another chapter (collapse)."""
    s = str(c)
    for t in raw_tokens:
        if t == s:
            return True
        if len(t) == len(s) + 1 and any(t[:k] + t[k + 1:] == s for k in range(len(t))):
            return True
    return False

# ---- same-act collapse (conservative; ground-truth anchored) ----
def _title_set(a):
    t = (a.get("an_act_title_snippet") or a.get("title") or "")
    return set(re.findall(r"[a-z]{4,}", t.lower()))

def _body_set(a):
    return set(re.findall(r"[a-z]{4,}", (a.get("text") or "").lower()))

def _jac(s1, s2):
    return 0.0 if not s1 or not s2 else len(s1 & s2) / len(s1 | s2)

def _is_phantom(a):
    return len(_title_set(a)) < 3 and len(_body_set(a)) < 5

def dedup_header(by_ch, page_hdr):
    """Collapse OCR digit-garble SAME-ACT duplicates (one act under two chapter numbers) using the
    page's own CHAPTER header as ground truth. CONSERVATIVE -- it removes an act ONLY when:
      (a) it shares a source_page with another act AND their bodies (>=15 tok) or titles (>=4 tok)
          are >=0.6 Jaccard-similar (same physical act); the HEADER-ANCHORED one is kept, or
      (b) it is a pure phantom (empty title AND empty body) not header-anchored, or
      (c) it is a near-phantom stub (<15 body tok AND <=3 title tok) that shares a page with an
          anchored sibling AND has NO header of its own (not even an extra-digit garble) -> it is a
          garble label of the page's real chapter (e.g. 1915 ch636 on ch686's page).
    A header-anchored act -- or a stub with its OWN (possibly extra-digit-garbled) header -- is NEVER
    dropped. Weak (0.3-0.6) pairs, two anchored similars, and content-bearing unanchored stubs are
    FLAGGED for on-page review, not deleted. Returns (drops, flags)."""
    def anchored(c):
        p = by_ch[c].get("source_page")
        return isinstance(p, int) and c in page_hdr.get(p, (set(), []))[0]

    def raw_hdr(p):
        return page_hdr.get(p, (set(), []))[1]

    page_chs = defaultdict(list)
    for c, a in by_ch.items():
        p = a.get("source_page")
        if isinstance(p, int):
            page_chs[p].append(c)

    STUB = 15  # body-token floor below which an act is a bodyless garble-label, not a real act
    drops, flags = {}, []
    for p, chs in page_chs.items():
        if len(chs) < 2:
            continue
        chs = sorted(chs)
        for i in range(len(chs)):
            for j in range(i + 1, len(chs)):
                c1, c2 = chs[i], chs[j]
                if c1 in drops or c2 in drops:
                    continue
                a1, a2 = by_ch[c1], by_ch[c2]
                b1, b2 = _body_set(a1), _body_set(a2)
                t1, t2 = _title_set(a1), _title_set(a2)
                bj = _jac(b1, b2) if len(b1) >= STUB and len(b2) >= STUB else 0.0
                tj = _jac(t1, t2) if len(t1) >= 4 and len(t2) >= 4 else 0.0
                an1, an2 = anchored(c1), anchored(c2)
                stub1, stub2 = len(b1) < STUB, len(b2) < STUB
                if bj >= 0.6:  # near-identical BODIES -> same physical act (safe regardless of title)
                    if an1 and an2:
                        flags.append([c1, c2, p, round(bj, 2), "both-anchored"])
                        continue
                    if an2 and not an1:
                        drop, keep = c1, c2
                    elif an1 and not an2:
                        drop, keep = c2, c1
                    else:
                        drop, keep = (c2, c1) if len(b1) >= len(b2) else (c1, c2)
                    drops[drop] = [keep, p, round(bj, 2), "body"]
                elif tj >= 0.6 and (stub1 ^ stub2):  # shared title BUT one side is a bodyless stub:
                    stub_ch = c1 if stub1 else c2                  # the stub is the garble label;
                    real_ch = c2 if stub1 else c1                  # the side with a real body is the act
                    if anchored(stub_ch):  # a header-anchored stub is a real (bodyless) chapter -> keep
                        flags.append([c1, c2, p, round(tj, 2), "stub-anchored"])
                    else:
                        drops[stub_ch] = [real_ch, p, round(tj, 2), "title-stub"]
                elif 0.3 <= max(bj, tj) < 0.6 and (an1 ^ an2):  # weak signal -> review, never auto-drop
                    flags.append([c1, c2, p, round(max(bj, tj), 2), "weak-review"])

    def best_keeper(c, a, sibs):  # the anchored sibling whose CONTENT best matches the stub (a garble
        if not sibs:             # of the chapter NUMBER lands on its parent's page); accurate forensics
            return None
        ta = _title_set(a)
        return max(sibs, key=lambda s: (_jac(ta, _title_set(by_ch[s])), -abs(s - c)))

    for c, a in list(by_ch.items()):  # phantoms / near-phantom stubs not header-anchored
        if c in drops or anchored(c):
            continue
        p = a.get("source_page")
        anchored_sibs = [x for x in page_chs.get(p, []) if x != c and anchored(x)]
        ntitle, nbody = len(_title_set(a)), len(_body_set(a))
        if _is_phantom(a):  # empty title AND empty body
            drops[c] = [best_keeper(c, a, anchored_sibs), p, 0.0, "phantom"]
        elif nbody < STUB and ntitle <= 3 and anchored_sibs and not _has_own_garbled_header(c, raw_hdr(p)):
            drops[c] = [best_keeper(c, a, anchored_sibs), p, 0.0, "near-phantom-stub"]  # garble label of a page ch
        elif nbody < STUB and anchored_sibs and not _has_own_garbled_header(c, raw_hdr(p)):
            flags.append([c, best_keeper(c, a, anchored_sibs), p, 0.0, "unanchored-stub-review"])  # -> review
    return drops, flags

def merge_dir(D, N):
    by_ch, prov = {}, {}
    for f in TRUSTED:
        for a in load(D, f):
            c = cn(a, N)
            if c and c not in by_ch:
                a2 = dict(a); a2["_merge_source"] = f; by_ch[c] = a2; prov[c] = f
    anchors = sorted((c, page(by_ch[c])) for c in by_ch if page(by_ch[c]) is not None)
    dropped = 0
    for f in LOW:
        for a in load(D, f):
            c = cn(a, N)
            if not c or c in by_ch:
                continue
            if real_anact(a) or page_ok(c, page(a), anchors):
                a2 = dict(a); a2["_merge_source"] = f; by_ch[c] = a2; prov[c] = f
            else:
                dropped += 1
    raw = len(by_ch)
    page_hdr = load_headers(D, N)
    has_ocr = bool(page_hdr)
    drops, flags = dedup_header(by_ch, page_hdr)
    collapsed = [[c] + drops[c] for c in sorted(drops)]  # [dropped_ch, kept_ch, page, score, reason]
    for c in drops:
        prov.pop(c, None)
        del by_ch[c]
    merged = [by_ch[c] for c in sorted(by_ch)]
    by_source = {f: sum(1 for c in prov if prov[c] == f) for f in TRUSTED + LOW}
    out = {"merged_acts": merged,
           "_merge_meta": {"distinct": len(merged), "raw_before_dedup": raw, "cap_N": N,
                           "max_chapter": max(by_ch) if by_ch else 0,
                           "low_pass_dropped_by_filter": dropped,
                           "ocr_headers_available": has_ocr,
                           "same_act_collapsed": len(collapsed), "collapsed_pairs": collapsed,
                           "flagged_for_review": flags,
                           "by_source": {k: v for k, v in by_source.items() if v}}}
    json.dump(out, open(os.path.join(D, "parsed_acts_merged.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return out["_merge_meta"]

if __name__ == "__main__":
    pat = sys.argv[1] if len(sys.argv) > 1 else "production-1915*"
    dirs = sorted(d for d in glob.glob(os.path.join(SCRATCH, pat)) if os.path.isdir(d))
    total, total_collapsed, total_flagged = 0, 0, 0
    for D in dirs:
        N, yr = n_for(os.path.basename(D))
        m = merge_dir(D, N)
        total += m["distinct"]; total_collapsed += m["same_act_collapsed"]; total_flagged += len(m["flagged_for_review"])
        ocr = "" if m["ocr_headers_available"] else " [NO-OCR]"
        print(f"{os.path.basename(D):38} N={N:5} merged={m['distinct']:5} (raw {m['raw_before_dedup']:5}) "
              f"collapsed={m['same_act_collapsed']:3} flag={len(m['flagged_for_review']):3}{ocr}")
    print(f"\n{len(dirs)} volumes, {total} merged chapter-acts; {total_collapsed} same-act dups collapsed, "
          f"{total_flagged} pairs flagged for review.")
