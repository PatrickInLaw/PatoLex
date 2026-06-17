# Corpus Completeness Re-measurement — After Recovery Passes (2026-06-16)

**Type:** READ-ONLY measurement. No pipeline code changed, nothing committed.
**Box:** 5090 (`C:\Users\patolex\PatoLex-scratch\production-*`).
**Oracle:** corrected `docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv` from `origin/main` (1854 = 174).
**Method:** per session, *distinct chapter numbers in [1, N] / oracle N*, where N is the oracle's authoritative chapter count. Chapter int taken from `chapter_int_final` (renumber-repaired) when present, else `chapter_int`. Sessions bucketed by **true session/biennium**, not the leading-4-digit label (see "Biennium bucketing" below).
**Artifacts (this folder):** `corpus-remeasure-2026-06-16-per-session.tsv`, `…-per-era-task.tsv`, `…-per-era-bestof.tsv`. Source TSVs on the 5090 at `…\PatoLex-scratch\_remeasure_out\`.

---

## 1. What was measured & the consolidation rule

Per the brief, a **best-parse per volume** was consolidated from the three recovery outputs under each `production-<label>\`:

| Era | File preferred (TASK rule) | Why |
|-----|---------------------------|-----|
| Chaptered volumes that have it (1885-86, 1893, 1905, 1915, 1925, 1931, 1933, 1937, 1945) | `parsed_acts_chaptered_v2.json` | additive over recovered (redirect-stubs + detection) |
| Early italic (1850–1865 single-year + 1863-64/1865-66) | `parsed_acts_early_v2.json` | Surya-header corrected early volumes |
| Everything else | `parsed_acts_recovered.json` | prior baseline (incl. renumber repair) |

Completeness counts **confident** chapters (per-act `confident=true` or membership in `confident_acts`); flagged acts are tracked separately as the **all-extracted** ceiling.

**This is a conservative FLOOR, not a ceiling.** A full *detection + renumber MERGE* across the three files (union of confident coverage per session) has NOT been run — that is the future step. To bound the floor honestly, three scenarios were scored on identical biennium bucketing and oracle:

- **BEFORE** = `recovered`-only everywhere (the prior baseline).
- **TASK** = the file-preference rule above (what the brief asked for).
- **BEST-OF** = per-volume, whichever file certifies the most confident acts (a cheap proxy for the future merge's floor).

---

## 2. Biennium bucketing (the correction that moves the number)

The existing `chapter_vs_oracle.py` keys sessions on the leading 4 digits of the label, which **mis-buckets** the post-1900 biennium volumes. California published these as a biennium named by the *first* year, but the volume actually contains the *second* (odd) year's **regular** session:

| Volume label | Holds (verified by max chapter) | Oracle N |
|--------------|--------------------------------|----------|
| `1900-01` | 1901 Regular (max 274) | 275 |
| `1906-07` | 1907 Regular (max 539) | 539 |
| `1907-09` | 1909 Regular (max 729) | 729 |
| `1910-11` | 1911 Regular (max 751) | 753 |

Rule applied: a `YYYY-YY` regular label maps to the **second** year if that year's regular session exists in the oracle; otherwise the first year (which keeps the early ranges `1863-64`, `1865-66`, `1885-86`, etc. correct, since the oracle itself labels those as ranges). `NNchapters` suffixes map to `19NN`. Without this fix, ~4 large regular sessions (≈2,300 chapters) were scored against the wrong (or no) oracle row.

---

## 3. Results — per era and corpus-wide (TASK scenario)

`conf%` = confident floor; `all%` = ceiling if every extracted-but-flagged chapter were certified.

| Era | Oracle N | Confident | conf% | All-extracted | all% |
|-----|---------:|----------:|------:|--------------:|-----:|
| 1850–59 | 2,189 | 0 | **0.0%** | 1,735 | 79.3% |
| 1860–79 | 5,934 | 2,155 | 36.3% | 3,836 | 64.6% |
| 1880–99 | 2,014 | 1,811 | 89.9% | 1,816 | 90.2% |
| 1900–19 | 6,236 | 4,411 | 70.7% | 4,477 | 71.8% |
| 1920–49 | 16,018 | 13,055 | 81.5% | 13,207 | 82.5% |
| 1950–79 | 35,956 | 33,309 | 92.6% | 33,772 | 93.9% |
| 1980–99 | 27,208 | 25,874 | 95.1% | 25,910 | 95.2% |
| **CORPUS (1850–1999)** | **95,555** | **80,615** | **84.4%** | **84,753** | **88.7%** |

**Coverage span:** these `production-*` dirs cover **1850–1999 only**. The 25 oracle *regular* sessions with no parse here are **2000–2024** — the modern leginfo-CAML-XML era, ingested by a separate path (not OCR), so they are correctly excluded from this OCR-corpus measurement. Against the **full** oracle grand total (119,157 chapters, all sessions 1850–2024) the confident floor is **67.7%**; the 84.4% is the right figure for *the OCR corpus this measurement covers*.

### Before vs after (apples-to-apples, same bucketing & oracle)

| Scenario | Corpus confident | Corpus all-extracted |
|----------|-----------------:|---------------------:|
| BEFORE (`recovered`-only) | 85.0% (81,189) | 88.1% (84,160) |
| TASK (brief's file rule) | **84.4%** (80,615) | **88.7%** (84,753) |
| BEST-OF (per-vol max-confident) | **85.2%** (81,403) | 88.2% (84,260) |

The "raw 88.7%" the brief cites as the *before* number is the **all-extracted ceiling** of the TASK consolidation — it matches exactly. The recoveries raised the *ceiling* (more chapters extracted: 84,160 → 84,753) but did **not** raise the confident *floor* in aggregate, because of the early-era regression below.

---

## 4. The early-era regression (an honest caveat on the TASK rule)

Preferring `early_v2` for the italic volumes (1850–1865) **lowers** the confident count versus `recovered`:

- `early_v2` certifies **zero** acts for these volumes — every act is `confident=false` (e.g. 1862: 0 confident, 397 flagged). This is the **C87 finding** (early-era header loss = a Tesseract-italic consensus bug): the chapters were *extracted* (1850–59 reaches 79.3% all-coverage) but the consensus step flagged all of them.
- For the same volumes, `recovered` already had real confident acts (1862: 113, 1863-64: 236, 1865-66: 302).

Net effect on 1860–79: TASK 36.3% confident vs BEFORE/BEST-OF 49.6%. **The early italic chapters are present in the OCR; they are simply uncertified.** BEST-OF (which takes `recovered` where it certifies more) recovers this and is the better floor (85.2%). The future detection+renumber merge should union confident coverage across files rather than pick one file per volume — it will land at or above BEST-OF.

---

## 5. Residual — how much is still missing, and what kind (TASK scenario)

Confident-missing chapters: **14,940** of 95,555. Each missing chapter classified:

| Class | Count | Meaning / lever |
|-------|------:|-----------------|
| **Garbled-header (recoverable)** | **14,741 (98.7%)** | chapter is in the OCR page range but not certified as a `CHAPTER n` token |
| — of which *flagged-present* | 4,138 | the int is already parsed, just flagged → **certify only** (cheap) |
| — of which *interior-absent* | 10,603 | numeral lost inside a span we otherwise cover → numeral/header repair or targeted re-OCR |
| Early-era over-extraction noise | 0 | over-extraction is negligible in this corpus (under-/garbled-extraction dominates) |
| Genuinely uncertain | 199 (1.3%) | boundary gaps in clean sessions; no page bracket — true unknowns |

(BEST-OF residual: 14,152 missing → 13,944 garbled [2,857 flagged-present + 11,087 interior-absent], 208 uncertain. BEFORE: 14,366 → 14,158 garbled, 208 uncertain. The shape is identical across scenarios.)

**The residual is essentially one problem.** ~99% of what's still "missing" is the garbled-header class — chapters whose text the OCR captured but whose `CHAPTER n` header/numeral was lost or left uncertified. Genuine unknowns are only ~200 chapters corpus-wide.

---

## 6. Honest answer — how complete is the corpus now, and how much is truly missing?

The OCR corpus (1850–1999) is **~85% complete on a strict confident-only floor and ~88.7% on the all-extracted ceiling**, measured against the corrected oracle with biennium-correct bucketing. Recoveries to date raised the extraction ceiling but not the confident floor, because the early italic volumes (1850–1865) are a known consensus bug (C87): their chapters are extracted (≈80% coverage) yet certified at 0% — taking `recovered` there instead (BEST-OF) already lifts the floor to ~85.2% with no new OCR. Of the ~14,900 chapters still short of confident, **~99% (≈14,700) are the garbled-header residual** — present in the OCR but missing a recognized `CHAPTER n` token — and only **~200 are genuinely uncertain**. About 4,100 of the garbled set are already-parsed-but-flagged (a certification pass, not new OCR). So the corpus is not missing its text; it is missing *headers*. The single remaining lever is numeral/header repair + a confident-merge of the three recovery files (with a re-OCR or italic-consensus fix for the early volumes) — there is no large pool of genuinely absent statute pages to recover.

---

### Notes / caveats
- "Missing" here means *not certified as a confident chapter in [1,N]*; it does not assert the page is physically absent. The garbled-header dominance is the evidence that most "missing" chapters are header-loss, not page-loss.
- 2000–2024 is intentionally out of scope (separate leginfo-XML ingest path).
- Code volumes (`*-code`, e.g. Civil/Penal Code reprints) carry 0 session-chapter acts and contribute nothing to the session scores.
- Numbers are a conservative floor pending the detection+renumber MERGE (union of confident coverage per session across the three files), which is the next step and will land at or above the BEST-OF figures.
