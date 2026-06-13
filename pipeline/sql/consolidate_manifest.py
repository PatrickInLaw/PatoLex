"""
consolidate_manifest.py -- build the AUTHORITATIVE 205-volume source manifest, deterministically, by keying on
the volumes that were actually processed (the cascade out_context labels) and resolving each to its source PDF
via the existing pdf_name_for() rule + the explicit `pdf` overrides recorded in the queue snapshots.

Inputs (all already in the repo / on the box):
  --out-context <dir>   the 205 processed cascade volumes (production-<label>.json)  [ground truth of scope]
  --snapshots  <f...>   queue-state JSONs carrying explicit pdf/year overrides
                        (pipeline/sql/live_queue_snapshot.json, pipeline/5080/production_queue_state.json)
  --archive    <dir>    chief-clerk-archive (to confirm the resolved PDF actually exists)
Output:
  manifest.tsv  with columns: label, pdf, yr, pdf_exists, source, note
    source = 'explicit' (pdf came from a snapshot override) | 'derived' (<label>_Statutes.pdf rule)
    note   = 'ambiguous:<reason>' for the 1929/1949 variant cases, else ''

This is the seed for dbo.volume_manifest + dbo.ocr_queue. Deterministic: same inputs -> same output, no LLM.
"""
import argparse, os, json, glob, re

def _norm(s):
    """normalize a label or pdf stem for matching: lowercase, drop all non-alphanumerics."""
    return re.sub(r"[^a-z0-9]", "", s.lower())

# the two genuinely-ambiguous variant cases flagged in the provenance reconstruction
AMBIGUOUS = {
    "1929-vol1-28chapters": "28 vs 29 Chapters edition relationship undocumented",
    "1929-vol1-29chapters": "28 vs 29 Chapters edition relationship undocumented",
    "1949-vol1-49chapters-prior": "'_prior' edition relationship to full Vol1_Chapters undocumented",
}

def pdf_name_for(label, explicit):
    """Mirror pipeline/sql/seed_ocr_queue.py: explicit 'pdf' else '<label>_Statutes.pdf'."""
    return explicit or (label + "_Statutes.pdf")

def year_of(label, explicit_year):
    if explicit_year:
        return int(explicit_year)
    m = re.match(r"(\d{4})", label)
    return int(m.group(1)) if m else 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-context", required=True)
    ap.add_argument("--snapshots", nargs="+", required=True)
    ap.add_argument("--archive", required=True)
    ap.add_argument("--out", default="manifest.tsv")
    a = ap.parse_args()

    # 1) ground-truth scope: the processed labels
    labels = []
    for fp in sorted(glob.glob(os.path.join(a.out_context, "*.json"))):
        b = os.path.basename(fp)[:-5]
        labels.append(b[len("production-"):] if b.startswith("production-") else b)

    # 2) overrides (explicit pdf + year) from the queue snapshots
    override = {}
    for sf in a.snapshots:
        if not os.path.exists(sf):
            print(f"[warn] snapshot missing: {sf}"); continue
        data = json.load(open(sf, encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("volumes", data)
        for r in (rows if isinstance(rows, list) else []):
            lab = r.get("label")
            if lab:
                override[lab] = {"pdf": r.get("pdf"), "year": r.get("year") or r.get("yr")}

    # archive PDF index for normalized-name fallback matching (labels were derived from these filenames)
    archive_pdfs = [os.path.basename(p) for p in
                    glob.glob(os.path.join(a.archive, "*.pdf")) + glob.glob(os.path.join(a.archive, "*.PDF"))]
    norm_index = {}
    for fn in archive_pdfs:
        norm_index.setdefault(_norm(os.path.splitext(fn)[0]), []).append(fn)

    # 3) resolve each processed label -> pdf
    rows = []
    missing = 0
    for lab in labels:
        ov = override.get(lab, {})
        pdf = pdf_name_for(lab, ov.get("pdf"))
        yr = year_of(lab, ov.get("year"))
        source = "explicit" if ov.get("pdf") else "derived"
        exists = os.path.exists(os.path.join(a.archive, pdf))
        # fallback: derived name absent -> normalized match against the actual archive filenames
        if not exists and not ov.get("pdf"):
            cand = norm_index.get(_norm(lab), [])
            if len(cand) == 1:
                pdf, exists, source = cand[0], True, "matched"
            elif len(cand) > 1:
                source = "ambiguous-match"
        if not exists:
            missing += 1
        note = ("ambiguous:" + AMBIGUOUS[lab]) if lab in AMBIGUOUS else ""
        rows.append((lab, pdf, yr, "1" if exists else "0", source, note))

    rows.sort(key=lambda r: (r[2], r[0]))
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("label\tpdf\tyr\tpdf_exists\tsource\tnote\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")

    print(f"volumes: {len(rows)}   explicit-pdf: {sum(1 for r in rows if r[4]=='explicit')}   "
          f"derived: {sum(1 for r in rows if r[4]=='derived')}   PDF-missing: {missing}   ambiguous: {len(AMBIGUOUS)& len(rows)}")
    print(f"-> {a.out}")
    miss = [r for r in rows if r[3] == "0"]
    if miss:
        print("MISSING PDFs (resolved name not found in archive):")
        for r in miss:
            print(f"  {r[0]}  ->  {r[1]}")

if __name__ == "__main__":
    main()
