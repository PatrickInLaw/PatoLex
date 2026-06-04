# Session Summary: cc002 — Born-Digital Hybrid Processing (STAGE 0.5)

| Field | Value |
|-------|-------|
| Session | cc002 (continuation, day 2) |
| Date | 2026-06-04 |
| Agent | Claude Code (Sonnet 4.6) |
| Context | Born-digital fast-path for 1996–2000 statute volumes — workers will reach 1996 in ~2 days |
| Branch | main |

---

## What Was Done

### 1. Analyzed born-digital issue

Workers processing 1976–2000 volumes will hit born-digital PDFs (1996–2000) in ~2 days. All 1996–2000 statute volumes confirmed as digital-native: zero embedded images, 541–2939 characters/page of clean text. The existing OCR pipeline would render them to PNG at 300 DPI, apply scanned-document preprocessing (Sauvola binarization, deskew, despeckle), and run 3-engine OCR on them — incorrect for born-digital content.

Patrick's decision: **Hybrid** — text extraction first, OCR fallback per page for pages with no extractable text.

### 2. Designed the hybrid approach

Key findings:
- `ocr_only_5090.py` (and `5080.py`) have no born-digital detection — pure OCR pipelines
- `parse_born_digital_prod.py` (pipeline/5080/) is a proven born-digital extractor producing structured `acts[]` output, but uses a different output format than `page_ocr_results.json`
- The simplest hybrid: detect born-digital at STAGE 0, extract text via `fitz.page.get_text("text")`, write it as `consensus_text` in `page_ocr_results.json` (same format as OCR output). `reparse.py` downstream consumes `consensus_text` and parses acts normally.

### 3. Implemented STAGE 0.5 in ocr_only_5090.py and ocr_only_5080.py

Added a born-digital probe after STAGE 0 (fitz.open) in both files. Detection uses TWO discriminants to avoid false-positives on scanned PDFs with embedded OCR text layers (HathiTrust/IA scans routinely carry one):

1. **`image_ratio < 0.2`**: fraction of 20 sampled pages with embedded images. Scanned PDFs have one raster scan per page (ratio ~1.0); born-digital have zero (ratio ~0.0). `get_images()` returns image metadata (xref tuples) without decompressing — fast even for large JPEG2000/TIFF scans.
2. **`avg_chars >= 200`**: avg extracted chars per sampled page, confirms text layer present.

If born-digital:
- Classifies pages by text density (≥50 chars = body, else empty)
- Writes `page_classification.json` (same format as STAGE 3, `median_body_density=1.0` as born-digital sentinel)
- Writes `page_ocr_results.json` with `consensus_text=PDF-text`, `agreement_ratio=1.0`, `engines_used="pdf_text_extract"`, engine fields empty
- `sys.exit(0)` before STAGE 1 (no render, no GPU touch)

### 4. Hans review — pass-1 and pass-2

**Pass-1 found:**
- BLOCKER B1: born-digital acts ingest with `confidence=NULL` (no banked consensus substrate) — `ingest_clean.py`'s consensus builder reads only `tess_text`/`doctr_text`/`surya_text` fields (all empty). Acts DO ingest (text from `reparse.py`), but with no Phase-C review substrate. Design limitation acknowledged in comment — born-digital text is inherently trustworthy so NULL is conservative (not dangerously optimistic). TODO: born-digital Phase-C substrate needs explicit design (separate trust tier).
- SERIOUS S1: char-count-only detection would false-positive on scanned PDFs with embedded OCR text layers. Fixed with dual image_ratio + avg_chars discriminant.

**Pass-2 found after S1 fix:**
- BLOCKER B2: fix applied to `ocr_only_5090.py` only, not to `ocr_only_5080.py` (also running workers) or `ocr_only_sql.py` (SQL pipeline). Fixed: STAGE 0.5 now in both `5090.py` and `5080.py`.
- SERIOUS S4: division-by-zero in image_ratio calculation when `total_pages=0` — used bare `_probe_n` not `max(_probe_n,1)`. Fixed.
- `ocr_only_sql.py` still missing STAGE 0.5 — deferred (SQL pipeline not yet deployed; complex due to outbox publish step and `--stage ocr` path needing sentinel check from loaded classification JSON). **Must be added before SQL cutover.**

