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

## What remains (toward 100% + ingest-readiness) — all need YOUR call
The cheap, high-confidence text-recovery levers are DONE (92.7%, missing 6,962). Everything left is a decision for you — I deliberately did **not** launch any of these unsupervised:

1. **Genuine re-OCR (bucket iii)** — the residual where NO engine ever read a usable header. Per the sizing (§3f) this is only ~16% of the gap and is an *upper bound* (the early oracle over-counts, below). It's the heavy GPU job: thermally-guarded re-OCR on the 5090 (`pipeline/thermal_guardian_launch_5090.ps1`, limits 70/75/80/83 °C). I did NOT start it — it's multi-hour, wouldn't finish before the heartbeat deadline, and shouldn't run unmonitored. **Your go decides this.** Recommend: re-OCR a *targeted* page list (the genuinely glyph-lost residual), not whole volumes.
2. **Early-era oracle OVER-count (raises the % once fixed)** — e.g. 1860 oracle says 455 but historically ~374 acts; 1865-66 confirmed 280. Several early sessions' "missing" counts are inflated because the oracle denominator is too high. A sourced re-derivation of the 1850s–60s oracle would lift the measured early-era % without any new recovery. Needs authoritative sources — your call (don't want to guess the denominator).
3. **Early-era FLOOR over-extraction (PRECISION / your "garbage" bar)** — e.g. 1865-66's *certified floor* has 463 chapters vs oracle 280 (~183 phantom: resolutions/special-acts/garble miscounted as chapters). Pre-existing, NOT introduced by recovery. **Should be cleaned before ingest** — the clearest remaining "garbage." Delicate (real-vs-phantom discrimination) — left for a supervised pass. *(A quick over-extraction scan I ran is CONFOUNDED — it conflates this with the even-year bundling artifact and oracle errors, and misses 1865-66 on a key mismatch; a clean measure needs the biennium-aware tool. Confirms this is delicate, not a night job.)*
   - **Two oracle-quality flags surfaced (feed item 2) — evidence points to ORACLE UNDERCOUNT, not floor over-extraction:** the 1880s regular sessions run 1880=126, 1881=77, 1885=169, 1889=290, but **1883=23 and 1887=51** are anomalously low. Memory records the **1883-84 regular session is the large Code.pdf (448 pp)** → oracle 23 is near-certainly wrong. Their certified floors (1883-84≈82, 1887≈169) EXCEED the oracle, which is the signature of an oracle undercount (a real session bigger than the oracle says), NOT floor over-extraction. **Recommend: verify 1883 & 1887 against the cited clerk.assembly.ca.gov archive pages and correct the oracle (like the 1854 fix), supervised — I did not change the ground-truth oracle autonomously.** Net effect on the 92.7% is small (~±0.2 pts) but it sharpens early-era accuracy.
4. **Ingest** — not started (constraint: no ingest/DB writes overnight). The recovery outputs (multiengine/lostheader JSON) are staged on the 5090, not yet merged into the floor or DB.
5. **15 quarantined multi-slot lostheader recoveries** (1917/1919/1921/1935/1943) — need a 2-minute manual scan check (off-by-one risk); not counted in the 92.7%.

## Notes
- No DB writes, no ingest, no deletions, no source mutation all night (additive/new-files-only).
- Recovery outputs live as new scratch JSON on the 5090 (`parsed_acts_multiengine.json`/`.new`); not yet ingested.
- ~40 min of back-off mid-run during an API 529 overload; one one-line fix was applied + verified directly (via SSH) because agents kept dying on the overload.
