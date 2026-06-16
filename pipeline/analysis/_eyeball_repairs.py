"""_eyeball_repairs.py -- pull a sample of repaired_position OVERRIDE acts and show their
immediate page-order neighbors (prev/next confident act + chapter number) so a human can
eyeball that the assigned number genuinely fits the slot. Read-only."""
import json, glob, os, sys
sys.path.insert(0, r"C:\github\PatoLex\pipeline")
import importlib.util as u
_s = u.spec_from_file_location("ing", r"C:\github\PatoLex\pipeline\ingest\ingest_from_ocr.py")
ing = u.module_from_spec(_s); _s.loader.exec_module(ing)

ROOT = r"C:\Users\patolex\PatoLex-scratch"

def main():
    want = ["1909", "1945-vol1-chapters", "1963-vol1-63chapters", "1931-vol1-chapters",
            "1971-vol1-chapters"]
    for lbl in want:
        fp = os.path.join(ROOT, "production-" + lbl, "parsed_acts_repaired.json")
        if not os.path.exists(fp):
            continue
        data = json.load(open(fp, encoding="utf-8"))
        acts = sorted(data.get("confident_acts", []), key=lambda a: a.get("source_page", 0))
        print(f"\n=== {lbl} (showing up to 4 OVERRIDE repairs with neighbors) ===")
        shown = 0
        for i, a in enumerate(acts):
            if a.get("renumber_status") != "repaired_position":
                continue
            rep = a.get("_repair") or {}
            if rep.get("from") == a.get("chapter_int_final"):
                continue  # confirmation, not override
            prev_a = acts[i-1] if i > 0 else None
            next_a = acts[i+1] if i+1 < len(acts) else None
            pn = prev_a.get("chapter_int_final") if prev_a else None
            nn = next_a.get("chapter_int_final") if next_a else None
            print(f"  page {a.get('source_page')}: prev_ch={pn}  "
                  f"[REPAIRED from {rep.get('from')} -> {a.get('chapter_int_final')}]  "
                  f"next_ch={nn}")
            print(f"      title: {(a.get('title') or '')[:75]}")
            shown += 1
            if shown >= 4:
                break

if __name__ == "__main__":
    main()
