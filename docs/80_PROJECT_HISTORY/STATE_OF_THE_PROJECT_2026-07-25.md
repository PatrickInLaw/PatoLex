# PatoLex — State of the Project

**SNAPSHOT IN TIME: 2026-07-25.** This is a point-in-time executive report, not a living document. Figures below were measured on this date and will drift. Do not treat it as current after the next reparse or ingest.

---

## 1. The project, in one paragraph

PatoLex is a searchable, point-in-time archive of California statutory law — what any statute said on any given date, back to **1850**. It is built **historical-first**: the hardest, least-certain segment (statutes reconstructed by OCR from scanned 19th-century session laws) is being built *before* the easy modern era, and **there is no public launch until the full corpus is present and validated**. The deliverable is a legal-research instrument for attorneys, and a one-time gift: build it right once, hand it on.

---

## 2. Where the corpus actually is

### The distinction that matters most

**There are three separate things, and they are NOT the same:**

| Layer | State | Contains |
|---|---|---|
| **A. Scanned page images + OCR text** | ✅ **Complete, ~1850–2000** | 216 volumes · 332,608 pages · 3.44 GiB of consensus OCR |
| **B. Parsed act files** (`parsed_acts_*.json`) | ⚠️ Built, but from a **defective parser** | 71,443 confident acts + 7,822 flagged |
| **C. The database** (Postgres `patolex`) | ⚠️ **Stale** | 35,332 enactments, ingested from an **older parse** |

**The widely-quoted "99.9% chapter recall" (95,923 / 96,002) is a statistic about layer B — the FILES. It is not a statement about the database.** Nothing from the 2026-06 recovery campaign, and nothing from this session's parser work, has been ingested. Layer C has not moved.

### What the OCR layer covers

- **~1850–2000** — image scans → 3-engine consensus (Tesseract + docTR + Surya)
- **~1997–2008** — born-digital Chief Clerk PDFs → direct text extract, no OCR needed
- **1989/1994–present** — official leginfo XML → no OCR at all (the "Gate F" modern layer, ~22,780 acts, already in the DB)

**The OCR-era problem is essentially solved at the image level. The remaining work is interpretation, not acquisition.**

---

## 3. ★ What actually needs re-sourcing — the number you asked for

**175 distinct printed pages, across 45 distinct physical volumes.**

That is the total from a deterministic, corpus-wide page-continuity audit (printed running-head numbers that skip, i.e. a leaf that was never digitized by anyone). It breaks into three confidence tiers:

| Tier | Pages | Volumes | What it is | Confidence |
|---|---|---|---|---|
| **1 — named chapter loss** | **25** | **8** | Pages whose absence loses a **specific, identifiable chapter**. 21 chapters + 4 chapter tails. | **HIGH — all 8 ranges pixel-verified** |
| **2 — body-text loss** | ~102 | 17 more | Even-parity dropped leaves; real statutory text lost, but no whole chapter | **MEDIUM — audit-derived, NOT individually verified** |
| **3 — "inspect only"** | 49 | 24 more | Odd-parity single-page breaks. May be dropped leaves, may be printing artifacts | **LOW — unresolved by anyone** |

### The honest caveat on those numbers

**Only ~10 of the 45 volumes have had their page ranges verified against the actual images.** Tiers 2 and 3 rest entirely on the automated audit — **and that audit was proven wrong on a Tier-1 volume this session.** For 1929 it reported the missing leaf 12 pages away from its true location, because an unnumbered section-divider page defeated its detector. The same failure mode plausibly affects a fraction of Tiers 2 and 3.

**Tier 3 should not go to a library at all until it is triaged against the page images we already hold — at zero cost.**

### What is NOT on that list, and why

| | Status |
|---|---|
| **The "71 unreadable chapters"** | ❌ **Not a scanning problem.** All 71 recovered from the volumes' own printed contents tables. The pages were always present and legible at 300 DPI. |
| **5 chapters in *Amendments to the Codes*** | ⚠️ **Different book.** 1874 ch. 587/679, 1876 ch. 306/497/498 were enacted but printed in a companion volume we do not hold. **No existing plan covers acquiring it.** |
| **7 elections, 1911–1924** | ❓ **Unknown.** No "Measures Submitted to Vote of Electors" section exists anywhere in the digital series — including the **Oct 1911 special that created the initiative power**. Cannot tell whether the printed volumes lack it or the scanning skipped it. **A 10-minute physical check answers it.** |
| **9 unauditable 1850s volumes** (3,059 pp) | ❓ **Invisible to the method.** Could hide dropped leaves. On no list. |
| **Extra/special sessions** | ❓ **Unmeasured.** `production-1927-vol1-26chapters` (1926 Extra Session) parses to **0 acts**. |

---

## 4. Monday 2026-07-27 — the trip

**Witkin State Law Library**, Gillis Hall 3rd floor, 914 Capitol Mall · call number **`L325`** · **copy c.2** · 9:30–4:00 · no appointment · photography permitted, **no flash** · scanners need **photo ID**.

**Do NOT go to the State Archives (1020 O St)** — it holds the volumes but **bans cell phones in the research room and prohibits patron copying of bound volumes**. Nor CSL Government Publications (does not hold the title) or California History (closed Mondays).

