# Corpus Completeness — State of the Corpus & Path to Ingest-Ready
**Snapshot: 2026-06-16.** Consolidates the cc007 completeness investigation. Supersedes scattered claims in the run/session logs; for method detail see `docs/30_SYSTEM_DESIGN/CHAPTER_COMPLETENESS_FINDINGS.md`.

---

## 1. The one-paragraph truth
**The source corpus is COMPLETE and verified — every volume is acquired and on disk, the OCR is page-complete, and the authoritative chapter-count oracle is now trustworthy.** Nothing needs re-acquiring or re-scanning. The corpus is NOT yet ingest-ready, but every remaining gap is a **parse/OCR-extraction problem recoverable from data we already hold** — plus a bounded slice of genuinely OCR-garbled headers. We are validating and refining extraction, not chasing missing material.

## 2. What is VERIFIED solid
- **Source acquisition is complete.** Spot-verified against the CA Chief Clerk archive: 1915–1949 are single-volume sessions (no missing "Vol 2"); multi-volume sessions from 1951 on have every volume. The OCR for sampled sessions runs to the full oracle chapter count (1931 OCR→1220=oracle; 1933→1059=oracle).
- **OCR is page-complete** — 0 missing body pages across all 205 volumes (`verify_volume_completeness.py`).
- **The oracle is authoritative** (`docs/30_SYSTEM_DESIGN/sources/ca_chapter_counts.tsv`, 215 sessions 1850–2024). Audited 2026-06-16: 1854 corrected (71→174, dual series); 1852/1853/1865-66 confirmed correct.
- **Infrastructure**: single canonical store on the 5090 + tiered offsite backup on the 3060 (F: SSD warm, D: HDD cold), hash-verified. See `docs/60_OPERATIONS/STORAGE_AND_BACKUP.md`.

## 3. The nature of the "gap" (the key reframe)
The raw ~88.7%-complete figure conflated FOUR different things. Separating them is the main result of this investigation:

| Component | What it is | Fix | Status |
|---|---|---|---|
| **Recoverable extraction** | real acts the parser missed (early italic headers; chaptered redirect-stubs; mis-numbered acts) | better detection / renumber from data we have | passes built; in Hans-fix cycle |
| **Measurement noise** | resolutions (~80/vol) + mid-sentence chapter *references* + non-statute series counted as "missing" or over-counted | exclude (line-head only; statutes-series only) | identified; folds into re-measure |
| **Genuine OCR-garbled headers** | real acts whose `CHAPTER n` header is broken in OCR (e.g. "CHAPTER 12"→"G JAC TET 12") | numeral/header repair vs the page-complete OCR, or targeted re-OCR of the worst pages | **the one big lever not yet built** |
| **Oracle errors** | wrong denominators (1854) | authoritative re-derivation | **DONE** |

## 3b. CAUTION on residual sizing (2026-06-16 evening — bucketing artifact, 5th false alarm)
A numeral-repair pass re-measured residual against the FULL oracle and reported "residual 33,886, of which **22,197 = whole unparsed volumes**" (naming 1956 @2.4%, 1960 @3.4%, 1954, 1962). **This was VERIFIED FALSE — it is the biennium/label bucketing artifact again (the 5th "missing/unparsed" alarm to dissolve this campaign).** Direct probe of the 5090 store:
- There is **no `production-1956/1954/1960/1962` dir** because those are **even-year special/budget sessions whose statutes are physically bound in the adjacent ODD-year volume**, labeled with a `NNchapters` suffix that encodes the TRUE statute year: **1954→`production-1955-vol1-54chapters`, 1956→`production-1957-vol1-56chapters`, 1960→`production-1961-vol1-60chapters`, 1962→`production-1963-vol1-62chapters`, 1952→`-1953-...-52chapters`, 1958→`-1959-...-58chapters`.** The statutes ARE present and parsed.
- The pass's NEW `residual_profile.py` keyed sessions off the leading 4 digits of the label and never decoded the `NNchapters` suffix — **it reintroduced the exact biennium bug C96 fixed in `chapter_vs_oracle.py`.** Its 71.33% / 33,886-residual / 22,197-"unparsed" / 11,109-"interior" numbers are therefore **untrustworthy for sizing the re-OCR pass.** The `recover_lost_header.py` *recovery itself* (+578 acts, 0 dups introduced, 20/20 spot-check correct) is valid; only its *measurement* is tainted.
- **RULE for any re-OCR sizing: measure with the biennium-correct `chapter_vs_oracle.py` (C96 fix), against the OCR-scope oracle (1850–1999), NOT a fresh year-keyed tool.** `NNchapters` suffix = true statute year; even years = special/budget sessions bound in the odd-year volume.

