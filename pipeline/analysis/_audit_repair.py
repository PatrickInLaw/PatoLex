"""_audit_repair.py -- adversarial audit of renumber_repair output. Read-only.
Breaks the 'repaired_position' acts into honest buckets so we can see what the repair
actually did and whether it is trustworthy:
  A) from == assigned  : repair assigned the SAME number the act already carried
                         (prev_status was a flagged/ambiguous numeral that turned out to
                         be the only open slot). NOT a renumber -- a confirmation.
  B) from != assigned  : repair OVERRODE the act's prior numeral with a positional slot.
For bucket B, compare assigned vs the act's own readable printed header (chapter_raw /
leading CHAPTER NN). If a CLEAN header disagrees with the assigned number, that's a risk.
"""
import json, glob, os, re, sys
sys.path.insert(0, r"C:\github\PatoLex\pipeline")
from ingest import renumber_repair as rr

ROOT = r"C:\Users\patolex\PatoLex-scratch"
HDR = re.compile(r"^\s*CHAP(?:TER|T\.?|\.)?\s*([0-9]{1,4})\s*[.,;:]?\s*$", re.I | re.M)
ORACLE = rr.load_oracle()
import importlib.util as _u
_s = _u.spec_from_file_location("ing", r"C:\github\PatoLex\pipeline\ingest\ingest_from_ocr.py")
_ing = _u.module_from_spec(_s); _s.loader.exec_module(_ing)

def oracle_for(lbl):
    sess = _ing.LEGISLATURE_MAP.get(lbl, (None,))[0]
    return ORACLE.get(sess)


def clean_witness(a):
    raw = str(a.get("chapter_raw", "")).strip()
    if re.fullmatch(r"[0-9]{1,4}", raw):
        return int(raw)
    m = HDR.search(a.get("text", "")[:400])
    if m:
        return int(m.group(1))
    return None


def main():
    same = override = 0
    prev_status_counts = {}
    override_header_disagree = []
    override_header_agree = override_no_header = 0
    for fp in sorted(glob.glob(os.path.join(ROOT, "production-*", "parsed_acts_repaired.json"))):
        lbl = os.path.basename(os.path.dirname(fp))[len("production-"):]
        data = json.load(open(fp, encoding="utf-8"))
        for a in data.get("confident_acts", []):
            if a.get("renumber_status") != "repaired_position":
                continue
            rep = a.get("_repair") or {}
            frm = rep.get("from")
            asg = a.get("chapter_int_final")
            ps = rep.get("prev_status")
            prev_status_counts[ps] = prev_status_counts.get(ps, 0) + 1
            if frm == asg:
                same += 1
            else:
                override += 1
                N = oracle_for(lbl)
                w = clean_witness(a)
                # only an IN-RANGE clean header is a trustworthy witness; an out-of-range
                # numeral is OCR-inflated garble (the very reason the act was flagged).
                if w is not None and N is not None and not (1 <= w <= N):
                    w = None
                if w is None:
                    override_no_header += 1
                elif w == asg:
                    override_header_agree += 1
                elif w == frm:
                    # in-range header agrees with the ORIGINAL numeral we overrode -> RISK
                    override_header_disagree.append(
                        (lbl, frm, asg, w, (a.get("title") or "")[:55]))
                else:
                    pass
    print(f"repaired_position total acts:")
    print(f"  same (from==assigned, confirmation only): {same}")
    print(f"  override (from!=assigned, true renumber):  {override}")
    print(f"\n  prev_status of repaired acts: {prev_status_counts}")
    print(f"\n  among OVERRIDES:")
    print(f"    header agrees with NEW assigned:     {override_header_agree}")
    print(f"    header agrees with OLD (overrode!):  {len(override_header_disagree)}")
    print(f"    no clean header / garbled:           {override_no_header}")
    print(f"\n  OVERRIDE-vs-OWN-HEADER conflicts (risk sample):")
    for r in override_header_disagree[:40]:
        print(f"    {r[0]:<22} overrode {r[1]} -> {r[2]} but own header says {r[3]} | {r[4]}")


if __name__ == "__main__":
    main()
