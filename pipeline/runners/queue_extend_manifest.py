"""queue_extend_manifest.py -- append manifest entries to the JSON queue.

Usage:
    python queue_extend_manifest.py manifest_1976_2000.json

Each manifest entry must have: label, pdf, year.
Entries already in the queue (by label) are skipped.
The pdf field is written explicitly so queue_worker.py uses the correct filename.
"""
import os, sys, json, time, errno
from pathlib import Path

S = Path(r"C:\Users\patolex\PatoLex-scratch")
Q = S / "production_queue_state.json"
L = S / "production_queue_state.lock"

def lock():
    while True:
        try:
            fd = os.open(str(L), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.close(fd)
            return
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            if time.time() - os.path.getmtime(str(L)) > 60:
                os.remove(str(L))
                continue
            time.sleep(0.15)

def unlock():
    try:
        os.remove(str(L))
    except OSError:
        pass

if len(sys.argv) < 2:
    print("Usage: python queue_extend_manifest.py <manifest.json>")
    sys.exit(1)

manifest_path = Path(sys.argv[1])
if not manifest_path.exists():
    print(f"ERROR: manifest not found: {manifest_path}")
    sys.exit(1)

manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))

lock()
try:
    state = json.loads(Q.read_text(encoding="utf-8-sig"))
    have = {v["label"] for v in state["volumes"]}
    added = []
    skipped = []
    for entry in manifest:
        label = entry["label"]
        if label in have:
            skipped.append(label)
            continue
        state["volumes"].append({
            "label": label,
            "pdf":   entry["pdf"],
            "year":  int(entry["year"]),
            "status": "pending",
        })
        added.append(label)
    state["volumes"].sort(key=lambda v: (v["year"], v["label"]))
    tmp = Q.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(Q))
    print(f"APPENDED {len(added)} entries, skipped {len(skipped)} already present")
    if added:
        print("Added:", added[:10], "..." if len(added) > 10 else "")
    if skipped:
        print("Skipped:", skipped[:5], "..." if len(skipped) > 5 else "")
finally:
    unlock()
