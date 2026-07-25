# LESSON 2026-07-25 — Borrowed confidence, additive Roman, and validators that can't see

**Session:** cc021 · **Status:** all figures MEASURED across 208–216 volumes / ~71,000 confident acts · **Nothing here is inferred from samples**

---

## 1. ★ "Confident" did not mean what it looked like

The pre-cc019 parser could not match the very common OCR heading form `Cuap, LV.—` (comma where the period should be). So for a large part of the early corpus **it was not emitting acts — it was emitting merged blobs**:

| Act | BEFORE buffer | AFTER (correct boundary) |
|---|---|---|
| 1858 ch. 357 | **41,969 chars** | 868 |
| 1862 ch. 21 | **32,392 chars** | 2,031 |
| 1863 ch. 3 | 12,667 | 2,963 |
| 1860 ch. 272 | 11,791 | 5,165 |

Each blob contained the act's **own garbled** `[Approved …]` **plus the clean approval lines of the acts that follow**. `parse_act_date` scans forward and takes the first in-window hit — so it took a **downstream** date.

**Confirmed wrong in five cases:**

| Act | Its own printed date | What was emitted | Whose date that was |
|---|---|---|---|
| 1858 ch. 357 | `[Approved Apri` (truncated) | 1858-04-26 | **ch. 358's** |
| 1863 ch. 3 | *none printed at all* | 1863-02-05 | **ch. 55's** |
| 1862 ch. 21 | `Fubruury 20, 1862` | 1862-02-25 | wrong day |
| 1862 ch. 63 | `3larch 15, 1862` | 1862-03-13 | wrong day |
| 1860 ch. 171 | `April 8, 180.` | 1860-04-03 | **ch. 172's** |

### The consequence for measurement

When correct segmentation arrived, those acts **stopped being confident** — and a naive diff reported them as **"lost chapters."** They were not lost. They were present, correctly bounded, with the right chapter number and header. **They lost a confidence that was never real.**

> **Rule: a before/after comparison against a baseline that was silently merging records will report improvements as regressions.** Check whether the BEFORE record was *entitled* to the field you're comparing.

Of 17 apparent losses: **1 genuine regression, 5 correct rejections, 11 date-parser failures on acts that are present and flagged.**

---

## 2. Strict canonical Roman is the WRONG GRAMMAR for this corpus

The obvious fix for numeral corruption is to validate against canonical Roman. **Measured, it is a large net loss.**

**19th-century California printed the 400s additively** — `CCCCV`, `CCCCXXI`, `CCCCXCI` — **not `CDV`.**

| Validator | Placement | Correct chapters destroyed |
|---|---|---|
| Strict canonical | raw token | **1,199 / 6,959 (17.2%)** |
| Strict canonical | post-substitution | **396 (5.7%)** — to fix 122 keys |
| **Relaxed additive** | post-substitution | **9 (0.13%)** — all genuine garbage |

The 9 rejects are `CCLIXVII`, `XLX`, `DLIIX`, `DCDXX`, `CCCXXIIV`.

### And it cannot see the damage anyway

`CXCVIL` → `CXCVII` · `CCCVIIT` → `CCCVIII` · `CCCLY` → `CCCL` · `CXXXVIIL` → `CXXXVIII`

**All four are canonical *after* transformation.** The OCR-substitution rules (`T→I`, `J→I`, trailing-`L`-run→`I`, silent stripping of unknown characters) **manufacture well-formed numerals out of garbage**. A validator placed *downstream* of them is structurally blind to exactly the failure it was added to catch.

> **Rule: validating after a normalisation step only proves the normaliser produced well-formed output — not that the output is true.** Validate the raw token, or validate against an independent signal (page order), or accept that you're measuring the normaliser.

---

## 3. The Arabic path had no validation at all

`parse_chapter_number`'s Arabic branch was `int(t)` — accepting anything.

- **355 confident acts** carried out-of-range chapters: `90956` (1967-vol2), `14383` (1957-vol2), `6548` (1907-09).
- **611 of the 992 duplicate chapter keys are on the Arabic path** — *more than the Roman path* — and no Roman rule touches them.

The attention went to Roman numerals because they *look* fragile. The bigger hole was the branch that looked simple.

**Fixed:** both paths now bound at `MAX_PLAUSIBLE_CHAPTER = 5000` (the largest real session, 1945, had 1,527). Out-of-range → `chapter_int = 0` → routed to `flagged_acts` **with `chapter_raw` intact for review**. Visible and recoverable, rather than silently ingested under an impossible key.

---

## 4. The approval-date blocker was adjacency, not spelling

