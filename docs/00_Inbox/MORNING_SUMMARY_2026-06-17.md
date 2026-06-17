# Morning Summary — overnight autonomous run (2026-06-17)

**Status: PROGRESS (will be finalized at the heartbeat deadline 14:26 UTC).** Everything below is committed + pushed to `main`. Full detail in `docs/20_ROADMAP/CORPUS_COMPLETENESS_STATE.md`.

## The headline
**The OCR historical corpus (1850–1999) is 92.7% complete (confident), biennium-correct** — up from a starting *measured* 87.6%, and the confusing "71% / ~20k missing" narrative was proven to be a **measurement artifact, not missing data**. Cumulative chapters recovered this run, **all Hans-gated and 0-duplicate**: certify **+3,213**, modern multi-engine **+3,413**, early-era roman multi-engine **+~1,224**, lostheader position-fill **+224** (~8,070 total). Missing now 6,962. (15 multi-slot lostheader recoveries are quarantined for manual scan verification — a known off-by-one risk — not counted.)

## The big clarifying finding (please read)
The recurring "~20,000 missing chapters" (incl. an agent's "22,197 unparsed volumes") is **NOT missing data** — it is a **denominator bug**: California's even-year **Budget/Extra sessions** (tiny, 1–151 chapters each) are bound in the adjacent ODD-year volume under an `NNchapters` suffix (e.g. 1956's statutes are in `production-1957-vol1-56chapters`), and a measurement tool mis-stamped them with the odd-year *Regular* session's count (~1,900–2,400). The data is all present. Measure with `chapter_vs_oracle.py` (biennium-correct), never the certify-internal totals or year-keyed tools. Authoritative oracle denominator = **119,157 chapters / 215 sessions**. (This dissolved the 6th–7th "missing data" false alarm of the campaign.)

## Per-era completeness (confident, biennium-correct)
| era | % | note |
|---|---|---|
| 1850–79 | ~76% (was 62.5%) | lifted by the early-era roman recovery |
| 1880–99 | 90% | |
| 1900–19 | 85% (was 72%) | multi-engine |
| 1920–49 | 89% (was 82%) | multi-engine |
| 1950–88 | 95% | |
| 1989–99 | 99% | |
| 2000–24 | n/a | NOT OCR — modern leginfo-XML → DB, separate path |

## What was built/fixed (all committed; Hans-reviewed)
- `certify_chapters.py` — flagged→confident certification; fixed a duplicate-emission bug the pre-gate C97 run had shipped silently; write-gate + R2 fixes. +3,213, 0 dup.
- `recover_multiengine_headers.py` (NEW) — recovers parser-missed acts by reading clean `CHAPTER N.` / `CHAP. <ROMAN>.` headers from the independent surya/doctr/tess OCR fields where the token-majority *consensus* was garbled. Modern arabic + early roman modes. Two+ Hans passes each; key lessons: **consensus_text is NOT an independent OCR witness** (don't let it vote in cross-engine agreement), and a 0-duplicate self-check does **not** prove correctness (a false-positive header can emit a unique wrong-location number) — so every emission requires a colocated real-act body witness.

## What remains (toward 100% + ingest-readiness)
1. **`recover_lost_header.py` (bucket ii, garbled-numeral position-fill)** — hardening cycle was Hans-NO-GO'd and is queued; blocked tonight by an intermittent API 529 overload (agents kept dying at 0 tokens, so I backed off). Modest expected gain (multi-engine already harvested the clean-header cases). Resume when the API is stable.
2. **Early-era FLOOR over-extraction (PRECISION / your "garbage" bar)** — e.g. 1865-66's *certified floor* has 463 chapters vs the confirmed-correct oracle 280 (~183 phantom). This is pre-existing over-extraction (resolutions/special-acts/garble counted as chapters), NOT introduced by recovery. **It should be cleaned before ingest** — it's the clearest remaining "garbage" item.
3. **Genuine re-OCR (bucket iii)** — only ~16% of the residual, an *upper bound*; concentrated where no engine ever saw a header. **Deferred for your go** — it's the heavy GPU op; the cheap text levers carried the corpus to 92.5% without it.
4. **Ingest** — not started (per constraints: no ingest/DB writes overnight).

## Notes
- No DB writes, no ingest, no deletions, no source mutation all night (additive/new-files-only).
- Recovery outputs live as new scratch JSON on the 5090 (`parsed_acts_multiengine.json`/`.new`); not yet ingested.
- ~40 min of back-off mid-run during an API 529 overload; one one-line fix was applied + verified directly (via SSH) because agents kept dying on the overload.
