# LESSON 2026-06-14 — Mid-century parser misses are page-top CHAPTER-header loss; recover by sequence-renumber

**Context (cc010):** The production act parser (`pipeline/ingest/ingest_from_ocr.py`,
`parse_volume` / `header_starts_act` / `flush_act`) extracts only ~67-82% of acts in the
noisy mid-century OCR era. OCR page-completeness is independently verified (0 missing body
pages), so the missing acts ARE in the text — the parser fails to segment/number them.

## What the parser actually does (the gate that matters)

`header_starts_act` only starts an act when **both** (a) `HEADER_RE` matches a `CHAPTER NN`
line AND (b) `AN_ACT_RE` ("An Act") appears within the next 4 lines. `flush_act` then drops
the buffer unless an enactment marker ("People of the State of California" / "do enact as
follow") is present.

**Measured on 1957 (true 2424 chapters):** `header_starts_act` fires only **1995 times**
(1047 vol1 + 948 vol2) — this is the ~1990 figure prior runs reported. Of those, **almost
all survive `flush_act`** (no_enact_marker dropped only 5). So **the bottleneck is header
DETECTION, not the flush gates.** ~429 acts never trigger an act-start at all.

## Root failure mode (the finding)

In the CA Statutes single-column layout (roughly **1880-forward**), each act prints as
`CHAPTER NN` / `An act to ...` / body / `[Approved ... 19xx]`, and a new act frequently
**begins at the TOP of an OCR page**. The `CHAPTER NN` header line lands in the page
header / on the prior page / as garbled glyphs (`CILAPTER 82`, `CHAPTER �3`) — so
`HEADER_RE` never matches and the act is lost even though its body is intact.

Quantified on 1957: of the missed "An act" starts, **313 are at page-top with no header
in the prior 3 lines** (real losses), 37 have a header 4-8 lines above (just out of the
4-line window), and ~34 mid-page "An act" mentions are **body citations** ("of an act",
"entitled", "act of Congress") that must NOT be recovered (precision trap). A secondary
mode is **OCR-misread chapter NUMBERS** (e.g. `2387` for `237`, `5838` for `583`) that
inflate the sequence and manufacture fake gaps.

**Early era is DIFFERENT and NOT covered by this fix:** 1863 OCR contains only **30 "CHAP"
tokens across 855 pages** (vs 1893 = 305). Pre-~1880 volumes run acts continuously without
a per-act top header, so the page-top/header-loss detector finds nothing (1863 recovered
+6 chapters only). The 1850s-1870s need a separate **header-free** detector keyed on the
"An act ..." + approval-date sequence, not on `CHAPTER` at all.

## The fix (additive, never overwrites)

`pipeline/ingest/recover_acts.py` — reuses the production regexes/predicates, then:
1. **Tolerant, body-ref-safe act-start detector:** an "An act" line that begins the line,
   is page-top OR has a fuzzy `CHAPTER` header within 8 lines above, has an enact/approval
   marker within 14 lines after, and is not a body citation.
2. **Session-wide chapter-renumber-by-sequence:** acts are page-ordered and chapters run
   1..N. Pick a **longest strictly-increasing chain** of confident, plausibly-numbered acts
   as ANCHORS (robust to a single misread number). Between adjacent anchors A(=a), B(=b),
   deterministically number the intervening acts a+1..b-1 **only when the count of
   intervening acts equals (b-a-1)** (sequence + page order agree). Conservative rescue:
   an ambiguous act keeping its OWN plausible printed number, non-colliding and monotonic
   vs neighbors, is promoted ("self_numbered"). Otherwise flag, never guess.
3. **Process all physical volumes of a session together** (1957 vol1 = ch 1-1400, vol2 =
   ch 1401-2424 is ONE sequence) so the renumber spans the volume boundary.

## Results (confident distinct chapters, before -> after, gap recovered)

| Session | True | Before | After | Gap recovered | Dupes | Held-to-flagged |
|---|---|---|---|---|---|---|
| 1957 | 2424 | 1629 | **2284** | 82.4% | 24→0 | 2 |
| 1931 | 1220 |  622 | **992**  | 61.9% | 8→0  | 4 |
| 1893 |  244 |  199 | **226**  | 63.3% | 10→0 | 6 |
| 1863 |  476 |  154 | **160**  | 2.1%  | 3→0  | 3 (early-era, not addressable here) |

**Precision:** 0 duplicate chapter numbers in every session (was 24/8/10/3). For `filled`
acts that DO have a readable leading `CHAPTER NN` witness, 1957 = 322 agree / 44 disagree —
and the **disagreements are overwhelmingly the renumber CORRECTING an OCR-inflated/misread
printed number** (2387→237, 5838→583, 1825→1325), i.e. the pass fixes OCR errors, it does
not introduce them. No false splits / fabricated acts (`dup_text_check.py`). "Lost vs
baseline" chapters are not corrupted — they sit in `flagged_acts` with their correct number
for review.

## Durable rules / gotchas

- **`CA_HARD_CEILING` must be ≥ 2424.** It was 2300, which silently capped out 97 real 1957
  chapters (2301-2424). Set to **2500** (rejects OCR-garble 3000+, keeps real maxima). The
  same 2300 cap is baked into `pipeline/analysis/chapter_completeness.py` `robust_max`
  (`min(2300, n_acts*1.8)`) and `validate_recovery.py` — keep them consistent.
- **Verify true chapter totals from the Chief Clerk archive TOC**, not memory: 1957=2424,
  1931=1220 (vol1 is the whole session, NOT 1442), 1893=244, 1863=476. (Source:
  clerk.assembly.ca.gov/historical-information/archive-list/statutes-and-amendments-codes-YYYY.)
- **The residual gap after recovery is detection/data-availability limited, not
  renumber-limited.** 1957: 2331 of 2424 boundaries detected (96%); the ~93 truly-undetected
  are scattered singletons (63 of 89 runs) plus a few short garbled-page runs.
- **Recovered output is `production-<label>/parsed_acts_recovered.json` (NEW FILE).** It
  never overwrites `parsed_acts_fixed.json`. Per-act keys added: `origin`,
  `renumber_status` (anchor/filled/self_numbered/ambiguous/kept_parsed), `chapter_int_final`.

## Recommendation

Good enough to base ingestion on for the **~1880-forward chaptered era** (1957/1931/1893
land at 92-94% complete, precision clean), provided the few `ambiguous`/flagged acts are
reviewed rather than silently dropped. The **pre-~1880 segment (1850-1875) needs a separate
header-free detector** before its parse can reach comparable completeness — do not assume
this pass fixes the early corpus.
