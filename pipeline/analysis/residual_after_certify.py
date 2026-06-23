"""residual_after_certify.py -- POST-CERTIFICATION residual measurement (biennium-correct).

For each production-<label> volume, read the BEST parse (parsed_acts_certified.json >
parsed_acts_chaptered_v2.json > parsed_acts_early_v2.json > parsed_acts_recovered.json),
group volumes by SESSION (certify_chapters.session_key / oracle_N -- the biennium-correct
map), and for each session compute, against the oracle N:
  - distinct confident chapters present in [1,N]
  - the residual = the set of chapter numbers in [1,N] NOT present as a confident act

This is a pure measurement: it writes a JSON report, no parse files touched.

Usage:
  python -m analysis.residual_after_certify                 # all sessions -> report
  python -m analysis.residual_after_certify --parse NAME    # force a specific parse file
  python -m analysis.residual_after_certify --worst 5       # also print 5 worst sessions
"""
import sys, json
from pathlib import Path
from collections import defaultdict
import importlib.util

REPO = Path(__file__).resolve().parents[2]

def _load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

sys.path.insert(0, str(REPO / "pipeline"))
sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
import config  # noqa
ROOT = Path(config.path_for("data_root"))
cc = _load_mod("certify_chapters", REPO / "pipeline" / "ingest" / "certify_chapters.py")

PARSE_PREF = ("parsed_acts_certified.json",
              "parsed_acts_chaptered_v2.json",
              "parsed_acts_early_v2.json",
              "parsed_acts_recovered.json")


def best_parse(d, forced=None):
    if forced:
        p = d / forced
        return (p, forced) if p.exists() else (None, None)
    for n in PARSE_PREF:
        p = d / n
        if p.exists():
            return p, n
    return None, None


def assigned(a):
    v = a.get("chapter_int_final", a.get("chapter_int", 0))
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def main():
    forced = None
    worst_n = 0
    args = sys.argv[1:]
    if "--parse" in args:
        i = args.index("--parse"); forced = args[i + 1]
    if "--worst" in args:
        i = args.index("--worst"); worst_n = int(args[i + 1])

    oracle = cc.load_oracle()

    # group volumes by session key
    by_session = defaultdict(list)   # sk -> [(label, present_confident_set, parse_name)]
    for d in sorted(ROOT.glob("production-*")):
        if not d.is_dir():
            continue
        label = d.name[len("production-"):]
        p, name = best_parse(d, forced)
        if p is None:
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        conf = data.get("confident_acts", []) or []
        present = set()
        for a in conf:
            n = assigned(a)
            if n > 0:
                present.add(n)
        sk = cc.session_key(label) or ("__noleg__" + label)
        by_session[sk].append((label, present, name))

    sessions = []
    tot_N = tot_have = 0
    for sk, members in by_session.items():
        # N from any member
        N = None
        for label, _, _ in members:
            N = cc.oracle_N(label, oracle)
            if N is not None:
                break
        if N is None:
            continue
        present = set()
        for _, s, _ in members:
            present |= s
        in_range = {c for c in present if 1 <= c <= N}
        residual = sorted(c for c in range(1, N + 1) if c not in in_range)
        have = len(in_range)
        sessions.append({
            "session": sk,
            "labels": [m[0] for m in members],
            "parse": members[0][2],
            "N": N,
            "have": have,
            "missing": N - have,
            "compl_pct": round(100.0 * have / N, 1) if N else 0.0,
            "residual": residual,
        })
        tot_N += N
        tot_have += have

    sessions.sort(key=lambda s: (-s["missing"], s["session"]))
    report = {
        "totals": {
            "sessions": len(sessions),
            "oracle_N": tot_N,
            "have_distinct": tot_have,
            "missing": tot_N - tot_have,
            "compl_pct": round(100.0 * tot_have / max(1, tot_N), 2),
        },
        "sessions": sessions,
    }
    out = ROOT / "_residual_after_certify.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["totals"], indent=2))
    if worst_n:
        print("\nWORST SESSIONS (by #missing):")
        for s in sessions[:worst_n]:
            res = s["residual"]
            rs = (str(res[:30]) + (" ...+%d" % (len(res) - 30) if len(res) > 30 else ""))
            print(f"  {s['session']:<28} N={s['N']:>4} have={s['have']:>4} "
                  f"miss={s['missing']:>4} ({s['compl_pct']}%)  parse={s['parse']}")
            print(f"      residual: {rs}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
