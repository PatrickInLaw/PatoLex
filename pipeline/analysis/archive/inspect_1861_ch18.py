import json
base = r"C:\PatoLex-scratch\production-1861"

for fn, key in [("parsed_acts_merged.json", "merged_acts"),
                ("parsed_acts_clauserec.json", None),
                ("parsed_acts_visual.json", "recovered_acts")]:
    try:
        d = json.load(open(f"{base}\\{fn}", encoding="utf-8"))
    except Exception as e:
        print(fn, "ERR", e); continue
    if isinstance(d, dict):
        acts = d.get(key) if key else None
        if acts is None:
            for k, v in d.items():
                if isinstance(v, list):
                    acts = v; break
    else:
        acts = d
    print(f"\n===== {fn} ({len(acts)} acts) =====")
    for a in acts:
        ch = a.get("chapter_int_final", a.get("chapter_int"))
        if ch in (17, 18, 19):
            print(f"  ch{ch} p{a.get('source_page')} origin={a.get('origin','')} "
                  f"title={(a.get('title') or '')[:65]!r}")
