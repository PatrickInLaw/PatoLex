"""Recall-ceiling probe: how many lines have a DASH immediately followed by
'An Act' (the act-title separator)? That bounds the dash-form recall. Also show
the LEADING token of those lines (what precedes the dash) so we can see which
chapter-glyph OCR variants my strict family is missing.
  python _diag_early7.py <label>
  python _diag_early7.py --leads <label>   # show leading tokens not matched by glyph
"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
ROOT = Path(config.path_for("data_root"))

# dash immediately before An Act (allow a little OCR junk/space between)
DASH_ANACT = re.compile(r"[—–\-‐‑‒―~]{1,3}\s*[<«]?\s*(An?\s+A[CEO][TI]\b)", re.I)
GLYPH = (r"C(?:hapter|uarrer|oarrer|hapt|hap|uap|rap|iap|nap|lap|oap|aap"
         r"|uav|uar|har|nar|oar|ap)r?t?")
LEAD = re.compile(r"^[\s.,;:'\"`]{0,4}(" + GLYPH + r")\b", re.I)

def load(label):
    p = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    out = []
    for pidx in sorted(pages):
        for ln in pages[pidx].get("consensus_text", "").split("\n"):
            out.append((pidx, ln))
    return out

label = sys.argv[-1]
lines = load(label)
showleads = "--leads" in sys.argv
n_dash = 0
n_leadglyph = 0
unmatched_leads = {}
for pidx, t in lines:
    s = t.strip()
    m = DASH_ANACT.search(s)
    if not m:
        continue
    # only count if the dash-AnAct is near the START (a header), within first ~40 chars
    if m.start() > 45:
        continue
    n_dash += 1
    if LEAD.match(s):
        n_leadglyph += 1
    else:
        lead_tok = re.match(r"^[\s.,;:'\"`]{0,4}(\S+)", s)
        key = lead_tok.group(1)[:12] if lead_tok else "?"
        unmatched_leads[key] = unmatched_leads.get(key, 0) + 1

print(f"{label}: dash+AnAct(header-pos)={n_dash}  lead-matches-glyph={n_leadglyph}  "
      f"unmatched-lead={n_dash-n_leadglyph}")
if showleads:
    for k, v in sorted(unmatched_leads.items(), key=lambda x: -x[1])[:40]:
        print(f"   {v:>4}  {k!r}")
