#!/usr/bin/env python3
"""
build_session_reference.py  -- READ-ONLY: build the canonical session reference
table from the corpus itself.

Each statute volume declares its session ordinal on its title page ("...PASSED AT THE
FOURTEENTH SESSION OF THE LEGISLATURE..."). This reads that ordinal robustly
(de-hyphenation + engine-union over the 4 OCR fields + extended 1..99 parser),
plus the modal approval year and an extraordinary/special flag, for every
production volume. Output is the empirical ordinal<->year(s) mapping that grounds
the session-number remodel (see SESSION_NUMBER_REMODEL_PLAN.md). Writes new files
only; changes no oracle or parse.

Output (under SCRATCH): _session_reference.tsv  (+ stdout coverage summary)
Usage: python build_session_reference.py --scratch <dir> --oracle <tsv>
"""
import argparse, json, os, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
import rederive_index_counts as R

FIELDS = ["consensus_text", "surya_text", "doctr_text", "tess_text"]

ONES = {"first":1,"second":2,"third":3,"fourth":4,"fifth":5,"sixth":6,"seventh":7,
        "eighth":8,"ninth":9,"tenth":10,"eleventh":11,"twelfth":12,"thirteenth":13,
        "fourteenth":14,"fifteenth":15,"sixteenth":16,"seventeenth":17,"eighteenth":18,
        "nineteenth":19}
TENS = {"twentieth":20,"thirtieth":30,"fortieth":40,"fiftieth":50,"sixtieth":60,
        "seventieth":70,"eightieth":80,"ninetieth":90}
TENS_PREFIX = {"twenty":20,"thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,
               "eighty":80,"ninety":90}
ONES_SUFFIX = {"first":1,"second":2,"third":3,"fourth":4,"fifth":5,"sixth":6,
               "seventh":7,"eighth":8,"ninth":9}

ORD_PHRASE = re.compile(r"((?:[A-Za-z]+[\s-]+){1,2}session\s+of\s+the\s+legislature)",
                        re.IGNORECASE)
EXTRA = re.compile(r"(extraordinary|special)\s+session", re.IGNORECASE)

def dehyphenate(text):
    # join line-break and stray "wo- rd" splits so "Fif- teenth" -> "Fifteenth"
    text = re.sub(r"-\s*\r?\n\s*", "", text)
    text = re.sub(r"([A-Za-z])-\s+([a-z])", r"\1\2", text)
    return text

def parse_ordinal(phrase):
    p = phrase.lower()
    m = re.search(r"(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[\s-]*"
                  r"(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth)", p)
    if m:
        return TENS_PREFIX[m.group(1)] + ONES_SUFFIX[m.group(2)]
    for w, n in TENS.items():
        if re.search(r"\b"+w+r"\b", p):
            return n
    for w, n in sorted(ONES.items(), key=lambda x: -len(x[0])):
        if re.search(r"\b"+w+r"\b", p):
            return n
    return None

def extract(label, scratch):
    path = os.path.join(scratch, label, "ocr_consensus", "page_ocr_results.json")
    if not os.path.exists(path):
        return None
    pages = json.load(open(path, encoding="utf-8"))
    ordered = R.numeric_page_order(pages.keys())
    ordinal, phrase, extra = None, "", ""
    approval = Counter()
    # title page is usually in the first ~30 page-keys; scan a bit deeper for
    # combined/multi-part volumes.
    for k in ordered[:40]:
        rec = pages.get(k) or {}
        for fld in FIELDS:
            t = rec.get(fld) or ""
            if not t.strip():
                continue
            dt = dehyphenate(t)
            if ordinal is None:
                for mo in ORD_PHRASE.finditer(dt):
                    cand = parse_ordinal(mo.group(1))
                    if cand:
                        ordinal, phrase = cand, re.sub(r"\s+", " ", mo.group(1)).strip()
                        break
            if not extra and EXTRA.search(dt):
                extra = EXTRA.search(dt).group(0).lower()
        for ym in R.APPROVAL_YEAR.finditer(rec.get("consensus_text") or ""):
            approval[ym.group(1)] += 1
    modal_year = approval.most_common(1)[0][0] if approval else ""
    return ordinal, phrase, extra, modal_year

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--oracle", required=True)
    args = ap.parse_args()
    scratch = args.scratch.replace("\\", "/").rstrip("/")
    oracle_rows = R.load_oracle(args.oracle)

    rows, resolved = [], 0
    vols = sorted(n for n in os.listdir(scratch)
                  if n.startswith("production-") and os.path.isdir(os.path.join(scratch, n)))
    for label in vols:
        res = extract(label, scratch)
        okey, on, _ = R.find_oracle_match(label, oracle_rows)
        if res is None:
            rows.append([label, "", "", "", "", okey or "", "" if on is None else str(on), "no_ocr"])
            continue
        ordinal, phrase, extra, modal_year = res
        if ordinal:
            resolved += 1
        rows.append([label, "" if ordinal is None else str(ordinal), phrase,
                     "extra" if extra else "regular", modal_year,
                     okey or "", "" if on is None else str(on),
                     "ok" if ordinal else "ordinal_not_read"])
        print(f"{label:36} ord={str(ordinal):>4} {('['+extra+']') if extra else '':16} "
              f"yr={modal_year:5} oracle={on}")
        sys.stdout.flush()

    out = os.path.join(scratch, "_session_reference.tsv")
    with open(out, "w", encoding="utf-8") as f:
        f.write("label\tsession_number\tordinal_phrase\tsession_kind\tmodal_year\t"
                "current_oracle_key\tcurrent_oracle_N\tstatus\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    print(f"\nWROTE {out}")
    print(f"resolved ordinal: {resolved}/{len(vols)}  ({len(vols)-resolved} need pattern/manual fill)")

if __name__ == "__main__":
    main()
