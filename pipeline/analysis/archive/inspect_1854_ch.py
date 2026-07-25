import json
base = r"C:\PatoLex-scratch\production-1854"
mg = json.load(open(f"{base}\\parsed_acts_merged.json", encoding="utf-8"))["merged_acts"]
vis = json.load(open(f"{base}\\parsed_acts_visual.json", encoding="utf-8"))["recovered_acts"]

def show(ch):
    print(f"\n--- chapter {ch} ---")
    for a in mg:
        if a.get("chapter_int_final") == ch or a.get("chapter_int") == ch:
            print(f"  MERGED p{a.get('source_page')} origin={a.get('origin')} "
                  f"renumber={a.get('renumber_status')} title={(a.get('title') or '')[:55]!r}")
    for a in vis:
        if a.get("chapter_int_final") == ch or a.get("chapter_int") == ch:
            print(f"  VISUAL p{a.get('source_page')} series={a.get('dualseries_series')} "
                  f"conf={a.get('match_confidence')} title={(a.get('title') or '')[:55]!r}")

for ch in (3, 12, 35, 50, 63, 84, 94, 95):
    show(ch)

# how many merged entries have a low source_page (<17 = front matter / contents)
low = [a for a in mg if (a.get("source_page") or 999) < 17]
print(f"\nmerged entries with source_page<17 (contents/front-matter region): {len(low)}")
for a in low[:20]:
    print(f"   ch{a.get('chapter_int_final')} p{a.get('source_page')} {(a.get('title') or '')[:50]!r}")
