"""Probe key page ranges to understand chapter header format in OCR text."""
import pathlib
import json
import re

ocr_file = pathlib.Path(r'C:\PatoLex-scratch\production-1850\ocr_consensus\page_ocr_results.json')
with open(ocr_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

def get_page(p):
    """Get page by 1-indexed source page number."""
    return data.get(str(p))

def show_page(p, label=""):
    pg = get_page(p)
    if not pg:
        print(f"\n--- Page {p} {label}: NOT IN OCR ---")
        return
    print(f"\n--- Page {p} {label} ---")
    print(f"TESS:  {repr(pg['tess_text'][:300])}")
    print(f"DOCTR: {repr(pg['doctr_text'][:300])}")

# Probe around the first few missing chapters
# Chapter 1: page_range 51-55, hi_ch=2 hi_page=55
# These might be before OCR starts (page 54 is first OCR page)
print("=== CHAPTER 1 region (pages 51-57) ===")
for p in range(51, 58):
    show_page(p, f"(ch1 region)")

print("\n\n=== CHAPTER 5,6,7 region (pages 57-63) ===")
for p in range(57, 64):
    show_page(p, f"(ch5-7 region)")
