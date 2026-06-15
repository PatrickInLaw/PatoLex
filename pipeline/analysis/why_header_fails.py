"""why_header_fails.py -- for each 'An Act' start whose header HEADER_RE missed, look
at the 1-3 lines ABOVE for a CHAPTER-ish word and bucket WHY the production regex failed:

  missing_numeral   a CHAPTER-ish word is there but no readable numeral after it
  garbled_word      the CHAPTER word itself is OCR-mangled beyond HEADER_RE's class
  noise_prefix      header has leading junk chars HEADER_RE's prefix class can't eat
  no_chap_line      no CHAPTER-ish line at all in prior 3 (header truly absent/merged)
  other

Also dumps the candidate header line so we can design a tolerant detector.

Usage: python -m analysis.why_header_fails <label> [<label> ...]
"""
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

# very loose "looks like the word CHAPTER" probe (diagnostic only)
CHAPWORD = re.compile(r"c[\W_]*[hilu]?[\W_]*[ila]?[\W_]*p", re.I)  # c..h..a..p-ish
CHAPWORD2 = re.compile(r"\b(c[hilu]a?p|cilap|chap|ohap|ghap|chae|chav|chat)", re.I)
NUMERAL = re.compile(r"[IVXLCDM0-9]", re.I)


def main():
    labels = sys.argv[1:]
    grand = Counter()
    samples = {"missing_numeral": [], "garbled_word": [], "noise_prefix": [], "no_chap_line": []}
    for label in labels:
        ocr_path = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
        raw = json.loads(ocr_path.read_text(encoding="utf-8"))
        pages = {int(k): v for k, v in raw.items()}
        lines = []
        for pidx in sorted(pages.keys()):
            for line in pages[pidx].get("consensus_text", "").split("\n"):
                lines.append((pidx, line))
        for i, (pidx, line) in enumerate(lines):
            if not ing.AN_ACT_RE.search(line):
                continue
            if any(ing.HEADER_RE.match(lines[j][1].strip()) for j in range(max(0, i-3), i)):
                continue  # header WAS matched -> not a miss
            # look at prior 3 non-empty lines for a chapter-ish header
            cand = None
            for j in range(i-1, max(-1, i-4), -1):
                s = lines[j][1].strip()
                if not s:
                    continue
                if CHAPWORD2.search(s) or s.lower().startswith(("chap", "cilap", "ohap")):
                    cand = s
                    break
            if cand is None:
                # broader: any line in prior 3 with a chap-ish token + short
                for j in range(i-1, max(-1, i-4), -1):
                    s = lines[j][1].strip()
                    if s and len(s) < 25 and CHAPWORD.search(s):
                        cand = s
                        break
            if cand is None:
                grand["no_chap_line"] += 1
                if len(samples["no_chap_line"]) < 12:
                    samples["no_chap_line"].append((label, pidx+1, line.strip()[:60]))
                continue
            # we have a candidate header line that HEADER_RE rejected -> why?
            mword = re.match(r"^[^A-Za-z0-9]*", cand)
            prefix = mword.group(0)
            rest = cand[len(prefix):]
            has_num = bool(NUMERAL.search(rest[4:14])) if len(rest) > 4 else bool(NUMERAL.search(rest))
            if len(prefix) > 4:
                grand["noise_prefix"] += 1
                bucket = "noise_prefix"
            elif not has_num:
                grand["missing_numeral"] += 1
                bucket = "missing_numeral"
            else:
                grand["garbled_word"] += 1
                bucket = "garbled_word"
            if len(samples[bucket]) < 12:
                samples[bucket].append((label, pidx+1, cand[:60]))

    print("WHY HEADER_RE MISSED (across", labels, ")")
    for k, v in grand.most_common():
        print(f"  {k:<16} {v}")
    for b, ex in samples.items():
        print(f"\n  --- {b} examples ---")
        for lbl, pg, txt in ex:
            print(f"    p{pg}: {repr(txt)}")


if __name__ == "__main__":
    main()
