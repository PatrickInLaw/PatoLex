import json, sys, glob, os, re
root = r'C:\Users\patolex\PatoLex-scratch'
# show early_meta for a few volumes, and overall confident/flagged + clean-numeral stats
def clean_int(a):
    raw = str(a.get('chapter_raw', a.get('chapter',''))).strip()
    if re.fullmatch(r'[1-9][0-9]{0,3}', raw):
        return int(raw)
    ci = a.get('chapter_int')
    if isinstance(ci, int) and ci > 0:
        return ci
    return None

for vol in ('1850','1851','1852','1853','1854','1860','1862','1865-66'):
    fp = os.path.join(root, 'production-'+vol, 'parsed_acts_early_v2.json')
    if not os.path.exists(fp):
        print(vol, 'NO early_v2'); continue
    d = json.load(open(fp, encoding='utf-8'))
    conf = d.get('confident_acts', [])
    flag = d.get('flagged_acts', [])
    meta = d.get('_early_meta', {})
    clean_flag = sum(1 for a in flag if clean_int(a) is not None)
    print(vol, 'conf', len(conf), 'flag', len(flag), 'flag_with_clean_int', clean_flag, 'meta_keys', list(meta.keys()))
