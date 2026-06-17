"""probe_chap.py -- READ-ONLY. Dump OCR context around where a given chapter's
act should begin, by finding the act whose body precedes/follows the kept
neighbors. Helps see what the header line actually OCR'd as for 'no_header_found'
cases. Also: scan ALL lines for any CHAP-like token (roman or arabic, fuzzy) so
we can see if the header is present but mis-OCR'd.

Usage: python probe_chap.py <label> <chap1> [<chap2> ...]
       python probe_chap.py <label> --census   # census of CHAP-like header lines
"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import importlib.util
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
ROOT = Path(config.path_for("data_root"))
_ING = Path(__file__).resolve().parents[1] / "ingest" / "ingest_from_ocr.py"
_spec = importlib.util.spec_from_file_location("ing_ro", str(_ING))
ing = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ing)


def load_lines(label):
    p = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    out = []
    for pidx in sorted(pages):
        for k, ln in enumerate(pages[pidx].get("consensus_text", "").split("\n")):
            out.append((pidx, ln, k))
    return out


# fuzzy chapter-glyph header (start of line), arabic OR roman numeral after
FUZZY_HDR = re.compile(
    r"^[^A-Za-z0-9]{0,4}"
    r"(?:c[hilou][\w]{0,2}p\w{0,4}|cilap\w{0,4}|ohap\w{0,4}|ghap\w{0,4}|chap\w{0,4}|chapter)"
    r"\.?\s*([ivxlcdmIVXLCDM0-9JjTtYyLl!|]{1,9})", re.I)


def census(label):
    lines = load_lines(label)
    plain = [(p, t) for (p, t, k) in lines]
    n_header_re = 0
    n_fuzzy = 0
    n_fuzzy_not_headerre = 0
    samples = []
    for i, (p, t, k) in enumerate(lines):
        s = t.strip()
        hr = bool(ing.HEADER_RE.match(s))
        fz = bool(FUZZY_HDR.match(s))
        if hr:
            n_header_re += 1
        if fz:
            n_fuzzy += 1
            if not hr:
                n_fuzzy_not_headerre += 1
                if len(samples) < 40:
                    samples.append((p + 1, k, s[:90]))
    print(json.dumps({
        "label": label,
        "lines": len(lines),
        "HEADER_RE_matches": n_header_re,
        "FUZZY_HDR_matches": n_fuzzy,
        "fuzzy_but_not_headerre": n_fuzzy_not_headerre,
        "samples_fuzzy_not_headerre": samples,
    }, indent=2, ensure_ascii=False))


def probe(label, chaps):
    lines = load_lines(label)
    for c in chaps:
        print("\n===== chapter", c, "=====")
        # find any line mentioning the number near a CHAP token, OR an 'An act'
        # whose surrounding text references this chapter weakly; just show all
        # lines containing a CHAP token followed by this exact number anywhere.
        pat = re.compile(r"chap\w*\.?\s*0*" + str(c) + r"\b", re.I)
        found = 0
        for i, (p, t, k) in enumerate(lines):
            if pat.search(t):
                print(f"  [p{p+1} ln{k}] {t.strip()[:120]}")
                found += 1
                if found >= 8:
                    break
        if not found:
            print("  (no 'chap... <n>' token line found at all)")


def main():
    label = sys.argv[1]
    if "--census" in sys.argv:
        census(label)
        return
    chaps = [int(x) for x in sys.argv[2:]]
    probe(label, chaps)


if __name__ == "__main__":
    main()
