"""reocr_sizing.py -- size the re-OCR pass: split the post-lostheader residual into
  (a) recovered-by-sequence (this pass)         -> done
  (b) detected-boundary-but-ambiguous slots      -> re-OCR could disambiguate cheaply
  (c) interior slots with NO detected boundary    -> genuine re-OCR (header truly lost)
  (d) non-interior residual (leading/trailing/block) -> mostly unparsed volumes, separate pass

Uses _residual_after_certify.json (pre-lostheader residual + per-session present sets are
recomputable) and the per-volume parsed_acts_lostheader.json.
"""
import json
from pathlib import Path
from collections import defaultdict
import importlib.util, sys
REPO = Path(__file__).resolve().parents[2]
def _lm(n,p):
    s=importlib.util.spec_from_file_location(n,str(p)); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
sys.path.insert(0,str(REPO/"pipeline")); sys.path.insert(0,str(REPO/"pipeline"/"ingest"))
import config  # noqa
ROOT=Path(config.path_for("data_root"))
cc=_lm("certify_chapters",REPO/"pipeline"/"ingest"/"certify_chapters.py")

def assigned(a):
    v=a.get("chapter_int_final",a.get("chapter_int",0))
    try: return int(v)
    except: return 0

oracle=cc.load_oracle()
by=defaultdict(lambda:{"N":None,"present":set(),"recovered":set(),"need_pages":0})
for d in sorted(ROOT.glob("production-*")):
    if not d.is_dir(): continue
    label=d.name[len("production-"):]
    sk=cc.session_key(label)
    if not sk: continue
    N=cc.oracle_N(label,oracle)
    if N is None: continue
    cert=d/"parsed_acts_certified.json"
    if not cert.exists(): continue
    s=by[sk]; s["N"]=N
    cd=json.loads(cert.read_text(encoding="utf-8"))
    for a in cd.get("confident_acts",[]):
        n=assigned(a)
        if 1<=n<=N: s["present"].add(n)
    lh=d/"parsed_acts_lostheader.json"
    if lh.exists():
        ld=json.loads(lh.read_text(encoding="utf-8"))
        for r in ld.get("recovered_acts",[]):
            n=assigned(r)
            if 1<=n<=N: s["recovered"].add(n)
        s["need_pages"]+=len(ld.get("needs_reocr",[]))

tot=dict(b_residual=0, after_residual=0, recovered=0, interior_after=0,
         need_boundary=0, noninterior_after=0)
for sk,s in by.items():
    N=s["N"]; present=s["present"]; rec=s["recovered"]
    after=present|rec
    b_res=N-len(present); a_res=N-len(after)
    tot["b_residual"]+=b_res; tot["after_residual"]+=a_res; tot["recovered"]+=len(rec)
    tot["need_boundary"]+=s["need_pages"]
    # interior-after = residual slots between present anchors AFTER recovery
    if after:
        lo=min(after); hi=max(after)
        miss=[c for c in range(1,N+1) if c not in after]
        interior=sum(1 for c in miss if lo<c<hi)
    else:
        interior=0
    tot["interior_after"]+=interior
    tot["noninterior_after"]+=(a_res-interior)

print(json.dumps({
  "pre_lostheader_residual": tot["b_residual"],
  "recovered_this_pass": tot["recovered"],
  "post_lostheader_residual": tot["after_residual"],
  "post_residual_INTERIOR (between anchors -> re-OCR candidate)": tot["interior_after"],
  "  of which detected-boundary-but-ambiguous (needs_reocr pages)": tot["need_boundary"],
  "post_residual_NONINTERIOR (leading/trailing/block -> mostly unparsed volumes)": tot["noninterior_after"],
}, indent=2))
