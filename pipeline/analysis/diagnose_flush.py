"""diagnose_flush.py -- instrument the EXACT parse walk to see where each candidate
act-start (header_starts_act==True) is dropped on its way to confident_acts.

Read-only. Re-implements parse_volume's walk but, instead of writing output, tallies
the drop reason for every flushed buffer using the same predicates the real flush_act uses:

  reasons (mutually exclusive, in flush_act's own order):
    buf_lt_60          full text < 60 chars
    header_is_appr     header line itself is an Approved/Passed line
    no_enact_marker    has_enact_marker(full) is False   <-- the big OCR-garble drop
    kept_flagged       survives flush, but not confident (no An Act, no date, len<100, or chap_int==0)
    kept_confident     lands in confident_acts

Also: for kept records, tally chap_int==0 (number misread to nothing) and chap_int>3000
(implausible / OCR-inflated number).

Usage: python -m analysis.diagnose_flush <label> [<label> ...]
"""
import sys, re, json
from pathlib import Path
import importlib.util
import config

_ING = Path(__file__).resolve().parent.parent / "ingest" / "ingest_from_ocr.py"
_spec = importlib.util.spec_from_file_location("ingest_from_ocr", str(_ING))
ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ing)
ROOT = Path(config.path_for("data_root"))


def classify(chap_token, buf, volume_year):
    """Mirror flush_act's gates and return (reason, chap_int)."""
    if not buf:
        return "empty", 0
    full = "\n".join(buf).strip()
    if len(full) < 60:
        return "buf_lt_60", 0
    header_line = re.sub(r"\s+", " ", buf[0]).strip()
    if re.search(r"\b(?:Approved|Passed)\b", header_line, re.I):
        return "header_is_appr", 0
    if not ing.has_enact_marker(full):
        return "no_enact_marker", 0
    chap_int = ing.parse_chapter_number(chap_token)
    confident = (ing.is_confident_act(full, volume_year=volume_year) and chap_int > 0)
    if confident:
        return "kept_confident", chap_int
    return "kept_flagged", chap_int


def walk(label):
    ocr_path = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(ocr_path.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    volume_year = int(re.match(r"(\d{4})", label).group(1))
    lines = []
    for pidx in sorted(pages.keys()):
        for line in pages[pidx].get("consensus_text", "").split("\n"):
            lines.append((pidx, line))

    tally = {}
    chap0 = chap_big = 0
    cur_token = None
    cur_buf = []
    def emit(token, buf):
        nonlocal chap0, chap_big
        reason, ci = classify(token, buf, volume_year)
        tally[reason] = tally.get(reason, 0) + 1
        if reason.startswith("kept"):
            if ci == 0:
                chap0 += 1
            elif ci > 3000:
                chap_big += 1
    for i, (pidx, line) in enumerate(lines):
        is_hdr, token = ing.header_starts_act(lines, i)
        if is_hdr:
            if cur_token is not None:
                emit(cur_token, cur_buf)
            cur_token, cur_buf = token, [line]
        elif cur_token is not None:
            cur_buf.append(line)
    if cur_token is not None:
        emit(cur_token, cur_buf)

    print(f"\nVOLUME {label}")
    total = sum(tally.values())
    for r in ("buf_lt_60", "header_is_appr", "no_enact_marker", "kept_flagged", "kept_confident"):
        print(f"  {r:<18} {tally.get(r,0):>5}")
    print(f"  {'TOTAL act-starts':<18} {total:>5}")
    print(f"  kept w/ chap_int==0 (number unreadable): {chap0}")
    print(f"  kept w/ chap_int>3000 (OCR-inflated num): {chap_big}")


def main():
    for label in sys.argv[1:]:
        walk(label)


if __name__ == "__main__":
    main()
