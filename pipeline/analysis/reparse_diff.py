"""Before/after reparse diff -- measure EXACTLY what the cc019 parser fixes change.

NO OCR IS PERFORMED and NO CORPUS FILE IS MODIFIED. This loads the banked
`ocr_consensus/page_ocr_results.json` for each volume and runs TWO parsers over
the identical input:

    BEFORE = pipeline/ingest/ingest_from_ocr.py as of a chosen git ref
             (default: the pre-cc019 baseline)
    AFTER  = the current working-tree parser

Both are invoked with write=False, so nothing is written into any volume
directory. The only output is this script's own report.

Why a diff and not an in-place reparse: the corpus is ingested exactly once, and
a reparse moves chapter counts, which feed the recall oracle. We want the delta
measured and reviewed BEFORE anything is committed to the corpus.

Usage
-----
    # one volume, quick look
    python reparse_diff.py --volumes 1865-66

    # a sample across eras
    python reparse_diff.py --volumes 1865-66,1875-76,1877-78,1982-vol5

    # everything reparseable
    python reparse_diff.py --all

    # compare against a different baseline
    python reparse_diff.py --all --before-ref f152284

Output
------
    <root>/_reparse_diff_<stamp>.json   full machine-readable delta
    stdout                              per-volume + corpus summary

What is compared, per volume
----------------------------
  * confident / flagged act counts
  * the SET of chapter numbers found (gained / lost)
  * per-chapter date changes (added / removed / changed)
  * enactment-path distribution (approved / unsigned_lapse / veto_override)

A GAINED chapter is a recovery. A LOST chapter is a regression and is reported
loudly -- the fixes should be strictly additive, and anything lost needs a look
before this is run for real.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_PARSER_REL = "pipeline/ingest/ingest_from_ocr.py"
DEFAULT_BEFORE_REF = "f152284"  # cc019 docs baseline == pre-parser-fix code

SCRATCH = Path(os.environ.get("PATOLEX_LOCATION_ROOT", r"C:\PatoLex-scratch"))


def _load_parser(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _materialise_before(ref, workdir):
    """git show <ref>:<parser> -> a temp file we can import."""
    out = subprocess.run(
        ["git", "show", "%s:%s" % (ref, _PARSER_REL)],
        cwd=str(_REPO), capture_output=True, text=True, encoding="utf-8",
    )
    if out.returncode != 0:
        raise SystemExit("git show %s:%s failed:\n%s" % (ref, _PARSER_REL, out.stderr))
    dest = Path(workdir) / "ingest_from_ocr_BEFORE.py"
    dest.write_text(out.stdout, encoding="utf-8")
    return dest


def _acts_index(result):
    """{chapter_int: act} from a parse result, confident acts only."""
    if not result:
        return {}
    idx = {}
    for a in result.get("confident", []):
        c = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
        if isinstance(c, int):
            idx.setdefault(c, a)
    return idx


def _path_of(act):
    return act.get("enactment_path") or "approved"


def diff_volume(label, mod_before, mod_after):
    t0 = time.time()
    try:
        r_before = mod_before.parse_volume(label, write=False)
    except TypeError:
        # BEFORE predates the write= kwarg -- redirect its output to a temp file
        # so the corpus is still never touched.
        with tempfile.TemporaryDirectory() as td:
            saved = mod_before.SCRATCH_ROOT
            try:
                r_before = mod_before.parse_volume(label)
            finally:
                mod_before.SCRATCH_ROOT = saved
    except Exception as e:
        return {"volume": label, "error": "BEFORE: %s" % e}
    try:
        r_after = mod_after.parse_volume(label, write=False)
    except Exception as e:
        return {"volume": label, "error": "AFTER: %s" % e}

    if r_before is None or r_after is None:
        return {"volume": label, "error": "parse returned None (missing OCR?)"}

    a_before = _acts_index(r_before)
    a_after = _acts_index(r_after)
    s_before, s_after = set(a_before), set(a_after)

    gained = sorted(s_after - s_before)
    lost = sorted(s_before - s_after)

    date_added, date_removed, date_changed = [], [], []
    for c in sorted(s_before & s_after):
        d0 = a_before[c].get("iso_date")
        d1 = a_after[c].get("iso_date")
        if d0 == d1:
            continue
        if d0 is None and d1 is not None:
            date_added.append({"chapter": c, "date": d1})
        elif d0 is not None and d1 is None:
            date_removed.append({"chapter": c, "date": d0})
        else:
            date_changed.append({"chapter": c, "before": d0, "after": d1})

    paths = {}
    for c, a in a_after.items():
        p = _path_of(a)
        paths[p] = paths.get(p, 0) + 1

    return {
        "volume": label,
        "seconds": round(time.time() - t0, 2),
        "pages": r_after.get("page_count"),
        "confident_before": len(r_before.get("confident", [])),
        "confident_after": len(r_after.get("confident", [])),
        "flagged_before": len(r_before.get("flagged", [])),
        "flagged_after": len(r_after.get("flagged", [])),
        "chapters_before": len(s_before),
        "chapters_after": len(s_after),
        "gained": gained,
        "lost": lost,
        "date_added": date_added,
        "date_removed": date_removed,
        "date_changed": date_changed,
        "enactment_paths_after": paths,
    }


def discover_labels():
    out = []
    for d in sorted(SCRATCH.glob("production-*")):
        if (d / "ocr_consensus" / "page_ocr_results.json").exists():
            out.append(d.name[len("production-"):])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--volumes", help="comma-separated session labels")
    ap.add_argument("--all", action="store_true", help="every reparseable volume")
    ap.add_argument("--before-ref", default=DEFAULT_BEFORE_REF)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.all:
        labels = discover_labels()
    elif args.volumes:
        labels = [v.strip() for v in args.volumes.split(",") if v.strip()]
    else:
        ap.error("pass --volumes or --all")

    print("BEFORE ref : %s" % args.before_ref)
    print("AFTER      : working tree")
    print("volumes    : %d" % len(labels))
    print("NOTE: no OCR is performed; no corpus file is modified.\n")

    with tempfile.TemporaryDirectory() as td:
        before_path = _materialise_before(args.before_ref, td)
        mod_before = _load_parser(before_path, "ing_before")
        mod_after = _load_parser(_REPO / _PARSER_REL, "ing_after")

        rows = []
        t0 = time.time()
        for i, label in enumerate(labels, 1):
            row = diff_volume(label, mod_before, mod_after)
            rows.append(row)
            if row.get("error"):
                print("[%d/%d] %-22s ERROR %s" % (i, len(labels), label, row["error"]))
                continue
            flag = "  <-- LOST %d" % len(row["lost"]) if row["lost"] else ""
            print("[%d/%d] %-22s pages=%-5s chapters %d -> %d  (+%d/-%d)  dates +%d ~%d -%d  %.1fs%s"
                  % (i, len(labels), label, row["pages"],
                     row["chapters_before"], row["chapters_after"],
                     len(row["gained"]), len(row["lost"]),
                     len(row["date_added"]), len(row["date_changed"]),
                     len(row["date_removed"]), row["seconds"], flag))

    ok = [r for r in rows if not r.get("error")]
    tot_gain = sum(len(r["gained"]) for r in ok)
    tot_lost = sum(len(r["lost"]) for r in ok)
    tot_dadd = sum(len(r["date_added"]) for r in ok)
    tot_dchg = sum(len(r["date_changed"]) for r in ok)
    tot_drem = sum(len(r["date_removed"]) for r in ok)
    paths = {}
    for r in ok:
        for p, n in r["enactment_paths_after"].items():
            paths[p] = paths.get(p, 0) + n

    print("\n" + "=" * 70)
    print("CORPUS DELTA   volumes ok=%d err=%d   wall=%.1fs"
          % (len(ok), len(rows) - len(ok), time.time() - t0))
    print("  chapters gained : %d" % tot_gain)
    print("  chapters LOST   : %d%s" % (tot_lost, "   <-- REGRESSION, investigate" if tot_lost else ""))
    print("  dates added     : %d" % tot_dadd)
    print("  dates changed   : %d" % tot_dchg)
    print("  dates removed   : %d%s" % (tot_drem, "   <-- investigate" if tot_drem else ""))
    print("  enactment paths : %s" % json.dumps(paths, sort_keys=True))
    print("=" * 70)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else (SCRATCH / ("_reparse_diff_%s.json" % stamp))
    out.write_text(json.dumps({
        "before_ref": args.before_ref,
        "volumes": rows,
        "totals": {"gained": tot_gain, "lost": tot_lost,
                   "date_added": tot_dadd, "date_changed": tot_dchg,
                   "date_removed": tot_drem, "enactment_paths": paths},
    }, indent=1), encoding="utf-8")
    print("\nfull delta -> %s" % out)


if __name__ == "__main__":
    main()
