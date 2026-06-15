# Chapter-Sequence Completeness — Findings (cc007, 2026-06-14)

**Question:** are any acts/chapters missing in the parsed corpus, and is it ready for ingestion?

**Tools (committed):** `pipeline/analysis/extract_chapters.py` (emits a small TSV of chapter_int/iso_date/source_page per act from the 197-volume aggregated parse on the 5090) → `pipeline/analysis/chapter_completeness.py` (per-session gap triage). Input: `chapters.tsv` (76,691 acts).

## Method (fixes the old report's false positives)
The old `completeness-report.json` counted 122,475 "gaps" — meaningless, dominated by: multi-volume sessions split by page range, the `NNchapters` suffix (real statute year ≠ physical-volume year), independent extra-session numbering, and OCR-garbled chapter numbers. The new check: groups by true legislative session (suffix-aware), drops provably-corrupt chapter numbers (only **0.7%**, 507/76,691, are > the CA hard ceiling), and triages sessions CLEAN / SMALL_GAP / LARGE_GAP / ANOMALY.

## Key findings (durable)
1. **No source data is lost.** OCR page-completeness was independently verified (0 missing body pages across all 205 volumes, `verify_volume_completeness.py`). Every act is present in the scanned text.
2. **The parser is correct on CLEAN OCR.** 1996 parsed to a perfect contiguous Chapters 1–1171; the authoritative leginfo data in Postgres confirms 1996 max chapter = 1171. Exact match.
3. **The parser UNDER-EXTRACTS on noisy mid-century OCR.** Calibration: California Statutes of **1957 had 2,424 chapters** (confirmed externally AND by our own OCR, which found chapter headers up to 2424); our parser extracted ~1,990 (~82%). The ~430 shortfall is acts present in the OCR text that the parser did not cleanly segment/number — a **parse deficiency, not lost data and not a re-OCR problem.**
4. **Internal sequence analysis cannot CERTIFY completeness alone — two blind spots:**
   - *Trailing truncation:* a session parsed cleanly as 1..N looks "CLEAN" even if the real session ran to N+k. Example: our 1997 parse is a clean 1..951, but the authoritative max is higher — the tail is silently missing.
   - *Misnumber vs missing:* an OCR-misread chapter number creates a fake gap (missing) and a fake collision (dupe); these are indistinguishable from a truly absent act without an external reference.
   Therefore a trustworthy "nothing is missing" claim **requires an external per-session chapter-count oracle** (CA publishes chapters-per-session via the Chief Clerk archive / leginfo) or the referential cross-check vs current codified law (the `COVERAGE_CERTIFICATION.md` design, currently unbuilt).

## State by era
- **Modern (1991→present):** authoritative leginfo data already in Postgres; 1996 OCR cross-validates. Effectively complete (modulo per-year trailing-tail verification).
- **OCR era (≈1850–1990):** all OCR pages present, but current parse extracts only ~80–85% of true chapters as cleanly-numbered acts (calibrated on 1957 = 82%). The already-ingested 1850–1876 segment carries the same chapter-number OCR noise (e.g. DB shows 1863 max chapter 1120, 1869-70 max 1092 — impossible, OCR errors in already-loaded data).

## MEASURED completeness vs the authoritative oracle (2026-06-14, "before recovery")
Gate 2 produced an authoritative per-session chapter-count oracle: `docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv`
(215 sessions 1850–2024, validated against 1957=2424 and 1996=1171; method = highest chapter number in the
session ToC). `pipeline/analysis/chapter_vs_oracle.py` joins our parse against it (oracle total as the cap).

**Result (OCR era 1861–1999): 72,562 of 91,153 authoritative chapters parsed = 79.6% complete; ~18,591 missing.**
- The deficit is systematic (most sessions 70–88%), not random → parser under-extraction on noisy OCR, consistent
  with the 1957 calibration (79% here). 1996–1999 = 100% (clean OCR); earliest hand-set volumes worst (1861 47%, 1915 33%).
- Caveats: 1850–1860 came from the ORIGINAL 1850–75 ingest (not the 197-vol parse set) → not scored here, scored
  separately; a few biennial volumes spanning two sessions (e.g. 1907-09) add minor per-session noise; OCR-garbled
  high chapter numbers (e.g. 90623) are neutralized by the oracle cap.
- This is the BEFORE-recovery baseline. After the Gate-1 parser completion/renumber pass, re-run chapter_vs_oracle.py
  to measure how much of the 18,591 is recovered.

## Ingestion readiness: NOT READY (OCR era)
Ingesting the mid-century parse as-is would under-populate it by ~15–20% and carry chapter-number noise. Before full ingestion:
1. **Parser completion/repair pass for the OCR era** — recover the ~15–20% of acts the segmenter misses + a chapter-number reconstruction pass (re-number from sequence/page order, since OCR pages are complete).
2. **Acquire an external per-session chapter-count oracle** to certify completeness (separate "missing" from "misnumbered"/"trailing-truncated").
3. Carry-overs: re-parse the 13 timing-stale 1996–99 volumes on the 5080 (OCR present; already parsed on the 5090), add non-statute "BILL CHAPTERS" digests (e.g. 1998-vol6) to `SKIP_LABELS`, back up the DB before the one-pass ingest.
