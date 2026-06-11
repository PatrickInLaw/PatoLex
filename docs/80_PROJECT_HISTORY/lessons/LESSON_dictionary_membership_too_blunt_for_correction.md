# Lesson: Dictionary *membership* is too blunt for OCR correction — you need *scoring*

**Date:** 2026-06-10 · **Source:** cc007 vocab-diff correction-pass run (v5, full 1850–2024 OCR consensus corpus, 134,105,434 tokens) · **Script:** `pipeline/correction_passes.py`

## What we ran
Three deterministic correction passes over the OCR consensus corpus, measuring the
non-dictionary ("bad") token rate before/after each:

| Stage | Bad occ | % of corpus | Recovered |
|---|---|---|---|
| Baseline | 1,562,764 | 1.1653% | — |
| After Pass A (dehyphenation + adjacent-pair rejoin) | 1,346,308 | 1.0171% | 216,456 |
| After Pass B (de-merge run-together tokens) | 1,274,945 | 0.9626% | 71,363 |
| After Pass C (spell-correct freq≥10 head) | 668,131 | **0.5045%** | 606,814 |

Residual: 668,131 occ / 461,129 types — singletons 385,131; low-freq(2–9) 75,324 types/251,727 occ; high-freq(≥10) 674 types/31,273 occ.

## The finding (the headline number is partly illusory)
The "0.5045% residual" **overstates real cleaning**. Pass A (rejoin) is genuinely
safe and high-precision. But **Pass B and Pass C produce a large minority of WRONG
"fixes"** that merely convert *flagged*-garbage into *dictionary-passing*-garbage —
which deflates the bad-token metric without improving (and sometimes corrupting) the text.

