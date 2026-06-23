"""inspect_gap.py -- for a SESSION, find interior residual slots and dump the OCR lines
between the confident anchors that bracket each open slot, so we can see whether a
header-independent 'An Act ... [Approved ...]' boundary is present.

Builds the session's page-ordered confident-act stream (across member volumes), maps each
confident act to its source (label,page). For a single-open-slot gap between anchor a (num lo,
page p_lo) and anchor b (num hi=lo+2, page p_hi), the missing chapter lo+1 lives on a page in
[p_lo, p_hi] of that volume. Dump consensus_text lines for those pages.

  python -m analysis.inspect_gap "1961 Regular Session" [--max 8]
"""
import sys, json, re
from pathlib import Path
from collections import defaultdict
import importlib.util

REPO = Path(__file__).resolve().parents[2]
def _load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path)); m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); return m
sys.path.insert(0, str(REPO / "pipeline")); sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
import config  # noqa
ROOT = Path(config.path_for("data_root"))
cc = _load_mod("certify_chapters", REPO / "pipeline" / "ingest" / "certify_chapters.py")

PARSE_PREF = ("parsed_acts_certified.json", "parsed_acts_chaptered_v2.json",
              "parsed_acts_early_v2.json", "parsed_acts_recovered.json")

def best_parse(d):
    for n in PARSE_PREF:
        p = d / n
        if p.exists(): return p, n
    return None, None

def assigned(a):
    v = a.get("chapter_int_final", a.get("chapter_int", 0))
    try: return int(v)
    except (TypeError, ValueError): return 0

def load_pages(label):
    ocr = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    if not ocr.exists(): return {}
    raw = json.loads(ocr.read_text(encoding="utf-8"))
    return {int(k): v.get("consensus_text", "") for k, v in raw.items()}

def main():
    target = sys.argv[1]
    mx = 8
    if "--max" in sys.argv:
        mx = int(sys.argv[sys.argv.index("--max") + 1])
    oracle = cc.load_oracle()
    # gather member volumes of this session
    members = []
    for d in sorted(ROOT.glob("production-*")):
        if not d.is_dir(): continue
        label = d.name[len("production-"):]
        sk = cc.session_key(label)
        if sk != target: continue
        p, name = best_parse(d)
        if p is None: continue
        members.append((label, p, name))
    if not members:
        print("no members for", target); return
    N = None
    for label, _, _ in members:
        N = cc.oracle_N(label, oracle)
        if N: break
    print(f"session={target} N={N} members={[m[0] for m in members]}")

    # page-ordered confident stream with (label,page,num)
    label_order = {lbl: i for i, (lbl, _, _) in enumerate(members)}
    conf = []
    for label, p, name in members:
        data = json.loads(p.read_text(encoding="utf-8"))
        for a in data.get("confident_acts", []):
            n = assigned(a)
            if 1 <= n <= N:
                conf.append((label, a.get("source_page", 0), n))
    conf.sort(key=lambda t: (label_order[t[0]], t[1]))

    present = sorted({c for _, _, c in conf})
    present_set = set(present)
    # unique-num anchors with position
    pos_of = {}
    for label, pg, n in conf:
        pos_of.setdefault(n, (label, pg))

    # single-open-slot interior gaps: lo present, lo+1 missing, lo+2 present, same volume, pages close
    shown = 0
    for lo in present:
        if shown >= mx: break
        slot = lo + 1
        hi = lo + 2
        if slot in present_set or hi not in present_set: continue
        l_lo, p_lo = pos_of[lo]; l_hi, p_hi = pos_of[hi]
        if l_lo != l_hi: continue
        if not (0 <= p_hi - p_lo <= 4): continue
        pages = load_pages(l_lo)
        print(f"\n===== open slot {slot} between conf {lo}(p{p_lo}) and {hi}(p{p_hi}) vol={l_lo} =====")
        for pg in range(p_lo, p_hi + 1):
            txt = pages.get(pg - 1, "")  # source_page is 1-based (lines[start][0]+1)
            for ln in txt.split("\n"):
                s = ln.strip()
                if not s: continue
                if re.search(r"\bAn?\s+A[CEO][TI]\b", s, re.I) or re.search(r"Approved|CHAP|Filed with Sec", s, re.I):
                    print(f"   p{pg}: {s[:110]}")
        shown += 1

if __name__ == "__main__":
    main()
