"""_validate_early_backfill.py -- VALIDATION-ONLY (read-only) probe for the
recover_early_consensus.py CRITICAL-A1 / MAJOR-A1/A2 fixes. Writes nothing.

Checks, per label:
  (1) Every BACKFILLED header line is followed (within the same page block) by at
      least one consensus body line -> it can acquire a body, not a zero-body drop.
  (2) How many detected acts START on a backfilled header line AND clear the
      SANITY gate (real body + enact/approved) -> backfilled headers yield real acts.
  (3) Substitution sanity: for every substituted consensus header, the engine line
      it took carries a numeral whose value is within +-3 of the consensus header's
      own (display) numeral OR the consensus numeral was unparseable (garbled) --
      i.e. no wildly-wrong-rank numeral swaps.
"""
from __future__ import annotations
import sys
from pathlib import Path
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # pipeline/ on path

_RC = Path(__file__).resolve().parents[1] / "ingest" / "recover_early_consensus.py"
_spec = importlib.util.spec_from_file_location("rec_consensus_val", str(_RC))
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)
re_early = rc.re_early


def validate(label: str):
    corr, n_sub, n_backfill = rc.corrected_lines(label)
    # group by page to check "header followed by body within page"
    by_page = {}
    for k, (p, t, src) in enumerate(corr):
        by_page.setdefault(p, []).append((k, t, src))

    backfill_with_body = 0
    backfill_zero_body = 0
    for p, items in by_page.items():
        for pos, (k, t, src) in enumerate(items):
            if "backfill" not in src:
                continue
            # is there a non-empty consensus body line AFTER this within the page?
            has_body = any(bt.strip() and "backfill" not in bsrc
                           for (_bk, bt, bsrc) in items[pos + 1:])
            if has_body:
                backfill_with_body += 1
            else:
                backfill_zero_body += 1

    # detection: which act starts sit on a backfilled line + pass SANITY
    lines = [(pp, tt) for (pp, tt, _s) in corr]
    src_of = [ss for (_p, _t, ss) in corr]
    starts = re_early.detect_starts(lines)
    backfill_real_acts = 0
    for j, (si, tok, form) in enumerate(starts):
        ei = starts[j + 1][0] if j + 1 < len(starts) else len(lines)
        rec = re_early.build_act(lines, si, ei, tok, form, label, j)
        if len(rec["text"]) < re_early.SANITY_MIN_TEXT:
            continue
        if not (rec["has_enact"] or rec["has_approved"]):
            continue
        if "backfill" in src_of[si]:
            backfill_real_acts += 1

    # (3) substitution numeral sanity -- faithfully replay the SAME matching the
    #     production corrected_lines() uses, recording (consensus_numeral ->
    #     engine_numeral) for every substitution. A "wrong-rank" swap = the engine
    #     numeral differs from a PARSEABLE consensus numeral by > 3.
    sub_ok = sub_garbled_cons = sub_suspect = 0
    worst = (0, None)
    pages = rc.load_pages(label)
    for pidx in sorted(pages):
        page = pages[pidx]
        cons_lines = rc._engine_lines(page, "consensus_text")
        n_cons = len(cons_lines)
        eng_hdrs = rc._page_engine_headers(page)
        cons_hdr_idx = [i for i, ln in enumerate(cons_lines)
                        if rc.header_numeral(ln) is not None]
        eng_targets = []
        for clean_line, num, eng, eidx, en in eng_hdrs:
            epos = rc._norm_pos(eidx, en)
            eng_targets.append((clean_line, num, epos))
        cons_pos = [rc._norm_pos(ci, n_cons) for ci in cons_hdr_idx]
        used_eng = set()
        for ci_rank, ci in enumerate(cons_hdr_idx):
            cpos = cons_pos[ci_rank]
            cands = [(abs(epos - cpos), e_rank)
                     for e_rank, (_l, _n, epos) in enumerate(eng_targets)
                     if e_rank not in used_eng and abs(epos - cpos) <= rc._POS_TOL]
            if not cands:
                continue
            cands.sort()
            best_d, best_rank = cands[0]
            if len(cands) > 1 and (cands[1][0] - best_d) < 0.04:
                continue
            epos = eng_targets[best_rank][2]
            nearest_cons = min(range(len(cons_pos)),
                               key=lambda r: abs(cons_pos[r] - epos))
            if nearest_cons != ci_rank:
                continue
            used_eng.add(best_rank)
            cons_num = re_early.parse_chapter_numeral(rc.header_numeral(cons_lines[ci]))
            eng_num = re_early.parse_chapter_numeral(eng_targets[best_rank][1])
            if cons_num <= 0:
                sub_garbled_cons += 1            # consensus numeral unreadable -> engine wins, fine
            elif abs(cons_num - eng_num) <= 3:
                sub_ok += 1
            else:
                sub_suspect += 1
                if abs(cons_num - eng_num) > worst[0]:
                    worst = (abs(cons_num - eng_num), (pidx, cons_num, eng_num))

    print(f"{label:<10} sub={n_sub:>4} backfill={n_backfill:>4} "
          f"| backfill_with_body={backfill_with_body:>4} "
          f"backfill_zero_body={backfill_zero_body:>4} "
          f"| backfill_real_acts={backfill_real_acts:>4} "
          f"| sub_ok={sub_ok} garbled_cons={sub_garbled_cons} "
          f"SUSPECT_swaps={sub_suspect} worst={worst[1]}")


if __name__ == "__main__":
    for lab in sys.argv[1:] or ["1861", "1862", "1863-64", "1865-66"]:
        validate(lab)
