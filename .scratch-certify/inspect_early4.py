import json, os, re
from collections import Counter
root = r'C:\Users\patolex\PatoLex-scratch'

HDR_RE = re.compile(r'^\s*\.?\s*CHAP(?:TER|T\.?|\.)?\s*([0-9IVXLC]{1,6})\b', re.I | re.M)
def roman_to_int(s):
    s=s.upper(); vals={'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}
    if not s or not all(c in vals for c in s): return None
    t=0;p=0
    for c in reversed(s):
        v=vals[c]; t+= -v if v<p else v; p=max(p,v)
    return t if t>0 else None
def hdr_num(a):
    m=HDR_RE.search((a.get('text') or '')[:160])
    if not m: return None
    tok=m.group(1)
    return int(tok) if tok.isdigit() else roman_to_int(tok)

for vol in ('1850','1852','1853','1854','1860','1862','1865-66'):
    fp=os.path.join(root,'production-'+vol,'parsed_acts_early_v2.json')
    if not os.path.exists(fp): continue
    d=json.load(open(fp,encoding='utf-8'))
    enact=[a for a in d.get('flagged_acts',[]) if a.get('has_enact')]
    ci=[a.get('chapter_int') for a in enact]
    cnt=Counter(c for c in ci if c)
    uniq_ci=sum(1 for c in ci if c and cnt[c]==1)
    # agreement: where header numeral present, does it equal chapter_int?
    agree=disagree=hdr_missing=0
    for a in enact:
        c=a.get('chapter_int'); h=hdr_num(a)
        if not c: continue
        if h is None: hdr_missing+=1
        elif h==c: agree+=1
        else: disagree+=1
    print(f'{vol}: enact={len(enact)} ci_present={sum(1 for c in ci if c)} ci_unique={uniq_ci} | hdr_agree={agree} hdr_disagree={disagree} hdr_missing={hdr_missing}')
