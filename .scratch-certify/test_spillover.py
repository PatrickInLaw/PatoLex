import importlib.util, json, os
spec=importlib.util.spec_from_file_location("cc", r"C:\Users\patolex\PatoLex-scratch\_certify_chapters.py")
cc=importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
root=r'C:\Users\patolex\PatoLex-scratch'
# For several early/chaptered volumes: distribution of chapter_header_count among real flagged acts
import re
from collections import Counter
for vol,fn in [('1854','parsed_acts_early_v2.json'),('1860','parsed_acts_early_v2.json'),
               ('1862','parsed_acts_early_v2.json'),('1891','parsed_acts_recovered.json'),
               ('1863','parsed_acts_recovered.json'),('1885-86','parsed_acts_chaptered_v2.json')]:
    fp=os.path.join(root,'production-'+vol,fn)
    if not os.path.exists(fp): continue
    d=json.load(open(fp,encoding='utf-8'))
    flag=[a for a in d.get('flagged_acts',[]) if cc.is_real_act(a)]
    cnt=Counter(min(cc.chapter_header_count(a.get('text','')),5) for a in flag)
    print(vol, 'real_flagged', len(flag), 'hdrcount_dist', dict(sorted(cnt.items())))
# Verify a clean single act has count==1
d=json.load(open(os.path.join(root,'production-1854','parsed_acts_early_v2.json'),encoding='utf-8'))
ena=[a for a in d['flagged_acts'] if a.get('has_enact')]
ones=[a for a in ena if cc.chapter_header_count(a.get('text',''))==1]
print('1854 enact with exactly 1 header:', len(ones), 'of', len(ena))
# show a count==1 sample head
if ones: print('SAMPLE1:', ones[0]['text'][:80].replace(chr(10),' '))
