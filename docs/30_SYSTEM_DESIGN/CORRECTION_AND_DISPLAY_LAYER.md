# Correction & Display Layer — Architecture Sketch + Open Decisions

**Status:** DESIGN — decisions to be finalized BEFORE corpus finalization / ingestion / UI.
**Date opened:** 2026-06-11 (cc007). Owner: Patrick.

## The principle (settled)
The OCR `consensus_text` is the **immutable source-of-record**. Nothing is ever
destructively edited. Every correction — deterministic, model/vision, OR community —
is stored as a **reversible overlay** with full provenance, and is auditable/revertible.

## The shape (Patrick's proposal, 2026-06-11)
A **single materialized "display" layer** per text unit holds the *current best* text,
with the **layer stack stored behind it** for review/revert:

```
display_text  =  original_OCR  +  [ layer 1: deterministic auto-correct ]
                               +  [ layer 2: model / vision resolution   ]
                               +  [ layer 3: community wiki edits         ]
```

- **99.99% of reads hit only the materialized display layer** (fast, denormalized,
  full-text indexed). The derivation history is present but cold — pulled only for
  audit / review / revert.
- Each overlay entry carries provenance: `method`, `confidence`, `actor`,
  `timestamp`, `original_value`, `corrected_value`, and a stable anchor.

## Layers (sources, in precedence order — to confirm)
1. **Original OCR** (immutable).
2. **Deterministic** (Pass A rejoin, scored de-merge, corpus-freq spell) — high precision subset only.
3. **Model / vision** (LLM-with-context + vision-on-scan) for the hard residual.
4. **Community wiki edits** (the crowdsource-correction feature; trust-tiered, moderated —
   see `CROWDSOURCE_CORRECTION.md`).

## OPEN DECISIONS (must resolve before ingestion)
1. **Anchor granularity.** Token-position is fragile across a re-OCR; prefer anchoring
   corrections to a stable unit (char span within a versioned page? content hash + offset?).
   This determines whether corrections survive a future re-OCR pass.
2. **Materialization & sync.** How/when the display layer is rebuilt when any underlying
   layer changes (on-write vs scheduled projection). Keep it denormalized for serving + FTS.
3. **Layer precedence / conflict resolution.** When two layers touch the same span
   (e.g. deterministic said X, a community editor says Y) — what wins, and how is the
   loser preserved/surfaced?
4. **Provenance & reversibility schema.** Exact columns; one-row revert guarantee;
   audit trail for legal defensibility.
5. **Search semantics.** FTS indexes the corrected display layer, but must the *original*
   also be searchable (attorney wants "what the scan literally said")? Likely both.
6. **Trust tiers for community edits.** Who can edit, moderation queue, reputation —
   intersects the existing crowdsource design.
7. **Point-in-time interaction.** Corrections are about *text fidelity*; the statute's
   *as-of-date* versioning is a separate axis. Confirm they compose cleanly (a correction
   applies to a source page; the page underlies many point-in-time statute states).

## Layer-2 in practice — chapter-number vision resolution (RESULTS, 2026-06-11, cc007)
The first real layer-2 (model/vision) artifact is the **chapter-number** overlay. The
deterministic chapter pass (`chapter_corrections.py`, monotonic-sequence reconstruction)
left **215 REVIEW** garbled chapter numbers it would not silently override. Those were
resolved by **reading the source-page scans directly** — Claude vision validated against
Sonnet-vision-at-scale:

- **Validation gate:** Sonnet returns the *printed numeral as it appears* (e.g. `CCCCXLIII`);
  Roman→int conversion is done deterministically in `aggregate_chvis.py` (Sonnet reads
  reliably but does Roman arithmetic unreliably). On the 7-case overlap with Claude's own
  hand-reads, **agreement was 7/7** — the basis for trusting the Sonnet batch.
- **Result:** **129 of 215 resolved** (61 first batch / 68 second batch) →
  `run-logs/chapter_vision_final.tsv` (`vol, order, resolved_chapter, source`).
- **3 Sonnet-UNKNOWN** (1971-vol1 o1034, 1982-vol3 o72, 1999-vol4 o159): Claude read the
  staged images directly and confirmed they are **body-text pages, not chapter-heading
  pages** — the parse's `source_page` for these points one or more pages off the heading.
