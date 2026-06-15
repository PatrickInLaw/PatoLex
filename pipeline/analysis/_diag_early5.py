"""Portable diagnostic for recover_early: uses config (works on any box).
Modes:
  --starts <label>    : print every detected start line + parsed numeral, flag non-monotone
  --toc <label>       : list TOC/index-looking pages (dotted leaders / CONTENTS / INDEX)
  --pages <label> A B : dump raw consensus_text for page indices [A,B)
  --enact <label>     : count enacting-clause lines + Approved-bracket lines + chap-markers
"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))          # pipeline/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
import config
import recover_early as RE

ROOT = Path(config.path_for("data_root"))

def load_pages(label):
    p = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}

TOC_HEAD = re.compile(r"TITLE\s+OF\s+ACT|CONTENTS|No\.\s+of\s+bill|INDEX|GENERAL\s+INDEX", re.I)
LEADER = re.compile(r"\.{4,}|(?:\.\s){4,}")

def main():
    mode = sys.argv[1]
    label = sys.argv[2]
    if mode == "--starts":
        lines = RE.load_lines(label)
        starts = RE.detect_starts(lines)
        print(f"{label}: {len(starts)} raw starts")
        prev = 0
        for k, (li, tok, _form) in enumerate(starts):   # detect_starts -> (i, tok, form)
            s = lines[li][1].strip()
            num = RE.parse_chapter_numeral(tok)
            flag = ""
            if num and prev and num < prev:
                flag = "  <==NON-MONOTONE(prev=%d)" % prev
            if num == 0:
                flag += "  [num=0]"
            print(f"  o{k:>4} pg{lines[li][0]:>4} num={num:<5} tok={tok!r:<8}| {s[:88]}{flag}")
            if num:
                prev = num
    elif mode == "--toc":
        pages = load_pages(label)
        for pidx in sorted(pages):
            txt = pages[pidx].get("consensus_text", "")
            ls = [l for l in txt.split("\n") if l.strip()]
            if not ls:
                continue
            head = TOC_HEAD.search(txt)
            nl = sum(1 for l in ls if LEADER.search(l))
            frac = nl / len(ls)
            if head or frac > 0.25:
                print(f"pg{pidx:>4} leaders={nl}/{len(ls)} ({frac:.0%}) head={bool(head)}")
    elif mode == "--pages":
        a, b = int(sys.argv[3]), int(sys.argv[4])
        pages = load_pages(label)
        for pidx in range(a, b):
            if pidx in pages:
                print(f"==== page idx {pidx} ====")
                print(pages[pidx].get("consensus_text", "")[:1800])
                print()
    elif mode == "--enact":
        pages = load_pages(label)
        lines = []
        for pidx in sorted(pages):
            for ln in pages[pidx].get("consensus_text", "").split("\n"):
                lines.append(ln)
        n_enact = sum(1 for t in lines if RE.ENACT.search(t))
        n_appr = sum(1 for t in lines if RE.APPROVED.search(t) or RE.APPROVED_DATE.search(t))
        # RE.CHAP_MARKER was removed when recover_early moved to the FORMA triad +
        # production header_starts_act union; count joined-form (FORMA) header lines
        # instead so --enact still runs.
        n_chap = sum(1 for t in lines if RE.FORMA.match(t.strip()))
        n_anact = sum(1 for t in lines if RE.AN_ACT_STRICT.search(t) or RE.AN_ACT_FUZZY.search(t))
        print(f"{label}: enact_lines={n_enact} approved_lines={n_appr} "
              f"forma_header_lines={n_chap} an_act_lines={n_anact} total_lines={len(lines)}")

if __name__ == "__main__":
    main()
