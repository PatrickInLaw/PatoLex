import json, pprint, sys
fp = sys.argv[1]
d = json.load(open(fp, encoding='utf-8'))
print('KEYS', list(d.keys()))
for k in d.keys():
    v = d[k]
    if isinstance(v, list):
        print('LIST', k, 'len', len(v))
print('--FLAG0--')
pprint.pprint((d.get('flagged_acts') or [{}])[0])
print('--FLAG1--')
fl = d.get('flagged_acts') or []
pprint.pprint(fl[1] if len(fl) > 1 else {})
print('--CONF0--')
pprint.pprint((d.get('confident_acts') or [{}])[0])
