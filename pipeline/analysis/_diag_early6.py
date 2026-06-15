"""Candidate v2 detector for recover_early -- precision-first, dash-joined FORM-A
primary + strict glyph family + real-numeral gate. Scores vs oracle and (with
--show) prints detected header lines so precision can be eyeballed.

  python _diag_early6.py <label> [label...]
  python _diag_early6.py --show <label>
"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
ROOT = Path(config.path_for("data_root"))
ORACLE = {'1857':277,'1858':358,'1859':330,'1860':455,'1861':538,'1862':455,
          '1863-64':476,'1863':476,'1865-66':280,'1867-68':545,'1869-70':583,
          '1871-72':637,'1873-74':679,'1875-76':613,'1877-78':673}

_DASH = r"—–\-‐‑‒―~"
# STRICT chapter-glyph family: C + a SHORT abbrev body that is a real chapter word
# OCR variant, NOT an arbitrary C-word. Allowed bodies (case-insens):
#   hap/uap/rap/iap/nap/lap/oap/aap  (Chap/Cuap/Crap/Ciap/Cnap...)
#   uav/uar/har/nar/oar              (Cuav/Cuar tails)
#   hapter/uarrer/oarrer/hapt        (Chapter/Cuarrer long forms)
#   ap                               (Cap. abbreviation)
GLYPH = (r"C(?:hapter|uarrer|oarrer|hapt|hap|uap|rap|iap|nap|lap|oap|aap"
         r"|uav|uar|har|nar|oar|ap)r?t?")
# real numeral token: contains >=1 roman letter (incl OCR subs J T) OR a digit.
NUMTOK = r"[IVXLCDMivxlcdmJjTt0-9!|\]\[lO]{1,9}"
AN_ACT = re.compile(r"\bAn?\s+A[CEO][TI]\b", re.I)
AN_ACT_FUZZY = re.compile(r"\b[AÄdl][nu]\s+A[a-z]{1,4}\b")
# FORM-A joined: ^ glyph [sep] numeral [punct] DASH ... An Act
# Allow punctuation (.,;:) AND/OR a dash between the numeral and the title; the
# real separator OCRs as "VIII.—" / "I.--" / "L.-" / "XXI,—" etc.
FORMA = re.compile(
    r"^[\s.,;:'\"`]{0,4}(" + GLYPH + r")\.?\s*(" + NUMTOK + r")\s*[.,;:]?\s*[" + _DASH + r"]+\s*(.*)$",
    re.I)
# RELAXED FORM-A glyph: any short C-word (<=6 letters) as the glyph. SAFE here because
# the numeral + dash + "An Act" triad is the precision guarantee -- a prose C-word
# ("County", "Court") is not followed by a roman/arabic numeral + em-dash + "An Act".
GLYPH_LOOSE = r"C[a-zA-Z]{1,6}"
FORMA_LOOSE = re.compile(
    r"^[\s.,;:'\"`]{0,4}(" + GLYPH_LOOSE + r")[.,]?\s*(" + NUMTOK + r")\s*[.,;:]?\s*[" + _DASH + r"]+\s*(.*)$",
    re.I)
# FORM-B / dashless: ^ glyph [sep] numeral, then optional trailing junk (no dash
# required). An-Act must follow within a couple lines OR be later on the SAME line.
FORMB = re.compile(
    r"^[\s.,;:'\"`]{0,4}(" + GLYPH + r")\.?\s*(" + NUMTOK + r")\b\s*[.,;:]?\s*(.*)$", re.I)
BODYREF = re.compile(
    r"of\s+an\s+act\b|\bentitled\b|\bsaid\s+act\b|provisions?\s+of\s+(?:the\s+|an\s+)?act"
    r"|under\s+an\s+act|amendatory\s+of\s+an\s+act|supplement\w*\s+to\s+an\s+act", re.I)
_OPENQ = "\"'“‘„‚«‹`’”›»"
_ROMAN = set("IVXLCDM")

def numeral_ok(tok):
    # accept if it contains a real roman char (incl OCR subs J/T/!/|/]/[ for I) or a digit
    return any(c in _ROMAN for c in tok.upper()) or any(c.isdigit() for c in tok)

def anact_within(lines, i, n):
    """An Act within the next n NON-BLANK lines (blank/running-header lines skipped)."""
    seen = 0
    j = i
    while j < len(lines) and seen < n:
        t = lines[j][1]
        if t.strip():
            if AN_ACT.search(t) or AN_ACT_FUZZY.search(t):
                return True
            seen += 1
        j += 1
    return False

def quoted_before(seg, am):
    head = seg[:am.start()].rstrip(" \t")
    return bool(head) and head[-1] in _OPENQ

def detect(label):
    p = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    lines = []
    for pidx in sorted(pages):
        for ln in pages[pidx].get("consensus_text", "").split("\n"):
            lines.append((pidx, ln))
    out = []; last = -9
    for i, (pidx, t) in enumerate(lines):
        s = t.strip()
        hit = None
        ma = FORMA_LOOSE.match(s)
        if ma and numeral_ok(ma.group(2)):
            title = ma.group(3)
            am = AN_ACT.search(title) or AN_ACT_FUZZY.search(title)
            # NOTE: do NOT blanket-reject on BODYREF here. A genuine chapter header
            # ("Crap. XXI.—An Act to amend an Act entitled ...") legitimately contains
            # "entitled"/"of an act" in its OWN title. The structural proof (strict
            # glyph + real numeral + dash + An Act) IS the act start. We only reject a
            # QUOTED title (opening quote right before "An Act"), the true citation cue.
            if am and not quoted_before(title, am):
                hit = (ma.group(1), ma.group(2))
        if hit is None:
            mb = FORMB.match(s)
            if mb and numeral_ok(mb.group(2)):
                rest = mb.group(3)
                am = AN_ACT.search(rest) or AN_ACT_FUZZY.search(rest)
                if am:                       # An Act later on the SAME line (dashless)
                    if not BODYREF.search(s) and not quoted_before(rest, am):
                        hit = (mb.group(1), mb.group(2))
                elif not rest.strip() and anact_within(lines, i + 1, 3):
                    # glyph+numeral ALONE on the line -> An Act on next lines (split form)
                    hit = (mb.group(1), mb.group(2))
        if hit is None:
            continue
        if i - last < 2:
            continue
        out.append((i, hit, pidx))
        last = i
    return out, lines

if "--show" in sys.argv:
    sys.argv.remove("--show")
    label = sys.argv[1]
    out, lines = detect(label)
    print(f"{label}: {len(out)} detected  oracle={ORACLE.get(label,0)}")
    for k, (i, (g, n), pg) in enumerate(out):
        print(f"  o{k:>4} pg{pg:>4} g={g!r:<10} n={n!r:<10}| {lines[i][1].strip()[:80]}")
    sys.exit()

for label in sys.argv[1:]:
    out, _ = detect(label)
    N = ORACLE.get(label, 0)
    print(f"{label:<10} detected={len(out):>5} oracle={N:>5} {100.0*len(out)/N if N else 0:>5.0f}%")
