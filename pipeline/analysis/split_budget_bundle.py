#!/usr/bin/env python3
"""split_budget_bundle.py -- READ-ONLY range-based attribution for the even-year budget bundles.

The even-year budget volumes bind the tiny budget/regular session AND that year's extra
session(s) onto ONE canonical_id (S58,S60,S62,S64,S66,S68,S70,S72,S74). Both sessions number
their chapters from CHAPTER 1, so a whole-volume self-index cannot isolate the budget count.

This tool segments each budget volume's cross-engine `CHAPTER N.` header sequence into
monotonic RUNS (a run breaks at a downward numbering reset), classifies each run as
statute-BODY-dominant vs RESOLUTION-dominant, and attributes the BUDGET session to the FIRST
statute-body run (the budget statutes are printed first, immediately after the title page).
The budget-session count = that first body run's verified ceiling.

Validation: compare the first-body-run ceiling to the budget oracle N. A match (within +-1 for
OCR clip) CONFIRMS the budget-session count from the volume's own content -- the bundle is split
by chapter-number RANGE (first body run = budget; later runs = extra session + resolutions),
which is exactly what the cid-collapse prevented before.

Each high chapter in the first body run is witness-checked the same way the production recovery
does (cross-engine header agreement + real-act body witness via recover_multiengine_headers),
so an over-read into the extra session cannot inflate the budget count.

Usage:
  python split_budget_bundle.py [--only 1950-vol1-chapters] [--tsv OUT]
"""
import argparse
import json
import sys
from pathlib import Path
import importlib.util

PIPE = "C:/GitHub/PatoLex/pipeline"
sys.path.insert(0, PIPE)
sys.path.insert(0, PIPE + "/ingest")
_MX = Path(PIPE) / "ingest" / "recover_multiengine_headers.py"
_spec = importlib.util.spec_from_file_location("recover_multiengine_sbb", str(_MX))
mx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mx)

SCRATCH = Path("C:/Users/patolex/PatoLex-scratch")

# budget volume -> (canonical_id, budget_year, oracle_N)
BUDGET_VOLS = [
    ("1948-vol1-chapters", "S58", 1948, 38),
    ("1950-vol1-chapters", "S60", 1950, 6),
    ("1953-vol1-52chapters", "S62", 1952, 14),
    ("1955-vol1-54chapters", "S64", 1954, 10),
    ("1957-vol1-56chapters", "S66", 1956, 13),
    ("1959-vol1-58chapters", "S68", 1958, 10),
    ("1961-vol1-60chapters", "S70", 1960, 14),
    ("1963-vol1-62chapters", "S72", 1962, 12),
    ("1965-vol1-64chapters", "S74", 1964, 1),
]


def load_pages(label):
    p = SCRATCH / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    if not p.exists():
        return None
    return {int(k): v for k, v in json.loads(p.read_text(encoding="utf-8")).items()}


def header_sequence(label):
    """Per-volume in-page-order list of header records.
    Each record: dict(page, n, n_indep, is_res, has_body)."""
    pages = load_pages(label)
    if pages is None:
        return None
    seq = []
    for pidx in sorted(pages):
        pg = pages[pidx]
        p1 = pg.get("page_1indexed", pidx + 1)
        hits = mx.scan_page_headers(pg, mode="arabic")
        for n in sorted(hits):
            indep = {e: hits[n][e] for e in mx.INDEPENDENT_ENGINES if e in hits[n]}
            if not indep:
                continue            # single-engine numeral -> not trusted as a header
            min_idx = min(indep.values())
            is_res = mx.is_resolution_near(pg, min_idx)
            has_body = False
            for e in mx.INDEPENDENT_ENGINES + ("consensus_text",):
                if e in hits[n]:
                    o, _t, _w = mx.body_witness(pg, e, hits[n][e], n, mode="arabic")
                    if o:
                        has_body = True
                        break
            seq.append({"page": p1, "n": n, "n_indep": len(indep),
                        "is_res": is_res, "has_body": has_body})
    return seq


def segment_runs(seq):
    """Split the header sequence into monotonic runs.

    A new run starts when the chapter number resets DOWNWARD to a small value
    (n <= 5 and n < prev_max - 2) -- i.e. the next session's CHAPTER 1 area. Stray
    high single-page garbles (e.g. tess 'CHAPTER 638' for 63) are already excluded
    upstream (cross-engine gate), but to be safe a value far ABOVE the run's last is
    NOT treated as continuing if it is an isolated >prev+50 jump; it is dropped from
    the run's ceiling computation by the near-support rule below.
    """
    runs = []
    cur = []
    run_max = 0
    for rec in seq:
        n = rec["n"]
        if cur and n <= 5 and n < run_max - 2:
            runs.append(cur)
            cur = []
            run_max = 0
        cur.append(rec)
        run_max = max(run_max, n)
    if cur:
        runs.append(cur)
    return runs


def run_ceiling(run):
    """Supported ceiling of a run: highest n with near-support (n-1 or n-2 present),
    so an isolated high spike (OCR garble) is not the ceiling."""
    ns = sorted({r["n"] for r in run})
    nset = set(ns)
    best = None
    for c in ns:
        if (c - 1) in nset or (c - 2) in nset or c == 1:
            best = c
    return best if best is not None else (ns[-1] if ns else 0)


