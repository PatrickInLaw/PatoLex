"""Probe all missing chapter regions - full text scan."""
import pathlib
import json
import re

ocr_file = pathlib.Path(r'C:\PatoLex-scratch\production-1850\ocr_consensus\page_ocr_results.json')
with open(ocr_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

def get_page(p):
    return data.get(str(p))

def show_chap_headers(p):
    """Show chapter headers found on a page."""
    pg = get_page(p)
    if not pg:
        return None, None
    tess = pg.get('tess_text','')
    doctr = pg.get('doctr_text','')
    cons = pg.get('consensus_text','')

    # Find chapter headers
    pat = re.compile(r'(?:Chap\.|Chapter|CHAP\.)\s*([IVXLCDM]+|\d+)\.?', re.IGNORECASE)

    results = {}
    for engine, text in [('tess', tess), ('doctr', doctr), ('cons', cons)]:
        matches = pat.findall(text)
        if matches:
            results[engine] = matches

    # Also look for "An Act" titles
    act_pat = re.compile(r'AN ACT[^\n]{0,120}', re.IGNORECASE)
    acts = act_pat.findall(tess + '\n' + doctr)

    return results, acts

# Target page ranges from manifest
missing_chapters = [
    (1, 51, 58),      # ch1: pages 51-57 (mostly pre-OCR)
    (5, 57, 63),      # ch5,6,7
    (13, 66, 77),     # ch13-17
    (22, 84, 90),     # ch22
    (30, 95, 106),    # ch30,31,32
    (35, 106, 112),   # ch35
    (37, 110, 113),   # ch37
    (45, 128, 133),   # ch45
    (47, 131, 140),   # ch47
    (51, 141, 147),   # ch51
    (53, 145, 157),   # ch53
    (55, 155, 162),   # ch55
    (58, 161, 166),   # ch58
    (64, 169, 179),   # ch64,65
    (78, 206, 210),   # ch78
    (92, 227, 231),   # ch92
    (94, 229, 233),   # ch94,95
    (104, 264, 269),  # ch104
    (107, 268, 272),  # ch107
    (111, 274, 282),  # ch111,112
    (115, 276, 285),  # ch115
    (118, 283, 287),  # ch118
    (122, 342, 350),  # ch122
    (125, 350, 355),  # ch125
    (127, 353, 359),  # ch127
    (129, 357, 416),  # ch129
    (132, 416, 420),  # ch132
    (141, 434, 440),  # ch141
    (145, 468, 471),  # ch145
]

print("Chapter header scan (±2 pages of expected range):\n")
for (ch_start, lo, hi) in missing_chapters:
    print(f"=== Region starting ch{ch_start} pages {lo}-{hi} ===")
    for p in range(max(54, lo-2), min(478, hi+3)):
        hdrs, acts = show_chap_headers(p)
        if hdrs or acts:
            print(f"  p{p}: headers={hdrs}")
            if acts:
                for a in acts[:2]:
                    print(f"       act: {repr(a[:80])}")
