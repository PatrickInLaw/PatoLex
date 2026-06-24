import json

base = r"C:\PatoLex-scratch\production-1854"

for fn, key in [("parsed_acts_visual.json", "recovered_acts"),
                ("parsed_acts_merged.json", "merged_acts")]:
    d = json.load(open(f"{base}\\{fn}", encoding="utf-8"))
    acts = d[key]
    print(f"\n===== {fn}: {len(acts)} acts =====")
    print("keys:", list(acts[0].keys()))
    origins = {}
    for a in acts:
        o = a.get("origin", a.get("_merge_source", "?"))
        origins[o] = origins.get(o, 0) + 1
    print("origins:", origins)
    # page range
    pgs = [a.get("source_page") for a in acts if a.get("source_page") is not None]
    print("page range:", min(pgs), "-", max(pgs))
    # show first 6
    for a in acts[:6]:
        print(f"  ch={a.get('chapter_int_final', a.get('chapter_int'))} p={a.get('source_page')} "
              f"origin={a.get('origin','')} src={a.get('_merge_source','')} "
              f"title={ (a.get('title') or '')[:50]!r}")
