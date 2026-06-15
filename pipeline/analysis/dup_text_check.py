"""dup_text_check.py -- precision guard: detect FALSE SPLITS where the recovery created
two confident acts from the same underlying act (e.g. a spurious 'An act' line mid-body
split one act in two). Heuristic: adjacent confident acts (by source_page then number)
whose title texts are near-identical, or where a recovered act's title is a substring of
a neighbor, are suspect. Also flags confident acts with suspiciously short text.
Usage: python -m analysis.dup_text_check <label> [<label> ...]"""
import sys, json, re
from pathlib import Path
import config
ROOT = Path(config.path_for("data_root"))

def norm(t):
    return re.sub(r"[^a-z0-9 ]", "", (t or "").lower())[:120]

def main():
    acts = []
    for label in sys.argv[1:]:
        d = json.loads((ROOT / ("production-" + label) / "parsed_acts_recovered.json").read_text(encoding="utf-8"))
        for a in d["confident_acts"]:
            a["_label"] = label
            acts.append(a)
    acts.sort(key=lambda a: (a["_label"], a.get("source_page", 0), a.get("chapter_int", 0)))
    dup_titles = 0
    short = 0
    examples = []
    for i in range(1, len(acts)):
        a, b = acts[i - 1], acts[i]
        ta, tb = norm(a.get("title")), norm(b.get("title"))
        if ta and tb and (ta == tb or (len(ta) > 30 and (ta in tb or tb in ta))):
            dup_titles += 1
            if len(examples) < 12:
                examples.append((a.get("chapter_int"), b.get("chapter_int"), a.get("source_page"), ta[:50]))
    for a in acts:
        if len(a.get("text", "")) < 120:
            short += 1
    print(f"confident acts: {len(acts)}")
    print(f"adjacent near-identical titles (possible false split): {dup_titles}")
    for ca, cb, pg, t in examples:
        print(f"  ch{ca} & ch{cb} p{pg}: {repr(t)}")
    print(f"confident acts with text < 120 chars (thin): {short}")

if __name__ == "__main__":
    main()
