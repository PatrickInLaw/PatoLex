"""FORM-B census for the split-layout volumes (1873+): count lines that ARE a
'CHAPTER <numeral>' header (glyph-alone), how many have An Act within 3 non-blank
lines (real act) vs '[See volume of Amendments]' (code stub) vs neither.
  python _diag_early8.py <label>
"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
ROOT = Path(config.path_for("data_root"))

GLYPH = (r"C(?:hapter|uarrer|oarrer|hapt|hap|uap|rap|iap|nap|lap|oap|aap"
         r"|uav|uar|har|nar|oar|ap)r?t?")
NUMTOK = r"[IVXLCDMivxlcdmJjTt0-9!|\]\[lO]{1,9}"
FORMB = re.compile(r"^[\s.,;:'\"`]{0,4}(" + GLYPH + r")\.?\s*(" + NUMTOK + r")\b\s*[.,;:]?\s*(.*)$", re.I)
AN_ACT = re.compile(r"\bAn?\s+A[CEO][TI]\b", re.I)
STUB = re.compile(r"See\s+volume\s+of\s+Amendments|Amendments\s+to\s+the\s+Code", re.I)
_ROMAN = set("IVXLCDM")

def numeral_ok(tok):
    return any(c in _ROMAN for c in tok.upper()) or any(c.isdigit() for c in tok)

label = sys.argv[1]
p = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
raw = json.loads(p.read_text(encoding="utf-8"))
pages = {int(k): v for k, v in raw.items()}
lines = []
for pidx in sorted(pages):
    for ln in pages[pidx].get("consensus_text", "").split("\n"):
        lines.append(ln)

def anact_near(i, n=3):
    seen = 0; j = i
    while j < len(lines) and seen < n:
        if lines[j].strip():
            if AN_ACT.search(lines[j]):
                return True
            seen += 1
        j += 1
    return False

def stub_near(i, n=3):
    seen = 0; j = i
    while j < len(lines) and seen < n:
        if lines[j].strip():
            if STUB.search(lines[j]):
                return True
            seen += 1
        j += 1
    return False

n_hdr = n_real = n_stub = n_neither = 0
for i, t in enumerate(lines):
    s = t.strip()
    mb = FORMB.match(s)
    if not (mb and numeral_ok(mb.group(2)) and not mb.group(3).strip()):
        continue
    n_hdr += 1
    if anact_near(i + 1):
        n_real += 1
    elif stub_near(i + 1):
        n_stub += 1
    else:
        n_neither += 1
print(f"{label}: glyph-alone-headers={n_hdr}  real(AnAct<=3)={n_real}  "
      f"code-stub={n_stub}  neither={n_neither}")
