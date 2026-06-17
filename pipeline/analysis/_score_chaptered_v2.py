"""READ-ONLY biennium-correct BEFORE/AFTER scorer for the chaptered recovery.
For each label: distinct in-range [1..N] chapter numbers from
  BEFORE = parsed_acts_recovered.json (confident_acts)
  AFTER  = parsed_acts_chaptered_v2.json (confident_acts)
vs the oracle N for that label's session (start_year,type) from ca_chapter_counts.tsv.
Also reports redirect-stub count and the resolution/no-anact exclusions (the part of the
'gap' that is NOT real statutes). Usage: python _score_chaptered_v2.py <label> [label...]"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config

ROOT = Path(config.path_for("data_root"))
ORACLE_TSV = Path(__file__).resolve().parents[2] / "docs" / "30_SYSTEM_DESIGN" / "sources" / "ca_chapter_counts.tsv"

def parse_type(s):
    l = s.lower()
    if "firstextra" in l or "1stextra" in l or "extra1" in l: return "extra1"
    if "secondextra" in l or "extra2" in l: return "extra2"
    if "thirdextra" in l or "extra3" in l: return "extra3"
    if "extra" in l: return "extra1"
    return "regular"

def parse_session_year(label):
    m = re.search(r"(\d{2})chapters", label.lower())
    if m: return 1900 + int(m.group(1))
    m = re.match(r"(\d{4})", label)
    return int(m.group(1)) if m else 0

# oracle (year,type)->N
oracle = {}
with open(ORACLE_TSV, encoding="utf-8") as f:
    f.readline()
    for line in f:
        p = line.rstrip("\n").split("\t")
        if len(p) < 4: continue
        y = int(re.match(r"(\d{4})", p[0]).group(1))
        oracle[(y, p[2].strip())] = int(p[3])

def nums(path, listname="confident_acts"):
    if not path.exists(): return None
    d = json.load(open(path, encoding="utf-8"))
    out = set()
    for a in d.get(listname, []):
        ci = a.get("chapter_int")
        if isinstance(ci, int) and ci > 0:
            out.add(ci)
    return out

print(f"{'label':<26}{'N':>6}{'before':>8}{'b%':>6}{'after':>8}{'a%':>6}{'redir':>7}{'reso':>6}{'noanact':>8}")
for label in sys.argv[1:]:
    key = (parse_session_year(label), parse_type(label))
    N = oracle.get(key, 0)
    before = nums(ROOT / ("production-" + label) / "parsed_acts_recovered.json")
    after_path = ROOT / ("production-" + label) / "parsed_acts_chaptered_v2.json"
    after = nums(after_path)
    meta = {}
    if after_path.exists():
        meta = json.load(open(after_path, encoding="utf-8")).get("_chaptered_meta", {})
    b = len({c for c in (before or set()) if 1 <= c <= N})
    a = len({c for c in (after or set()) if 1 <= c <= N})
    bp = 100.0*b/N if N else 0
    ap = 100.0*a/N if N else 0
    print(f"{label:<26}{N:>6}{b:>8}{bp:>5.0f}%{a:>8}{ap:>5.0f}%"
          f"{meta.get('codes_redirect',0):>7}{meta.get('excluded_resolutions',0):>6}"
          f"{meta.get('excluded_no_anact',0):>8}")
