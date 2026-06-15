"""validate_recovery.py -- BEFORE vs AFTER scoring for the recovery pass.

For one or more physical volumes of a session, compare parsed_acts_fixed.json (baseline)
against parsed_acts_recovered.json (recovered) and score completeness vs a known true
total. Reports acts extracted, distinct chapters, max, count still-missing, duplicates,
and recovery-introduced precision risks.

Usage:
  python -m analysis.validate_recovery --true 2424 1957-vol1-57chapters 1957-vol2-57chapters
"""
import sys, json
from pathlib import Path
import config

ROOT = Path(config.path_for("data_root"))
CEIL = 2500  # matches recover_acts.CA_HARD_CEILING (1957 truly reaches ch. 2424)


def load(label, fname):
    p = ROOT / ("production-" + label) / fname
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def chap_list(data, key="confident_acts", field="chapter_int"):
    out = []
    for a in data.get(key, []):
        c = a.get(field, 0)
        if isinstance(c, str):
            c = int(c) if c.isdigit() else 0
        out.append(c)
    return out


def score(name, chaps, true_total):
    plausible = [c for c in chaps if 1 <= c <= CEIL]
    distinct = sorted(set(plausible))
    present = set(distinct)
    cmax = distinct[-1] if distinct else 0
    target = true_total or cmax
    missing = [n for n in range(1, target + 1) if n not in present]
    dupes = len(plausible) - len(distinct)
    inflated = sum(1 for c in chaps if c > CEIL)
    zero = sum(1 for c in chaps if c == 0)
    print(f"  [{name}]")
    print(f"    acts (chap rows) ...... {len(chaps)}")
    print(f"    plausible (1..{CEIL}) .... {len(plausible)}")
    print(f"    distinct chapters ..... {len(distinct)}")
    print(f"    max chapter ........... {cmax}")
    print(f"    duplicates ............ {dupes}")
    print(f"    inflated (>{CEIL}) ...... {inflated}")
    print(f"    chap_int==0 ........... {zero}")
    print(f"    MISSING vs {target} ...... {len(missing)}")
    return {"distinct": len(distinct), "missing": len(missing), "dupes": dupes,
            "present": present, "max": cmax, "acts": len(chaps)}


def main():
    args = sys.argv[1:]
    true_total = None
    if "--true" in args:
        k = args.index("--true")
        true_total = int(args[k + 1]); del args[k:k + 2]
    labels = args

    base_all, rec_conf_all, rec_flag_all = [], [], []
    for label in labels:
        b = load(label, "parsed_acts_fixed.json")
        r = load(label, "parsed_acts_recovered.json")
        if b:
            base_all += chap_list(b, "confident_acts")
        if r:
            rec_conf_all += chap_list(r, "confident_acts")
            rec_flag_all += chap_list(r, "flagged_acts")

    print("=" * 70)
    print("SESSION:", " + ".join(labels), " true_total =", true_total)
    print("\nBEFORE (baseline parsed_acts_fixed.json, confident):")
    sb = score("baseline-confident", base_all, true_total)
    print("\nAFTER (recovered parsed_acts_recovered.json, confident):")
    sr = score("recovered-confident", rec_conf_all, true_total)
    print("\nAFTER (recovered, confident + flagged together):")
    srf = score("recovered-all", rec_conf_all + rec_flag_all, true_total)

    print("\n" + "-" * 70)
    print("DELTA (confident):")
    print(f"  distinct chapters: {sb['distinct']} -> {sr['distinct']}  (+{sr['distinct']-sb['distinct']})")
    print(f"  missing vs {true_total}: {sb['missing']} -> {sr['missing']}  ({sr['missing']-sb['missing']:+d})")
    print(f"  duplicates: {sb['dupes']} -> {sr['dupes']}  ({sr['dupes']-sb['dupes']:+d})")
    if true_total:
        gap0 = sb["missing"]
        recovered = sb["missing"] - sr["missing"]
        pct = 100.0 * recovered / gap0 if gap0 else 0.0
        print(f"  gap recovered: {recovered} of {gap0} ({pct:.1f}% of the original gap)")
        # newly-present chapters (precision: were any 'recovered' numbers spurious?)
        new = sr["present"] - sb["present"]
        lost = sb["present"] - sr["present"]
        print(f"  chapters newly present: {len(new)}  | chapters LOST vs baseline: {len(lost)}")
        if lost:
            ll = sorted(lost)
            print(f"    lost sample: {ll[:25]}")


if __name__ == "__main__":
    main()