- **86 still open** = 81 whose volume bundle has no cached page image + 3 wrong-page + 2
  out-of-range. These are **render-from-PDF jobs, NOT lost scans** (see finding below).

**Finding (root cause of "missing" scans — corrected 2026-06-11):** the per-volume OCR
output bundle **does NOT retain page images**. The pipeline renders the source PDF to a
`pages_prep_gray` working intermediate, runs consensus OCR, banks only the *text* artifacts
(`ocr_consensus/`, `parsed_acts_fixed.json`, `page_classification.json`, `sha256.txt`), then
**purges the page rasters to reclaim disk**. Early-processed volumes (1850–1875) have already
been cleaned, which is why their REVIEW heading pages couldn't be staged. **The source scans
are intact** in the master archive `…\PatoLex-scratch\chief-clerk-archive\{vol}_Statutes.pdf`
(verified: 1873-74 = 1086 pp, 1869-70 = 1027 pp, 1867-68 = 828 pp) — any heading page is
**re-renderable on demand with PyMuPDF**. So the remaining limit is a cheap local render +
re-run of the Sonnet-vision pass, **not** image loss or model capability. When applied, vision
results land as overlay tier **`VISION`** keyed by `(source_document_id, in_act_order)` (same
key as the deterministic overlay), precedence above deterministic.

