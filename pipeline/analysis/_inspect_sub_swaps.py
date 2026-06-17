"""_inspect_sub_swaps.py -- read-only: dump the suspect substitution pairs
(consensus header line vs engine header line) so we can confirm which side is the
GARBLED numeral. Writes nothing."""
from __future__ import annotations
import sys
from pathlib import Path
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_RC = Path(__file__).resolve().parents[1] / "ingest" / "recover_early_consensus.py"
_spec = importlib.util.spec_from_file_location("rec_consensus_insp", str(_RC))
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)
re_early = rc.re_early


def run(label, limit=12):
    pages = rc.load_pages(label)
    shown = 0
    for pidx in sorted(pages):
        page = pages[pidx]
        cons_lines = rc._engine_lines(page, "consensus_text")
        n_cons = len(cons_lines)
        eng_hdrs = rc._page_engine_headers(page)
        cons_hdr_idx = [i for i, ln in enumerate(cons_lines)
                        if rc.header_numeral(ln) is not None]
        eng_targets = [(cl, num, rc._norm_pos(ei, en)) for (cl, num, eng, ei, en) in eng_hdrs]
        cons_pos = [rc._norm_pos(ci, n_cons) for ci in cons_hdr_idx]
        used = set()
        for ci_rank, ci in enumerate(cons_hdr_idx):
            cpos = cons_pos[ci_rank]
            cands = [(abs(p - cpos), r) for r, (_l, _n, p) in enumerate(eng_targets)
                     if r not in used and abs(p - cpos) <= rc._POS_TOL]
            if not cands:
                continue
            cands.sort()
            bd, br = cands[0]
            if len(cands) > 1 and (cands[1][0] - bd) < 0.04:
                continue
            ep = eng_targets[br][2]
            if min(range(len(cons_pos)), key=lambda r: abs(cons_pos[r] - ep)) != ci_rank:
                continue
            used.add(br)
            cn = re_early.parse_chapter_numeral(rc.header_numeral(cons_lines[ci]))
            en_ = re_early.parse_chapter_numeral(eng_targets[br][1])
            if cn > 0 and abs(cn - en_) > 3 and shown < limit:
                print(f"  p{pidx} cons#{cn} -> eng#{en_}")
                print(f"      CONS: {cons_lines[ci][:90]!r}")
                print(f"      ENG : {eng_targets[br][0][:90]!r}")
                shown += 1
        if shown >= limit:
            break


if __name__ == "__main__":
    lab = sys.argv[1] if len(sys.argv) > 1 else "1865-66"
    print(f"== {lab} suspect substitution pairs ==")
    run(lab)
