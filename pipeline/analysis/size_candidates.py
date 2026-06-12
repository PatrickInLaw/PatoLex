"""Size the SymSpell candidate worklist for Sonnet: distinct (token->candidate) TYPES and their
occurrence counts, tiered by corpus frequency. Reads the autocorrect audit (es1/es2 rows)."""
import glob, os
from collections import Counter
import config
AUD = config.path_for("cascade_dir", "audit")
pair_occ = Counter()      # (token, candidate, dist) -> occurrences
for fp in glob.glob(os.path.join(AUD, "*.autocorrect.tsv")):
    for line in open(fp, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 4 and p[1] in ("autocorrect_es1", "autocorrect_es2"):
            pair_occ[(p[2], p[3], p[1][-2:])] += 1
total_types = len(pair_occ)
total_occ = sum(pair_occ.values())
# tier by occurrence count of the (token->candidate) pair
def tier(c): return "freq>=10" if c >= 10 else ("2-9" if c >= 2 else "singleton")
tt = Counter(); to = Counter()
for k, c in pair_occ.items():
    tt[tier(c)] += 1; to[tier(c)] += c
s1_types = sum(1 for k in pair_occ if k[2] == "s1")
s2_types = sum(1 for k in pair_occ if k[2] == "s2")
print(f"distinct candidate (token->fix) TYPES: {total_types:,}  ({s1_types:,} s1 / {s2_types:,} s2)")
print(f"total occurrences: {total_occ:,}")
print("by pair-frequency tier (distinct types / occ):")
for t in ("freq>=10", "2-9", "singleton"):
    print(f"  {t:10s} {tt[t]:7,} types / {to[t]:8,} occ")
# rough est: a Sonnet adjudication row ~ token + fix + 2 short contexts ~ 60 tok in, ~15 tok out
for label, n in (("freq>=10 only", tt["freq>=10"]), ("freq>=2", tt["freq>=10"] + tt["2-9"]), ("ALL types", total_types)):
    print(f"est Sonnet tokens [{label}, {n:,} types @ ~75 tok/type]: ~{n*75/1000:.0f}K")