**Operational note:** `chief-clerk-archive\` is the durable source-of-record for the scanned
historical volumes; per-volume `production-*` bundles are *derived text* and intentionally
image-free. Never treat an absent `pages_prep_gray` as data loss — render from the archive PDF.

## Chapter REVIEW closeout — 214/215 (RESULTS, 2026-06-11, cc007)
The 86 open REVIEW cases were finished by **rendering each heading page from the archive PDF**
(`source_page − 1` = PDF page index; calibrated 1:1 on 1862 = 660pp == 660 prep images) and
resolving deterministic-first per Patrick's direction:
- **Deterministic re-OCR (fresh Tesseract on the rendered heading, accept only if a clean
  numeral fits the clean-neighbour bracket):** RELIABLE for **modern Arabic** chapters
  (1971-vol1 o1034 = 1235, 1982-vol3 o72 = 830 — both confirmed by eye), but **NOT for
  19th-century Roman numerals** — single-engine Tesseract drops strokes (`CXIII`→`CXI`),
  and range-fit lets the wrong value through (caught a false 1869-70 o82=111 where the page
  says 113). So deterministic is gated to Arabic-numeral volumes only; Roman → vision.
- **Vision (Sonnet, 4 agents over 84 rendered pages) + bracket validation:** 48 answers fit
  the clean-neighbour bracket and were accepted; **35 were flagged by the bracket as not
  fitting — and the bracket was right**: those were Sonnet stroke-drops on long Roman
  numerals (`CCXLI`→`CXLI` dropping a C, `CXCIII`→`XCIII`, etc.). All 35 were hand-read by
  Claude against the page (the bracket usually pinpointed the value). This is the key method
  result: **vision + sequence-bracket cross-validation catches vision misreads that neither
  signal catches alone.**
- **Total: 215 of 215 resolved** → `run-logs/chapter_corrections_GRAND.tsv` (129 first
  campaign + 86 this round: 48 vision-fit, 36 hand-read, 2 Arabic-tesseract).
- **`1883-84-regular` o42 — initially mis-called "missing source," actually a resolver bug
  (corrected 2026-06-11).** The render step's `resolve_pdf()` mapped the volume to its source
  PDF by *filename keyword* (preferring `*_Statutes.pdf`), and silently grabbed the 15-page
  `1883-84_Statutes.pdf` — which is really the *other*, tiny bundle (`production-1883-84`,
  2 acts). The full 1883-84 regular-session volume was OCR'd from `1883-84_Code.pdf`
  (**448 pages**, matching the bundle's `page_classification` max of 448). The file was never
  missing — the resolver picked the wrong one. o42 = **CHAPTER LIV (54)** (Napa Asylum
  amendment), read from `1883-84_Code.pdf` p329. **Fix:** map a `production-*` bundle to its
  source PDF by checking the candidate PDF's `page_count` ≥ the bundle's max `source_page`
  (and ideally == its `page_classification` body count) — NEVER by filename keyword alone.
  An integrity sweep (`verify_mapping.py`) confirmed this was the ONLY mismapped volume of
  the 16 open; every other chosen PDF's page count comfortably exceeds its bundle's max
  source_page. **Lesson: do not infer a source file from a convenient name — verify it
  against what the bundle was actually built from.**

## Text-correction overlay — Sonnet adjudication expanded + residual characterized (2026-06-11, cc007)
**Sonnet adjudication consolidated** (`text_corrections_overlay.tsv`): the 2,655 freq≥10
ambiguous types, expanded past the timid 541 both-models-agree floor to Sonnet's full
authoritative set (Sonnet wins disagreements ~27/30). Tiers: AUTO_SAFE 538 / SONNET_FIX 909 /
SONNET_NAME 257 / KEEP 587 / GARBAGE_FLAG 361 / FRAGMENT_HOLD 2. **Applied corrections: 1,704
types covering 58,700 occurrences** (vs 16,506 under the old floor). A guard holds "fixes" whose
*output* is itself a non-word (line-split fragments mis-cast as substitutions, e.g.
`gation→igation`); the wordfreq-based guard must run on a box with `wordfreq` (the 5080
orchestrator interpreter lacks it) before application.

**Residual fully characterized** (`residual_triage.tsv`, 467,978 types = 385,131 singletons +
80,192 freq 2–9 + 2,655 freq≥10). Triage categories: NAMELIKE 243,441 (52%!), TYPO 146,770,
NOISE 38,513, GARBLE 36,644, FRAGMENT 2,610.
- **Structural garbage ("eeee"/cons-run/no-vowel): 67,201 types (63,695 singletons).** NOISE+
  GARBLE (~75K) quarantine most of it, BUT **~6,785 garbage tokens still leak into TYPO (2,166)
  + NAMELIKE (4,619)** — the procedural garbage filter is real but not airtight; tighten it so
  no `eeee`-class token rides in a fixable/real bucket.
- **NAMELIKE (243K, 52% of residual) is a heuristic label — and it is MOSTLY WRONG.** A name
  gazetteer was built and MEASURED against the residual (2026-06-11): **370,183 names** = US
  Census 2010 surnames (162,253) + SSA given names (88,297) + GeoNames US place tokens (119,619)
  + ca_gazetteer. Result: **only 5,438 residual types / 17,929 occurrences (1.2% of types,
  2.4% of occ) match a real name** — and even that includes coincidental matches (`repressuring`,
  `agricul`, `meanor` = OCR fragments equal to some place token). **Correction of an earlier
  overclaim:** the name gazetteer is NOT "the highest-leverage move," and the residual is NOT
  "mostly rare real names." The 243K NAMELIKE bucket is overwhelmingly pronounceable OCR garble,
  not real vocabulary. **The residual really is mostly OCR damage / typos / line-split fragments
  — names explain only ~1–2% of it, so a name dictionary does NOT materially lower the true-error
  rate.** What the gazetteer IS good for: a high-confidence KEEP list of genuine names being
  wrongly flagged (real CA legislators `ducheny`/`karnette`/`escutia`/`migden`/`poochigian`,
  places `islais`/`fricot`) — apply it (esp. the high-freq, cross-checked subset:
  `gazetteer_keep.tsv`) so corrections never overwrite a real name, but it is a precision
  cleanup, not a residual-slasher. Gazetteer build: `build_gazetteer.py`; GNIS per-state URLs
  are dead (404/503) — GeoNames `US.zip` is the working place source.

## The residual is measured PRE-overlay (2026-06-11) — fragments like `agricul`/`ramento` are already solved
Diagnostic from Patrick ("`agricul` is a fragment of agricul|tural; `ramento` of sac|ramento — why
are these in the residual?"). Answer: they ARE line-split fragments, and the **line-reunify overlay
already fixes them** — `agricul+tural→agricultural` and `sac+ramento→sacramento` are both in
`line_split_corrections.tsv` (**11,156 rejoin corrections**, HYPHEN + NOHYPHEN + margin-interleaved).
They still appear in `residual_triage.tsv` because **the residual/garble metric was computed on text
BEFORE the line-reunify (and Sonnet text, and chapter) overlays were applied.**
- Measured: **1,104 residual types / 14,792 occ (~2% of residual) are already-solved line-split
  fragments** (`erty`, `superin`, `pensation`, `priation`, `retary`, `legisla`, `munici`, `terest`…).
- **Implication: the 0.44–0.56% "residual" OVERSTATES the true post-correction error rate** — it
  reflects none of the three computed overlays (chapter, Sonnet text 58,700 occ, line-reunify 11,156).
  A faithful residual number requires re-measuring AFTER the overlays are applied (which happens at
  mass-ingest). Until then, treat 0.56% as an upper bound inflated by already-solved items.
- **Gap this exposes:** the reunify pass still MISSES some fragments (margin-interleaved / cross-page
  / cross-column breaks where adjacency is broken). Those are recoverable by the neighbour-
  concatenation + dictionary check Patrick described (a fragment + its real neighbour → a real word).
  Worth extending the reunify pass to the missed cases before the residual is re-measured.

## The REAL number — residual AFTER overlays (2026-06-11, `post_overlay.py`)
Applying every computed overlay (Sonnet text-fix + line-reunify + gazetteer-KEEP) to the
post-ABC residual (467,978 types / 737,115 occ = the 0.5568% figure):
| disposition | types | occ |
|---|---|---|
| FIXED_sonnet | 1,704 | 58,700 |
| FIXED_linesplit | 840 | 4,138 |
| NOT_ERROR_name (gazetteer) | 5,228 | 10,444 |
| UNRESOLVED_still_suspect | 378,379 | 565,729 |
| TRUE_GARBAGE_unrecoverable | 81,827 | 98,104 |

**Post-overlay residual = 0.5014%** (663,833 occ) — down only from 0.5568%. Of that:
**0.0741% (98k occ) is confirmed unrecoverable garbage**, and **0.4273% (565k occ) is
"unresolved still-suspect"** — a MIX, NOT a measured error rate: it contains (a) rare REAL words
the gazetteer misses, (b) freq 2–9 + singleton typos never adjudicated, and (c) fragment classes
the reunify doesn't cover (below). The true error rate sits between 0.07% and 0.50% and is not
yet pinned, because the 0.43% mass is unprocessed.

## Reunify gap (Patrick directed margin/line-wrap handling — it's implemented but INCOMPLETE)
`line_split_reunify.py` DOES look beyond adjacency (`LOOKAHEAD=3`, emits margin + blank-gap
splits — 11,156 total, 1,507 margin). But the residual still carries high-freq fragments
(`superin` 464, `pensation` 346, `priation` 210, `retary` 169…), so classes slip through:
1. **Cross-page splits** — the pass scans `consensus_text` PER PAGE, so a word broken across a
   page boundary (`superin-` end of page N / `tendent` top of N+1) can never be joined.
2. **Same-line spurious-space splits** — `superin tendent` / `com pensation` on ONE line is a
   mid-word space insertion, not a line break; the line-oriented reunify can't see it. Needs a
   space-rejoin pass (adjacent same-line tokens whose concatenation is a known word, neither half
   known).
3. **Gaps > 3 lines** (long margin notes) exceed `LOOKAHEAD`.
**Honest failure:** the reunify was declared done without verifying its completeness against the
residual — the directed margin/line-wrap work exists but covers only the per-page line-break case.
Fix: sample the uncovered fragments to confirm classes, add cross-page + same-line space-rejoin +
larger lookahead, re-run, then RE-MEASURE the residual (the number above is not final).

## Reunifier FIXED (v2) + re-measured — the bottleneck is the singleton tail, not fragments (2026-06-11)
`line_split_reunify.py` v2 adds the missing classes: **same-line space-splits** (`superin tendent`),
**cross-page splits** (head end of page N / tail start of N+1), **NOHYPHEN-adjacent** (Pass A only
did HYPHEN), and **LOOKAHEAD 3→6**. Corrections **11,156 → 15,516** (+1,068 crosspage, +834
nohyphen-adjacent, +602 same-line, +1,856 margin). Same-line rejoin uses a STRICTER guard
(`_strong_known`: static dict OR zipf≥2.8) after the first run produced false joins
(`philadephia`, `administra`, `offerred`) — those are now rejected. Cross-page + line-break samples
are clean.
**Re-measured residual after the fix: 0.5014% → 0.5005% — essentially unchanged.** Two reasons,
and they matter:
1. **Overlap with the Sonnet overlay.** The high-freq fragments the reunifier catches (`superin`,
   `pensation`, `legisla`, `retary`) are freq≥10, so the Sonnet adjudication ALREADY fixed them —
   the reunifier's catch is largely redundant at the type level (its unique add ≈ +1,348 occ).
2. **The residual is dominated by the SINGLETON TAIL.** Of the 564k unresolved occ, ~385k are
   freq-1 singletons — one-off tokens that NEITHER the reunifier (recurring fragments) NOR Sonnet
   (freq≥10) touches. **That tail is the real bottleneck, not fragments.**
**Conclusion:** fixing the reunifier was necessary for correctness (and it IS correct now), but it
does not move the headline number — because the 0.43% lives in 385k one-off tokens (a mix of rare
REAL words, one-off garbles, one-off fragments). Lowering the rate requires decomposing and
processing that tail, not more fragment work. The reunifier still belongs in the overlay stack as a
deterministic, no-LLM correction; it just isn't the lever on the rate.

## Reunifier v3 — multi-fragment + fuzzy (misspelled-real-word) + Hans pass (2026-06-11)
Patrick caught two correctness gaps in v2: (a) it only joined 2 fragments — a word split into 3+
pieces (`ad min istration`) was missed; (b) a join can produce a MISSPELLED real word
(`philade+phia → 'philadephia'`, the `l` dropped at the split) which v2 just discarded.
v3 fixes both:
- **Multi-fragment greedy** (`MAXFRAG=4`): from each token, take the shortest run of 2–4
  consecutive pieces whose concatenation is a real word (not-all-pieces-known), consume the whole
  run (no overlap). Corpus has ~0 same-line 3-fragment cases, but the blind spot is gone.
- **`FUZZY_REVIEW` tier (flag-only, 131 found)**: when an all-fragment run is ONE inserted char
  from a strong word (`_insert1_known`), emit the suggestion WITHOUT auto-applying — recovers
  `subdivision`, `slaughter`, `apportionment`, `succession`, `embezzlement`, `indebtedness`,
  `unconstitutional`, etc. These go to a review/LLM pass before any application (no auto-corrupt).
- **Hans review (round 1)**: flagged CRITICAL-3 (same-line could emit overlapping pairs for a
  multi-fragment word → fixed by the greedy consume-the-run). His CRITICAL-1 (missing break) was
  a MISREAD (the break exists, verified line 139); MAJOR-2 (page-key sort) and MAJOR-4 (CRLF) were
  hypothetical — verified against data: keys are pure digits, text is LF-only. Hardened anyway
  (CRLF-safe regex, numeric TSV sort, cross-page lookahead 2→LOOKAHEAD). **Round-2 Hans on the new
  multi-fragment/fuzzy loop still owed.**

Total corrections 11,156 (v1) → 15,647 (v3). Re-measured residual: **still 0.5003%** — confirms
again the rate is bound by the singleton tail, not fragments; the reunifier work is a correctness
fix, not a rate lever. FUZZY suggestions are flag-only and excluded from auto-applied fixes.

## Corpus vocabulary: frequency ≠ validity (KEY methodology finding, 2026-06-11)
Patrick: the dictionary should start from the corpus's own words, not just standard English
(`build_dictionary` = pyspellchecker + nltk + wordfreq + small LEGAL_SUPPLEMENT — verified, no
corpus vocab). Correct in principle: real corpus words (legislator names, legal terms, archaic
statutory words) are absent from English dicts and get wrongly flagged into the residual.
**BUT the naive "high-frequency corpus token = trusted word" approach FAILS, and the data proves
it.** Built corpus-confident vocab (`build_corpus_confident.py`, freq≥15, word-like, minus Sonnet-
adjudicated errors): 40,854 confident / 9,588 "new" (not in English). The TOP of that "new" list
is systematic OCR ERRORS and FRAGMENTS, not words: `wuereas`(whereas), `secrion`/`seetion`/
`scction`(section), `publie`(public), `sball`(shall), `sueh`(such), `thercof`(thereof),
`califorma`(california), `trict`/`appropria`/`compen`/`sioner`/`urer`/`priated`/`poration`
(fragments). **OCR errors are SYSTEMATIC -> they recur thousands of times -> frequency cannot
distinguish a real legal term from a recurring error.** Adding raw corpus vocab to `is_known`
would legitimize thousands of recurring errors (marked "real", never corrected) — the opposite of
the goal, and the reason the original curated-dictionary design was right.
- Real corpus words DO hide in the same list (`deukmbejian`=Gov. Deukmejian, `encumbrancers`,
  `distributees`, `roadmasters`, `subhaulers`, `slungshot`, `indorser`, `reflectorized`) — so
  curated corpus vocab has value, but only after validation.
- Measured: only **1,707 of 467,978 residual types** reclaimed even by the contaminated filter
  (several themselves errors, e.g. `lambra`). So the residual is **mostly genuine errors**, NOT
  wrongly-flagged real-corpus-words.
- **Correct path:** to use corpus vocab, separate real-words from systematic-errors via VALIDATION
  (extend the Sonnet/LLM adjudication to the high-freq corpus vocab), then add only the validated
  real words to `is_known` (benefits the reunifier's join-target check AND shrinks the residual).
  Frequency alone cannot do this. Corollary: high-freq systematic errors (`secrion`→section,
  `sball`→shall) are HIGH-VALUE correction targets (each fixes thousands of occurrences) — the
  same validation pass that curates the vocab also yields these bulk fixes.

## Singleton autocorrect (Patrick's idea) — the real lever on the tail (2026-06-11)
Patrick: run the residual through autocorrect weighted toward corpus-attested words. The freq≥2
passes (B de-merge, C spell) had SKIPPED the 385k singletons for safety (autocorrecting a freq-1
token risks corrupting a rare real word). Tested corpus-weighted edit-1 autocorrect on a random
8,000 singletons (`singleton_autocorrect_test.py`):
- **confident fix (dominant corpus-attested edit-1) = 23.1% → ~89,000 of 385k.** Sample quality
  high: `cisplayed→displayed`, `califorcia→california`, `appurtevances→appurtenances`,
  `sufficiens→sufficient`, `fuperintendent→superintendent`, `impiisonment→imprisonment`,
  `transzortation→transportation`. These are one-off typos the freq≥2 passes never touched.
- ambiguous (multi-candidate, needs context/LLM) = 13.8% (~53k).
- **no candidate (deep garbage / novel) = 63.1% (~243k)** — `eeee`-class, ≥26-char mashed tokens,
  severe garbles; not close to any word, so autocorrect can't help (re-OCR / illegible floor).
**Caveat:** corpus-frequency weighting occasionally picks a FREQUENT CORPUS ERROR as the target
(`clther→cither`, `ofticia→officia`, `yality→ality`) — ~10–15% of the "confident" fixes. Mitigate
by ALSO requiring the target be common in GENERAL English (not just corpus), and/or run it as a
flagged reversible layer with an LLM pass on borderline cases.
**Conclusion — corrects my earlier "tail is intractable" claim:** ~25–35% of the singleton tail
is recoverable typos (the autocorrect lever), ~60% is deep unrecoverable garbage (the honest
re-OCR floor), small remainder real-words. This is the most promising rate-reducer found; sequence
it as: guarded corpus+English-weighted autocorrect on singletons → apply as reversible layer →
re-measure residual → the deep-garbage 60% defines the true unrecoverable floor.

## Singleton tail decomposed — "60% garbage" was WRONG; it's ~17% (2026-06-11)
Patrick challenged the "60% deep garbage" claim (it was built on the weak proxy "no edit-1 to an
English word = garbage", which conflates garbage with fragments, over-merges, and edit-2 typos).
Measured properly (`singleton_decompose.py`, 6,000 sample, context-aware, first-match wins):
- **GARBAGE (structural) = 17.4%** — the SOLID number (char-salad, repeat-runs); NOT 60%.
- EDIT1 typo = 15.7% (solid, recoverable).
- OVER_MERGE = 38.5% **(inflated — unreliable)**: examples are mostly typos (`applicatien`,
  `swearirg`, `ternories`) that `splittable()` falsely split because `known()`=permissive `wf>0`.
- STANDALONE = 28.3% **(mislabeled)**: mostly edit-2 typos (`cunstructcd`→constructed,
  `eonsohdated`→consolidated, `mployces`→employees) and fragments (`maiunicipali`=municipality).
- FRAG by context ≈ 0% **(artifact)**: fragments hide in the above because the context-fragment
  test needs the join in the ENGLISH dict (the dict gap) and an unknown neighbour.
**Honest conclusion:** garbage ≈ 17% (reliable); the other ≈ 83% is recoverable-error territory
(typos edit-1/2, fragments, over-merges) — exact split fuzzy until the dict includes validated
corpus vocab + names and the dedicated passes (reunify / split / spell-1-2-3) run. The tail is
NOT mostly garbage; it is mostly recoverable. (Lesson: don't label a bucket by what one test
can't do — measure its contents.)

## Correct correction-pass architecture (Patrick, 2026-06-11)
1. **Dict integration FIRST** — add validated corpus vocab + corpus-attested names
   (`gazetteer_keep` 5,438, NOT the raw 370k) to `build_dictionary`. Currently only the 319-name
   `ca_gazetteer` is integrated; the 370k gazetteer and corpus-confident vocab are standalone,
   never wired in. #1/#2/#5 all depend on this.
2. **Reunify (fragments)** — exists (`line_split_reunify.py` v3); gains coverage once the dict
   has corpus-word join targets. Orphaned fragments (other half missing/garbled) stay stuck.
3. **Split (over-merges)** — NEW pass, inverse of reunify; only split tokens not themselves known.
4. **Spell edit-1/2/3** — edit-1 high-precision auto; edit-2 auto-with-dominance; edit-3
   flag/LLM only. Singletons were skipped by the freq≥2 passes — this is their pass.
5. **Systematic-error sweep** — high-freq consistently-broken corpus words (`secrion`→section)
   are highest-ROI; largely covered by Pass C + Sonnet but completeness UNVERIFIED.
All emit reversible overlays; re-measure residual AFTER they run for the first real error rate.

## Dict integration LIVE + singleton tail decomposed RIGHT (2026-06-11)
**Dictionary integration (Patrick #4) — DONE for names.** `build_dictionary()` now loads
`_vocab/dict_additions.txt` (5,438 DB-validated, corpus-attested names from `gazetteer_keep`) →
dict 328,139 → 333,563. The reunifier + all correction passes that call `build_dictionary` now
recognize these names. **Legal/corpus vocab NOT added** — both heuristic curation attempts failed:
(a) the "genuine-novel" freq+edit filter kept fragments/legal-word-errors (`admunistra`,
`aforesnid`, `actshall`); (b) an edit/affix filter on the names DROPPED real legislators
(`ducheny`/`karnette`/`escutia`) and KEPT garbage (`aaad`/`aaca`). Lesson (3rd time): heuristics
cannot separate real corpus vocab from systematic errors — the legal vocab needs an LLM validation
pass. Names were addable only because they had real ground truth (census/GeoNames match).

**Singleton tail decomposed RIGHT** (`singleton_decompose.py` v2: integrated dict, order
GARBAGE→FRAG_join→EDIT1→EDIT2→strict-OVER_MERGE→FRAG_affix→STANDALONE, `strong_known` splits,
efficient edit-2 via pyspellchecker):
| bucket | % | note |
|---|---|---|
| GARBAGE (structural) | 17.1% | the real floor (was mis-claimed 60%) |
| EDIT1 typo | 36.3% | was 15.7% — strict split stopped OVER_MERGE stealing typos |
| EDIT2 typo | 25.2% | was 0 (edit-2 had been removed) |
| OVER_MERGE | 1.9% | was 38.5% — strong_known split killed the false merges (real: `aprilnext`,`bondisue`) |
| STANDALONE | 19.4% | mostly HARDER typos (`inaivtenance`→maintenance), edit-3/LLM; few real words |

**Corrected conclusion: the tail is ~17% structural garbage, ~63% cleanly autocorrectable
(edit-1/2 + real merges), ~19% harder typos. Genuine rare-real-words are a tiny sliver.** The
error rate is therefore very reducible via the pass architecture (reunify → split → spell-1/2/3),
not bound by garbage. (Two bugs Patrick caught fixed: classifier ORDER put OVER_MERGE before EDIT1,
and permissive `known`=`wf>0` false-split typos; plus edit-2 had been dropped.)

## LLM validation unlocked the legal-vocab dict layer (2026-06-11)
The legal/corpus vocab that heuristics could NOT curate (kept fragments `admunistra`, errors
`aforesnid`) was validated by an LLM pass: 4 Sonnet agents classified the 1,266 genuine-novel
candidates as REAL / NAME / FRAGMENT / ERROR. Result: **REAL 446 + NAME 119 = 565 validated real
vocab** (e.g. `estrays`, `subpenas`, `depositaries`, `appraisements`, `apprenticeable`,
`acetylmethadol`, `accountholder`), vs FRAGMENT 412 + ERROR 289 = 701 correctly excluded
(`expendi`, `cerning`, `frecholders`, `hcense`). The LLM cleanly did what frequency/edit heuristics
could not. Validated terms merged → **`dict_additions.txt` now 5,926 (5,425 names + 501 legal
vocab)**, live in `build_dictionary`. (`validated_legal_vocab.txt`, `sub_nv_b1..4.tsv`.)
**Pattern confirmed: corpus-vocab curation = real ground truth (name DBs) OR LLM validation, never
a frequency/distance heuristic.**

## SEQUENCE IS THE ARCHITECTURE — the correction cascade (Patrick, 2026-06-11)
The passes must run as an **ordered cascade**, each consuming the PREVIOUS pass's corrected output
— NOT each in isolation on raw text. Running them isolated on raw text is why each over-fired: the
word-splitter mangled `tollowing`→"toll owing" only because the typo was still present; had
autocorrect already produced `following`, the splitter would never have seen it. **A pass's
precision collapses while the error classes it can't handle are still in the text, and jumps once
they're removed.** Order is fixed by two rules — dependency (remove a class before it confuses a
later pass) and confidence (most certain first):
1. **Dictionary** (foundation; `is_known` used by all). Names + LLM-validated legal vocab. DONE.
2. **Reunify (fragments)** — rejoin split words FIRST; fragments masquerade as typos and over-merges.
   Highest confidence (context-confirmed). After it, `superin`+`tendent`→`superintendent` can't be
   mis-grabbed downstream.
3. **Autocorrect edit-1 then edit-2 (typos)** — removes the typo class that was wrecking the splitter
   (`cornmission`→commission, `tollowing`→following).
4. **Split (over-merges)** — runs on text where fragments + typos are already gone, so a token that
   segments into two real words is genuinely likely a true over-merge; precision jumps. Residual to
   LLM validation (the heuristic alone is ~50% precise — `word_splitter.py` is a candidate generator).
5. **Re-measure** on the fully-cascaded text → the defensible error rate.

**Order also IS the conflict-resolution policy:** when reunify wants to join and split wants to cut
the same token, the earlier/higher-confidence pass (reunify) wins. **Build a cascade harness**
(apply overlay N → intermediate text → run pass N+1 on it → repeat → one clean re-measure), which is
also exactly what produces the defensible error number. NOTE: the standalone pass outputs measured
so far (reunify 15,434; splitter 4,888 @ ~50%; autocorrect TBD) are ISOLATED-on-raw numbers and will
change under the cascade.

## Cross-refs
`CROWDSOURCE_CORRECTION.md` (community tier), `SCHEMA_DESIGN` / `docs/40_SCHEMA/`
(event-sourced model), the correction pipeline (`pipeline/correction_passes.py`),
and the dictionary-membership lesson (`docs/80_PROJECT_HISTORY/lessons/`).
