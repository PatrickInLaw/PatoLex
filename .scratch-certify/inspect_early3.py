import json, os, re
from collections import Counter
root = r'C:\Users\patolex\PatoLex-scratch'

HDR_RE = re.compile(r'^\s*\.?\s*CHAP(?:TER|T\.?|\.)?\s*([0-9IVXLC]{1,6})\b', re.I | re.M)

def roman_to_int(s):
    s = s.upper()
    vals = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}
    if not all(ch in vals for ch in s): return None
    total = 0; prev = 0
    for ch in reversed(s):
        v = vals[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total if total>0 else None

def clean_own_numeral(a):
    """clean in-range own numeral: prefer bare-digit chapter_raw; else CHAPTER header (digit or roman) in first 120 chars of text."""
    raw = str(a.get('chapter_raw', a.get('chapter',''))).strip()
    if re.fullmatch(r'[1-9][0-9]{0,3}', raw):
        return int(raw)
    m = HDR_RE.search((a.get('text') or '')[:160])
    if m:
        tok = m.group(1)
        if tok.isdigit():
            return int(tok)
        return roman_to_int(tok)
    return None

for vol in ('1850','1852','1853','1854','1860','1862','1865-66'):
    fp = os.path.join(root, 'production-'+vol, 'parsed_acts_early_v2.json')
    if not os.path.exists(fp): continue
    d = json.load(open(fp, encoding='utf-8'))
    flag = d.get('flagged_acts', [])
    enact = [a for a in flag if a.get('has_enact')]
    # numeral from header for enact acts
    nums = [clean_own_numeral(a) for a in enact]
    have = [n for n in nums if n]
    cnt = Counter(have)
    uniq = [n for n in have if cnt[n]==1]
    print(f'{vol}: flag={len(flag)} enact={len(enact)} hdr_numeral={len(have)} distinct={len(set(have))} UNIQUE_certifiable={len(uniq)}')
