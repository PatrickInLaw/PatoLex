import importlib.util, json, os, glob
from pathlib import Path
spec=importlib.util.spec_from_file_location("cc", r"C:\Users\patolex\PatoLex-scratch\_certify_chapters.py")
cc=importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
root=Path(r"C:\Users\patolex\PatoLex-scratch")
oracle=cc.load_oracle()

# 1) volumes discovered vs certified written; identify the 14 without certified
disc=[]; nocert=[]; empty=[]
for d in sorted(root.glob("production-*")):
    label=d.name[len("production-"):]
    p,name=cc.best_parse_path(d)
    if p is None: continue
    disc.append(label)
    cf=d/"parsed_acts_certified.json"
    data=json.load(open(p,encoding="utf-8"))
    nacts=len(data.get("confident_acts",[]))+len(data.get("flagged_acts",[]))
    if nacts==0: empty.append((label,name))
    if not cf.exists(): nocert.append((label,name,nacts))
print("discovered:",len(disc),"no_certified_file:",len(nocert),"empty_parses:",len(empty))
print("empty:",empty)
print("nocert:",nocert)

# 2) GLOBAL precision: across ALL certified files, no duplicate confident chapter within a session
from collections import defaultdict
sess_conf=defaultdict(list)
for cf in root.glob("production-*/parsed_acts_certified.json"):
    label=cf.parent.name[len("production-"):]
    sk=cc.session_key(label) or ("__noleg__"+label)
    data=json.load(open(cf,encoding="utf-8"))
    for a in data.get("confident_acts",[]):
        sess_conf[sk].append((cc.assigned(a), label, a.get("source_page"), bool(a.get("_certify"))))
dups=0; dup_introduced=0
for sk,items in sess_conf.items():
    seen={}
    for n,label,pg,intro in items:
        if n in seen:
            dups+=1
            if intro or seen[n][2]: dup_introduced+=1
        else:
            seen[n]=(label,pg,intro)
print("GLOBAL confident dup pairs within sessions:",dups,"of which involve a certified act:",dup_introduced)

# 3) certified-act count present in output (confident with _certify stamp)
ncert=0; r1=0; r2=0
for cf in root.glob("production-*/parsed_acts_certified.json"):
    data=json.load(open(cf,encoding="utf-8"))
    for a in data.get("confident_acts",[]):
        c=a.get("_certify")
        if c:
            ncert+=1
            if c.get("rule","").startswith("R1"): r1+=1
            elif c.get("rule","").startswith("R2"): r2+=1
print("certified stamps in output:",ncert,"R1",r1,"R2",r2)
