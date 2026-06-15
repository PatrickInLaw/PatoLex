"""header_witness.py -- strict precision check: among 'filled' acts, find those whose
TEXT STARTS with a real 'CHAPTER NN' header and compare that printed number to the
positionally-assigned number. This is the only trustworthy independent witness (body-text
'Chapter NNN' references are excluded). Disagreement here = a genuine renumber error.
Usage: python -m analysis.header_witness <label> [<label> ...]"""
import sys, re, json
from pathlib import Path
import config
ROOT = Path(config.path_for("data_root"))

def main():
    acts = []
    for label in sys.argv[1:]:
        d = json.loads((ROOT / ("production-" + label) / "parsed_acts_recovered.json").read_text(encoding="utf-8"))
        acts += d["confident_acts"]
    agree = disagree = 0
    ex = []
    for a in acts:
        if a.get("renumber_status") != "filled":
            continue
        head = a.get("text", "")[:40]
        m = re.match(r"\s*CHAP\w*\.?\s*([0-9]{1,4})\b", head, re.I)
        if not m:
            continue
        wit = int(m.group(1))
        asg = a["chapter_int"]
        if wit == asg:
            agree += 1
        else:
            disagree += 1
            if len(ex) < 25:
                ex.append((asg, wit, a.get("source_page")))
    print(f"filled acts with a leading CHAPTER-NN header witness: agree={agree} disagree={disagree}")
    for asg, wit, pg in ex:
        print(f"  assigned={asg} header_says={wit} p{pg}")

if __name__ == "__main__":
    main()
