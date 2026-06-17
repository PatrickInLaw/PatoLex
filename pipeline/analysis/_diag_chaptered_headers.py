"""READ-ONLY diagnostic for recover_chaptered: where do line-head CHAPTER headers go?
Counts headers under loose vs strict glyph rules, dumps which oracle chapters 1..N are
NOT in the emitted confident set, and shows the context of a sample of those misses.
Usage: python _diag_chaptered_headers.py <label> <oracleN>"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import importlib.util

ROOT = Path(config.path_for("data_root"))
label = sys.argv[1]
N = int(sys.argv[2])

# import the detector
_RC = Path(__file__).resolve().parents[1] / "ingest" / "recover_chaptered.py"
spec = importlib.util.spec_from_file_location("rc", str(_RC))
rc = importlib.util.module_from_spec(spec); spec.loader.exec_module(rc)

lines = rc.load_lines(label)

# LOOSE: any line starting (light noise) with a C-glyph + arabic numeral, case-insensitive
LOOSE = re.compile(r"^[^A-Za-z0-9]{0,4}[Cc][HhIiljUu][A-Za-z]{0,5}\.?[.,\s]+([0-9]{1,4})\b")
loose_nums = {}
for i, (p, ln, k) in enumerate(lines):
    m = LOOSE.match(ln.strip())
    if m:
        loose_nums.setdefault(int(m.group(1)), []).append(i)

strict = rc.detect_headers(lines)
strict_nums = {}
for (i, num, raw) in strict:
    strict_nums.setdefault(num, []).append(i)

conf, flag, meta = rc.process_label(label)
emitted_nums = {a["chapter_int"] for a in conf}

print(f"{label}: oracle N={N}")
print(f"  loose line-head headers (distinct arabic#): {len(loose_nums)}  total hits {sum(len(v) for v in loose_nums.values())}")
print(f"  strict detect_headers (distinct#): {len(strict_nums)}  total {len(strict)}")
print(f"  emitted confident distinct#: {len(emitted_nums)}")
print(f"  meta: {meta}")

# which 1..N are missing from emitted
missing = [n for n in range(1, N + 1) if n not in emitted_nums]
print(f"  missing from emitted (of 1..{N}): {len(missing)}")
# of those, how many DID appear as a loose header somewhere?
miss_loose = [n for n in missing if n in loose_nums]
print(f"    of missing, present as a LOOSE line-head header: {len(miss_loose)}")
print(f"    of missing, present as a STRICT header: {len([n for n in missing if n in strict_nums])}")
print(f"    sample missing-but-loose-present: {miss_loose[:30]}")

# dump context for a few missing-but-loose-present
print("\n  --- context of missing chapters that DO have a loose header ---")
for n in miss_loose[:8]:
    i = loose_nums[n][0]
    print(f"  [ch {n}] line {i} page {lines[i][0]}")
    for j in range(i, min(len(lines), i + 6)):
        print("      ", repr(lines[j][1])[:110])
