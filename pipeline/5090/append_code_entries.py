"""append_code_entries.py -- one-shot merge of the prepared Code/amendment
work-items into the LIVE 5090 production_queue_state.json, PRESERVING each
entry's 'pdf' field (the stock queue_append.py drops 'pdf', so it cannot be
used here). Atomic: takes the same exclusive lock the workers use, writes a
.tmp, then os.replace. Idempotent by label -- never alters/deletes existing
entries; skips any label already present.
"""
import os, sys, json, time, errno
from pathlib import Path

S = Path(r"C:\Users\patolex\PatoLex-scratch")
Q = S / "production_queue_state.json"
L = S / "production_queue_state.lock"

NEW = [
    {"label": "1883-84-regular", "pdf": "1883-84_Code.pdf", "year": 1883, "status": "pending"},
    {"label": "1873-74-code",    "pdf": "1873-74_Code.pdf", "year": 1873, "status": "pending"},
    {"label": "1875-76-code",    "pdf": "1875-76_Code.pdf", "year": 1875, "status": "pending"},
    {"label": "1877-78-code",    "pdf": "1877-78_Code.pdf", "year": 1877, "status": "pending"},
    {"label": "1880-code",       "pdf": "1880_Code.pdf",    "year": 1880, "status": "pending"},
]


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


def main():
    lock()
    try:
        st = json.loads(Q.read_text(encoding="utf-8-sig"))
        have = {v["label"] for v in st["volumes"]}
        added = []
        for item in NEW:
            if item["label"] in have:
                continue
            st["volumes"].append(dict(item))
            added.append(item["label"])
        st["volumes"].sort(key=lambda v: (v["year"], v["label"]))
        tmp = Q.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(st, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(Q))
        print("APPENDED " + str(added))
        print("TOTAL " + str(len(st["volumes"])))
    finally:
        unlock()


if __name__ == "__main__":
    main()
