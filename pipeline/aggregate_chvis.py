import os
RL = r"C:\Users\PatrickKolasinski\Documents\GitHub\patolex\docs\80_PROJECT_HISTORY\run-logs"
_RV = {"I":1,"V":5,"X":10,"L":50,"C":100,"D":500,"M":1000}
def to_int(s):
    s = (s or "").strip().strip(".,;:")
    if s.isdigit():
        return int(s)
    u = s.upper()
    if u and all(c in _RV for c in u):
        v = p = 0
        for c in reversed(u):
            cur = _RV[c]; v += cur if cur >= p else -cur; p = cur
        return v
    return None

son = {}
for n in (1, 2, 3):
    fp = os.path.join(RL, f"sub_chvis_part{n}.tsv")
    if not os.path.exists(fp):
        continue
    for ln in open(fp, encoding="utf-8"):
        p = ln.rstrip("\n").split("\t")
        if len(p) >= 3 and p[0].startswith("production-"):
            son[(p[0], p[1])] = p[2].strip()

mine = {}
for i, ln in enumerate(open(os.path.join(RL, "chapter_vision_resolved.tsv"), encoding="utf-8")):
    if i == 0:
        continue
    p = ln.rstrip("\n").split("\t")
    if len(p) >= 5:
        mine[(p[0], p[1])] = int(p[4])

print("=== OVERLAP: my hand-read vs Sonnet (trust check) ===")
agree = disagree = 0
for k, mv in mine.items():
    sp = son.get(k)
    sv = to_int(sp) if sp else None
    if sp is None:
        print(f"  {k}: mine={mv}  sonnet=<not in batch>")
        continue
    ok = (sv == mv)
    print(f"  {k}: mine={mv}  sonnet={sp}({sv})  {'OK' if ok else 'MISMATCH'}")
    agree += ok; disagree += (not ok)
print(f"  -> agree={agree} disagree={disagree}")

res = {}
for k, sp in son.items():
    v = to_int(sp)
    if v:
        res[k] = (v, sp)
for k, mv in mine.items():
    res[k] = (mv, "hand")
unp = [(k, son[k]) for k in son if to_int(son[k]) is None]
print(f"\ntotal resolved = {len(res)} of 63  | sonnet unparseable/UNKNOWN = {len(unp)}: {unp}")

with open(os.path.join(RL, "chapter_vision_final.tsv"), "w", encoding="utf-8") as f:
    f.write("vol\torder\tresolved_chapter\tsource\n")
    for (vol, order), (v, src) in sorted(res.items()):
        f.write(f"{vol}\t{order}\t{v}\t{src}\n")
print("wrote chapter_vision_final.tsv")
