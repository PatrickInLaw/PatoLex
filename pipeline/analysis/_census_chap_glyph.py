"""throwaway: per-engine raw 'CHAP' header-glyph census for early volumes, to
reconcile two counting methods:
  (1) LITERAL upright 'CHAP'/'CHAPTER' glyph at line start (what the root-cause
      doc likely counted -- 'Surya read 236, consensus 0').
  (2) the recover_early JOINED TRIAD (glyph+real numeral+dash+An Act).
Prints both per engine field so we can see WHERE the consensus bug actually is.
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
ROOT = Path(config.path_for("data_root"))

# literal upright CHAP/CHAPTER at (or near) line start, followed by a numeral-ish token
LIT = re.compile(r"^[\s.,'\"]{0,3}CHAP(?:TER)?\b\.?\s*[IVXLCDM0-9]", re.I)
# strict upright (case-sensitive) -- only matches CLEAN 'CHAP'/'CHAPTER', not garble
LIT_CLEAN = re.compile(r"^[\s.,'\"]{0,3}(?:CHAP\.|CHAPTER)\s*[IVXLCDM0-9]")

def lines(page, field):
    return (page.get(field) or "").split("\n")

def main():
    labels = sys.argv[1:]
    fields = ["surya_text", "doctr_text", "tess_text", "consensus_text"]
    print(f"{'label':<10}{'engine':<14}{'litCASEi':>9}{'litCLEAN':>9}")
    for label in labels:
        p = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
        if not p.exists():
            print(f"{label:<10} (no json)")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for field in fields:
            ci = cl = 0
            for k in d:
                for ln in lines(d[k], field):
                    s = ln.strip()
                    if LIT.match(s):
                        ci += 1
                    if LIT_CLEAN.match(s):
                        cl += 1
            print(f"{label:<10}{field:<14}{ci:>9}{cl:>9}")
        print()

if __name__ == "__main__":
    main()
