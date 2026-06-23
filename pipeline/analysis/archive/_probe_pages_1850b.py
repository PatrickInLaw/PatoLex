"""Probe later chapters to see if Roman or Arabic chapter numbering."""
import pathlib
import json

ocr_file = pathlib.Path(r'C:\PatoLex-scratch\production-1850\ocr_consensus\page_ocr_results.json')
with open(ocr_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

def show_page_brief(p, label=""):
    pg = data.get(str(p))
    if not pg:
        print(f"  Page {p}: NOT IN OCR")
        return
    t = pg.get('tess_text','')[:400]
    d = pg.get('doctr_text','')[:400]
    print(f"  Page {p} {label}")
    print(f"    TESS:  {repr(t[:200])}")
    print(f"    DOCTR: {repr(d[:200])}")

# Look at pages around higher numbered chapters to see numbering style
# ch 78 at pages 206-208
print("=== ch78 region (pages 204-210) ===")
for p in range(204, 211):
    show_page_brief(p)

print("\n=== ch 92/94/95 region (pages 225-232) ===")
for p in range(225, 233):
    show_page_brief(p)

print("\n=== ch 111/112 region (pages 272-280) ===")
for p in range(272, 281):
    show_page_brief(p)