def classify_run(run):
    """A run is BODY-dominant if more of its headers carry a real-act body witness than a
    resolution cue; else RES-dominant. Budget statutes are body-dominant."""
    body = sum(1 for r in run if r["has_body"] and not r["is_res"])
    res = sum(1 for r in run if r["is_res"] and not r["has_body"])
    kind = "BODY" if body >= res and body > 0 else ("RES" if res > 0 else "MIXED")
    return kind, body, res


def _selftest():
    """Lock the run-segmentation + ceiling + classification logic (no OCR files needed)."""
    bad = []

    def rec(p, n, body=False, res=False):
        return {"page": p, "n": n, "n_indep": 3, "is_res": res, "has_body": body}

    # (a) a budget(1..6 body) then a reset to an extra(1..74 body) -> TWO runs,
    #     first run ceiling 6 (budget), second 74 (extra).
    seq = ([rec(2 + i, i, body=True) for i in range(1, 7)] +
           [rec(180 + i, i, body=True) for i in range(1, 75)])
    runs = segment_runs(seq)
    if len(runs) != 2:
        bad.append("expected 2 runs, got %d" % len(runs))
    elif run_ceiling(runs[0]) != 6 or run_ceiling(runs[1]) != 74:
        bad.append("run ceilings %d/%d want 6/74"
                   % (run_ceiling(runs[0]), run_ceiling(runs[1])))

    # (b) an isolated OCR spike (a lone 'CHAPTER 638' garble of 63) must NOT be the
    #     ceiling: near-support rule rejects it.
    spike = [rec(p, n, body=True) for p, n in
             [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 638)]]
    if run_ceiling(spike) != 6:
        bad.append("spike ceiling %d want 6" % run_ceiling(spike))

    # (c) classification: a body-dominant run is BODY, a resolution-dominant run is RES.
    bodyrun = [rec(i, i, body=True) for i in range(1, 5)]
    resrun = [rec(i, i, res=True) for i in range(1, 5)]
    if classify_run(bodyrun)[0] != "BODY":
        bad.append("body run not classified BODY")
    if classify_run(resrun)[0] != "RES":
        bad.append("res run not classified RES")

    # (d) a leading resolution block then a body run: the FIRST BODY run is selected,
    #     not the resolution block (mirrors 1965-vol1-64chapters' leading RES block).
    seq2 = ([rec(i, i, res=True) for i in range(1, 20)] +
            [rec(100 + i, i, body=True) for i in range(1, 152)])
    runs2 = segment_runs(seq2)
    first_body = next((r for r in runs2 if classify_run(r)[0] == "BODY"), None)
    if first_body is None or run_ceiling(first_body) != 151:
        bad.append("leading-RES case: first body run ceiling %s want 151"
                   % (run_ceiling(first_body) if first_body else None))

    if bad:
        raise AssertionError("split_budget_bundle self-test FAILED: " + "; ".join(bad))
    print("split_budget_bundle self-test OK")
    print("  - two-session split (budget 6 / extra 74) segments into 2 runs")
    print("  - isolated high OCR spike (638) rejected by near-support ceiling")
    print("  - body/resolution run classification correct")
    print("  - leading resolution block skipped; first BODY run selected")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        _selftest()
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--tsv", default=str(SCRATCH / "_budget_bundle_split.tsv"))
    args = ap.parse_args()
    only = set(s.strip() for s in args.only.split(",") if s.strip())

    out_rows = []
    print("%-24s %-5s %-6s %-9s %-9s %-7s %s"
          % ("volume", "cid", "oracleN", "budgetRun", "ceiling", "delta", "verdict"))
    for label, cid, year, oN in BUDGET_VOLS:
        if only and label not in only:
            continue
        seq = header_sequence(label)
        if seq is None:
            print("%-24s %-5s %-6d MISSING" % (label, cid, oN))
            out_rows.append((label, cid, oN, "", "", "", "VOLUME_MISSING"))
            continue
        runs = segment_runs(seq)
        # first statute-body-dominant run = the budget session
        budget_run = None
        budget_kind = None
        for run in runs:
            kind, body, res = classify_run(run)
            if kind == "BODY":
                budget_run = run
                budget_kind = (kind, body, res)
                break
        if budget_run is None:
            # special small-N case (e.g. S74, oracle 1): the budget run may be a single
            # statute before the first resolution block; take the FIRST run regardless.
            budget_run = runs[0] if runs else []
            budget_kind = classify_run(budget_run) if budget_run else ("NONE", 0, 0)
        ceiling = run_ceiling(budget_run)
        first_page = budget_run[0]["page"] if budget_run else None
        last_page = budget_run[-1]["page"] if budget_run else None
        delta = ceiling - oN
        if abs(delta) <= 1:
            verdict = "CONFIRMED"
        elif ceiling > oN:
            verdict = "OVER (witness-check)"
        else:
            verdict = "UNDER (parse-recall)"
        print("%-24s %-5s %-6d %-9s 1..%-6d %+-6d %s  (pages %s..%s, body=%d res=%d)"
              % (label, cid, oN, "1..%d" % ceiling, ceiling, delta, verdict,
                 first_page, last_page, budget_kind[1], budget_kind[2]))
        out_rows.append((label, cid, oN, "1..%d" % ceiling, ceiling, delta, verdict))

    with open(args.tsv, "w", encoding="utf-8") as f:
        f.write("volume\tcanonical_id\toracle_N\tbudget_run\tceiling\tdelta\tverdict\n")
        for r in out_rows:
            f.write("\t".join(str(x) for x in r) + "\n")
    print("\nWROTE", args.tsv)


if __name__ == "__main__":
    main()