**Plan: Tier 1 only — 8 volumes, 25 pages, ~2–2.5 hours**, in order:

> **1872 → 1986 → 1927 → 1985 (two leaves) → 1970 → 1929 → 1981 → 1972**

Then the **proposition presence check** (6 volumes, ~1 hour) — highest information-per-minute of the day, and it answers a question that blocks an entire track.

**Why not all 175 pages:** 45 heavy folios in a 6.5-hour day, with reading rooms typically capping simultaneous volumes at 3–5 and paging likely stopping ~3:30, is **7.5+ hours of retrieval before a single photograph**. Tier 2 is better handled by a **mail-order duplication request**; Tier 3 shouldn't leave the office.

---

## 5. Where the parser stands

The corpus files (layer B) were built by a parser with **structural defects**, all found and fixed this session, all measured against the real corpus:

| Defect | Effect | Measured |
|---|---|---|
| Em-dash / comma chapter headings | Whole heading forms unmatched | **+465 chapters** |
| Unsigned & veto-override enactments | Acts with **no `[Approved]` line at all** were invisible | 977 unsigned found |
| Approval-line adjacency (`"by Governor"` garble) | Intact dates unreachable | **+1,364 acts** |
| Headings that never say "An Act" | Real acts rejected | recovered |
| Merged-act blobs | Acts inherited a **neighbour's date** | 5 confirmed wrong dates |
| Arabic chapter numbers unvalidated | Confident acts at chapter **90956** | 355 flagged |

**Status: fixed, tested (187 tests, full suite green), committed and pushed — but NOT YET APPLIED to the corpus.** Every measurement was a dry-run diff; no corpus file has been modified.

### The three big structural findings

1. **The old parser's "confidence" was partly fraudulent.** It was merging many acts into single blobs (one buffer was **41,969 characters**) and taking a clean approval date from a *following* chapter. Correct segmentation exposed this — which is why a naive diff first reported *improvements* as "23 lost chapters."

2. **The recovery chain never reaches the database.** `ingest_clean.py` reads **only** `parsed_acts_fixed.json`, and only its `confident_acts`. The entire 2026-06 recovery campaign's output sits in files nothing downstream consumes. **However** — measurement showed nothing with real text is un-reproducible by a corrected parser, so **no new bridge component is needed**. A correct reparse subsumes it.

3. **7,822 acts are being silently discarded.** Their text sits in `parsed_acts_fixed.json` under `flagged_acts`, which the ingest drops. **99.4% carry both "An Act" and an enacting clause**; essentially all are flagged for one reason — a date the parser couldn't read. The connector fix recovers ~1,364 of them; the rest need date-level work.

---

## 6. What is blocking the finish line

The end state is **one single mass ingest** of the full 1850–2026 corpus, run exactly once. In sequence:

| # | Step | State |
|---|---|---|
| 1 | Apply the parser fixes to the corpus (reparse) | **Ready.** ~15–30 s. Diff verified, nothing lost. |
| 2 | Triage `flagged_acts` | Measured, rule proposed, **not implemented** |
| 3 | The 23 volumes with **no parse file at all** | Invisible to ingest; 5 hold real text |
| 4 | Acquire *Amendments to the Codes* | **No plan exists** |
| 5 | Propositions / constitutional amendments (Track 2) | Retrieval complete; **7 elections unresolved** |
| 6 | `source_document` registration, 1877–1990 | Open prerequisite |
| 7 | Gate F gaps (1993-94, 2001-04, 2025-26) | Open |
| 8 | The single mass ingest: backup → wipe → full re-ingest → diff | **Not started** |

**Nothing is blocked on scanning.** The physical-acquisition gap (175 pages) is real but small, and Monday closes the part of it that costs whole chapters.

---

## 7. Honest assessment

**What is genuinely in good shape:** the image and OCR layer is complete and of known quality (native 300 DPI); the parser defects are now found, measured, and fixed; the trip list is verified; the test suite went from 8/11 with three suites silently dead to 11/11 green.

**What is weaker than the headline numbers suggest:**
- The "99.9% recall" describes files, not the database. **The DB is stale and has never seen any of this work.**
- ~35 of 45 volumes on the re-scan list are **unverified**, and the audit behind them has a demonstrated failure mode.
- 992 duplicate chapter keys remain, and the fix requires page images to settle — text alone cannot.
- The *Amendments to the Codes* volumes are a **genuine hole in the corpus with no owner**.

**The single biggest risk** is that the mass ingest runs exactly once, and several inputs to it are still measured rather than verified. Every measurement this session that was checked against the corpus rather than reasoned about **overturned the assumption** — three times out of four.

---

## 8. Recommended next three moves

1. **Monday: Tier 1 + the proposition check.** 21 chapters that exist nowhere else, plus an answer that unblocks Track 2.
2. **Run the reparse and re-measure recall against the oracle.** Cheap, reversible, and it tells us what the corpus actually contains rather than what a June-dated file says.
3. **Decide the *Amendments to the Codes* question.** It is the only known gap with no plan attached, and it cannot be closed by any amount of parser work.
