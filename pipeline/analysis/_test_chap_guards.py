"""Read-only unit checks for the MAJOR-B1 (Title-case Chapter guard) and
MAJOR-B3 (redirect-note tightening) fixes in recover_chaptered.py."""
import sys
from pathlib import Path
import importlib.util
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_RC = Path(__file__).resolve().parents[1] / "ingest" / "recover_chaptered.py"
spec = importlib.util.spec_from_file_location("recover_chaptered_test", str(_RC))
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

print("=== MAJOR-B1: is_header_line case guard ===")
b1 = [
    # (input, should_be_header?)
    ("CHAPTER 88.", True),
    ("CHAPTER 25,", True),
    ("CHAP. 17", True),
    ("CHAPTEH 4.", True),                    # all-caps OCR garble -> still a header
    ("Chapter 32.", False),                  # Title-case citation -> REJECT (the bug)
    ("Chapter 400. Laws of 1931", False),    # Title-case body line -> REJECT
    ("chapter 32, Statutes of 1911", False), # lowercase body ref -> REJECT
    ("...to repeal Chapter 32, Statutes", False),  # mid-sentence (also not line-head)
    ("Chap. 17", False),                     # Title-case "Chap." -> REJECT
]
b1_fail = 0
for s, want in b1:
    got = rc.is_header_line(s) is not None
    ok = (got == want)
    if not ok:
        b1_fail += 1
    print(f"  [{'OK ' if ok else 'FAIL'}] header={got!s:<5} want={want!s:<5} | {s!r}")

print("\n=== MAJOR-B3: REDIRECT_NOTE_RE ===")
b3 = [
    ("Note.--For text see Stats. 1933, Ch. 25.", True),     # genuine redirect note
    ("Note.--See Stats. 1933, Ch. 25.", True),              # genuine (terse)
    ("Norz.-For text see Stats. 1931, Ch. 4.", True),       # OCR-garbled Note token
    ("Notze. see Stats. 1933, Ch. 88.", True),              # OCR-garbled Note token
    ("No. 14 see Stats. 1933", False),                      # body footnote "No." -> REJECT
    ("No. see Stats. 1933, Ch. 4.", False),                 # the false-positive Hans found
    ("see Stats. 1933, Ch. 25.", False),                    # no Note anchor -> REJECT
    ("Note.--For text see the Agricultural Code.", False),  # no Stats/Ch pointer -> REJECT
]
b3_fail = 0
for s, want in b3:
    got = bool(rc.REDIRECT_NOTE_RE.search(s))
    ok = (got == want)
    if not ok:
        b3_fail += 1
    print(f"  [{'OK ' if ok else 'FAIL'}] match={got!s:<5} want={want!s:<5} | {s!r}")

print(f"\nB1 failures={b1_fail}  B3 failures={b3_fail}")
sys.exit(1 if (b1_fail or b3_fail) else 0)
