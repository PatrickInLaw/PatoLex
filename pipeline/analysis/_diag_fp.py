"""Show the header lines recover_early detects, to find false positives /
over-segmentation. Prints the matched chap-marker line for each detected start."""
import sys
from pathlib import Path
sys.path.insert(0, r"C:\Users\PatrickKolasinski\Documents\GitHub\PatoLex\pipeline")
sys.path.insert(0, r"C:\Users\PatrickKolasinski\Documents\GitHub\PatoLex\pipeline\ingest")
import os
os.environ.setdefault("PATOLEX_LOCATION_ROOT", r"C:\Users\PatrickKolasinski\PatoLex-scratch")
import recover_early as re_mod

label = sys.argv[1]
lines = re_mod.load_lines(label)
starts = re_mod.detect_starts(lines)
print(f"{label}: {len(starts)} starts")
# print every matched header line + its parsed numeral; flag suspicious ones
prev_num = 0
for i,(li,tok) in enumerate(starts):
    s = lines[li][1].strip()
    num = re_mod.parse_chapter_numeral(tok)
    flag = ""
    if num and prev_num and num < prev_num:        # non-monotone -> suspicious
        flag = "  <== NON-MONOTONE"
    if num == 0:
        flag += "  [num=0]"
    print(f"  ord{i:>4} pg{lines[li][0]:>4} num={num:<5} tok={tok!r:<8} | {s[:90]}{flag}")
    if num: prev_num = num
