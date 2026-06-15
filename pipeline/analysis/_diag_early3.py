"""Test the proposed early-era act-start detector and score vs oracle totals.
Detector logic (header-free, position-free):
  An act starts at a CHAPTER-MARKER line:  ^<chap-glyph><sep><numeral><dash-or-EOL>
  corroborated by an "An Act" title on the SAME line OR within 2 lines below,
  AND an act-marker (enacting clause OR [Approved date]) within ANCHOR lines below.
Reject body refs: 'of an act', 'entitled', a quote before 'An act', text before chap glyph.
"""
import json, sys, re
from pathlib import Path

root = Path(r'C:\Users\PatrickKolasinski\PatoLex-scratch')
ORACLE = {'1850':146,'1851':139,'1852':202,'1853':180,'1854':71,'1855':231,'1856':152,
          '1857':277,'1858':358,'1859':330,'1860':455,'1861':538,'1862':455,'1863-64':476,
          '1865-66':280,'1867-68':545,'1869-70':583,'1871-72':637,'1873-74':679,'1875-76':613,
          '1863':476}

# Chapter-marker glyph: C/c then 2-6 letters from the OCR variants seen
# (Cuap, Cuarrer, Coarrer, Crap, Ciap, Chap, Chapter). Require it be a word
# that STARTS the line, then a marker-internal '.' OR whitespace, then a numeral.
# Numeral token: roman (I V X L C D M + OCR subs J T Y 1 ! | l) or arabic, len<=7.
CHAP = re.compile(
    r"^[\s.,;:'\"\-]{0,4}"
    r"(c(?:uarrer|oarrer|hapter|uap|hap|rap|iap|nap|lap)t?\.?)"
    r"\s*"
    r"([ivxlcdmJjTtYy0-9!|l]{1,7})"
    r"\s*[.,;:�\-]",   # numeral followed by punctuation / dash / OCR junk
    re.I)
# An Act title (very tolerant for garble): An/dn/ln + space + (A/s/d-led short word)
ANACT = re.compile(r"\b[AdДl][nun]\s+[AdsБ][a-z]{1,4}\b", re.I)   # An Act / An slet / dn det / ln lect
ANACT_STRICT = re.compile(r"\bAn?\s+A[CEO][TI]\b", re.I)
ENACT = re.compile(r"d[ouae]\s+[ceu][nu][aou][crt]t?\s+a[sx]\s+f[oi]ll?[oi]w", re.I)  # 'do enact as follows' garble
APPR = re.compile(r"[\[\(\{].{0,4}A[Pp]{1,3}[Rr]?[Oo]?[Vv]\w{0,4}", re.I)
APPR2 = re.compile(r"\b(?:A[Pp]{1,3}[Rr]?[Oo]?[Vv]\w{0,4}|Pass\w{0,3})\s+.{0,3}(?:Jan|Feb|Mar|Apr|May|Mav|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", re.I)
BODYREF = re.compile(r"of\s+an\s+act|entitled|said\s+act|provisions?\s+of", re.I)

def marker_ahead(lines, i, n=8):
    for j in range(i, min(len(lines), i+n)):
        t = lines[j]
        if ENACT.search(t) or APPR.search(t) or APPR2.search(t):
            return True
    return False

def has_anact(lines, i):
    for j in range(i, min(len(lines), i+3)):
        if ANACT_STRICT.search(lines[j]) or ANACT.search(lines[j]):
            return True
    return False

for label in sys.argv[1:]:
    p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
    raw = json.loads(p.read_text(encoding='utf-8'))
    pages = {int(k): v for k, v in raw.items()}
    lines = []
    for pidx in sorted(pages):
        for ln in pages[pidx].get('consensus_text','').split('\n'):
            lines.append(ln)
    starts = []
    for i, t in enumerate(lines):
        s = t.strip()
        m = CHAP.match(s)
        if not m:
            continue
        if BODYREF.search(s):
            continue
        if not has_anact(lines, i):
            continue
        if not marker_ahead(lines, i):
            continue
        # dedup: not within 2 lines of a previous start
        if starts and i - starts[-1] < 2:
            continue
        starts.append(i)
    N = ORACLE.get(label, 0)
    pct = 100.0*len(starts)/N if N else 0
    print(f"{label}: detected={len(starts)}  oracle={N}  -> {pct:.0f}%")
