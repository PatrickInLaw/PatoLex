"""
check_golden_master.py -- regression gate for the deterministic correction cascade.

Compares a fresh cascade report against tests/golden_master_cascade.json. The deterministic stages
(reunify + split + edit-1-strict) MUST reproduce the locked numbers EXACTLY; a diff is a refactor
regression. SymSpell es1/es2 corrections are IGNORED here (they route to adjudication, not auto-apply),
so this gate stays valid even when the cascade also emits SymSpell candidates.

Usage:
  python check_golden_master.py [path/to/cascade_report.json]
Default report path: <scratch>/_cascade/cascade_report.json on the 5090, or pass it explicitly.
Exit 0 = matches (no regression); exit 1 = mismatch (prints every diff).
"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "golden_master_cascade.json")
DEFAULT_REPORT = r"C:\Users\patolex\PatoLex-scratch\_cascade\cascade_report.json"

# only these correction keys are deterministic/auto-applied (SymSpell es1/es2 deliberately excluded)
DET_CORRECTION_KEYS = ["reunify_space", "reunify_break", "reunify_xpage", "reunify_window",
                       "split", "autocorrect_e1"]
STAGES = ["raw", "after_reunify", "after_split", "after_autocorrect"]
RESID_KEYS = ["garbage", "roman", "recoverable"]
RULE_KEYS = ["garbage_repeat4", "garbage_cons5", "garbage_repeat3", "garbage_toolong", "garbage_mojibake"]

def main():
    report_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REPORT
    if not os.path.exists(report_path):
        print(f"FAIL: report not found: {report_path}"); return 1
    g = json.load(open(GOLDEN, encoding="utf-8"))
    r = json.load(open(report_path, encoding="utf-8"))
    diffs = []

    def cmp(label, exp, got):
        if exp != got:
            diffs.append(f"  {label}: expected {exp}, got {got}")

    sp = r.get("stage_progression", {})
    for s in STAGES:
        for f in ("flagged", "total", "rate_pct"):
            cmp(f"stage_progression.{s}.{f}", g["stage_progression"][s][f], sp.get(s, {}).get(f))

    sc = r.get("stage_corrections", {})
    for k in DET_CORRECTION_KEYS:
        cmp(f"stage_corrections.{k}", g["stage_corrections"][k], sc.get(k))

    rc = r.get("residual_classification", {})
    for k in RESID_KEYS:
        cmp(f"residual.{k}", g["residual_classification"][k], rc.get(k))
    br = rc.get("by_rule", {})
    for k in RULE_KEYS:
        cmp(f"residual.by_rule.{k}", g["residual_classification"]["by_rule"][k], br.get(k))

    if diffs:
        print(f"GOLDEN-MASTER MISMATCH ({len(diffs)} diffs) -- deterministic cascade changed:")
        print("\n".join(diffs))
        print("\nIf this was an intentional algorithm change (not a refactor), re-bless the golden master.")
        return 1
    print("GOLDEN-MASTER OK -- deterministic cascade reproduces the locked numbers exactly.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
