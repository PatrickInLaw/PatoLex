"""recover_clause_seq.py -- DRAFT (Stage-1) header-independent act recovery for the chaptered OCR era.
================================================================================================
STATUS: PROTOTYPE. Validated on the worst year (1915: 62% -> 86%, text-verified). NOT yet Hans-gated
and NOT wired into merge_passes.py. Writes an ADDITIVE `parsed_acts_clauserec.json` per volume; never
touches any existing file or the DB. Safe to run; its output is not consumed until reviewed.

WHY THIS EXISTS
---------------
The precision-first recovery (recover_lost_header.py) seeds act boundaries on line-head `CHAPTER`
headers and fills a gap only when #boundaries == #open-slots. The residual it leaves (1915 stuck at
~62%) is the subclass where the CHAPTER header AND the "An act" title both OCR-garbled -- so no header
seed exists -- even though the act BODY (incl. a garbled enactment clause) is fully present in the OCR
(proven on-page: ch103 "ln act to amend sections 2152..." @ p182, etc.). This pass recovers those.

METHOD (header-independent, garble-robust, sequence-assigned -- the printed numeral is NOT trusted)
--------------------------------------------------------------------------------------------------
1. ANCHORS: chapters whose number is header-confirmed on their merged source_page (merge_passes
   fuzzy headers). Reduce to the longest page-monotonic backbone via LIS (drops stray garbled
   'CHAPTER n' headers that would otherwise create impossible gaps).
2. BOUNDARIES: per-act act-head signals, fuzzy/garble-tolerant -- the enactment clause ("...people
   of the State of California do enact as follows") OR the head approval bracket ("[Approved <date>
   ... In effect ...]"). Deduped within a same-act-head line window. LINE-LEVEL (not page-level), so
   multiple short appropriation acts sharing one page are split correctly.
3. FILL: between two adjacent anchor header-lines holding K open chapter slots, if exactly K+1
   boundaries fall in range (anchor-lo's own clause + one per missing act), assign the K missing
   slots in line order to the K post-anchor boundaries. Each recovered act carries real buffer TEXT
   -> text-verified by construction. Gaps that don't match are left (ambiguous) for Stage 2/3.

KNOWN RESIDUAL / NEXT POLISH (do before Hans + wiring into the merge):
  - Over-detection in some gaps from BODY citations ("...as approved <date>... in effect...", quoted
    enactment clauses in amendments) -> add a body-citation filter (require bracket / colon / Section-1
    follow).
  - A few wrong-SLOPE anchors survive LIS (page-monotonic but magnitude-off) -> add local-slope outlier
    rejection.
  - source_page is the CLAUSE page; for acts whose title sits on the previous page, walk back to the
    'An act' title line so source_page = act start.
  - Stage 2 (aggressive multi-slot alignment) + Stage 3 (residual fill + heavy per-act verify) then
    Hans-gate before this feeds the merge / ingest.

USAGE: python recover_clause_seq.py "production-1915*"   (glob; writes parsed_acts_clauserec.json each)
"""
import os, json, glob, sys, re, bisect
REPO_INGEST = os.path.join(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_INGEST)
import merge_passes as mp  # fuzzy_headers / load_headers ground truth

SCRATCH = r"C:\PatoLex-scratch"
DEDUP_WIN = 7          # merge same-act-head signals (title/[approved]/clause span ~6 lines)
BODY_LINES = 70        # buffer length captured as the recovered act's text

ENACT = re.compile(r"\benact\w{0,3}\s+as\s+follow", re.I)
ENACTg = re.compile(r"[eco]n[ae]ct\w{0,2}\s+as\s+follow", re.I)
PEOPLE = re.compile(r"p[eco]ople\s+of\s+the\s+stat\w{0,2}\s+of\s+calif", re.I)
APPR = re.compile(r"appr[oc]ved\b", re.I)
INEFF = re.compile(r"in\s+[eco]ff[eco]ct", re.I)
# 'An act' title (heavily garbled in this corpus: 'ln act','Anact','clin act','Anoacl','An aet'),
# confirmed by a following title verb so body prose doesn't match.
ANACT = re.compile(r"\b([A4cl][nmli]{0,3}\s*a[ce]t|\bln\s+act|\banoac[lt])\b[^.]{0,40}?"
                   r"\b(to|for|author|provid|amend|appropriat|relat|establ|creat|requir|reg)", re.I)


