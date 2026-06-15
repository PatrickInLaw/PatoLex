"""precision_check.py -- PRECISION audit of the renumber pass.
For 'filled' acts (number assigned positionally, not parsed), check whether the act's
OWN text contains a readable 'CHAPTER NN' / numeral that AGREES with the assigned number.
A disagreement = a renumber error (bad). Also report duplicate assigned numbers (should be 0).
Usage: python -m analysis.precision_check <label> [<label> ...]"""
import sys, re, json
from collections import Counter
from pathlib import Path
import importlib.util
import config
_ING = Path(__file__).resolve().parent.parent / "ingest" / "ingest_from_ocr.py"
_spec = importlib.util.spec_from_file_location("ingest_from_ocr", str(_ING))
ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ing)
ROOT = Path(config.path_for("data_root"))

def main():
    acts=[]
    for label in sys.argv[1:]:
        d=json.loads((ROOT/('production-'+label)/'parsed_acts_recovered.json').read_text(encoding='utf-8'))
        acts+=d['confident_acts']
    nums=[a['chapter_int'] for a in acts]
    c=Counter(nums)
    dups=[n for n,k in c.items() if k>1]
    print(f"confident acts: {len(acts)}  distinct numbers: {len(set(nums))}  duplicate numbers: {len(dups)} {sorted(dups)[:15]}")
    # check filled acts: does the act text carry a chapter numeral agreeing with assigned?
    agree=disagree=noreadable=0
    examples=[]
    for a in acts:
        if a.get('renumber_status')!='filled':
            continue
        assigned=a['chapter_int']
        # the recovered acts have chapter_raw='' (header lost). Look in first ~120 chars
        # of text for a 'CHAPTER NN' pattern as an independent witness.
        head=a.get('text','')[:200]
        m=re.search(r'CHAP\w*\.?\s*([0-9]{1,4})', head, re.I)
        if not m:
            noreadable+=1
            continue
        witness=int(m.group(1))
        if witness==assigned:
            agree+=1
        else:
            disagree+=1
            if len(examples)<15:
                examples.append((assigned,witness,a.get('source_page'),head[:60]))
    print(f"\nFILLED acts independent-witness check:")
    print(f"  agree={agree} disagree={disagree} no-readable-witness={noreadable}")
    for asg,wit,pg,h in examples:
        print(f"  assigned={asg} witness={wit} p{pg}: {repr(h)}")

if __name__ == "__main__":
    main()
