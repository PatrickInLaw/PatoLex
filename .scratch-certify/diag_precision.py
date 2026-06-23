import importlib.util, json, os, re
spec=importlib.util.spec_from_file_location("cc", r"C:\Users\patolex\PatoLex-scratch\_certify_chapters.py")
cc=importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
root=r'C:\Users\patolex\PatoLex-scratch'
oracle=cc.load_oracle()

# For the precision-problem sessions, show: member volumes, session key, oracle N,
# and whether the oor_confident acts are PRE-EXISTING in the source confident list.
problem_sessions = ['1873-74','1883 Regular Session','1887 Regular Session']
# map session -> member volume labels
from collections import defaultdict
sess_vols=defaultdict(list)
for d in sorted(__import__('glob').glob(os.path.join(root,'production-*'))):
    label=os.path.basename(d)[len('production-'):]
    p,name=cc.best_parse_path(__import__('pathlib').Path(d))
    if p is None: continue
    sk=cc.session_key(label) or ('__noleg__'+label)
    sess_vols[sk].append((label,str(p),name))

for sk in problem_sessions:
    print('==== session', repr(sk))
    if sk not in sess_vols:
        # maybe it's the session_key form; find member labels by oracle_N path
        print('  not a grouping key; searching labels whose oracle_N session matches')
    for label,p,name in sess_vols.get(sk,[]):
        N=cc.oracle_N(label,oracle)
        d=json.load(open(p,encoding='utf-8'))
        conf=d.get('confident_acts',[])
        ints=[cc.assigned(a) for a in conf]
        print(f'  vol={label} parse={name} oracleN={N} conf={len(conf)} conf_int_min={min(ints) if ints else None} conf_int_max={max(ints) if ints else None}')
        # how many source-confident are out of [1,N]?
        if N:
            oor=[cc.assigned(a) for a in conf if not (1<=cc.assigned(a)<=N)]
            print('    source_confident_OOR count=', len(oor), 'sample', sorted(set(oor))[:15])
