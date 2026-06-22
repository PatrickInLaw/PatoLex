"""Normalize status strings across all per-volume parsed_acts_visual.json draft files so the
scoreboard counts every genuine recovery and treats only real gaps as gaps. ADDITIVE to the data
in the sense that NO chapter record is added/removed and no title/page is changed -- only the
`status` label is canonicalized and `_visual_meta` recomputed. Draft artifacts only; never touches
the DB or any parsed/merged/certified file.

Canonical status vocabulary (3 recovered tiers + 2 not-recovered):
  image_verified        -- printed number read off the scan (highest confidence)
  ocr_text_verified     -- recovered via OCR/multi-engine, no readable image header
  legislative_gap       -- number was NEVER enacted (printed volume skips it) -> reduces effN
  not_found_needs_reocr -- act EXISTS but pages are physically un-scanned -> real residual, re-scan

Mappings applied:
  'verified'     -> 'image_verified'      (agent shorthand; all had printed_number_confirmed=True)
  'ocr_verified' -> 'ocr_text_verified'   (agent shorthand for tier-2)
  explicit per-chapter fixes (see FIXES): a legislative_gap that is really a scan-gap (act exists).

Run with --apply to write; default is a DRY RUN that only reports what would change.
"""
import json, glob, os, sys

SCRATCH = r"C:\PatoLex-scratch"
APPLY = "--apply" in sys.argv

STATUS_MAP = {
    "verified": "image_verified",
    "ocr_verified": "ocr_text_verified",
}
# Explicit per-(dir-substring, chapter_int) reclassifications with justification.
FIXES = {
    ("production-1972-vol1-chapters", 517): "not_found_needs_reocr",  # act exists; title pages in scan gap pp896-897
}
RECOVERED = ("image_verified", "ocr_text_verified")

def chap_int(a):
    v = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

changed_files = 0
changed_records = 0
for d in sorted(glob.glob(os.path.join(SCRATCH, "production-*"))):
    p = os.path.join(d, "parsed_acts_visual.json")
    if not os.path.exists(p):
        continue
    try:
        j = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        print(f"  SKIP (parse fail) {os.path.basename(d)}: {e}")
        continue
    acts = j.get("recovered_acts", [])
    base = os.path.basename(d)
    file_changes = []
    for a in acts:
        if not isinstance(a, dict):
            continue
        old = a.get("status")
        new = old
        ci = chap_int(a)
        # explicit fix takes precedence
        for (sub, ch), tgt in FIXES.items():
            if sub in base and ci == ch:
                new = tgt
        if new == old and old in STATUS_MAP:
            new = STATUS_MAP[old]
            # guard (Hans MINOR-3): only promote to image_verified when the printed number
            # was actually confirmed; otherwise keep it in the tier-2 ocr_text bucket.
            if new == "image_verified" and not a.get("printed_number_confirmed"):
                new = "ocr_text_verified"
        if new != old:
            file_changes.append((ci, old, new))
            if APPLY:
                a["status"] = new
    if file_changes:
        changed_files += 1
        changed_records += len(file_changes)
        print(f"{base}: {len(file_changes)} record(s)")
        for ci, old, new in file_changes:
            print(f"    ch{ci}: {old!r} -> {new!r}")
        if APPLY:
            meta = j.setdefault("_visual_meta", {})
            recs = [a for a in acts if isinstance(a, dict)]
            meta["verified"] = sum(1 for a in recs if a.get("status") in RECOVERED)
            meta["legislative_gap"] = sum(1 for a in recs if a.get("status") == "legislative_gap")
            meta["not_found"] = sum(1 for a in recs if a.get("status") == "not_found_needs_reocr")
            json.dump(j, open(p, "w", encoding="utf-8"), indent=1)

print(f"\n{'APPLIED' if APPLY else 'DRY RUN'}: {changed_records} record(s) in {changed_files} file(s)")
if not APPLY:
    print("Re-run with --apply to write changes.")
