"""throwaway: print the per-page field names + a header sample from an early OCR json."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
ROOT = Path(config.path_for("data_root"))

label = sys.argv[1] if len(sys.argv) > 1 else "1862"
p = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
d = json.loads(p.read_text(encoding="utf-8"))
keys = list(d.keys())
print("npages", len(keys))
print("firstkey", keys[0])
mid = d[keys[len(keys) // 2]]
print("page fields:", sorted(mid.keys()))
# show a sample of each text field for a mid page
for f in ("consensus_text", "committed_text", "tess_text", "doctr_text", "surya_text"):
    v = mid.get(f)
    if v is None:
        print(f"  {f}: <MISSING>")
    else:
        head = v.split("\n")[:3]
        print(f"  {f}: present, {len(v)} chars, first lines={head}")
