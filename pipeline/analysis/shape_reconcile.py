"""
shape_reconcile.py -- procedurally reconcile Surya's NON-BODY page flags against the page's OCR text, so the
expensive VLM only sees the genuinely-ambiguous residual. Pure stdlib / CPU (runs on the idle 5080).

Rationale (Patrick): if a page already contains chapter/law text, that's a clear BODY signal -- no VLM needed.
For every page Surya flagged non-body (INDEX_TOC / TABLE_ROSTER / DIVIDER / PICTURE), look at its OCR tokens:
  RESCUE -> BODY    if the text shows statute-body signals (enacting clause, chapter+section structure,
                    appropriations money-prose). These are the false positives (esp. appropriations) Surya makes.
  CONFIRM -> NONBODY if the text shows index signals (TITLE OF ACT / INDEX / CONTENTS header) and NO body signal.
  AMBIGUOUS         neither decisive (or no text) -> route to the VLM tiebreaker.

Body pages keep BODY (we only re-check the exclusion set). Inputs are joined by page: shape pidx <-> out_context
page key (pk). NOTE: numbers are stripped from out_context, but money/number WORDS (thousand, hundred, dollars)
and structural words survive -- which is what these signals use.

  python shape_reconcile.py --shape-tsv <vol>.shapes.tsv --text-json production-<label>.json \
                            --out <vol>.reconciled.tsv --ambiguous <worklist.tsv> --label <label>
  python shape_reconcile.py --text-json ... --shape-tsv ... --debug 8,32,304   # dump signals for those pidx
"""
import argparse, json, os, re

NONBODY = {"INDEX_TOC", "TABLE_ROSTER", "DIVIDER_TITLE", "PICTURE", "MARGIN"}
STAT_KW = {"section", "sections", "chapter", "chapters", "approved", "whereas", "shall",
           "enacted", "enact", "provided", "sec", "code", "amended", "repealed", "constitution"}
MONEY   = {"dollars", "appropriated", "appropriation", "thousand", "hundred", "salary", "sum", "expended"}
INDEXHDR = {"index", "contents", "table"}

def page_tokens(textjson, pk):
    lines = textjson.get(pk) or textjson.get(str(pk))
    if not lines:
        return None
    return [t for line in lines for t in line]

def _has_seq(toks, seq):
    n, m = len(toks), len(seq)
    for i in range(n - m + 1):
        if toks[i:i + m] == seq:
            return True
    return False

def body_signals(toks):
    s = set(toks); head = set(toks[:14]); n = max(1, len(toks))
    enacting = _has_seq(toks, ["be", "it", "enacted"]) or ("enacted" in s) or \
               _has_seq(toks, ["people", "of", "the", "state"])
    chapsec  = bool(({"chapter", "chap"} & s) and ({"section", "sec", "sections"} & s))
    money_n  = sum(1 for t in toks if t in MONEY)
    approp   = ("dollars" in s) and (money_n >= 2 or "appropriated" in s)
    stat_n   = sum(1 for t in toks if t in STAT_KW)
    body = enacting or chapsec or approp or (stat_n >= 4 and "enacted" in s)
    return body, {"enacting": enacting, "chapsec": chapsec, "approp": approp, "stat_n": stat_n,
                  "money_n": money_n}

def index_signals(toks):
    head = toks[:16]; s = set(head)
    title_of_act = _has_seq(head, ["title", "of", "act"]) or _has_seq(toks[:30], ["title", "of", "act"])
    return bool((INDEXHDR & s) or title_of_act), {"index_hdr": bool(INDEXHDR & s), "title_of_act": title_of_act}

def decide(toks):
    if toks is None:
        return "AMBIGUOUS", "no_text"
    body, bs = body_signals(toks)
    if body:
        why = "enacting" if bs["enacting"] else ("approp" if bs["approp"] else ("chapsec" if bs["chapsec"] else "statkw"))
        return "BODY", "rescued:" + why
    idx, _ = index_signals(toks)
    if idx:
        return "NONBODY", "confirmed"
    return "AMBIGUOUS", "no_signal"

def read_shape(fp):
    rows = []
    with open(fp, encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 4:
                rows.append((int(p[0]), p[1], p[2], float(p[3])))
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shape-tsv", required=True)
    ap.add_argument("--text-json", required=True)
    ap.add_argument("--out")
    ap.add_argument("--ambiguous")
    ap.add_argument("--label", default="")
    ap.add_argument("--debug")
    a = ap.parse_args()
    text = json.load(open(a.text_json, encoding="utf-8", errors="replace"))

    if a.debug:
        for pidx in [int(x) for x in a.debug.split(",")]:
            toks = page_tokens(text, pidx)
            verdict, why = decide(toks)
            head = " ".join(toks[:18]) if toks else "(no text for this pk)"
            print(f"pidx={pidx} -> {verdict} ({why})\n   head: {head}")
        return

    rows = read_shape(a.shape_tsv)
    counts = {"BODY_kept": 0, "rescued": 0, "confirmed": 0, "ambiguous": 0}
    out_rows = []; amb = []
    for pidx, cls, lab, conf in rows:
        if cls not in NONBODY:
            counts["BODY_kept"] += 1
            out_rows.append((pidx, "BODY", "surya_body", conf)); continue
        toks = page_tokens(text, pidx)
        verdict, why = decide(toks)
        if verdict == "BODY":
            counts["rescued"] += 1
        elif verdict == "NONBODY":
            counts["confirmed"] += 1
        else:
            counts["ambiguous"] += 1; amb.append((a.label, pidx, cls, conf))
        out_rows.append((pidx, verdict, why, conf))

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write("pidx\tfinal\twhy\tsurya_conf\n")
            for pidx, v, why, conf in out_rows:
                f.write(f"{pidx}\t{v}\t{why}\t{conf}\n")
    if a.ambiguous and amb:
        with open(a.ambiguous, "a", encoding="utf-8") as f:
            for lab, pidx, cls, conf in amb:
                f.write(f"{lab}\t{pidx}\t{cls}\t{conf}\n")
    print(f"{a.label or os.path.basename(a.shape_tsv)}\tkept_body={counts['BODY_kept']}\t"
          f"rescued={counts['rescued']}\tconfirmed={counts['confirmed']}\tambiguous={counts['ambiguous']}")

if __name__ == "__main__":
    main()