def is_boundary(win):
    # An act head fires on the enactment clause (strong 'enact as follow' OR 'people of the State of
    # Calif' CONFIRMED by a nearby 'enact'/'follow' -- bare 'people of the State' is a body citation,
    # e.g. 'payable to the people of the State of California') OR the head approval bracket 'Approved
    # <date> ... In effect ...'. The 'An act' title is NOT used: it over-fires on amendment
    # cross-references ("an act entitled 'An act to ...'"), which broke the boundary counts.
    clause = ENACT.search(win) or ENACTg.search(win) or (
        PEOPLE.search(win) and re.search(r"en[ae]ct|follow", win, re.I))
    return bool(clause or (APPR.search(win) and INEFF.search(win)))


def theil_sen_filter(items):
    """Drop magnitude-wrong anchors (stray garbled 'CHAPTER n' headers on a far page) that LIS keeps
    because they are page-monotonic. chapter->page is ~linear over a volume; fit a robust Theil-Sen
    line (median pairwise slope + median intercept) and drop anchors whose page residual is a gross
    outlier. Items: [(chapter, page)] sorted by chapter."""
    n = len(items)
    if n < 6:
        return items
    cs = [c for c, _ in items]
    ps = [p for _, p in items]
    slopes = []
    for i in range(n):
        for j in range(i + 1, n):
            if cs[j] != cs[i]:
                slopes.append((ps[j] - ps[i]) / (cs[j] - cs[i]))
    slopes.sort()
    b = slopes[len(slopes) // 2]
    inter = sorted(ps[k] - b * cs[k] for k in range(n))
    a = inter[n // 2]
    res = [abs(ps[k] - (a + b * cs[k])) for k in range(n)]
    sres = sorted(res)
    mad = sres[len(sres) // 2] or 1.0
    thr = max(25.0, 5 * mad)
    return [items[k] for k in range(n) if res[k] <= thr]


def load_lines(D):
    ocr = os.path.join(D, "ocr_consensus", "page_ocr_results.json")
    if not os.path.exists(ocr):
        return []
    raw = json.load(open(ocr, encoding="utf-8"))
    out = []
    for v in sorted(raw.values(), key=lambda v: v.get("page_1indexed", 0)):
        p = v.get("page_1indexed")
        for ln in (v.get("consensus_text") or "").split("\n"):
            out.append((p, ln))
    return out


def lis_anchors(anchor_items):
    """Longest subsequence with strictly increasing page (anchor_items sorted by chapter asc)."""
    if not anchor_items:
        return []
    pages = [p for _, p in anchor_items]
    tails, prev = [], [-1] * len(pages)
    tail_pages = []
    for k, val in enumerate(pages):
        j = bisect.bisect_left(tail_pages, val)
        if j == len(tails):
            tails.append(k); tail_pages.append(val)
        else:
            tails[j] = k; tail_pages[j] = val
        prev[k] = tails[j - 1] if j > 0 else -1
    seq, k = [], tails[-1]
    while k != -1:
        seq.append(anchor_items[k]); k = prev[k]
    return list(reversed(seq))


def recover_volume(D, N):
    lines = load_lines(D)
    if not lines:
        return None
    ph = mp.load_headers(D, N)
    mpath = os.path.join(D, "parsed_acts_merged.json")
    if not os.path.exists(mpath):
        return None
    merged = json.load(open(mpath, encoding="utf-8"))["merged_acts"]
    present, anchor, present_page = set(), {}, {}
    for a in merged:
        c = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
        p = a.get("source_page")
        if isinstance(c, int) and 1 <= c <= N:
            present.add(c)
            if isinstance(p, int):
                present_page[c] = p
                if c in ph.get(p, (set(), []))[0]:
                    anchor[c] = p
    anchors = lis_anchors(theil_sen_filter(sorted(anchor.items())))

    # boundaries (global line index), deduped to one per act head. STRICT (clause/approval) for the
    # main pass; LOOSE (also a garbled 'An act <verb>' title) reserved for under-filled gaps only.
    def detect(loose):
        out, last = [], -DEDUP_WIN
        for i in range(len(lines)):
            win = lines[i][1] + " " + (lines[i + 1][1] if i + 1 < len(lines) else "")
            if (is_boundary(win) or (loose and ANACT.search(win))) and i - last >= DEDUP_WIN:
                out.append(i); last = i
        return out
    bnds = detect(False)
    bnds_loose = detect(True)

    # anchor header line index (first line on its page matching a fuzzy 'CHAPTER <c>')
    def anchor_line(c, p):
        pat = re.compile(r"[CUO0][HI1l]{0,2}A[PFB]?T[EI]?[RN]?\s*0*%d\b" % c, re.I)
        first = None
        for i, (pg, ln) in enumerate(lines):
            if pg == p:
                if first is None:
                    first = i
                if pat.search(ln):
                    return i
            elif pg > p:
                break
        return first

    aline = [(c, p, anchor_line(c, p)) for c, p in anchors]
    aline = [t for t in aline if t[2] is not None]

    def title_near(li):
        for j in range(li, min(len(lines), li + 6)):
            if ANACT.search(lines[j][1]):
                return re.sub(r"\s+", " ", lines[j][1]).strip()[:300]
        return ""

    def try_fill(c_lo, l_lo, c_hi, l_hi, bnd_list, status):
        """If exactly one boundary per chapter in [c_lo,c_hi) AND every present chapter aligns to its
        positional boundary (within 2pp), return the recovered records for the missing slots; else
        None. The checkpoint test is what makes a relaxed boundary set safe to use."""
        span = c_hi - c_lo
        rng = bnd_list[bisect.bisect_right(bnd_list, l_lo):bisect.bisect_left(bnd_list, l_hi)]
        if len(rng) != span:
            return None
        for c in range(c_lo + 1, c_hi):
            if c in present and c in present_page and abs(lines[rng[c - c_lo]][0] - present_page[c]) > 2:
                return None
        recs = []
        for slot in range(c_lo + 1, c_hi):
            if slot in present:
                continue
            bi = rng[slot - c_lo]
            body = " ".join(lines[j][1] for j in range(bi, min(len(lines), bi + BODY_LINES)))
            recs.append({
                "chapter": str(slot), "chapter_int": slot, "chapter_int_final": slot,
                "chapter_raw": "(seq-clause)", "title": title_near(bi),
                "text": re.sub(r"[ \t]+", " ", body)[:6000], "source_page": lines[bi][0],
                "lo_anchor": c_lo, "hi_anchor": c_hi, "origin": "clause_seq", "status": status,
            })
        return recs

    recovered, fillable, ambiguous, loose_fills = [], 0, 0, 0
    for (c_lo, _, l_lo), (c_hi, _, l_hi) in zip(aline, aline[1:]):
        if not [s for s in range(c_lo + 1, c_hi) if s not in present]:
            continue
        recs = try_fill(c_lo, l_lo, c_hi, l_hi, bnds, "seq_assigned_clause")
        if recs is None:  # Stage-2: retry under-filled gaps with the LOOSE boundary set (gap-local)
            recs = try_fill(c_lo, l_lo, c_hi, l_hi, bnds_loose, "seq_assigned_loose")
            if recs is not None:
                loose_fills += 1
        if recs is None:
            ambiguous += 1
        else:
            fillable += 1
            recovered.extend(recs)

    out = {"recovered_acts": recovered,
           "_clauserec_meta": {"N": N, "present_before": len(present), "anchors_lis": len(aline),
                               "boundaries": len(bnds), "gaps_fillable": fillable,
                               "gaps_loose_filled": loose_fills,
                               "gaps_ambiguous": ambiguous, "recovered": len(recovered),
                               "after": len(present) + len(recovered),
                               "pct_after": round(100 * (len(present) + len(recovered)) / N, 1),
                               "draft": True, "hans_gated": False, "wired_into_merge": False}}
    json.dump(out, open(os.path.join(D, "parsed_acts_clauserec.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    return out["_clauserec_meta"]


def n_for(name):
    oracle = {}
    with open(mp.ORACLE_TSV, encoding="utf-8") as f:
        import csv
        for row in csv.DictReader(f, delimiter="\t"):
            try:
                y = int(row["session_year"]); oracle[y] = max(oracle.get(y, 0), int(row["total_chapters"]))
            except Exception:
                pass
    m = re.search(r"production-(\d{4})", name)
    return oracle.get(int(m.group(1))) if m else None


if __name__ == "__main__":
    pat = sys.argv[1] if len(sys.argv) > 1 else "production-1915*"
    dirs = sorted(d for d in glob.glob(os.path.join(SCRATCH, pat)) if os.path.isdir(d))
    for D in dirs:
        N = n_for(os.path.basename(D))
        if not N:
            continue
        m = recover_volume(D, N)
        if m:
            print(f"{os.path.basename(D):38} N={N:5} {m['present_before']:4} -> {m['after']:4} "
                  f"({m['pct_after']:4}%)  recovered={m['recovered']:3} fill={m['gaps_fillable']:3} "
                  f"amb={m['gaps_ambiguous']:3}")
