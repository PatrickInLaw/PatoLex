import json, re, sys
from pathlib import Path
root = Path(r'C:\Users\PatrickKolasinski\PatoLex-scratch')
ORACLE={'1850':146,'1851':139,'1852':202,'1853':180,'1854':71,'1855':231,'1856':152,
 '1857':277,'1858':358,'1859':330,'1860':455,'1861':538,'1862':455,'1863-64':476,
 '1865-66':280,'1867-68':545,'1869-70':583,'1871-72':637,'1873-74':679,'1875-76':613}

ANACT = re.compile(r'\b[Adl][nuy]\s+A[CEO][TI]\b', re.I)          # An/Ay/dn Act
ANACT_FUZZY = re.compile(r'\b[Adl][nuy]\s+[AsdБ][a-z]{1,4}\b')    # An slet / dn det
# enacting clause (very tolerant) -- the TOC-discriminating marker
ENACT = re.compile(r"P[eo]{1,2}ple\s+of\s+the\s+Stat[eo]\s+of\s+Calif|d[ouae]\s+[ceu][nu][aou][crt]t?\s+a[sx]\s+f[oi]l?l?[oi]w", re.I)
_MON = r"(?:Jan|Feb|Mar|Apr|May|Mav|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
APPR_BRK = re.compile(r"[\[\(\{]\s*A[Pp]{1,3}[Rr]?[Oo]?[Vv]\w{0,5}", re.I)

# Unified chapter-header line: starts with glyph family (C-word incl CHAPTER),
# optional sep, a numeral-ish token, then EITHER a dash+title OR (near end of line).
GLYPH = r"C[a-z]{1,7}"
NUM = r"[A-Za-z0-9!|\]\[. ]{0,13}"
# joined: glyph num dash title
HDR_JOINED = re.compile(r"^[\s.,;:'\"]{0,3}" + GLYPH + r"[.,]?\s*" + NUM + r"[—–]\s*(.+)$", re.I)
# stacked: glyph + numeral, little else after (the title is on following lines)
HDR_STACK = re.compile(r"^[\s.,;:'\"]{0,3}(" + GLYPH + r")[.,]?\s*([IVXLCDMivxlcdmJTYjty0-9!|\]\[lo]{1,7})\s*[.,]?\s*$", re.I)
# prose C-words that are never a chapter glyph in stacked form
PROSE_C = re.compile(r"^(county|court|city|contents|certi|civil|const|comm|compan|coast|colo)", re.I)
BODYREF_HDRLINE = re.compile(r"of\s+an\s+act\b|said\s+act\b|provisions?\s+of\s+(the|an)\s+act", re.I)
OPEN_Q = "\"'“‘`’”«»"

def anact_at(lines, i, n=4):
    for j in range(i, min(len(lines), i+n)):
        if ANACT.search(lines[j]) or ANACT_FUZZY.search(lines[j]):
            return True
    return False

def marker_ahead(lines, i, n=16):
    enact = False
    for j in range(i, min(len(lines), i+n)):
        if ENACT.search(lines[j]):
            enact = True; break
    return enact

def appr_ahead(lines, i, n=8):
    # an [Approved...] bracket on a line AFTER the header line (j>i), not the header itself
    for j in range(i+1, min(len(lines), i+n)):
        if APPR_BRK.search(lines[j]):
            return True
    return False

def detect(label, require_enact=True):
    p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
    raw = json.loads(p.read_text(encoding='utf-8'))
    pages = {int(k): v for k, v in raw.items()}
    lines=[]
    for pidx in sorted(pages):
        for ln in pages[pidx].get('consensus_text','').split('\n'):
            lines.append(ln)
    out=[]; last=-9
    for i,t in enumerate(lines):
        s=t.strip()
        is_hdr=False
        mj=HDR_JOINED.match(s)
        if mj:
            title=mj.group(1)
            # An Act must be in the title part (after the dash) -- same line
            if ANACT.search(title) or ANACT_FUZZY.match(title.strip()):
                if not (BODYREF_HDRLINE.match(title.strip())):
                    # opening quote right before An Act -> quoted cited title
                    am=ANACT.search(title) or ANACT_FUZZY.search(title)
                    head=title[:am.start()].rstrip()
                    if not (head and head[-1] in OPEN_Q):
                        is_hdr=True
        if not is_hdr:
            ms=HDR_STACK.match(s)
            if ms and not PROSE_C.match(ms.group(1)) and anact_at(lines, i+1, 3):
                is_hdr=True
        if not is_hdr:
            continue
        # marker gate: enacting clause within 16 lines (TOC-discriminating).
        # Fallback: an [Approved] bracket on a SEPARATE line below (for sessions
        # whose enact clause OCR'd too garbled), but NOT the dense-TOC case.
        ok = marker_ahead(lines, i) or appr_ahead(lines, i)
        if not ok:
            continue
        if i-last>=2:
            out.append(i); last=i
    return out

if '--show' in sys.argv:
    label=sys.argv[1]
    p = root/('production-'+label)/'ocr_consensus'/'page_ocr_results.json'
    raw = json.loads(p.read_text(encoding='utf-8'))
    pages={int(k):v for k,v in raw.items()}
    lines=[]
    for pidx in sorted(pages):
        for ln in pages[pidx].get('consensus_text','').split('\n'):
            lines.append((pidx,ln))
    flat=[t for _,t in lines]
    out=detect(label)
    for i in out[:40]:
        print(f"pg{lines[i][0]:>4} | {flat[i].strip()[:95]}")
    sys.exit()

for label in sys.argv[1:]:
    out=detect(label)
    N=ORACLE.get(label,0)
    print(f"{label}: detected={len(out)}  oracle={N}  {100.0*len(out)/N if N else 0:.0f}%")
