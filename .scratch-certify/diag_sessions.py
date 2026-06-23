import sys, re, json, importlib.util
from pathlib import Path
REPO = Path(r"C:\github\PatoLex"); ROOT = Path(r"C:\Users\patolex\PatoLex-scratch")
sys.path.insert(0, str(REPO/"pipeline")); sys.path.insert(0, str(REPO/"pipeline"/"ingest"))
def lm(n,p):
    s=importlib.util.spec_from_file_location(n,str(p)); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
ing=lm("ingest_from_ocr", REPO/"pipeline"/"ingest"/"ingest_from_ocr.py")
LEG=ing.LEGISLATURE_MAP
# oracle
oracle={}
with open(REPO/"docs"/"30_SYSTEM_DESIGN"/"sources"/"ca_chapter_counts.tsv",encoding="utf-8") as f:
    f.readline()
    for line in f:
        p=line.rstrip("\n").split("\t")
        if len(p)>=4 and p[3].strip().isdigit(): oracle[p[0].strip()]=int(p[3])
# early labels
for d in sorted(ROOT.glob("production-18*")):
    label=d.name[len("production-"):]
    yr=int(re.match(r"(\d{4})",label).group(1)) if re.match(r"(\d{4})",label) else 0
    if yr>=1880: continue
    sk = LEG[label][0] if label in LEG else None
    N = oracle.get(sk) if sk else None
    print(f"{label:<24} inLEG={label in LEG} sess={sk!r:<28} N={N}")
print("--- sample oracle keys ---")
for k in list(oracle)[:6]: print(repr(k), oracle[k])
print("--- early oracle keys ---")
for k in oracle:
    if re.match(r"18[5-7]\d", k): print(repr(k), oracle[k])
