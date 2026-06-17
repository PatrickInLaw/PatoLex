# Chaptered-era (1880-1999) detection-miss diagnosis — 1931 & 1933

**Date:** 2026-06-16 · **Scope:** READ-ONLY. Why does the production parser
(`ingest_from_ocr.py` → `header_starts_act` / `flush_act`) miss chaptered-era
acts whose `CHAPTER <n>` header IS present in the consensus OCR?

**Method:** On the 5090 (data root `C:\Users\patolex\PatoLex-scratch`), reproduced
the exact production header walk against `production-<label>/ocr_consensus/page_ocr_results.json`,
listed chapter numbers present in the OCR but absent from `parsed_acts_recovered.json`,
located each `CHAPTER <n>` header line, and classified the failure. A second probe
(`diag_dropped_probe.py`) isolated the acts where `header_starts_act` *fires* but
`flush_act` *drops* the act, and `diag_ctx.py` dumped verbatim context.

What the production detector requires to keep an act (all must hold):
1. `HEADER_RE` matches the line — anchored `^…$`, CHAP-ish word + a 1–8 char numeral, line ends after the numeral (+optional dash tail).
2. `AN_ACT_RE` ("An Act") within the next **4 non-empty** lines (`_next_nonempty(lines,i,4)`).
3. In `flush_act`: buffer ≥ 60 chars, header line has no "Approved/Passed", **and `has_enact_marker(full)` is True** — i.e. `ENACT_MARKER_RE` = `"People of the State of California"` **or** `"do enact as follow"` appears somewhere in the act body.

## Failure-mode counts (sampled headers that ARE in the OCR but missing from parse)

| Mode | What breaks | 1931 | 1933 |
|------|-------------|-----:|-----:|
| **redirect-stub: no enacting clause** (`has_enact_marker` False) | Header + "An Act" present, but body is a one-line "Note.—For text see Stats. 19xx Ch. N" redirect with NO "do enact"/"People of the State" → `flush_act` drops it. **Dominant 1933 mode.** | 7 | **94** |
| **resolution, no "An Act"** | Item has a real CHAPTER number but is a Concurrent/Constitutional Resolution / charter approval — never contains "An Act", so cond. 2 fails | 46 | 18 |
| **`CHAPTER n` shares a line w/ body text** | Number is embedded mid-sentence (cross-reference, e.g. "…repeal chapter 32, Statutes of 1911…") so `HEADER_RE`'s `^…$` anchor fails | 30 | 12 |
| **garbled header glyph / numeral** | OCR noise on the header line ("CHAPTER 92■.", "CHAPTER 8&6.") breaks `HEADER_RE`'s numeral group / trailing anchor | 4 | 1 |
| **"An Act" beyond the 4-line lookahead** | An interposed "Note.—See Stats…" or blank lines push "An Act" past 4 non-empty lines; also stacked headers on one page | 3 | 1 |

Notes on the counts: these are per-sampled-header classifications over the missing
set; the *raw* "missing" number is inflated because high body-reference numbers
("chapter 1480, statutes of 1927") are counted as chapter mentions but are not acts.
The **mode mix**, not the absolute totals, is the finding. The split differs sharply
by volume: **1933 is overwhelmingly redirect-stubs** (acts whose printed text was
chaptered out-of-sequence with only a pointer left in place), while **1931 is a mix
of true resolutions, body-line merges, and header garble**.

## Verbatim OCR examples (tagged by mode)

**[redirect-stub: no enacting clause] — 1933 ch. 88 & 839 (two acts stacked on p535)**
```
>> CHAPTER 88.
   An act to amena section 809 of tie Agricultural Code, relating
   tie standardization of walnuts.
   {Approved by the Governor April 13, 1933. In effect August 21, 1933]
   Norz.—For text see Stats. 1933, Ch. 25.
   CHAPTER 839.
   An act to amene section 792 of the Agricultural Code, relating
   lo the standardization of avocados.
   [Approved by the Governor Apri■ 13, 1933 In effect August 21, 1933 ]
```
Header fires, "An Act" present, but the body has **no `do enact`/`People of the
State` line** → `has_enact_marker` False → dropped. (94× in 1933.)

**[resolution, no "An Act"] — 1931 ch. 3**
```
>> CHAPTER 3.
   assembly Concurrent Resolution No, 2--Approving amend-
   ments to the charter of the eidy of Alameda, after due
   ...
   [Filed with Seeretary of State Januniry 16, 1931 J
```
Real CHAPTER number, but it is a Concurrent Resolution — never contains "An Act",
so `header_starts_act` cond. 2 never fires. (46× in 1931.)

**[CHAPTER n shares a line] — 1933 ch. 32**
```
   An act to amend sections 2 and 16 of an act entitled "An act Stats 1931
   to provide far the recall of elective officers of incorporated matey
>> cities and towns, and to repeal chapter 32, Statutes of 1911,
```
`chapter 32` is a mid-sentence body cross-reference; `HEADER_RE`'s `^…$` anchor
rejects it. The oracle counts it; it is not an act-start.

**[garbled header glyph] — 1933 ch. 92**
```
>> CHAPTER 92■.            (trailing noise char after the numeral)
   An act to amend sections 2322228 and 4257 of the Political
   ...
   CApproved by the Governor June 14, 1933...
```
The trailing glyph breaks `HEADER_RE`'s `\s*[.,;:]?…$` close, so the header line
is not recognized even though "An Act" follows immediately.

## Recommendation — what a recovery detector must do differently

The single highest-yield fix is to **decouple act-start detection from the
`ENACT_MARKER_RE` gate**: a printed `CHAPTER <n>` header immediately followed by a
line beginning "An act …" and an `[Approved … 19xx]` / "Filed with Secretary of
State" approval footer is, by itself, a complete and valid act boundary — the
"do enact as follows" clause is **absent by design** in the very common
out-of-sequence "Note.—For text see Stats. 19xx, Ch. N" redirect entries (the
dominant 1933 miss, ~94 acts in one volume). `flush_act` should keep an act on
*header + An-Act + approval-marker* even when `has_enact_marker` is False (flagging
redirect-stubs for later text-join, not discarding them). Secondarily, the detector
should: (a) tolerate a garbled trailing glyph on the header numeral and a
mid-buffer "Note.—See Stats…" line by widening the "An Act" lookahead past 4
non-empty lines and re-segmenting **multiple headers stacked on one page** into
separate acts; (b) **exclude resolutions** (Concurrent/Constitutional Resolutions,
charter approvals — "Filed with Secretary of State", no "An Act") from the act count
rather than treating them as misses; and (c) only count a `CHAPTER <n>` token as an
act-start when it is the line head (page-top or after a blank line), never when it
is embedded mid-sentence — which simultaneously removes the body-cross-reference
inflation in the "missing" oracle. Net: the recovery pass must treat the **approval
footer**, not the enacting clause, as the act-completeness witness for this era.