## 3c. Certify precision gate caught C97-shipped duplicates (2026-06-16 evening)
The Hans-fix write-gate on `certify_chapters.py` (abort + `sys.exit(2)` on precision PASS=False) now **correctly blocks** on **3 introduced duplicate confident chapters in session 1853** (ch 105/107/140). Root cause: 1853's **table-of-contents front matter (pages 9–11)** is parsed as acts and certified to the SAME numbers as the real act bodies (pages 151/152/197, roman headers `CHAPTER CV/CVII/CXL`). **The pre-gate C97 certify run had NO write-gate, so it almost certainly shipped these dups silently into `production-1853/parsed_acts_certified.json`** — the early-era certified output must be re-generated after the TOC/dup fix (a manifestation of the known early-era over-extraction, §4). Fix in progress: R2 `is_cand` must require `is_real_act` (not just `has_an_act`), and open-slots must exclude EVERY number already held by a confident act, not just monotonic anchors.

## 3e. THE recurring "~20k gap" is a DENOMINATOR ARTIFACT — RESOLVED (2026-06-17, proven)
The single most clarifying result of the campaign. The "missing ~20k chapters" that surfaced repeatedly (most recently as the numeral-repair pass's "22,197 whole unparsed volumes") is **not missing data — it is even-year budget/special-session volumes measured against the wrong oracle N.**
- **Mechanism:** California's even-year sessions are small **Budget/Extra sessions** (oracle N = 1–151; the 88 small sessions total just **1,475** chapters). Their statutes are bound in the adjacent odd-year volume under an `NNchapters` suffix (`production-1953-vol1-52chapters` = the 1952 sessions). **certify's `oracle_N()` mis-maps these to the ODD-year Regular N** (proven: `…-52chapters` holds 76 acts, max chapter 34, but was stamped `oracle_N=1895`; `…-56chapters` 74 acts/max 67 stamped 2424; ~10 such volumes × ~1900-2400). So those sessions show a false ~0–4% completeness and certify's self-reported total (71.37%) is **denominator-deflated**.
- **The data is present.** Every even-year volume probed has its tens-of-acts captured. Nothing missing, nothing to re-acquire.
- **Authoritative denominator:** sum of all oracle N = **119,157** across 215 sessions (116,973 regular + 2,184 extra/budget). The numerator (84,363 distinct-confident actually present, post-certify) is sound. **True overall coverage is far higher than 71.37% — in the mid-to-high 80s once the even-year denominators are corrected.**
- **Action:** the authoritative completeness MUST be measured with `chapter_vs_oracle.py` (keys by year+type via the `NNchapters`→year rule, so it uses N=14 for 1952, not 1895), NOT certify's internal totals. certify's `oracle_N` mapping for even-year `NNchapters` volumes is a measurement bug to fix (does not affect certify's *output* — N only loosens the range cap; precision gate still passed 0-dups). Caveat: biennium volumes bundle regular+extra sessions under one label, which neither tool perfectly splits — a small (~dozens/biennium) residual, not the ~20k artifact.

## 3d. Adversarial-review outcomes + residual decomposition refinement (2026-06-17, Hans)
- **`certify_chapters.py`: Hans CONDITIONAL GO → cleared.** The 1853 TOC dup fix is precision-clean (write-gate hermetic, witness guard fires, no introduced dups corpus-wide, 3,213 certified). Two hardening MAJORs applied: explicit `all_taken.add(slot)` (intra-call no-reuse invariant) + delete dead `restore_sacred` (latent closure trap). The 200-char `is_real_act` guard was **empirically validated** (probe across 216 vols: it excludes exactly **1** real act corpus-wide, a 192-char garbled-header 1861 act that stays flagged anyway — guard is well-calibrated, not a recall risk).
- **`recover_lost_header.py`: Hans NO-GO (hardening, not a live precision hole).** The +578/0-dup recovery is structurally sound (it does NOT repeat the certify monotonic-anchor bug). Fixes queued: re-run output **overwrite guard** (CRITICAL: silent clobber of validated output), exclude **flagged**-act numbers from open-slots too (not just confident), strict `<` page filter, real `volume_year` for iso_date.
- **SCOPE CORRECTION (key residual finding).** `recover_lost_header.py` is **garbled-NUMERAL** repair, not "header-independent" — it requires a detectable line-head `CHAPTER` *glyph* (then renumbers by position). Acts whose header glyph is **entirely destroyed** (no `CHAPTER`-like token at all) are invisible to ALL text passes and are the **true re-OCR population**. So the residual splits into: (i) numeral-garbled-but-glyph-present → text-repairable (`recover_lost_header`); (ii) glyph-entirely-lost → **re-OCR only**; (iii) whole even-year volumes mis-keyed → **already present** (§3b). Re-OCR sizing must target (ii) specifically, measured biennium-correct.
- **Measurement-tool bug, precise location:** the bucketing fault is in `residual_after_certify.py` (`__noleg__` bucketing when a label isn't in `LEGISLATURE_MAP`), NOT `residual_profile.py` (which does no label parsing). `LEG` was verified to CONTAIN the `NNchapters` labels (`1957-vol1-56chapters`→`1956 Regular Session`), so the even-year volumes ARE mapped — confirming §3b that they're present, and that the agent's "unparsed" sizing is the artifact.

## 3a. MEASURED completeness
**2026-06-17 (post-certify, Hans-cleared, certify's internal totals — NOTE: denominator-deflated, see §3e):** certify non-dry run wrote 208 volumes, precision PASS, 3,213 flagged→confident (R1 2,979 + R2 234), **0 introduced dups corpus-wide.** Per-era distinct-confident vs certify's oracle_N: early **1850–79 26.5%→62.2%** (cert +2,895 — the early era was almost entirely flagged pre-cert), 1880–99 89.3%, 1900–49 66.9%, 1950–88 70.0%, 1989–99 87.6%. Internal total 84,363 / 118,206 = **71.37% — UNDERSTATED** because certify's even-year `NNchapters` denominators are inflated (§3e); true coverage is mid-to-high 80s. Authoritative re-measure via `chapter_vs_oracle.py` pending.

**2026-06-16 re-measure (superseded framing — `corpus-remeasure-2026-06-16.md`):**
First trustworthy number after the recovery passes, vs the CORRECTED oracle, biennium-correct (OCR corpus 1850–1999):
- **84.4% confident / 88.7% all-extracted** — ~80,600 of 95,555 chapters. Per era: 1880-99 90%, 1950-79 93%, 1980-99 95%; weakest 1860-79 (36% conf, the italic consensus bug) + 1900-19 (71%).
- **Residual = 14,940 chapters, and 98.7% are GARBLED HEADERS, not missing content — "missing headers, not pages."** The text is present in the OCR; only the `CHAPTER n` token is lost. Split: **~4,138 already-parsed-but-flagged (need CERTIFICATION)** + **~10,603 interior numeral loss (need header/numeral repair)** + ~200 genuinely uncertain + ~0 over-extraction noise.
- **=> literal 100% is achievable entirely from data on disk** (certify 4,138 + repair 10,603 garbled headers); no re-OCR of pages, no re-acquisition.
- Two tool findings: (1) `chapter_vs_oracle.py` biennium-bucketing BUG mis-files 1900-01/1906-07/1907-09/1910-11 (the odd-year session) — fix placed ~2,300 chapters; (2) `early_v2` certifies 0 (all flagged) — its acts need certification, so use best-of(recovered, early_v2) on the confident count, not early_v2 alone. (3) scope: production-* = 1850–1999; 2000–2024 = separate leginfo path (84.4% is the OCR figure; 67.7% vs the full 1850–2024 oracle).

## 4. State by era
- **Modern (1991→present):** from California's structured leginfo data; authoritative; in the Postgres DB. Effectively complete.
- **Chaptered OCR (1880–1999):** source complete; OCR holds the full chapter range. Gap = redirect-stubs (recovered, flagged — text lives in the companion Codes volume) + misnumbering (renumber-repairable) + garbled headers (residual) + noise (resolutions/body-refs, excludable). Upright-Roman headers read fine; the misses are gate/parse failures, not OCR loss, except the garbled-header slice.
- **Early OCR (1850–1879):** source complete. Two issues: (a) the 1861–1865-66 italic typeface — Tesseract misreads "CHAP." and the token-majority consensus picked its garble over correct Surya/DocTR (recoverable from the Surya field; bounded gain); (b) our early parse **OVER-extracts** — it counts resolutions, special-acts, and garbled/cross-volume-bleed numerals as statute chapters (a precision problem to tighten). Plus the same garbled-header residual.
- **DB today** (`localhost:5432/patolex`): 35,332 enactments = 1849–1876 OCR (early, ~half-complete & noisy) + 1991→present (authoritative). **The 1877–1990 middle era is parsed-and-staged but NOT ingested.**

## 5. Recovery work built this campaign
| Pass | File | Result | State |
|---|---|---|---|
| Chaptered renumber | `renumber_repair.py` | +257 safe position renumbers (+0.3 pts); self-Hans'd | done (small top-up) |
| Early consensus (Surya headers) | `recover_early_consensus.py` | +~180–220 acts on italic volumes (bounded) | **GO (re-Hans cleared 2026-06-16; precision-first)** |
| Chaptered detection | `recover_chaptered.py` | 1933 70→82%; redirect-stubs flagged; noise excluded | **GO (re-Hans cleared 2026-06-16; 0 dups across combined set)** |
| Flagged→confident certification | `certify_chapters.py` | R1 own-clean-header + R2 position-fill; ~3,170 certified in C97 BUT precision gate now FAILS on 3 introduced dups in 1853 (TOC contamination) | **write-gate added (Hans CRITICAL-3B); TOC/dup fix IN PROGRESS — must re-run** |
| Garbled-NUMERAL repair | `recover_lost_header.py` | line-head `CHAPTER` glyph present but numeral garbled → renumber by position (An-Act+Approved witness); **+578 acts, 0 dups, 20/20 spot-check** (arabic 1907–1989) | **recovery sound but Hans NO-GO (hardening): add re-run overwrite guard; exclude flagged-act numbers too; `<` not `<=` page filter; iso_date year; SCOPE: NOT truly-lost-glyph headers (see below)** |
| Early-era over-extraction tightening | — | exclude resolutions/special-acts/**TOC front matter**/bleed (the 1853 dup is this) | **not yet built (now has a concrete first target: TOC entries)** |

## 6. Process lessons (hard-won this session — adopted as rules)
1. **Verify "missing data" against the SOURCE extent + the OCR content before reporting it.** SIX "missing"/"unparsed"/"acquisition-gap" alarms this campaign ALL dissolved into recoverable-or-present data. The big one (§3e): the recurring "~20k missing" was even-year Budget/Extra-session volumes measured against the wrong (odd-year Regular) oracle N — a DENOMINATOR bug, not missing data. Never infer "missing" from a folder listing, a leading-digit label, OR a low completeness % without checking the denominator mapping. The corpus has the acts; the measurement was lying.
2. **Validate OCR findings against the IMAGES,** not text-census heuristics (the early-era "OCR loss" was a consensus bug invisible to text census).
3. **Token-majority consensus can let one garbling engine override correct ones** for a given typeface — consider per-typeface/per-engine weighting.
4. **Commit the baseline before editing; orchestrate + Hans-review every pass** — every first-build recovery pass had a precision defect Hans caught.

## 7. Path to ingest-ready
1. **Finish the recovery fix-cycle** (early-consensus + chaptered fixes → re-Hans clean).
2. **Build the garbled-header/numeral repair** (residual lever) + **tighten early-era over-extraction** (exclude non-statute series).
3. **Corpus-wide re-measure** vs the corrected oracle, with noise separated out → the first trustworthy completeness number, per era.
4. **Ingestion prep** (then, on explicit go): review the flagged residue (don't silently drop); handle redirect-stubs (text in companion Codes volumes); namespace 1854's dual series; **back up the DB**; one-pass ingest 1850→present; compare to backup.

## 8. Open decisions for Patrick
- **Completeness bar to launch:** how close to 100% (per era) is "complete enough" — and whether the genuinely OCR-garbled residual that resists text repair warrants targeted re-OCR of the worst pages, or is accepted as flagged.
- **Ingest sequencing:** all-at-once after full validation vs. ingest-in-tranches (e.g. the clean chaptered era now, early era after its precision tightening).
- **Redirect-stub policy:** ingest the stub chapters (real chapters, text in the Codes volume) with a pointer, or resolve their text from the companion volumes first.