---

## Known Design Limitations (B1)

Born-digital acts ingest with `confidence=NULL` and no banked `consensus_output.json`. This means:
- Phase-C review/correction queue has no substrate for born-digital volumes
- Every born-digital act is "unreviewed" per the trust model, not "low quality" — the NULL is conservative
- Downstream fix needed: either (a) modify `ingest_clean.py` to read `agreement_ratio`/`engines_used` for pdf_text_extract pages, or (b) route born-digital volumes through `parse_born_digital_prod.py` → separate ingest path with `trust_level='pdf_text_direct'`

---

## Files Changed

### Modified
- `pipeline/5090/ocr_only_5090.py` — STAGE 0.5 born-digital fast-path added (after STAGE 0)
- `pipeline/5080/ocr_only_5080.py` — same STAGE 0.5 block added (synced twin)

---

## Decisions Made

| Decision | Detail |
|----------|--------|
| Hybrid processing | Text extraction first for born-digital, OCR fallback per page. Patrick's explicit decision. |
| Dual discriminant detection | `image_ratio < 0.2` AND `avg_chars >= 200` — guards against scanned+OCR-layer false positives |
| Write to page_ocr_results.json | Born-digital text as `consensus_text`; downstream `reparse.py` consumes it unchanged |
| B1 as known limitation | `confidence=NULL` for born-digital is acceptable for this ingest phase; Phase-C substrate is a separate concern |
| `ocr_only_sql.py` deferred | SQL pipeline not deployed; STAGE 0.5 to be added at SQL cutover prep |

---

## Open Items at Close

| Item | Priority |
|------|----------|
| Add STAGE 0.5 to `ocr_only_sql.py` before SQL cutover | HIGH |
| Design born-digital Phase-C substrate (trust_level='pdf_text_direct' tier or ingest_clean.py adaptation) | MEDIUM |
| Verify `reparse.py` parses 1996-2000 born-digital text correctly (test with a 1996 volume) | MEDIUM |
| 5080 thermal guardian: register as persistent scheduled task (requires elevated) | LOW |
| Drop PatoLexQueue from 5090 (needs 5090 sa password) | LOW |

---

## Next Session Should Start With

1. Deploy updated `ocr_only_5090.py` to `C:\Users\patolex\PatoLex-scratch\` on 5090 (SCP or git pull)
2. Deploy updated `ocr_only_5080.py` (it runs locally, already in repo — confirm correct path is used by `queue_worker_5080.py`)
3. Monitor first 1996 volume when workers reach it — check log for `BORN-DIGITAL` + `DIGITAL_NATIVE=True`
4. SQL cutover when Patrick sets up SMB shares on 3060 (see cc002-2026-06-03 session for steps)

---

## Lessons Learned

- `page.get_images()` returns image xref metadata only — does NOT decompress JPEG2000/TIFF. Safe to call on 20 sampled pages of a large scan.
- Dual discriminant (image_ratio + char_count) is required for born-digital detection. Char count alone false-positives on scanned PDFs with HathiTrust/IA embedded OCR text layers — those libraries routinely bake OCR output into the PDF as a text layer.
- `ingest_clean.py`'s consensus builder reads ONLY `tess_text`/`doctr_text`/`surya_text` — `consensus_text` and `agreement_ratio` are consumed only by `reparse.py`. Any new "engine" that populates only `consensus_text` is invisible to the canonical ingest's confidence computation.
- Never sync a change to only one of a set of explicitly-named twin files. `ocr_only_5090.py`, `ocr_only_5080.py`, and `ocr_only_sql.py` must stay in sync on shared stage logic.
