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
    # The parser does `import config` (and siblings) at module level, so
    # pipeline/ must be importable regardless of the cwd this is launched from.
    # Without this the BEFORE module dies with ModuleNotFoundError: config.
    pipeline_dir = str(_REPO / "pipeline")
    if pipeline_dir not in sys.path:
        sys.path.insert(0, pipeline_dir)
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _materialise_before(ref, workdir):
    """git show <ref>:<parser> -> a temp file we can import, WITH ITS WRITES REMOVED.

    ★ THIS NEUTERING IS LOAD-BEARING. Read before touching it.

    The BEFORE parser predates the `write=` kwarg, so `parse_volume(label,
    write=False)` raises TypeError on it. An earlier version of this harness
    "handled" that by falling back to `parse_volume(label)` -- i.e. the DEFAULT,
    which WRITES `parsed_acts_fixed.json` straight into the live volume
    directory. That fallback would have fired on EVERY volume (the kwarg is
    absent from every pre-cc019 ref) and silently overwritten the corpus with
    PRE-FIX output while this script claimed to touch nothing. Caught in
    self-review, 2026-07-25.

    Rather than trust a runtime guard, the write is removed from the SOURCE
    before import, and the patch is ASSERTED. If the expected call site is not
    found -- e.g. a future refactor renames it -- this raises instead of
    silently importing a parser that can write.

    Redirecting SCRATCH_ROOT is NOT a valid alternative: the OCR input is read
    from the same root, so redirecting it breaks the read.
    """
    out = subprocess.run(
        ["git", "show", "%s:%s" % (ref, _PARSER_REL)],
        cwd=str(_REPO), capture_output=True, text=True, encoding="utf-8",
    )
    if out.returncode != 0:
        raise SystemExit("git show %s:%s failed:\n%s" % (ref, _PARSER_REL, out.stderr))

    src = out.stdout
    needle = "out_path.write_text("
    n = src.count(needle)
    if n != 1:
        raise SystemExit(
            "reparse_diff: expected exactly 1 `%s` in %s:%s, found %d. "
            "Refusing to import a BEFORE parser whose write path is unverified."
            % (needle, ref, _PARSER_REL, n))
    # `_DIFF_NEVER_WRITE and out_path.write_text(...)` -- the constant is False,
    # so Python short-circuits and write_text is never called. Keeps the
    # expression syntactically intact across the original's line breaks.
    src = src.replace(needle, "_DIFF_NEVER_WRITE and out_path.write_text(", 1)
    src = "_DIFF_NEVER_WRITE = False\n" + src

    # Also neuter the append-only date-review worklist. It is written from
    # flush_act during the parse, NOT at write time, so removing the JSON write
    # alone still leaves a shared-file side effect.
    if "def _append_date_review(record" in src:
        src = src.replace(
            "def _append_date_review(record: dict):",
            "def _append_date_review(record: dict):\n    return  # neutered by reparse_diff",
            1)
    elif "_append_date_review" in src:
        raise SystemExit(
            "reparse_diff: _append_date_review present but its definition was not "
            "matched -- refusing to run with an un-neutered side effect.")

    dest = Path(workdir) / "ingest_from_ocr_BEFORE.py"
    dest.write_text(src, encoding="utf-8")
    return dest


def _acts_index(result):
    """{chapter_int: FIRST act} from a parse result, confident acts only.

    ⚠ MEASUREMENT HAZARD -- documented 2026-07-25 after the first corpus diff.
    `setdefault` means the first act in reading order wins a chapter key. When a
    newly-recovered act carries an INFLATED Roman numeral (the `T`->`I` OCR
    substitution, or the trailing-`L`->`I` rule) it can collide with a real act
    and HIDE it, so a perfectly good act is reported as "lost" or its date as
    "changed". Four of the eight date-moves in the first full diff were exactly
    this artifact, not a re-read.

    Use _acts_dupes() alongside this to surface the collisions rather than
    silently resolving them.
    """
    if not result:
        return {}
    idx = {}
    for a in result.get("confident", []):
        c = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
        if isinstance(c, int):
            idx.setdefault(c, a)
    return idx


def _acts_dupes(result):
    """{chapter_int: [acts]} for every chapter key held by MORE THAN ONE act.

    A duplicate key means the ingest's chapter key is ambiguous for that volume,
    and it means this diff's gained/lost/date figures for that chapter are not
    trustworthy. Surfaced, not swallowed.
    """
    if not result:
        return {}
    by_ch = {}
    for a in result.get("confident", []):
        c = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
        if isinstance(c, int):
            by_ch.setdefault(c, []).append(a)
    return {c: acts for c, acts in by_ch.items() if len(acts) > 1}


def _path_of(act):
    return act.get("enactment_path") or "approved"


