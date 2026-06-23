"""Emit chapters.tsv from parsed_acts_certified.json files (label from dir name) so the
official analysis/chapter_vs_oracle.py can score the certified corpus.
Also emit a BEFORE tsv from the best-source parse (chaptered_v2>early_v2>recovered)."""
import json, sys, glob, os
from pathlib import Path
import importlib.util
spec=importlib.util.spec_from_file_location("cc", r"C:\Users\patolex\PatoLex-scratch\_certify_chapters.py")
cc=importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
root=Path(r"C:\Users\patolex\PatoLex-scratch")

def emit(out_path, which):
    with open(out_path,"w",encoding="utf-8") as out:
        out.write("vol_label\tlist\tchapter_raw\tchapter_int\tiso_date\tsource_page\n")
        for d in sorted(root.glob("production-*")):
            label=d.name[len("production-"):]
            if which=="certified":
                fp=d/"parsed_acts_certified.json"
                if not fp.exists(): continue
            else:
                fp,_=cc.best_parse_path(d)
                if fp is None: continue
            data=json.load(open(fp,encoding="utf-8"))
            for ln in ("confident_acts",):   # CONFIDENT-only: measures confident-completeness
                for a in data.get(ln,[]):
                    ci=a.get("chapter_int_final", a.get("chapter_int"))
                    out.write("\t".join([label, ln,
                        str(a.get("chapter_raw","")).replace("\t"," ").replace("\n"," "),
                        "" if ci is None else str(ci),
                        str(a.get("iso_date") or ""), str(a.get("source_page",""))])+"\n")

emit(root/"_certify_chapters_before.tsv","before")
emit(root/"_certify_chapters_after.tsv","certified")
print("wrote before+after tsv")
