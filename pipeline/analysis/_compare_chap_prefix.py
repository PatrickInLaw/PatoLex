"""Read-only: compare the PRE-FIX v2 backup to the POST-FIX v2 for 1933 to PROVE
the CRITICAL-B1 fix changed behavior -- i.e. how many newly-added confident acts in
the PRE-FIX output had a chapter number that already existed in the BEFORE
FLAGGED set (and would now be correctly suppressed). Writes nothing."""
import json
from pathlib import Path
base = Path(r"C:/Users/patolex/PatoLex-scratch/production-1933-vol1-chapters")

def ints(seq):
    return {a["chapter_int"] for a in seq
            if isinstance(a.get("chapter_int"), int) and a["chapter_int"] > 0}

rec = json.loads((base / "parsed_acts_recovered.json").read_text(encoding="utf-8"))
pre = json.loads((base / "_prefix_v2_backup.json").read_text(encoding="utf-8"))
post = json.loads((base / "parsed_acts_chaptered_v2.json").read_text(encoding="utf-8"))

before_conf = ints(rec.get("confident_acts", []))
before_flag = ints(rec.get("flagged_acts", []))
flag_only = before_flag - before_conf   # numbers present ONLY as flagged-before

def added(v2):
    return [a for a in v2.get("confident_acts", [])
            if a.get("origin") == "chaptered_v2"
            and a.get("status") in ("chaptered_new", "codes_redirect")]

pre_added = added(pre)
post_added = added(post)
pre_collide_flag = [a for a in pre_added if a.get("chapter_int") in flag_only]
post_collide_flag = [a for a in post_added if a.get("chapter_int") in flag_only]

print(f"before_confident_nums={len(before_conf)} before_flagged_nums={len(before_flag)} "
      f"flagged-ONLY(not in confident)={len(flag_only)}")
print(f"PRE-FIX  added_confident={len(pre_added)}  of which collide w/ flagged-only BEFORE = {len(pre_collide_flag)}")
print(f"POST-FIX added_confident={len(post_added)} of which collide w/ flagged-only BEFORE = {len(post_collide_flag)}")
if pre_collide_flag:
    print("  PRE-FIX leaked these flagged-before chapters as NEW confident:",
          sorted(a['chapter_int'] for a in pre_collide_flag)[:30])
