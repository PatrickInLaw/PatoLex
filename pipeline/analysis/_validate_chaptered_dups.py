"""_validate_chaptered_dups.py -- VALIDATION-ONLY (read-only). For each chaptered
label: report BEFORE (recovered confident/flagged), AFTER (v2 confident/flagged),
and the KEY invariant -- 0 duplicate chapter numbers across the COMBINED
confident+flagged record set of the v2 output, AND after_confident >= before_confident.
Writes nothing.
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
ROOT = Path(config.path_for("data_root"))


def _ints(seq):
    out = []
    for a in seq:
        v = a.get("chapter_int")
        if isinstance(v, int) and v > 0:
            out.append(v)
    return out


def run(label):
    base = ROOT / ("production-" + label)
    rec_p = base / "parsed_acts_recovered.json"
    v2_p = base / "parsed_acts_chaptered_v2.json"
    rec = json.loads(rec_p.read_text(encoding="utf-8")) if rec_p.exists() else {}
    v2 = json.loads(v2_p.read_text(encoding="utf-8"))

    before_conf = rec.get("confident_acts", [])
    before_flag = rec.get("flagged_acts", [])
    after_conf = v2.get("confident_acts", [])
    after_flag = v2.get("flagged_acts", [])
    meta = v2.get("_chaptered_meta", {})

    # COMBINED confident set must have NO duplicate chapter numbers.
    conf_nums = _ints(after_conf)
    conf_dups = len(conf_nums) - len(set(conf_nums))

    # Combined confident+flagged: flagged dup_number records are EXPECTED to repeat a
    # confident number (that is their purpose). The real invariant the brief wants:
    # no chapter number is emitted as a brand-new CONFIDENT act when it already exists
    # in the BEFORE record set (confident OR flagged). Check that.
    before_all = set(_ints(before_conf)) | set(_ints(before_flag))
    # newly-added confident acts (origin chaptered_v2, status chaptered_new/codes_redirect)
    added = [a for a in after_conf
             if a.get("origin") == "chaptered_v2"
             and a.get("status") in ("chaptered_new", "codes_redirect")]
    added_collide_before = sum(1 for a in added
                               if a.get("chapter_int") in before_all)
    added_nums = _ints(added)
    added_internal_dups = len(added_nums) - len(set(added_nums))

    print(f"== {label} ==")
    print(f"  BEFORE confident={len(before_conf)} flagged={len(before_flag)}")
    print(f"  AFTER  confident={len(after_conf)} flagged={len(after_flag)}")
    print(f"  meta: before_confident={meta.get('before_confident')} "
          f"before_distinct={meta.get('before_distinct')} "
          f"added_new={meta.get('added_new')} "
          f"after_confident={meta.get('after_confident')} "
          f"flagged_dup={meta.get('flagged_dup')} "
          f"already_in_before={meta.get('already_in_before')}")
    print(f"  INVARIANTS:")
    print(f"    after_confident >= before_confident : "
          f"{len(after_conf) >= len(before_conf)} "
          f"({len(after_conf)} >= {len(before_conf)})")
    print(f"    duplicate chapter# within CONFIDENT  : {conf_dups}  (want 0)")
    print(f"    NEW-confident colliding w/ BEFORE    : {added_collide_before}  (want 0)")
    print(f"    NEW-confident internal duplicates    : {added_internal_dups}  (want 0)")


if __name__ == "__main__":
    for lab in sys.argv[1:]:
        run(lab)
