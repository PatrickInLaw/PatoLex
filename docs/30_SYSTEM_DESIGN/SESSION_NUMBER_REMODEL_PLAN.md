# Plan: model sessions by their CANONICAL SESSION NUMBER, not by folder-year

**Status:** PLAN (2026-06-18, cc013). No code/oracle moved yet. For Patrick's review before execution.
This is denominator + schema code → **Hans ×2** when built.

## 1. Problem
The oracle (`ca_chapter_counts.tsv`) and the matchers (`find_oracle_match`, `chapter_vs_oracle.py`) key a
scanned volume to its chapter count by the **leading 4-digit year of the folder name**. That is a *proxy hack*,
not the session's identity. Symptoms it has caused:
- **1863/1864 collision:** the 14th session (1863) and 15th session (1863-64) both live in folders that lead
  with "1863", so year-keying cannot tell them apart; the 14th has no oracle row and can't be added cleanly.
- **The recurring "biennium bucketing" bug** (the "~20k missing chapters" artifact, hit 5+ times): even-year
  budget/extra sessions bound in odd-year volumes get mis-stamped — again, a pure year-keying artifact.

## 2. Principle
The California Legislature identifies a session by its **ordinal number** (1st, 7th, 14th, 49th, …), printed on
each volume's own title page. **Model that.** Year becomes a descriptive attribute, not the join key. Ground the
key in the source document.

## 3. Recon evidence (2026-06-18, representative volumes)
The ordinal is declared and readable — but extraction needs hardening, and extras are real:

| volume | declared ordinal | notes |
|---|---|---|
| 1850 | **1st** | clean |
| 1856 | **7th** | clean |
| 1863 | (not surfaced) | ordinal not in first 30 pages — needs deeper/engine-union scan |
| 1863-64 | **15th** | OCR'd "Fif- teenth" — needs **de-hyphenation** |
| 1865-66 | (not surfaced) | same as 1863 |
| 1887 | **27th** | clean ("twenty-seventh") |
| 1931 | **49th** | clean ("FORTY-NINTH") |
| 1945 | **56th** | also mentions an "extraordinary session" |
| 1957 (56/57chapters) | "REGULAR SESSION" + "Extraordinary Session" | even-year volumes; **extras present** |
| 1999 | (generic) | "Special Session"; modern phrasing differs |

**Conclusions:** (a) the ordinal↔year mapping is **irregular** (annual early, then biennial) → must be *read*,
not formula'd (the existing `1849+N` in the code is itself a hack and is wrong for later sessions); (b) robust
extraction must handle de-hyphenation, engine-union, title-page targeting, and modern phrasing; (c) **extra-
ordinary/special sessions** need a sub-designator in the model.

## 3a. P0/P1 build results (2026-06-18) — `build_session_reference.py`
Web sources didn't yield a machine-readable list (official PDF is image-only; Wikipedia overview lacks it), so
per Patrick's fallback the reference is built **from the corpus's own declared ordinals** (the authoritative
source for what we hold). Tool `pipeline/analysis/build_session_reference.py` (READ-ONLY; de-hyphenation +
engine-union + 1..99 parser); output `_session_reference.tsv`. **Resolved 61/222 ordinals directly.** Findings:
- **Historical era (1850–~1903): the ordinal sequence is clean and self-correcting.** 1850=1 … 1862=13 …
  1863-64=15 → **1863 = the 14th session** (proven by the sequence even though 1863's title page didn't OCR —
  independently confirms the missing-14th-session conclusion). OCR misreads (1855/1861/1873-74) are corrected
  by the monotonic sequence; `ordinal_not_read` gaps fill by interpolation.
- **Two-form canonical id, split ~1905.** From ~1905 the legislature uses **year-pair session naming
  ("1993-94 Regular Session") + extraordinary/special designations**, NOT ordinals (the extractor returns no
  ordinal but catches "1st/4th Extraordinary," "Special Session"). Both forms are the legislature's own identity.
- **Exposes more year-keying damage:** `production-1900-01` declares the **34th session** (= 1901 Regular, 275)
  but is currently matched to "1900 Extra Session = 15." The ordinal model fixes it.
- **Re-confirms 1873-74-code = 20th session** (same as the main volume) → code amendments share the session.

## 3b. P2 validation, Hans-audited (2026-06-18) — `build_canonical_sessions.py`
P2 walks the 133 regular oracle rows chronologically, assigns ordinals, validates vs the corpus-declared
ordinals. **Hans's first audit found the validation OVERSTATED** and three real flaws — all fixed:
- **CRITICAL (join):** declared ordinals were keyed by the label's *leading* year, but the oracle's
  `session_year` uses the START year for some biennia (1863-64→1863) and the END for others (1873-74→1874),
  so biennial anchors (1877-78, **1900-01→34th**) were silently lost → "ok" meant "no anchor," not "confirmed."
  Fixed by registering each ordinal under *both* years of the label.
- **MAJOR (extra captures):** modern extraordinary-session ordinals ("1st/4th Extraordinary") were polluting the
  declared map. Fixed by excluding `extraordinary|special` phrases.
- **MINORs fixed:** deterministic sort tie-break (for when the 14th row is added), unique extra `canonical_id`s.

