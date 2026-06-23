import json, os, re
root = r'C:\Users\patolex\PatoLex-scratch'
fp = os.path.join(root, 'production-1854', 'parsed_acts_early_v2.json')
d = json.load(open(fp, encoding='utf-8'))
flag = d.get('flagged_acts', [])
# distribution of has_an_act, has_enact, form; and how many texts mention >1 'Chapter NN'
chap_re = re.compile(r'Chapter\s+\d', re.I)
multi = 0
single = 0
fields = set()
for a in flag:
    fields |= set(a.keys())
    n = len(chap_re.findall(a.get('text','')))
    if n > 1: multi += 1
    else: single += 1
print('fields', sorted(fields))
print('multi_chapter_text', multi, 'single', single, 'total', len(flag))
# show has_enact / has_an_act distribution
from collections import Counter
print('has_enact', Counter(a.get('has_enact') for a in flag))
print('has_an_act', Counter(a.get('has_an_act') for a in flag))
print('has_approved', Counter(a.get('has_approved') for a in flag))
print('form', Counter(a.get('form') for a in flag))
# chapter_int distribution: are they unique? sequential?
ints = [a.get('chapter_int') for a in flag]
print('n_ints', len(ints), 'distinct', len(set(ints)), 'min', min(i for i in ints if i), 'max', max(i for i in ints if i))
from collections import Counter as C
dup = {k:v for k,v in C(ints).items() if v>1}
print('dup_ints', dup)
# show 3 acts that have_enact True
ena = [a for a in flag if a.get('has_enact')]
print('n_has_enact', len(ena))
for a in ena[:2]:
    print('---ENACT--- chapter_int', a.get('chapter_int'), 'page', a.get('source_page'))
    print(a.get('text','')[:300])
