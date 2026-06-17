import json
from pathlib import Path
base = Path(r"C:/Users/patolex/PatoLex-scratch/production-1933-vol1-chapters")
pre = json.loads((base / "_prefix_v2_backup.json").read_text(encoding="utf-8"))
post = json.loads((base / "parsed_acts_chaptered_v2.json").read_text(encoding="utf-8"))
def red(v2):
    return sum(1 for a in v2.get("confident_acts", []) if a.get("status") == "codes_redirect")
print(f"codes_redirect  PRE-FIX={red(pre)}  POST-FIX={red(post)}")
print(f"meta redirect   PRE-FIX={pre['_chaptered_meta'].get('codes_redirect')}  "
      f"POST-FIX={post['_chaptered_meta'].get('codes_redirect')}")
print(f"added_new       PRE-FIX={pre['_chaptered_meta'].get('added_new')}  "
      f"POST-FIX={post['_chaptered_meta'].get('added_new')}")
