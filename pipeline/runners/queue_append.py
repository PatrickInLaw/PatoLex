import os, sys, json, time, errno
from pathlib import Path
S = Path(r"C:\Users\patolex\PatoLex-scratch")
Q = S / "production_queue_state.json"; L = S / "production_queue_state.lock"
def lock():
    while True:
        try:
            fd = os.open(str(L), os.O_CREAT|os.O_EXCL|os.O_RDWR); os.close(fd); return
        except OSError as e:
            if e.errno != errno.EEXIST: raise
            if time.time()-os.path.getmtime(str(L)) > 60: os.remove(str(L)); continue
            time.sleep(0.15)
def unlock():
    try: os.remove(str(L))
    except OSError: pass
labels = sys.argv[1:]
lock()
try:
    st = json.loads(Q.read_text(encoding="utf-8-sig"))
    have = {v["label"] for v in st["volumes"]}
    added = [l for l in labels if l not in have]
    for lab in labels:
        if lab in have: continue
        st["volumes"].append({"label": lab, "year": int(lab[:4]), "status": "pending"})
    st["volumes"].sort(key=lambda v: (v["year"], v["label"]))
    tmp = Q.with_suffix(".json.tmp"); tmp.write_text(json.dumps(st, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(Q))
    print("APPENDED", added)
finally:
    unlock()
