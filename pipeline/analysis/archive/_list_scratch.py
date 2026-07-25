import pathlib
scratch = pathlib.Path(r'C:\PatoLex-scratch')
items = sorted(scratch.iterdir())
for item in items:
    print(f"{'DIR' if item.is_dir() else 'FILE'} {item.name}")