**Post-fix result (much stronger):** the **`+1` offset is anchored at ~28 points across 1863-64 (15) → 1945
(56)** — *every anchored biennium shows +1* — the signature of exactly **one missing regular session, the 14th
(1863)**. It is NOT literally every year: 1865-66/1867-68/1869-70, 1881, and 1905-1913 have no readable ordinal
(no anchor, interpolated), and **1937** ("Fifty-Second" OCR'd "Firry-SEcOND" → parser mis-grabbed "2") was a
garbage anchor — **2nd-Hans-flagged, now excluded by a magnitude gate** (|declared−assigned|>2 → OCR_GARBAGE,
not a real anchor; chosen over Hans's `session_kind` filter, which would have dropped ~8 *legitimate* modern
anchors that P1 mis-labeled "extra"). The 1855/1861 conflicts are OCR one-low (−1); the duplicate-"19th"
resolved correctly (1873-74 = 20, the code volume's reading). **2nd Hans pass verdict: the four fixes pass and
the "one missing 14th session" conclusion is SOUND** (arithmetic verified; the +1 cannot be a 2-missing or
duplicate-row artifact given the clean 1850-1862 anchors). **Honest caveat (Hans):** 1947+ has NO ordinal anchors (modern volumes use year-pair naming), so
"only one missing session" is *confirmed 1863–1945, unverified after* — which is fine, since the modern era is
identified by year-pair, not ordinal. The missing-14th conclusion also rests on an *independent* proof (the
index-read duplicate-title test), so it does not depend on P2.

## 4. Target data model (additive oracle columns)
Add to `ca_chapter_counts.tsv` (keep existing columns for back-compat during transition):
- `session_number` — the regular-session ordinal (int): 1, 7, 14, 15, 49, …
- `session_kind` — `regular` | `extraordinary`
- `extra_ordinal` — for `extraordinary`, which one (1, 2, …); `0`/blank for regular
- `canonical_id` — derived join key, **two-form by era** (both the legislature's own identity):
  - historical (1850–~1903): ordinal — `S14` (14th regular), `S15`, …
  - modern (~1905+): year-pair + kind — `1993-94R` (regular), `1994X1` (1994 1st extraordinary), `1999SP` (special)
- (existing `session_year` retained as descriptive `years`)

**Join key = `canonical_id`.** The 14th and 15th sessions become `S14` and `S15` — distinct rows, no collision.
For modern volumes the join uses the year-pair + extraordinary/special designation the volume declares (which is
also what retires the biennium-bucketing artifact — even-year extra sessions get their own `…X1`/`SP` id).

## 5. Establishing the numbers (the bulk of the work — two cross-checked sources)
1. **READ each volume's declared ordinal** with a hardened extractor (de-hyphenation, engine-union over the 4
   OCR fields, scan the title/front pages, handle "Nth Session" and modern phrasings).
2. **An authoritative reference table** of California legislative sessions (ordinal ↔ year(s) ↔ kind), from the
   Legislature's own records. *(Likely needs a web lookup — flag for Patrick: external fetch decision.)*
3. **Reconcile:** every oracle row + every production volume gets a `canonical_id`; volume-declared vs reference
   conflicts are flagged for review (never guessed).

## 6. Matcher changes (Hans-gated)
- `find_oracle_match` → join on the volume's parsed `canonical_id`; year only as a last-resort fallback.
- `chapter_vs_oracle.py` (the real completeness tool) → same; this **retires the `NNchapters`/biennium suffix
  hack** entirely.

## 7. Migration & safety
- Additive columns; keep year columns through the transition.
- **Golden controls must still hold:** the 12 MATCH volumes + the applied edits (1865-66=650, 1887=188,
  1883=96, 1860=385) reproduce.
- Hans ×2 (denominator + schema). Bundle with the deferred **engine-union** merge as one reviewed change.
- The **1863 14th-session row falls out naturally** once keys are canonical (no special-casing).

## 8. Phased execution
- **P0** — authoritative session reference table (ordinal↔years↔kind). *(web-fetch decision)*
- **P1** — hardened ordinal extractor; run over all 222 volumes → declared-ordinal table.
- **P2** — reconcile read-vs-reference → assign `canonical_id` to every oracle row + volume; resolve conflicts.
- **P3** — add the oracle columns + backfill `canonical_id` (additive).
- **P4** — rewrite the two matchers to key on `canonical_id`; **Hans ×2**.
- **P5** — re-measure; validate controls + applied edits; add the 1863 (14th) row; confirm the biennium
  artifact is gone.

## Known issues (carried forward, not fixed here)

- **1949X1 wrong match:** `1949-vol1-49chapters-prior` resolves to S59 (1949 Regular) via the NNchapters decode, but the volume is actually the 1st Extraordinary Session of 1949 (correct key: 1949X1, N=16).  Pre-existing in the old code; parity guard = 0 diffs.  Will be fixed when P5 re-measures with the full canonical map (the volume will get its own map entry).

## 9. Open questions for Patrick
1. **Reference table source** — OK to web-fetch California's official legislative-session list, or provide one?
2. **Modern-era identification** — confirm the modern volumes carry a usable ordinal (1931/1945 do; 1957/1999
   phrased differently — needs a closer look in P1).
3. **Extraordinary-session canonical numbering** — confirm the scheme (legislature + Nth extraordinary).
4. **Scope/sequencing** — do this as its own bundle, or fold the engine-union merge in with it?

## 10. Payoff
Fixes 1863 as a side effect; **retires the biennium-bucketing bug class**; one uniform, source-grounded model
from 1850→present; the oracle finally models the legislature's reality instead of a year proxy.
