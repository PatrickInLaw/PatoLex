"""recover_all.py -- run the chapter recovery+renumber pass (recover_acts.process_session) across the
WHOLE corpus, grouping volumes by their legislative SESSION (LEGISLATURE_MAP[label][0]) as the cross-session
guard requires. Writes parsed_acts_recovered.json per volume (additive; no DB, no overwrite of parsed_acts_fixed),
then aggregates all recovered acts into chapters_recovered.tsv (same columns as extract_chapters.py) so
chapter_vs_oracle.py can measure the after-recovery completeness.

  set PATOLEX_LOCATION_ROOT=<data_root> ; set PYTHONPATH=<repo>\\pipeline
  python -m ingest.recover_all              # all sessions
  python -m ingest.recover_all 1957 1931    # only sessions containing these year prefixes (substring filter)
"""
import sys, os, glob, json
from collections import defaultdict
from ingest import ingest_from_ocr as ing
from ingest import recover_acts as ra

SKIP = set(getattr(ing, "SKIP_LABELS", set()))

def discover_labels():
    labels = []
    for p in glob.glob(str(ra.ROOT / "production-*" / "ocr_consensus" / "page_ocr_results.json")):
        vol = os.path.basename(os.path.dirname(os.path.dirname(p)))   # production-<label>
        labels.append(vol[len("production-"):])
    return sorted(set(labels))

def main():
    filt = sys.argv[1:]
    labels = discover_labels()
    groups = defaultdict(list); skipped = []
    for label in labels:
        if filt and not any(f in label for f in filt):
            continue
        if label in SKIP:
            skipped.append((label, "skip_label")); continue
        if label not in ing.LEGISLATURE_MAP:
            skipped.append((label, "unmapped(pre-1880/non-statute)")); continue
        groups[ing.LEGISLATURE_MAP[label][0]].append(label)

    print(f"discovered {len(labels)} OCR volumes; {len(groups)} sessions to recover; "
          f"{len(skipped)} skipped", flush=True)
    for lbl, why in skipped:
        print(f"  SKIP {lbl}: {why}", flush=True)

    ok = fail = 0
    for sess in sorted(groups):
        grp = sorted(groups[sess])
        try:
            ra.process_session(grp)
            ok += 1
        except SystemExit as e:
            print(f"  GUARD-REJECT session {sess!r} {grp}: {e}", flush=True); fail += 1
        except Exception as e:
            print(f"  ERROR session {sess!r} {grp}: {type(e).__name__}: {e}", flush=True); fail += 1
    print(f"\nrecovery done: {ok} sessions ok, {fail} failed", flush=True)

    # aggregate recovered acts -> chapters_recovered.tsv (same columns as extract_chapters.py)
    out = ra.ROOT / "chapters_recovered.tsv"
    n = 0
    with open(out, "w", encoding="utf-8") as w:
        w.write("vol_label\tlist\tchapter_raw\tchapter_int\tiso_date\tsource_page\n")
        for p in sorted(glob.glob(str(ra.ROOT / "production-*" / "parsed_acts_recovered.json"))):
            label = os.path.basename(os.path.dirname(p))[len("production-"):]
            try:
                data = json.load(open(p, encoding="utf-8", errors="replace"))
            except Exception:
                continue
            for listname in ("confident_acts", "flagged_acts"):
                for a in data.get(listname, []):
                    ci = a.get("chapter_int")
                    w.write("\t".join([
                        label, listname,
                        str(a.get("chapter_raw", "")).replace("\t", " ").replace("\n", " "),
                        "" if ci is None else str(ci),
                        str(a.get("iso_date") or ""),
                        str(a.get("source_page", "")),
                    ]) + "\n")
                    n += 1
    print(f"wrote {out} ({n:,} acts)", flush=True)

if __name__ == "__main__":
    main()
