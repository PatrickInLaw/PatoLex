import importlib.util, json, os, random
spec=importlib.util.spec_from_file_location("cc", r"C:\Users\patolex\PatoLex-scratch\_certify_chapters.py")
cc=importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
ex=json.load(open(r"C:\Users\patolex\PatoLex-scratch\_certify_audit\audit_examples.json",encoding="utf-8"))
random.seed(7)
# stratify: sample R1 and R2 across distinct volumes/eras
r1=[e for e in ex if e["rule"]=="R1"]
r2=[e for e in ex if e["rule"]=="R2"]
# pick spread across labels
def spread(items, k):
    bylabel={}
    for e in items: bylabel.setdefault(e["label"],[]).append(e)
    out=[]
    labels=list(bylabel)
    random.shuffle(labels)
    i=0
    while len(out)<k and labels:
        lbl=labels[i%len(labels)]
        if bylabel[lbl]:
            out.append(bylabel[lbl].pop())
        else:
            labels.remove(lbl); continue
        i+=1
    return out
sample = spread(r1,20)+spread(r2,7)
print("SPOTCHECK n=",len(sample))
for e in sample:
    print(f'--- {e["label"]} rule={e["rule"]} assigned_chapter={e["to"]} page={e["page"]}')
    print('   head:', e["head"])
