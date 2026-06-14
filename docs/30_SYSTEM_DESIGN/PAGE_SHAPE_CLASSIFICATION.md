# Page-Shape Classification & Garble Payoff (cc007)

**Status: COMPLETE 2026-06-14.** All three stages ran over the full 205-volume historical OCR corpus; final garble-weighted number computed.

## Question answered
Of the long-tail of un-correctable OCR garble in the scanned 1850s–1990s corpus, **how much sits on NON-body pages (rosters / indexes / dividers / reprints) that we never ingest** — and can therefore be dropped from the re-OCR / cleaning consideration?

## Architecture — 3-stage funnel (queue-driven, crash-safe)
SQL queue `PatoLexQueue` on the 3060 drives it; renders/shape outputs persist on the 5090.
1. **Surya page-shape (5090 GPU)** — render each PDF page → Surya layout → dominant shape label. Cheap, broad, **noisy**: over-flags garbled/embedded-table statute pages as `TABLE_ROSTER`. Hard per-process VRAM cap is mandatory (a >32 GB spike TDR-resets the GPU). `pipeline/analysis/surya_page_shapes.py`.
2. **Procedural text-reconcile (5080 CPU)** — for each Surya non-body page, RESCUE→body on statute signals (enacting clause / chapter+section / appropriations prose), CONFIRM→nonbody on index headers, else AMBIGUOUS→VLM. Recovered **10,317** statute pages Surya wrongly flagged. `pipeline/analysis/shape_reconcile.py`.
3. **VLM tiebreaker (5090 GPU)** — Qwen2-VL-7B reads the clean page **image** (right, because the ambiguity comes from garbled OCR *text*, not bad scans) and votes BODY / ROSTER / INDEX_TOC / REPRINT / OTHER on the residual. `pipeline/sql/vlm_worker_sql.py`.

VLM verdict split on the 14,278 ambiguous pages: **BODY 12,098 (85%)**, INDEX_TOC 1,699, ROSTER 363, OTHER 107, REPRINT 11 (+12 failed-render pages). ~85% of the ambiguous pages are real statute — confirms Surya massively over-flags.

## Final result — `pipeline/analysis/garble_by_shape.py`
Joins per-page garble × final label (reconcile + folded-in VLM verdicts). Verdicts exported from `vlm_queue` to `_cascade/vlm_verdicts.tsv`; OTHER is kept on the BODY side (conservative — not claimed as removed). Run with `PATOLEX_USE_RECONCILED=1 PATOLEX_USE_VLM=1`.

Across 205 volumes, 328,628 pages, **158,188 garbled tokens**:

| Bucket | Garble | Share |
|---|---:|---:|
| Remains on BODY (real cleaning/re-OCR target) | 134,123 | **84.8%** |
| Removed — deterministic (reconcile non-body) | 3,274 | 2.1% |
| Removed — VLM (roster/index/reprint) | 20,758 | 13.1% |
| **Total removed** | **24,032** | **15.2%** |
| Still ambiguous (12 failed-render pages) | 33 | 0.0% |

### Full sieve — every layer, exact (`pipeline/analysis/full_sieve.py`)
Single-pass join of raw Surya class × reconcile decision × VLM verdict, per page, into six disjoint
categories (pages + garble). Cross-checks against the queue. Run on the 5080 with
`PATOLEX_SHAPES=...\page-shapes-5090` (full 205 shape TSVs pulled from the 5090).

```
TOTAL                                 158,188 garble  (328,628 text pages)
 Surya BODY ................. 118,114 ( 303,670 pg)  -> kept
 Surya NON-BODY .............  40,074 (  24,958 pg)  -> reconcile
   rescued -> BODY ..........   4,899 (  10,317 pg)  -> kept (Surya wrong)
   confirmed -> REMOVED .....   3,274 (     637 pg)  ✂ deterministic
   ambiguous -> VLM .........  31,901 (  14,004 pg)  -> VLM
     VLM kept -> BODY .......  11,110 (  12,123 pg)  -> kept
     VLM REMOVED ............  20,758 (   1,869 pg)  ✂ roster/index/reprint
     VLM failed (residual) ..      33 (      12 pg)
FINAL  kept 134,123 (84.8%) / removed 24,032 (15.2%) / residual 33
```
- **Garble density: removed pages 9.6 tok/pg vs kept body 0.4 tok/pg — 23× denser.** 0.76% of pages hold 15.2% of garble.
- **Surya alone would have wrongly removed 16,009 garble tokens of real statute** (4,899 rescued + 11,110 VLM-recovered) — the two downstream stages exist to recover exactly this.
- Page universe = text-bearing pages only (textless blanks carry no garble; ~286 ambiguous blanks excluded from the denominator).

### By era (removed % of that era's garble)
1860s **51.8%**, 1870s **59.2%**, 1880s 5.8%, 1890s 4.0%, 1900s 5.2%, 1910s 2.9%, 1920s 0.0%, 1930s 2.5%, 1940s 0.0%, 1950s 1.9%, 1960s 0.2%, 1970s 3.1%, 1980s 5.7%, 1990s **25.4%**.

## Conclusions (durable)
- **Most of the garbled long tail (~85%) is REAL statute text** that still needs cleaning / re-OCR. The page-shape effort is as much *diagnostic* (the tail is mostly real) as *subtractive*.
- The VLM found ~6× more removable garble than the deterministic pass alone (13.1% vs 2.1%), justifying the image-based stage.
- Removal is heavily concentrated in the **1860s–1870s** (roster/index/appropriation-table heavy) and a **1990s** index spike; the body-heavy 1920s–1960s volumes are ~0–2% removable. A re-OCR campaign should prioritize the early era and the clean mid-century body volumes; the early-era non-body bulk can be ignored.
- The `ocr_queue` factory (prep/ocr/tess/doctr/surya/consensus passes, currently inert) is the reusable engine for full OCR of a future new corpus — enable passes + reseed.
