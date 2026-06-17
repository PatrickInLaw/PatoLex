"""READ-ONLY precision check for parsed_acts_chaptered_v2.json.
(1) assert 0 duplicate chapter_int in confident_acts.
(2) sample N NEW additions (status in chaptered_new/codes_redirect) and dump
    chapter#, status, title, source_page, has_an_act/enact/approval/redirect so a human
    can verify each is a REAL distinct line-head act (not a body cite/resolution/false split).
Usage: python _precision_chaptered_v2.py <label> [n_sample]"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from collections import Counter

ROOT = Path(config.path_for("data_root"))
label = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 25
p = ROOT / ("production-" + label) / "parsed_acts_chaptered_v2.json"
d = json.load(open(p, encoding="utf-8"))
conf = d["confident_acts"]

nums = [a["chapter_int"] for a in conf if isinstance(a.get("chapter_int"), int) and a["chapter_int"] > 0]
dups = [k for k, v in Counter(nums).items() if v > 1]
print(f"{label}: confident={len(conf)} distinct#={len(set(nums))} DUPLICATE#={len(dups)} {dups[:20]}")
print("status counts:", Counter(a.get("status") for a in conf))

added = [a for a in conf if a.get("status") in ("chaptered_new", "codes_redirect")]
added.sort(key=lambda a: a["chapter_int"])
step = max(1, len(added) // n)
sample = added[::step][:n]
print(f"\n--- {len(sample)} sampled NEW additions (of {len(added)}) ---")
for a in sample:
    print(f"ch {a['chapter_int']:>4} [{a.get('status')}] p{a.get('source_page')} "
          f"an_act={int(a.get('has_an_act',0))} enact={int(a.get('has_enact',0))} "
          f"appr={int(a.get('has_approval',0))} redir={int(a.get('has_redirect_note',0))} "
          f"raw={a.get('chapter_raw')!r}")
    print(f"      title: {a.get('title','')[:140]}")
