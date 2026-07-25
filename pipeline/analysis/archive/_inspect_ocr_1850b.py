import pathlib
import json

ocr_file = pathlib.Path(r'C:\PatoLex-scratch\production-1850\ocr_consensus\page_ocr_results.json')
with open(ocr_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

keys = sorted(data.keys(), key=lambda x: int(x))
print(f"Page keys: min={keys[0]}, max={keys[-1]}, total={len(keys)}")
print(f"All keys: {keys}")

# Check if surya_text is present
sample = data[keys[0]]
print(f"\nSample page {keys[0]} keys: {list(sample.keys())}")
print(f"  tess_text snippet: {repr(sample.get('tess_text','')[:200])}")
print(f"  doctr_text snippet: {repr(sample.get('doctr_text','')[:200])}")
print(f"  consensus_text snippet: {repr(sample.get('consensus_text','')[:200])}")
print(f"  surya_text present: {'surya_text' in sample}")
