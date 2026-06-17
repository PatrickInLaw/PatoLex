"""Identify the chapters that were codes_redirect PRE-FIX but not POST-FIX, and
print the redirect-note text the OLD regex matched so we can judge whether each was
a genuine redirect note or the 'No.'-style false positive MAJOR-B3 targets."""
import json, re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_RC = Path(__file__).resolve().parents[1] / "ingest" / "recover_chaptered.py"
import importlib.util
spec = importlib.util.spec_from_file_location("rc_lost", str(_RC))
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)
NEW_RE = rc.REDIRECT_NOTE_RE
# the OLD regex (pre-fix), reconstructed verbatim for the diff:
OLD_RE = re.compile(
    r"\bN[A-Za-z]{1,5}\.?\s*[.\-—–~]*\s*(?:[xXsS]ce|[sS]ee|For\s+text\s+see)\s+Stats\.?\s*,?\s*\d"
    r"|For\s+text\s+see\s+Stats\.?\s*,?\s*\d", re.I)

base = Path(r"C:/Users/patolex/PatoLex-scratch/production-1933-vol1-chapters")
pre = json.loads((base / "_prefix_v2_backup.json").read_text(encoding="utf-8"))

def key(a):
    return (a.get("source_page"), a.get("chapter_int"))

lost = []
for a in pre.get("confident_acts", []):
    if a.get("status") != "codes_redirect":
        continue
    full = a.get("text", "")
    if not NEW_RE.search(full):     # old said redirect, new says not
        m = OLD_RE.search(full)
        snippet = m.group(0) if m else "(old-RE no longer matches either?)"
        lost.append((a.get("chapter_int"), a.get("source_page"), snippet, full[:160]))

print(f"LOST redirect classifications (PRE-FIX redirect, POST-FIX not): {len(lost)}")
for ch, pg, snip, ctx in lost:
    print(f"\n  ch#{ch} p{pg}")
    print(f"    OLD matched: {snip!r}")
    print(f"    context    : {ctx!r}")