Everyone (me included) assumed the 7,822 flagged acts were failing on mangled approval **keywords** — `"Pussed March 20, 1850"`, `"Arprovep. Avril 30. 1852"`.

**Measured: fixing keyword spelling recovers 60–77 acts. A rounding error.**

Holding `_KW` **completely unchanged** and only permitting a gap between keyword and month: **2 → 1,598 recoveries.** Gap length is bimodal — 3.4% at ≤10 chars, then 48% at ≤15, 85% at ≤40. That cliff is the width of one phrase:

```
239 " by Governor "    236 " hy Governor "    100 " bv Governor "
 84 " by the Governor "  40 " by Guvernor "     36 "tary of State "
```

`APPROVED_MODERN_RE` **already modelled this idiom** — but demanded the literal strings `Governor` / `Secretary of State`, so every OCR variant fell through to `APPROVED_RE` and died on strict adjacency.

### Why the targeted fix beat the general one

| Option | Recovered | Earlier-date FPs | Ratio |
|---|---|---|---|
| Guarded 40-char gap | 1,748 | 22 | 79:1 |
| **Fuzzy-connector arm** | **1,364** | **1** | **1364:1** |
| Positional (bare triple in head) | 3,701 | **491** | rejected |

A blanket gap *loosens* and admits cross-reference prose (`"…to amend an Act approved April 30th, 1855…"` on an 1856 act). The connector **requires a Governor/Secretary token inside the gap**, so it cannot.

The positional rule was rejected on measurement: **1.5% corruption of confident acts** vs 0.21%, and **12.8% of its no-keyword tier sits in operative-date language** (*"shall take effect … July 1, 1909"*) — which would stamp a wrong date on a real act.

> **Rule for a write-once corpus: a flagged record is visible and recoverable; a wrong value is silent and permanent.** Prefer the fix with the better false-positive ratio even at lower yield.

**Remaining, unfixed:** ~4,000 acts (51%) — 1,049 have a clean month but a corrupt year (`"Approven, May 4, 185"`), 112 need a fuzzy month (`"Avril"`, `"jApal"`), 203 neither. Day/year/month corruption is a separate axis.

---

## 5. Silent drops are worse than wrong values

`flush_act` contains `if not has_enact_marker(full): return` — **no record at all**, not even in `flagged_acts`, so the act never reaches the review worklist.

**1862 ch. 10** hit it. My own `ENACT_MARKER_RE` loosening was **asymmetric** — it tolerated OCR rot in the *second* "of" but left the *first* literal:

> *"The Prople **af** the State **of** California… **du enact an fellows**"*

Its own `[Approved February 11, 1862.]` parses cleanly. That one gate was all that stood between it and full confidence, and it vanished without trace.

> **Rule: a gate that DROPS should be strictly more conservative than a gate that FLAGS.** If you can't be sure, flag it — an invisible loss cannot be audited.

---

## 6. Open, explicitly deferred — needs a decision, not a guess

Measured options for the 992 duplicate keys:

| Pass | Duplicates resolved | Correct chapters broken |
|---|---|---|
| A — strict canonical reject | 122 keys | **396** ❌ |
| A′ — relaxed additive reject | 63 culprits | **9** |
| **B — monotonic single-edit repair** | **233/360 culprits; 223/303 dirty keys cleared** | 0 by construction — **but it TOUCHES 1,103 non-duplicate acts** |
| **C — duplicate arbitration by sequence fit** | **975/992 keys get a unique winner** | 0 — but never corrects the loser's value |

**B and C are not implemented.** Both *infer* a corrected chapter number from page order, which is **data mutation on inference** — and the ground truth here is circular: an inflated value often lands exactly on a slot vacated by a missing neighbour and looks correct. **4 of the 11 named-token instances are on-sequence.**

**The Y-strip class is the largest single opportunity and the least settled:** 316 acts where `Y` is silently deleted (`LY` → 50, true 55 — *deflation*, not inflation). Testing `Y→V`: fits where the current value doesn't in **138** cases, both fit in 24, neither in 20.

**None of this should be actioned without page images or the printed indexes.** Text alone cannot settle the trailing-`L` class: `XVIIL` is genuinely either `XVII` + a blot (17) or `XVIII` misread (18).

---

## Related

- Extends `[[LESSON_2026-07-24_residual_71_is_parser_grammar_not_ocr]]` — same session line, same theme: **the defect was never OCR quality.**
- Confirms `[[early-era-headers-consensus-bug]]`: the heading token remains the corpus's most variable element.
- The measurement discipline here is the one from the cc019 comma episode: **measure the problem before designing the solution, and re-measure after "fixing" it on someone else's count.**
