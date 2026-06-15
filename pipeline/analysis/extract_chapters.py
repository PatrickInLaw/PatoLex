"""extract_chapters.py -- emit a tiny TSV of (vol_label, list, chapter_raw, chapter_int, iso_date, source_page)
from the aggregated per-volume parse outputs, so the chapter-completeness analysis can iterate cheaply off-box.
Pure stdlib. Run on whichever box has the full _parse_outputs set (the 5090):
  python extract_chapters.py <parse_outputs_dir>   > chapters.tsv
"""
import os, sys, json, glob

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    files = sorted(glob.glob(os.path.join(d, "parsed_acts_*.json")))
    out = sys.stdout
    out.write("vol_label\tlist\tchapter_raw\tchapter_int\tiso_date\tsource_page\n")
    for fp in files:
        label = os.path.basename(fp)[len("parsed_acts_"):-len(".json")]
        try:
            data = json.load(open(fp, encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for listname in ("confident_acts", "flagged_acts"):
            for a in data.get(listname, []):
                ci = a.get("chapter_int")
                out.write("\t".join([
                    label, listname,
                    str(a.get("chapter_raw", "")).replace("\t", " ").replace("\n", " "),
                    "" if ci is None else str(ci),
                    str(a.get("iso_date") or ""),
                    str(a.get("source_page", "")),
                ]) + "\n")

if __name__ == "__main__":
    main()
