# 5090 HANDOFF — UPDATE (2026-06-20): data relocated + full source synced

**This supersedes the path/source-location details in `HANDOFF_5090_OPUS_2026-06-17.md`** (that doc has been read; its corpus-completeness content/tools/lessons are still valid, but use the paths + facts below). Summary of infra work done on the 5090 this session.

## What changed (what I did)
1. **Corpus moved OFF the `patolex` profile.** `C:\Users\patolex\PatoLex-scratch` → **`C:\PatoLex-scratch`** (same-SSD rename, instant; 222 production dirs intact, 993,248 files). **Reason:** the 5090 Opus agent runs under Patrick's interactive (AzureAD) login and could NOT access `C:\Users\patolex` — that profile is private to the `patolex` automation account. Moving it out of the profile fixes that.
2. **Any-account access granted.** `icacls … /grant Authenticated Users:(OI)(CI)M /T` over the whole tree — **993,248 files, 0 failures.** Any logged-in account (incl. Patrick's login / the new agent) now has read/write.
3. **Machine-wide path override set:** **`PATOLEX_LOCATION_ROOT=C:\PatoLex-scratch`** (`setx /M`). `pipeline/config.py` reads this env var, so all code on the 5090 resolves to the new path automatically. **USE `C:\PatoLex-scratch`.** (The old `C:\Users\patolex\PatoLex-scratch` is now a near-empty recreated dir containing one harmless stray `_scan_tail.py` — ignore it.)
4. **Full original source synced to the 5090.** `chief-clerk-archive` went from **211 → 653 PDFs** (copied the 442 missing from the 5080, 0 failures, 19.71 GB into ~330 GB free). Now present on the 5090: **all 114 `_Index`/`_TOC` PDFs** (was 0), the **1850–1860 decade incl. `1854_Statutes/Index/Rec_Exp`**, every component volume (`_Constitution`/`_Measures`/`_Tables`/`_StatRecord`/`_Summary`/`_Appendix`/extra-sessions/`_BR`/`_Treasury`/`_Code_Index`), and **2001–2008**.

## Why this matters for the completeness work
- **The modern-era `NO_INDEX` denominator gap is now solvable ON-BOX.** The 2026-06-17 handoff (§5/§6.1) found the index re-derivation returned `NO_INDEX` for 1905+ because the printed CONTENTS pages aren't inside the OCR *bundles*. **They now exist on the 5090 as standalone source PDFs** (`1931_Vol1_Index.pdf`, `1982_Vol6_Index.pdf`, `1994_TOC.pdf`, …). So you can OCR these `_Index.pdf` files to get authoritative per-session chapter counts for the whole corpus — no re-acquisition, no cross-machine fetch. This is the cleanest path to a trustworthy denominator (the oracle is unreliable — 1887 = 51 vs ~188, 1883 = 23 vs ~96, Hans-confirmed).
- **1854 + early-decade source is local** for the 1854 dual-series / early-era work.

## Paths quick-reference (on the 5090, any account)
- Corpus / scratch root: **`C:\PatoLex-scratch`** (env `PATOLEX_LOCATION_ROOT`)
- Source PDFs (653, incl. indexes): **`C:\PatoLex-scratch\chief-clerk-archive`**
- Repo: `C:\github\PatoLex` · Oracle (read-only): `C:\github\PatoLex\docs\30_SYSTEM_DESIGN\sources\ca_chapter_counts.tsv`

## What did NOT change
All corpus-completeness content in `HANDOFF_5090_OPUS_2026-06-17.md` remains valid: the tools (`certify_chapters.py`, `recover_multiengine_headers.py`, `recover_lost_header.py`, `chapter_vs_oracle.py`, `rederive_index_counts.py`), the 92.7% measurement, the residual decomposition, the lessons, and the oracle-error findings. Only the **scratch path** and the **"source location / 5090 has the canonical set" claims** are superseded by this doc.
