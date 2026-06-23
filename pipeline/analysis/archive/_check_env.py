import os
root = os.environ.get('PATOLEX_LOCATION_ROOT', 'NOT_SET')
print(f"PATOLEX_LOCATION_ROOT={root}")
import pathlib
candidates = [
    r'C:\PatoLex-scratch',
    r'C:\Users\patolex\PatoLex-scratch',
    r'C:\Users\PatrickKolasinski\PatoLex-scratch',
    r'D:\PatoLex-scratch',
]
for c in candidates:
    exists = pathlib.Path(c).exists()
    print(f"  {c}: {exists}")
    if exists:
        try:
            sub = list(pathlib.Path(c).iterdir())[:5]
            for s in sub:
                print(f"    -> {s.name}")
        except Exception as e:
            print(f"    ERROR: {e}")
