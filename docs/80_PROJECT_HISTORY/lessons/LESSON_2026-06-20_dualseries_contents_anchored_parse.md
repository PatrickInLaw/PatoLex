# LESSON 2026-06-20 — Dual-series volumes: anchor chapter numbering to the printed Contents, not body roman headers

**Context:** Validating/repairing the 1854 statutes parse (Fifth Session) toward the "100% OCR-era" denominator goal.

## The finding

**1854 is a dual-series volume:** one bound volume containing **General Laws (Chapters 1–71)** followed by **Special Acts/Laws (Chapters 1–103, restarting at 1)** = **174** total, then Resolutions (not chapters). The "highest chapter number = count" rule does NOT apply (see also `ca_chapter_counts_NOTES.md`). Early-era (1850s) body **roman-numeral headers OCR badly** (out of order, dropped, `CII`→`CH/CIT/COL`), so a body-header-driven parser mis-numbers and undercounts.

## The failure mode this exposed: **force-fit to a known target**

The first re-parse (`parsed_acts_dualseries.json`, v1) was *told* the target was 71+103=174 and returned a clean-looking **174/174, fully contiguous** — which was WRONG. It had:
- **dropped a real act** — General Ch18 ("An Act concerning County Judges", p27),
- **invented a phantom** — General "Ch23" = a body cross-reference fragment ("an Act supplementary thereto, passed May 17, 1853"), actually a tail clause inside the genuine Redemption-of-State-Prison-Bonds act, and
- run **off-by-one across General Ch18–24**.

The dropped act and the phantom **canceled out**, so the *total* still read 71 — the perfect count hid the defects.

> **Rule: a parse total that exactly equals a known target is a RED FLAG, not reassurance.** Drops and phantoms cancel. Verify per-chapter (title + page + a real body witness), never trust the aggregate count.

## The fix that worked: **Contents-anchored parsing**

Derive the numbering from the **printed front-matter Contents (table of acts)** — `chapter № → title → page`, which is the chapter-level oracle — *not* from body roman headers. Then locate each canonical chapter's body independently (title-token match near its contents page), report genuine misses honestly, and **reject anything that matches no Contents entry** (this auto-kills phantoms). Result (`parsed_acts_dualseries_v2.json`): General 71/71, Special 103/103, zero missing, one phantom rejected — **verified**, not force-fit.

**Verification that earned trust:** orchestrator independently confirmed the canonical Contents transcription at three sampled regions (General ch11–41, ch58–71; Special ch57–76 — all exact); Hans (verify-auditor) audited the body-matching adversarially — ~42 chapters individually header-confirmed + a full shared-page header census across all 174 — verdict **SOUND**. (Watch for benign `source_page` column-placement slips, e.g. General ch50/ch70, where the header sits a page off from the cited body page — body real, not a defect.)

## Reusable principles (apply corpus-wide)

1. **Anchor numbering to the printed Contents/Index, not body OCR**, for any dual-series / garbled-roman / early-era volume.
2. **Distrust perfect-vs-target counts**; require per-chapter body witnesses.
3. **The `_Index` / `_Statutes` Contents PDFs are now local** (`C:\PatoLex-scratch\chief-clerk-archive\*_Index.pdf`, 1850→modern, synced 2026-06-19). This makes index-anchored denominator/completeness validation available **corpus-wide** — the path to closing the modern-era NO_INDEX denominator gap on-box.

**Artifacts:** `C:\PatoLex-scratch\production-1854\{parsed_acts_dualseries_v2.json, _canonical.py, _finalize_v2.py}`. Oracle unchanged (1854 = 174, already correct).
