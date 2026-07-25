# LESSON 2026-07-25 — A page-numbering convention manufactured ~50 phantom missing leaves

**Session:** cc021 · **Status:** all 82 claimed gaps re-OCR'd at 400 DPI and adjudicated against page images · **Impact:** a 175-page "must re-scan" list collapsed to ~97 pages, and an entire confidence tier was eliminated

---

## What happened

A deterministic page-continuity audit reported **175 missing printed pages across 45 physical volumes** — pages whose printed running-head numbers skip, implying a leaf that was never digitized.

Verified against the images: **~97 pages across 20 volumes.** Of 82 claimed gaps:

| Class | n |
|---|---|
| CONFIRMED | 28 |
| WRONG_LOCATION | ≥4 |
| NOT_A_GAP | ≥30 |
| divider-adjacent (mostly artifact) | 50 |

**The entire odd-parity "inspect" tier — 49 pages, 24 volumes — produced ZERO confirmed losses.** Every volume from **1931 through 1967** in the list (27 directories, ~76 claimed pages) has **not one clean confirmed gap**.

---

## ★ The root cause: a drop folio the detector cannot see

**50 of the 82 claimed gaps sit at the same structural feature** — the transition from the chapter body into the `CONCURRENT AND JOINT RESOLUTIONS` section at the back of each volume.

That transition is 2–4 scan pages that yield **zero top-strip digits**:

1. a **blank verso** closing the chapters,
2. an **unnumbered section-divider half-title**, and
3. a **section-opening page whose folio is a DROP FOLIO — printed at the FOOT**, e.g. `( 141 )`.

The audit read only the **top** strip of each page. A drop folio is invisible to it. Its monotone dynamic-programming solver has no way to represent *"page present but unnumbered here"*, so when the numbering appears to jump it books an **offset step** — and **manufactures a gap.**

**Right count, wrong location — roughly fifty times.**

### Worked example — 1953 Vol. 1

- Printed **137** is the **last page of Ch. 14**, ending mid-page with the bottom third blank.
- The next scan page is the resolutions divider.
- The one after is printed **141**, with `( 141 )` **at the foot**.

The claimed missing "138–139" are **the blank verso and the divider's blank side. No statute text exists on them.** All five of that volume's claimed gaps are the same artifact.

Confirmed by eye in **1915, 1929, 1938, 1941, 1953, 1963, 1967**.

---

## What stops this from being a blanket dismissal

**1915 Vol. 1 printed 1547 is the *opening* of Chapter 771, with text running to the bottom margin.** There, printed 1548 genuinely is lost.

So divider adjacency alone does not prove artifact. The discriminating test is: **does the preceding numbered page's text terminate?** Measured as bottom-band ink density against the volume median:

| Ratio | Reading | n |
|---|---|---|
| ≤ 0.30 (often 0.00) | text ends — blank verso / divider | ~29 |
| 0.4 – 0.8 | ambiguous, needs eyes | ~9 |
| ≥ 0.85 | text runs on — **real candidate loss** | ~12 |

---

## The rules this produces

> **1. A page-number gap is evidence of a numbering discontinuity, not of a missing leaf.** Those are different claims. Unnumbered plates, dividers, blank versos, and drop folios all produce the first without the second.

> **2. Never read only one region of the page.** This corpus prints folios at the top *and*, at section boundaries, at the foot. A detector that reads one band will hallucinate structure at exactly the places where the printing convention changes — which is to say, at every section boundary in every volume.

> **3. A solver that cannot express "unknown" will invent a value.** The monotone DP had no state for "present but unnumbered", so uncertainty came out as a confident gap. **Detectors need an UNREADABLE class, and anything adjacent to one must be quarantined, not reported.**

> **4. Corroborate with content, not just structure.** The bottom-band ink test settled in minutes what page numbering alone could not settle at all. When a structural signal is ambiguous, ask whether the *content* is consistent with the claim.

> **5. Verify before anyone travels.** The unverified list was overstated by ~45% and would have sent someone to 25 extra volumes, most of them for blank pages. Verification cost a few hours of compute against page images we already held.

---

## Related

- The 1929 case was first caught in isolation during the trip reconciliation and looked like a one-off. **It was the visible instance of a systematic failure.** *One anomaly in an automated result is worth generalising before trusting the rest.*
- Same theme as `[[LESSON_2026-07-25_numerals_dates_and_borrowed_confidence]]`: **a validator or detector downstream of a lossy transformation measures the transformation, not the truth.**
- Same theme as `[[LESSON_2026-07-24_residual_71_is_parser_grammar_not_ocr]]`: the "71 unreadable chapters" also evaporated on inspection. **Twice now, a confidently-stated acquisition need turned out to be a measurement artifact.**
