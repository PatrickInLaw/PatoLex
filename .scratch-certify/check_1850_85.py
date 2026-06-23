import importlib.util, json, os
spec=importlib.util.spec_from_file_location("cc", r"C:\Users\patolex\PatoLex-scratch\_certify_chapters.py")
cc=importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
d=json.load(open(r"C:\Users\patolex\PatoLex-scratch\production-1850\parsed_acts_early_v2.json",encoding="utf-8"))
# find the act at page 215 with 'Offices'
for a in d.get('flagged_acts',[])+d.get('confident_acts',[]):
    if a.get('source_page')==215 and 'Offices' in (a.get('text','')[:60]):
        print('chapter_int', a.get('chapter_int'), 'raw', repr(a.get('chapter_raw')))
        print('header_numeral=', cc.header_numeral(a.get('text','')))
        print('raw_numeral=', cc.raw_numeral(a))
        print('hdr_count=', cc.chapter_header_count(a.get('text','')))
        print('head:', a.get('text','')[:120].replace(chr(10),' '))
# Also show the anchors around page 215 to confirm 85 is the single open slot
acts=sorted(d.get('flagged_acts',[])+d.get('confident_acts',[]), key=lambda x:x.get('source_page',0))
for a in acts:
    if 210 <= a.get('source_page',0) <= 220:
        print(a.get('source_page'), 'conf' if a.get('confident') else 'flag', 'ci', a.get('chapter_int'), 'hdrnum', cc.header_numeral(a.get('text','')), a.get('text','')[:45].replace(chr(10),' '))