**Pass B (de-merge) wrong splits** — the dictionary lets garbage *fragments* pass `is_known`:
- `retirant → reti+rant` (retirant is a real pension-law term)
- `habilitative → habi+lita+tive` (a real English word, fragmented)
- `offstreet → offs+treet`, `schoolage → schoo+lage` (correct split exists but wrong boundary chosen)
- `karnette`, `frusetta`, `kaloogian` (CA legislators' surnames shredded into fake "words")
- `citapter → cita+pter`, `sechon → sech+on` (OCR garbles of *chapter*/*section*, fragmented instead of corrected)
- Genuine wins do exist (mobilehomes→mobile homes, winegrapes→wine grapes, postconsumer→post consumer, toamend→to amend), but a large share of the 8,798 accepted splits are damage.

**Pass C (spell-correct) wrong corrections** — a 96% "correction rate" is a RED FLAG, not a success (`spell.correction()` returns *something* for almost any token):
- `conservatee → conservative` (**3,682 occ** — *conservatee* is a real conservatorship term, corrupted to the wrong word)
- `cight → right` (should be *eight*), `jands → hands` (should be *lands*), `lambra → lambda` (it's *Alhambra*), `cuap → cup` (it's *chap*)
- Genuine wins are excellent (wuereas→whereas 11,537; publie→public; secrion/seetion/scction→section; distriet→district), but ~5 of the top-25 corrections are flat wrong.

## Root cause
A **binary `is_known()` dictionary-membership test is too blunt** for both gating de-merges
and validating corrections. Two failure modes, both from the same cause:
1. **False "known" fragments:** nltk's word list contains thousands of obscure short
   strings (`reti`, `pria`, `sech`, `gian`, `etta`, `bili`, `tive`, `schoo`, `lage`,
   `offs`, `treet`, …). Any garble that happens to fragment into two of these passes the
   "both pieces known" test, so a wrong split is accepted.
2. **Real domain terms flagged "bad":** legal/compound vocabulary missing from an English
   dictionary (`conservatee`, `habilitative`, `mobilehome`, `twothirds`, `nonunitary`,
   `materialmen`, `feepayer`, `nonmotorized`, `statemandated`, `noninstitutional`,
   `postaudit`, `subcontainer`) gets flagged as garbage and then mis-split or mis-corrected.

**Membership ≠ plausibility.** The fix is *scoring* — frequency-weighted plausibility
(prefer splits/corrections into *common* words, not merely dictionary-present ones) and/or
the context-aware LLM cascade — not a richer dictionary alone.

## Silver lining: true OCR error rate is BELOW 0.5%
A meaningful chunk of the high-freq residual is **not OCR error at all** — it's real legal/
compound vocabulary missing from the English dictionary (e.g. `mobilehome` 11,138 occ,
`nonmotorized`, `statemandated`, `noninstitutional`, `postaudit`). A **legal/domain
dictionary supplement** would shrink the *apparent* residual further **without modifying any text**.

## What to do (decisions)
- **Apply Pass A only** to the corpus text — dehyphenation + adjacent-pair rejoin is
  deterministic and high-precision (216,456 occ recovered, safe).
- **Do NOT blind-apply Pass B or Pass C.** Their net effect on correctness is mixed.
- Route de-merge candidates and the freq≥10 correction head through a **scored** decision:
  - frequency-weighted plausibility (require both split pieces / the chosen correction to be
    *common*, e.g. `wordfreq` above a threshold — not just dictionary-present), AND/OR
  - the benchmarked **gemma3:27b → aya-expanse:32b** local cascade
    (see `docs/30_SYSTEM_DESIGN/LOCAL_MODEL_OCR_DETECTION_MATRIX.md`).
- Build a **legal/domain dictionary supplement** so real statutory terms stop being flagged.
- Consider emitting vetoed/ambiguous decisions (token, candidate, neighbor) to a TSV so the
  binary gate becomes a *logged, adjudicable* decision instead of a silent drop.

## Resolution (v7, 2026-06-10) — scoring fixed it
Reworked `correction_passes.py` to v7 with three scored changes (CPU-only, fully parallel, 208s wall vs v5's 1468s):
1. **Pass B pieces must be `is_common`, not `is_known`** — a piece passes only if it is a stopword,
   a curated legal term, or has `wordfreq.zipf_frequency >= 2.5` (validated: every real piece scored
   ≥2.94, every garbage fragment had ≥1 piece well below 2.5). Result: de-merge now yields only real
   compounds (`lienholders→lien+holders`); the `reti+rant` / `kaloo+gian` class is gone. Pass B
   "recovered" dropped 71,363 → 27,946 — the ~43k difference WAS the wrong splits.
2. **Pass C ranks candidates by CORPUS frequency, not general English** (general freq picks `small`
   over `shall`). Workers generate the edit-distance candidate set in parallel; main accepts only a
   confident winner (corpus_freq ≥ 50 AND ≥ 3× the runner-up). Fixed `sball→shall` (not small),
   `cuap→chap` (was cup), `jands→lands` (was hands). 2,655 genuinely ambiguous tokens (`cight`:
   right/eight; legislator surnames) routed to `_vocab/passC_review.tsv` instead of being mis-corrected.
3. **Legal supplement expanded** with the corrupted terms (`conservatee`, `habilitative`, `mobilehome`, …)
   so they stop being flagged.

Honest outcome: residual ROSE 0.5045% → 0.5568% — the v5 number was partly fake (achieved by corrupting
~50k tokens into dict-passing garbage). v7's 0.557% is real. Remaining edges (`califorma→cali+forma`,
`twenty-cight→...+ight`, a few real-word over-splits) + the 2,655-row review TSV are the next tier for the
gemma3→aya LLM cascade. Tunables: `DEMERGE_MIN_ZIPF` (2.5), `PASSC_MIN_CORPUS_FREQ` (50), `PASSC_DOMINANCE` (3.0).

## Process note (speed, secondary)
v5 wall time was 24.5 min, dominated by the still-single-threaded Pass A (6.4 min) and
Pass C (16 min); only Pass B was parallel (1.4s). v6 (`pipeline/correction_passes.py`,
staged) parallelizes the file-scan+Pass A and Pass C across 12 workers → projected ~3–4 min.
Parallelization changes only speed; it must be validated to reproduce these exact
baseline/A/B/C numbers before being trusted.
