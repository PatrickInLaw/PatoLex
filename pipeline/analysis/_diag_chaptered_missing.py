"""READ-ONLY: characterize chaptered misses. (1) count redirect-note occurrences in
full text; (2) for missing chapters with NO header, search the text for 'CHAPTER <n>'
in ANY form (incl mid-line) to see if it's truly absent; (3) tabulate emitted by status.
Usage: python _diag_chaptered_missing.py <label> <oracleN>"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config, importlib.util

ROOT = Path(config.path_for("data_root"))
label = sys.argv[1]; N = int(sys.argv[2])
_RC = Path(__file__).resolve().parents[1] / "ingest" / "recover_chaptered.py"
spec = importlib.util.spec_from_file_location("rc", str(_RC)); rc = importlib.util.module_from_spec(spec); spec.loader.exec_module(rc)

lines = rc.load_lines(label)
fulltext = "\n".join(ln for (_p, ln, _k) in lines)

# (1) redirect notes anywhere
rn = rc.REDIRECT_NOTE_RE.findall(fulltext)
# broader: any "see Stats" / "For text" pointer
broad = re.findall(r"For\s+text|see\s+Stats|See\s+Stats|in\s+full\s+see", fulltext, re.I)
print(f"redirect-note (strict) hits: {len(rn)}; broad 'For text/see Stats' hits: {len(broad)}")

conf, flag, meta = rc.process_label(label)
from collections import Counter
print("emitted status counts:", Counter(a["status"] for a in conf + flag))
emitted_nums = {a["chapter_int"] for a in conf}

# (2) missing chapters with NO header at all: does 'CHAPTER <n>' appear in any line?
missing = [n for n in range(1, N + 1) if n not in emitted_nums]
no_header_anywhere = []
midline_only = []
for n in missing:
    pat = re.compile(r"\bCHAP(?:TER|T\.?|\.)?\s*" + str(n) + r"\b", re.I)
    found_lines = [i for i, (_p, ln, _k) in enumerate(lines) if pat.search(ln)]
    if not found_lines:
        no_header_anywhere.append(n)
    else:
        # is it ever at line head?
        head = any(rc.HEAD_RE.match(lines[i][1].strip()) for i in found_lines)
        if not head:
            midline_only.append(n)
print(f"missing total {len(missing)}: truly-absent (no 'CHAPTER n' anywhere)={len(no_header_anywhere)}; "
      f"appears only mid-line={len(midline_only)}")
print("sample truly-absent:", no_header_anywhere[:30])

# (3) show a few truly-absent: dump where chapter n-1 ends and n+1 begins to see the gap
print("\n--- a few truly-absent chapters: neighbor context ---")
for n in no_header_anywhere[:5]:
    # find emitted act for n-1
    print(f"[missing ch {n}] (looking for any '{n}' near a header gap)")
