import pathlib
scratch = pathlib.Path(r'C:\PatoLex-scratch')
# find production-1850* directories
for item in sorted(scratch.iterdir()):
    if item.is_dir() and '1850' in item.name:
        print(f"DIR: {item}")
        # check for key subdirs
        for sub in ['pages_raw', 'ocr_consensus']:
            sp = item / sub
            if sp.exists():
                count = len(list(sp.iterdir()))
                print(f"  {sub}: {count} files")
            else:
                print(f"  {sub}: MISSING")
# Also check user profile location
alt = pathlib.Path(r'C:\Users\patolex\PatoLex-scratch')
for item in sorted(alt.iterdir()):
    if item.is_dir() and '1850' in item.name:
        print(f"ALT DIR: {item}")
        for sub in ['pages_raw', 'ocr_consensus']:
            sp = item / sub
            if sp.exists():
                count = len(list(sp.iterdir()))
                print(f"  {sub}: {count} files")
            else:
                print(f"  {sub}: MISSING")
