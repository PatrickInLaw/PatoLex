import pathlib
import json

ocr_dir = pathlib.Path(r'C:\PatoLex-scratch\production-1850\ocr_consensus')
files = sorted(ocr_dir.iterdir())
print(f"OCR files: {[f.name for f in files]}")

# Read the main OCR results file
ocr_file = ocr_dir / 'page_ocr_results.json'
if ocr_file.exists():
    with open(ocr_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"Type: {type(data)}")
    if isinstance(data, list):
        print(f"Total pages: {len(data)}")
        # Show first entry structure
        if data:
            first = data[0]
            print(f"First entry keys: {list(first.keys()) if isinstance(first, dict) else 'not dict'}")
            if isinstance(first, dict):
                for k, v in first.items():
                    if isinstance(v, str):
                        print(f"  {k}: {repr(v[:100])}")
                    else:
                        print(f"  {k}: {v}")
    elif isinstance(data, dict):
        print(f"Top-level keys: {list(data.keys())[:10]}")
        # Check if it's page-keyed
        sample_key = list(data.keys())[0]
        print(f"Sample key: {sample_key}")
        sample_val = data[sample_key]
        if isinstance(sample_val, dict):
            print(f"Page value keys: {list(sample_val.keys())}")
else:
    print("page_ocr_results.json NOT FOUND")
    for f in files:
        print(f"  Found: {f.name}")
