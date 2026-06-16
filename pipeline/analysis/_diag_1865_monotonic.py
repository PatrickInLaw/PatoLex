"""throwaway: is 1865-66 a real >280 sequence or duplicate/over-extraction?
Run the consensus detector, list distinct chapter_int in order, report the
longest monotonic run and any duplicates, and dump the SURYA clean headers
beyond numeral 280 with their page so we can judge if they're real acts."""
import json, sys, re
from pathlib import Path
import importlib.util
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
ROOT = Path(config.path_for("data_root"))

_RE = Path(__file__).resolve().parents[1] / "ingest" / "recover_early.py"
spec = importlib.util.spec_from_file_location("re_early", str(_RE))
re_early = importlib.util.module_from_spec(spec)
spec.loader.exec_module(re_early)

label = "1865-66"
# count clean surya headers + their numerals directly
p = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
d = json.loads(p.read_text(encoding="utf-8"))
FORMA = re_early.FORMA
nums = []
for k in sorted(d, key=lambda x: int(x)):
    for ln in (d[k].get("surya_text") or "").split("\n"):
        s = ln.strip()
        ma = FORMA.match(s)
        if ma and re_early.numeral_ok(ma.group(2)):
            title = ma.group(3)
            am = re_early.AN_ACT_STRICT.search(title) or re_early.AN_ACT_FUZZY.search(title)
            if am and not re_early._quoted_before(title, am):
                v = re_early.parse_chapter_numeral(ma.group(2))
                nums.append((int(k), v, s[:70]))

vals = [v for _, v, _ in nums if v > 0]
print(f"surya clean headers={len(nums)}  with numeral>0={len(vals)}")
print(f"distinct numerals={len(set(vals))}  min={min(vals)} max={max(vals)}")
dups = sorted([v for v in set(vals) if vals.count(v) > 1])
print(f"duplicate numerals (count>1): {len(dups)} -> {dups[:30]}")
# how many distinct numerals fall in 1..280 vs >280
le280 = len(set(v for v in vals if 1 <= v <= 280))
gt280 = len(set(v for v in vals if v > 280))
print(f"distinct numerals 1..280 = {le280}   distinct >280 = {gt280}")
print("\n--- sample surya headers with numeral >280 (page, numeral, line) ---")
shown = 0
for pg, v, s in nums:
    if v > 280:
        print(f"  pg{pg:>4} n={v:>4} :: {s}")
        shown += 1
        if shown >= 20:
            break
