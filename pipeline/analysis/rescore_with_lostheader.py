"""rescore_with_lostheader.py -- biennium-correct BEFORE/AFTER scoring of the lost-header
recovery. BEFORE = parsed_acts_certified.json confident acts. AFTER = certified confident
UNION recover_lost_header recovered acts (status=seq_assigned_no_header).

Per session, distinct chapter numbers in [1,N] vs the oracle N. Also reports the
recovered-vs-needs-reocr split sizing the re-OCR pass.

  python rescore_with_lostheader.py
"""
import json
from pathlib import Path
from collections import defaultdict
import importlib.util

REPO = Path(__file__).resolve().parents[2]
def _load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path)); m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); return m
import sys
sys.path.insert(0, str(REPO / "pipeline")); sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
import config  # noqa
ROOT = Path(config.path_for("data_root"))
cc = _load_mod("certify_chapters", REPO / "pipeline" / "ingest" / "certify_chapters.py")

def assigned(a):
    v = a.get("chapter_int_final", a.get("chapter_int", 0))
    try: return int(v)
    except (TypeError, ValueError): return 0

oracle = cc.load_oracle()

# group by session
by_session = defaultdict(lambda: {"before": set(), "after": set(), "labels": [],
                                   "recovered": 0, "needs": 0, "N": None})
for d in sorted(ROOT.glob("production-*")):
    if not d.is_dir(): continue
    label = d.name[len("production-"):]
    sk = cc.session_key(label)
    if not sk: continue
    N = cc.oracle_N(label, oracle)
    if N is None: continue
    cert = d / "parsed_acts_certified.json"
    if not cert.exists(): continue
    s = by_session[sk]
    s["N"] = N
    s["labels"].append(label)
    data = json.loads(cert.read_text(encoding="utf-8"))
    for a in data.get("confident_acts", []):
        n = assigned(a)
        if 1 <= n <= N:
            s["before"].add(n); s["after"].add(n)
    lh = d / "parsed_acts_lostheader.json"
    if lh.exists():
        ld = json.loads(lh.read_text(encoding="utf-8"))
        for r in ld.get("recovered_acts", []):
            n = assigned(r)
            if 1 <= n <= N:
                s["after"].add(n); s["recovered"] += 1
        s["needs"] += len(ld.get("needs_reocr", []))

tot_N = tot_b = tot_a = tot_rec = tot_need = 0
rows = []
for sk, s in by_session.items():
    N = s["N"]
    b = len(s["before"]); a = len(s["after"])
    rows.append((sk, N, b, a, a - b, s["recovered"], s["needs"]))
    tot_N += N; tot_b += b; tot_a += a; tot_rec += s["recovered"]; tot_need += s["needs"]

rows.sort(key=lambda r: -r[4])
print(f"{'session':<32}{'N':>6}{'before':>8}{'after':>8}{'gain':>6}{'rec':>5}{'need':>6}")
for sk, N, b, a, g, rec, need in rows:
    if g or rec or need:
        print(f"{sk:<32}{N:>6}{b:>8}{a:>8}{g:>6}{rec:>5}{need:>6}")

print("\n==== CORPUS TOTALS (sessions with oracle N + certified parse) ====")
print(f"oracle N (sum)          : {tot_N:,}")
print(f"distinct BEFORE         : {tot_b:,}  ({100.0*tot_b/tot_N:.2f}%)")
print(f"distinct AFTER          : {tot_a:,}  ({100.0*tot_a/tot_N:.2f}%)")
print(f"distinct GAIN           : {tot_a-tot_b:,}")
print(f"recovered acts emitted  : {tot_rec:,}")
print(f"needs_reocr boundaries  : {tot_need:,}")
print(f"residual BEFORE         : {tot_N-tot_b:,}")
print(f"residual AFTER          : {tot_N-tot_a:,}")
out = ROOT / "_rescore_lostheader.json"
out.write_text(json.dumps({
    "totals": {"oracle_N": tot_N, "before": tot_b, "after": tot_a,
               "gain": tot_a-tot_b, "recovered": tot_rec, "needs_reocr": tot_need,
               "residual_before": tot_N-tot_b, "residual_after": tot_N-tot_a},
    "rows": [{"session": sk, "N": N, "before": b, "after": a, "gain": g,
              "recovered": rec, "needs": need} for sk, N, b, a, g, rec, need in rows],
}, indent=2), encoding="utf-8")
print("wrote", out)
