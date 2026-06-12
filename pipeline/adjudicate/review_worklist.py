"""Stage the source-page scans for the REVIEW chapter cases so they can be eyeballed."""
import os, json, shutil, re
ROOT = r"C:\Users\patolex\PatoLex-scratch"
CORR = os.path.join(ROOT, "_vocab", "chapter_corrections.tsv")
STAGE = os.path.join(ROOT, "_vocab", "review_imgs")
os.makedirs(STAGE, exist_ok=True)

review = []
with open(CORR, encoding="utf-8") as f:
    next(f)
    for ln in f:
        p = ln.rstrip("\n").split("\t")
        if len(p) >= 7 and p[5] == "REVIEW":
            review.append(p)

cache = {}
def meta(vol, order):
    if vol not in cache:
        d = {}
        try:
            data = json.load(open(os.path.join(ROOT, vol, "parsed_acts_fixed.json"), encoding="utf-8", errors="replace"))
            for a in list(data.get("confident_acts", [])) + list(data.get("flagged_acts", [])):
                d[a.get("in_act_order")] = (a.get("source_page", 0), (a.get("title") or "")[:90])
        except Exception:
            pass
        cache[vol] = d
    return cache[vol].get(int(order), (0, ""))

rows = []; staged = 0
for p in review:
    vol, order, raw, ocr, reason = p[0], p[1], p[2], p[3], p[6]
    sp, title = meta(vol, order)
    img = os.path.join(ROOT, vol, "pages_prep_gray", f"page_{max(0, sp-1):04d}.png")
    has = os.path.exists(img)
    if has:
        dst = os.path.join(STAGE, f"{vol}__o{order}__ocr{ocr}__p{sp}.png")
        try:
            shutil.copy(img, dst); staged += 1
        except Exception:
            pass
    rows.append((vol, order, raw, ocr, sp, "Y" if has else "N", reason, title))

with open(os.path.join(ROOT, "_vocab", "review_worklist.tsv"), "w", encoding="utf-8") as f:
    f.write("vol\torder\traw\tocr\tsource_page\timg_5090\treason\ttitle\n")
    for r in rows:
        f.write("\t".join(str(x) for x in r) + "\n")
print(f"REVIEW={len(review)} staged_5090_images={staged} -> {STAGE}")
