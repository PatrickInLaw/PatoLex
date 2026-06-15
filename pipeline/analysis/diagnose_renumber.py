"""diagnose_renumber.py -- inspect the recovered file's renumber outcome: how acts
distribute across renumber_status, and for ambiguous inter-anchor gaps, whether the
mismatch is 'too few acts detected' (missing boundary) vs 'too many' (false split).
Usage: python -m analysis.diagnose_renumber <label> [<label> ...]"""
import sys, json
from collections import Counter
from pathlib import Path
import config
ROOT = Path(config.path_for("data_root"))

def main():
    allacts = []
    for label in sys.argv[1:]:
        p = ROOT / ("production-" + label) / "parsed_acts_recovered.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        for key in ("confident_acts", "flagged_acts"):
            for a in d[key]:
                allacts.append(a)
    # already per-volume sorted; rebuild session order by (volume, source_page)
    status = Counter(a.get("renumber_status") for a in allacts)
    origin = Counter(a.get("origin") for a in allacts)
    print("renumber_status:", dict(status))
    print("origin:", dict(origin))
    # confident by origin
    conf_by_origin = Counter(a.get("origin") for a in allacts if a.get("confident"))
    print("confident by origin:", dict(conf_by_origin))
    # ambiguous acts: how many have a plausible parsed number anyway?
    amb = [a for a in allacts if a.get("renumber_status") == "ambiguous"]
    amb_with_num = sum(1 for a in amb if 1 <= a.get("chapter_int_final", a.get("chapter_int",0)) <= 2300)
    print(f"ambiguous acts: {len(amb)}  of which have a plausible parsed chapter_int: {amb_with_num}")
    amb_with_date = sum(1 for a in amb if a.get("iso_date"))
    print(f"ambiguous acts with a parsed date: {amb_with_date}")

if __name__ == "__main__":
    main()
