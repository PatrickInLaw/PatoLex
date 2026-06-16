"""_verify_brackets.py -- final precision verification of renumber_repair output.
For every repaired_position act: confirm assigned number is strictly between its recorded
bracketing anchors (lo_anchor < assigned < hi_anchor). Also re-confirm corpus-wide that no
two confident acts in a session share a number, and that parsed_acts_recovered.json files
were not modified (mtime is older than parsed_acts_repaired.json). Read-only."""
import json, glob, os
from collections import defaultdict

ROOT = r"C:\Users\patolex\PatoLex-scratch"


def main():
    bad_bracket = []
    n_rep = 0
    recovered_newer = []
    for fp in sorted(glob.glob(os.path.join(ROOT, "production-*", "parsed_acts_repaired.json"))):
        d = os.path.dirname(fp)
        lbl = os.path.basename(d)[len("production-"):]
        rec = os.path.join(d, "parsed_acts_recovered.json")
        if os.path.exists(rec) and os.path.getmtime(rec) > os.path.getmtime(fp) + 1:
            recovered_newer.append(lbl)  # recovered modified AFTER repaired -> unexpected
        data = json.load(open(fp, encoding="utf-8"))
        for a in data.get("confident_acts", []):
            if a.get("renumber_status") != "repaired_position":
                continue
            n_rep += 1
            r = a.get("_repair") or {}
            lo = r.get("lo_anchor"); hi = r.get("hi_anchor")
            asg = a.get("chapter_int_final")
            if lo is None or hi is None or not (lo < asg < hi):
                bad_bracket.append((lbl, lo, asg, hi))
    print(f"repaired_position acts checked: {n_rep}")
    print(f"acts NOT strictly between their bracketing anchors: {len(bad_bracket)}")
    for b in bad_bracket[:20]:
        print(f"  {b}")
    print(f"\nrecovered.json modified after repaired.json (should be none): "
          f"{recovered_newer if recovered_newer else 'NONE'}")

    # corpus-wide duplicate re-check straight off the written files (per session)
    by_sess = defaultdict(lambda: defaultdict(int))
    import importlib.util as u
    s = u.spec_from_file_location("ing", r"C:\github\PatoLex\pipeline\ingest\ingest_from_ocr.py")
    ing = u.module_from_spec(s); s.loader.exec_module(ing)
    for fp in sorted(glob.glob(os.path.join(ROOT, "production-*", "parsed_acts_repaired.json"))):
        lbl = os.path.basename(os.path.dirname(fp))[len("production-"):]
        sess = ing.LEGISLATURE_MAP.get(lbl, (lbl,))[0]
        data = json.load(open(fp, encoding="utf-8"))
        for a in data.get("confident_acts", []):
            ci = a.get("chapter_int_final")
            if isinstance(ci, int) and ci > 0:
                by_sess[sess][ci] += 1
    dup_sessions = {s: {n: c for n, c in nums.items() if c > 1}
                    for s, nums in by_sess.items()
                    if any(c > 1 for c in nums.values())}
    print(f"\nsessions with a duplicate confident chapter number: "
          f"{len(dup_sessions)}")
    for s, nums in list(dup_sessions.items())[:10]:
        print(f"  {s}: {nums}")


if __name__ == "__main__":
    main()
