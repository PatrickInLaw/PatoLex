"""_spotcheck_repair.py -- precision spot-check of renumber_repair output. Read-only.
For every act repaired by renumber_repair (renumber_status == 'repaired_position'),
compare the ASSIGNED number against any chapter numeral the act's own text reveals:
  * chapter_raw (the numeral OCR pulled from the printed CHAPTER header), and
  * a re-scan of the act text for a leading 'CHAPTER NN' line.
We tally agree / disagree / no-witness. A DISAGREE where the witness is a clean readable
header is a correctness RISK to surface. Not committed (scratch)."""
import json, glob, os, re

ROOT = r"C:\Users\patolex\PatoLex-scratch"
HDR = re.compile(r"^\s*CHAP(?:TER|T\.?|\.)?\s*([0-9]{1,4})\s*[.,;:]?\s*$", re.I | re.M)


def witness(a):
    # 1) chapter_raw numeral if clean
    raw = str(a.get("chapter_raw", "")).strip()
    m = re.fullmatch(r"[0-9]{1,4}", raw)
    if m:
        return int(raw)
    # 2) leading CHAPTER NN in text (first 400 chars)
    m = HDR.search(a.get("text", "")[:400])
    if m:
        return int(m.group(1))
    return None


def main():
    agree = disagree = nowit = 0
    samples = []
    disagrees = []
    for fp in sorted(glob.glob(os.path.join(ROOT, "production-*", "parsed_acts_repaired.json"))):
        lbl = os.path.basename(os.path.dirname(fp))[len("production-"):]
        data = json.load(open(fp, encoding="utf-8"))
        for a in data.get("confident_acts", []):
            if a.get("renumber_status") != "repaired_position":
                continue
            assigned = a.get("chapter_int_final")
            w = witness(a)
            rep = a.get("_repair", {})
            row = (lbl, rep.get("from"), assigned, w,
                   (a.get("title") or "")[:60])
            if w is None:
                nowit += 1
            elif w == assigned:
                agree += 1
                if len(samples) < 15:
                    samples.append(("AGREE",) + row)
            else:
                disagree += 1
                disagrees.append(row)
    print(f"repaired acts: agree={agree} disagree={disagree} no_witness={nowit} "
          f"total={agree+disagree+nowit}")
    print("\n-- sample AGREE (witness == assigned) --")
    for s in samples:
        print(f"  {s[0]} {s[1]:<20} from={s[2]} ->{s[3]} wit={s[4]} | {s[5]}")
    print(f"\n-- DISAGREE (witness != assigned): {len(disagrees)} --")
    for r in disagrees[:40]:
        print(f"  {r[0]:<22} from={r[1]} assigned={r[2]} witness={r[3]} | {r[4]}")


if __name__ == "__main__":
    main()
