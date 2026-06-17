"""Probe the 'fires_but_dropped_downstream' bucket: header_starts_act fires but
flush_act drops the act. Determine WHICH gate dropped it (enact marker garbled,
header has Approved/Passed, text<60). READ-ONLY. Run on 5090."""
import sys, re, json
from pathlib import Path
import importlib.util
import config

_here = Path(__file__).resolve().parent
_ING = next(p for p in [_here / "ingest_from_ocr.py",
                        _here / "ingest" / "ingest_from_ocr.py"] if p.exists())
_spec = importlib.util.spec_from_file_location("ingest_from_ocr", str(_ING))
ing = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ing)
ROOT = Path(config.path_for("data_root"))


def load_lines(label):
    p = ROOT / ("production-" + label) / "ocr_consensus" / "page_ocr_results.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    pages = {int(k): v for k, v in raw.items()}
    lines = []
    for pidx in sorted(pages.keys()):
        for line in pages[pidx].get("consensus_text", "").split("\n"):
            lines.append((pidx, line))
    return lines


def main():
    for label in (sys.argv[1:] or ["1931-vol1-chapters", "1933-vol1-chapters"]):
        lines = load_lines(label)
        # walk production-style; for each header that fires, build buf to next header,
        # and record which flush_act gate would drop it.
        starts = []
        for i in range(len(lines)):
            is_hdr, tok = ing.header_starts_act(lines, i)
            if is_hdr:
                starts.append((i, tok))
        drop_reasons = {}
        enact_garble_examples = []
        for k, (si, tok) in enumerate(starts):
            ei = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
            buf = [lines[j][1] for j in range(si, ei)]
            full = "\n".join(buf).strip()
            reason = None
            if len(full) < 60:
                reason = "text_lt_60"
            elif re.search(r"\b(?:Approved|Passed)\b", re.sub(r"\s+", " ", buf[0]), re.I):
                reason = "header_line_has_approved"
            elif not ing.has_enact_marker(full):
                reason = "no_enact_marker"
            if reason:
                drop_reasons[reason] = drop_reasons.get(reason, 0) + 1
                if reason == "no_enact_marker" and len(enact_garble_examples) < 4:
                    # show whether a near-miss 'do enact' / 'People of the State' exists
                    snip = [ln for ln in buf if re.search(r"enact|peopl|californ", ln, re.I)][:3]
                    enact_garble_examples.append(
                        {"chapter_tok": tok, "src_page": lines[si][0] + 1,
                         "header": re.sub(r"\s+", " ", buf[0]).strip(),
                         "enactish_lines": snip})
        print(json.dumps({
            "label": label,
            "total_fires": len(starts),
            "drop_reasons": drop_reasons,
            "enact_garble_examples": enact_garble_examples,
        }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
