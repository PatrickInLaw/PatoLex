"""Local unit tests for the pure cores of mojibake_fix and context_resolve. Injects synthetic
dictionaries / bigram models -- no wordfreq/nltk/corpus needed. Run with any Python 3."""
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")        # Windows console is cp1252 by default
except Exception: pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mojibake_fix import mojibake_candidates, choose_fix
from context_resolve import resolve
from collections import Counter

FAIL = 0
def check(name, got, exp):
    global FAIL
    ok = got == exp
    if not ok: FAIL += 1
    print(f"{'OK ' if ok else 'XX '}{name}: got {got!r}  exp {exp!r}")

# ---------- mojibake ----------
KNOWN = {"moneys", "assessor", "money", "cat", "cot", "cut", "sheriff", "estate", "county", "elise"}
def known(w): return w in KNOWN
# corpus-freq style score: prefer attested; here just rank by a synthetic freq map
# cat/cot/cut deliberately close (within 4x) -> c�t is genuinely ambiguous -> must DECLINE (route to context)
FREQ = {"moneys": 500, "assessor": 300, "money": 9000, "cat": 90, "cot": 70, "cut": 200,
        "sheriff": 400, "estate": 600, "county": 800}
def score(w): return FREQ.get(w, 0) + 0.0

# single-char span, one known fix
check("moj m�neys", sorted(mojibake_candidates("m�neys", known) or []), ["moneys"])
check("moj a�sessor", sorted(mojibake_candidates("a�sessor", known) or []), ["assessor"])
# ambiguous single char -> multiple known -> choose declines
cs = mojibake_candidates("c�t", known)
check("moj c�t candset", sorted(cs), ["cat", "cot", "cut"])
check("moj c�t choose(ambiguous)", choose_fix(cs, score), (None, True))
# unambiguous choose applies
check("moj choose moneys", choose_fix({"moneys"}, score), ("moneys", False))
# two non-ascii spans -> not a single-span mojibake -> None
check("moj two spans", mojibake_candidates("m�n�y", known), None)
# >2 char span -> too damaged -> None
check("moj 3-char span", mojibake_candidates("a���b", known), None)
# tier-2 (2-char span -> 1 real char): "mon"+ey = money via two-letter escalation
check("moj 2-char->money", sorted(mojibake_candidates("mon��", known) or []), ["money"])
# dominant-by-margin applies even with a weak runner-up (money 9000 vs cot 8)
check("moj choose dominant", choose_fix({"money", "cot"}, score), ("money", False))

# ---------- context resolve ----------
big = Counter({("the", "section"): 100, ("section", "of"): 80,
               ("the", "petition"): 2, ("petition", "of"): 1,
               ("board", "control"): 30, ("control", "of"): 40,
               ("board", "central"): 0, ("central", "of"): 0})
# clear winner: "the [sectiou] of" -> section
check("ctx section>petition", resolve(["section", "petition"], "the", "of", big),
      ("section", "resolved"))
# clear winner via collocation: "board [contrcl] of" -> control
check("ctx control>central", resolve(["control", "central"], "board", "of", big),
      ("control", "resolved"))
# no attestation at all -> no_ctx
check("ctx no_ctx", resolve(["section", "petition"], "zzz", "qqq", big),
      (None, "no_ctx"))
# tie: both equally attested within margin
big2 = Counter({("a", "lien"): 10, ("lien", "b"): 10, ("a", "line"): 10, ("line", "b"): 10})
check("ctx tie", resolve(["lien", "line"], "a", "b", big2), (None, "tie"))

print(f"\n{'ALL PASS' if FAIL == 0 else str(FAIL) + ' FAILED'}")
sys.exit(1 if FAIL else 0)