def diff_volume(label, mod_before, mod_after):
    t0 = time.time()
    # BEFORE has had its write path removed at source (see _materialise_before),
    # so it is called with NO write kwarg -- the pre-cc019 signature -- and
    # cannot write regardless. There is deliberately NO TypeError fallback: a
    # fallback here is what previously would have written pre-fix output into
    # the live corpus.
    try:
        r_before = mod_before.parse_volume(label)
    except Exception as e:
        return {"volume": label, "error": "BEFORE: %s" % e}
    try:
        r_after = mod_after.parse_volume(label, write=False)
    except Exception as e:
        return {"volume": label, "error": "AFTER: %s" % e}

    if r_before is None or r_after is None:
        return {"volume": label, "error": "parse returned None (missing OCR?)"}

    # ★ BASELINE FIDELITY CHECK -- without this the whole diff is unfounded.
    #
    # The diff is only meaningful if BEFORE reproduces what is ACTUALLY on disk.
    # If the on-disk parsed_acts_fixed.json was produced by some other code path,
    # a hand edit, or a different ref, then "BEFORE" is a fiction and every
    # gained/lost number below is measured against the wrong baseline.
    #
    # Reported, not fatal: a mismatch is informative (it means the corpus state
    # has a provenance we do not understand) and must surface rather than abort
    # the sweep silently.
    on_disk = SCRATCH / ("production-" + label) / "parsed_acts_fixed.json"
    baseline = {"checked": False}
    if on_disk.exists():
        try:
            disk = json.loads(on_disk.read_text(encoding="utf-8"))
            disk_ch = set()
            for a in disk.get("confident_acts", []):
                c = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
                if isinstance(c, int):
                    disk_ch.add(c)
            before_ch = set(_acts_index(r_before))
            baseline = {
                "checked": True,
                "on_disk_confident": len(disk.get("confident_acts", [])),
                "before_confident": len(r_before.get("confident", [])),
                "chapters_on_disk": len(disk_ch),
                "chapters_before": len(before_ch),
                "matches": disk_ch == before_ch,
                "only_on_disk": sorted(disk_ch - before_ch)[:20],
                "only_in_before": sorted(before_ch - disk_ch)[:20],
            }
        except Exception as e:
            baseline = {"checked": False, "error": str(e)}

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
        "baseline_fidelity": baseline,
        # Duplicate chapter keys make this volume's gained/lost/date figures
        # unreliable -- see _acts_index's hazard note.
        "dupe_keys_before": sorted(_acts_dupes(r_before)),
        "dupe_keys_after": sorted(_acts_dupes(r_after)),
        "dupe_keys_new": sorted(set(_acts_dupes(r_after)) - set(_acts_dupes(r_before))),
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
            flags = []
            if row["lost"]:
                flags.append("LOST %d" % len(row["lost"]))
            if row["date_changed"]:
                # A date that MOVED is more alarming than one that appeared:
                # it means the parser now reads a different date off the same
                # text. Surface it as loudly as a lost chapter.
                flags.append("DATE-MOVED %d" % len(row["date_changed"]))
            bf = row.get("baseline_fidelity") or {}
            if bf.get("checked") and not bf.get("matches"):
                flags.append("BASELINE-MISMATCH")
            flag = ("  <-- " + " / ".join(flags)) if flags else ""
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

    dupe_before = sum(len(r.get("dupe_keys_before") or []) for r in ok)
    dupe_after = sum(len(r.get("dupe_keys_after") or []) for r in ok)
    dupe_new = sum(len(r.get("dupe_keys_new") or []) for r in ok)
    print("  duplicate chapter keys: %d -> %d  (NEW: %d)" % (dupe_before, dupe_after, dupe_new))
    if dupe_new:
        print("    A NEW duplicate key usually means a recovered act carries an")
        print("    INFLATED Roman numeral (T->I, trailing L->I). It also makes this")
        print("    volume's gained/lost/date numbers unreliable for that chapter --")
        print("    the first act in reading order wins the key and hides the other.")
        worst = sorted(ok, key=lambda r: -len(r.get("dupe_keys_new") or []))[:8]
        for r in worst:
            if r.get("dupe_keys_new"):
                print("      %-24s %s" % (r["volume"], r["dupe_keys_new"][:12]))

    bad_baseline = [r["volume"] for r in ok
                    if (r.get("baseline_fidelity") or {}).get("checked")
                    and not (r.get("baseline_fidelity") or {}).get("matches")]
    unchecked = [r["volume"] for r in ok
                 if not (r.get("baseline_fidelity") or {}).get("checked")]
    print("  baseline fidelity: %d/%d volumes reproduce their on-disk artifact"
          % (len(ok) - len(bad_baseline) - len(unchecked), len(ok)))
    if bad_baseline:
        print("    MISMATCH (%d): %s" % (len(bad_baseline), bad_baseline[:15]))
        print("    -> BEFORE does not reproduce what is on disk. The on-disk")
        print("       artifact has a provenance we do not understand, so the")
        print("       gained/lost numbers above are measured against the WRONG")
        print("       baseline for these volumes. Resolve before Phase 4.")
    if unchecked:
        print("    no on-disk artifact to compare (%d): %s" % (len(unchecked), unchecked[:15]))
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
