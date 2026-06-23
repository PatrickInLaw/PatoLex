import sys, importlib.util
from pathlib import Path
REPO=Path(r"C:\github\PatoLex"); ROOT=Path(r"C:\Users\patolex\PatoLex-scratch")
spec=importlib.util.spec_from_file_location("cc", r"C:\Users\patolex\PatoLex-scratch\_certify_chapters.py")
import re
cc=importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
oracle=cc.load_oracle()
miss=[]
for d in sorted(ROOT.glob("production-*")):
    label=d.name[len("production-"):]
    p,name=cc.best_parse_path(d)
    if p is None: continue
    N=cc.oracle_N(label, oracle)
    if N is None:
        miss.append(label)
print("volumes with NO oracle N (%d):" % len(miss))
for m in miss: print("  ", m)
# early-era spot
for lbl in ("1850","1854","1863-64","1865-66","1873-74-code","1877-78"):
    print(lbl, "->", cc.oracle_N(lbl, oracle))
