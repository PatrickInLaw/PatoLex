"""throwaway: diagnose the 1865-66 over-extraction. Run the CONSENSUS-only
recover_early detector and report: total acts, distinct chapter_int, max
chapter_int, count of form A vs B, and a sample of the act TITLES so we can see
whether the extras are resolutions/amendments/TOC echoes or real acts."""
import json, sys
from pathlib import Path
import importlib.util
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config

_RE = Path(__file__).resolve().parents[1] / "ingest" / "recover_early.py"
spec = importlib.util.spec_from_file_location("re_early", str(_RE))
re_early = importlib.util.module_from_spec(spec)
spec.loader.exec_module(re_early)

label = sys.argv[1] if len(sys.argv) > 1 else "1865-66"
lines = re_early.load_lines(label)
starts = re_early.detect_starts(lines)
acts = []
for k, (si, tok, form) in enumerate(starts):
    ei = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
    rec = re_early.build_act(lines, si, ei, tok, form, label, k)
    if len(rec["text"]) < re_early.SANITY_MIN_TEXT:
        continue
    if not (rec["has_enact"] or rec["has_approved"]):
        continue
    acts.append(rec)

ints = [a["chapter_int"] for a in acts]
distinct = sorted(set(i for i in ints if i > 0))
print(f"label={label} acts={len(acts)} formA={sum(1 for a in acts if a['form']=='A')} "
      f"formB={sum(1 for a in acts if a['form']=='B')}")
print(f"distinct chapter_int>0 = {len(distinct)}  max={max(distinct) if distinct else 0}")
print(f"zero/unparsed numerals = {sum(1 for i in ints if i==0)}")
# how many titles look like resolutions / amendments / concurrent
import re as _re
res = sum(1 for a in acts if _re.search(r"resolution|concurrent|memorial|joint res", a["title"], _re.I))
print(f"titles matching resolution/concurrent/memorial = {res}")
print("\n--- sample titles (every 25th act) ---")
for a in acts[::25]:
    print(f"  ch={a['chapter_int']:>5} form={a['form']} pg={a['source_page']} :: {a['title'][:90]}")
