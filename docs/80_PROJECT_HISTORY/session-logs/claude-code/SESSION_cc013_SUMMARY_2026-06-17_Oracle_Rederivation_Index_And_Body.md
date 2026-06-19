# Session cc013 Summary

| Field | Value |
|-------|-------|
| Session | cc013 |
| Date | 2026-06-17 |
| Agent | Claude Code (Opus 4.8, 1M ctx), ELEVATED PS on PK_Alien_5090 (admin token) |
| Context | Oracle reconciliation: verify index re-derivation findings by reading the volumes; assess modern-era denominator |
| Branch | main |

---

## What Was Done

**Access:** Relaunched in an elevated PowerShell → admin token now reaches the
`patolex` data root (`C:\Users\patolex\PatoLex-scratch`, 222 volumes). The earlier
non-elevated `PatrickKolasinski` account was ACL-blocked; elevation (Administrators
group active) resolved it without ACL surgery.

**Baseline / harness:** Backed up the morning rederivation outputs, re-ran the
unmodified `rederive_index_counts.py` → byte-identical reproduction (deterministic
regression harness established).

**FINDING 1 — 1865-66 is a REAL oracle undercount, NOT a parser artifact (overturns prior Hans tier).**
Read the volume's own printed index: a continuous run of ~380 real `An Act` titles
climbing chapter 1→650, ending cleanly at the resolutions marker — no
amendment/subject-index pollution (Hans's C1/M4 failure mode absent). Index distinct
≥488 (cov ≥0.75); parsed floor already holds 463 distinct — both impossible under a
true 280. ⇒ oracle 280 is a severe undercount (~650); the tool's 650 was correct.
The 6-16 "confirmed correct" + the "parser artifact" tier were the **1887 flip-flop
lesson repeating** (clerk web index trusted over the printed volume).

**FINDING 2 — verified the other ORACLE_LOW by reading index lines:** 1887 51→~188 REAL,
1883-84 23→~96 REAL, 1863 476→~538 REAL (+62); 1858 (+2) and 1891 (+2) = noise
(1891 modal_year=1872 was an old-code-citation red herring). Net early-era real
undercounts: **1865-66 +370, 1887 +137, 1883-84 +73, 1863 +62 (~+642).**

**FINDING 3 — modern era does NOT need the printed indices (overturns prior "must OCR CONTENTS pages" claim).**
(a) We hold every modern source PDF (`chief-clerk-archive/`, 211 PDFs, 1861–2000) —
absent CONTENTS pages are an OCR-*scope* matter, not an acquisition gap. (b) The
modern body is SELF-INDEXING; the contiguous-from-1 top of body `CHAPTER N` headers
IS the count: 1931 body=1220 (oracle 1220 exact), 1945 body=1526 (oracle 1527, −1).
Built `derive_modern_from_body.py` and swept 1905–1999 (176 vols): 11 exact MATCH;
the 110 "ORACLE_HIGH"/47 low-cov are two KNOWN artifacts (multi-vol granularity +
the biennium `NNchapters` keying I reintroduced via leading-year matching). **No real
modern oracle undercounts — the modern oracle is validated by the body.**

---

## Files Changed

**New tools:**
- `pipeline/analysis/derive_modern_from_body.py` — body-based chapter-count
  re-derivation (modern self-index cross-check; read-only, new-files-only).

**Modified docs:**
- `docs/20_ROADMAP/CORPUS_COMPLETENESS_STATE.md` §3h — struck + superseded the two
  wrong conclusions (1865-66 artifact; modern CONTENTS-OCR requirement) with evidence.

**Run log:**
- `docs/80_PROJECT_HISTORY/run-logs/index-rederivation-cc013-run.log`

**Throwaway (NOT committed; deleted at close):** `_probe_1865.py`, `_verify_oracle_low.py`,
`_probe_modern.py` under `pipeline/analysis/`.

**Scratch outputs (5090, not git):** `_index_rederivation.BEFORE.tsv/.md`,
`_body_rederivation.tsv/.md`.

---

## Decisions Made

| Decision | Detail |
|----------|--------|
| 1865-66 reclassified | Real ~650 undercount; flagged for Patrick's oracle decision (do NOT overwrite oracle) |
| Modern: no CONTENTS-OCR | Use body-max self-index instead; cheaper, no acquisition |
| Verify-by-reading first | Read the volume before "fixing" the parser — caught the 1865-66 reversal |

---

## Open Items at Close

| Item | Priority |
|------|----------|
| Biennium-fix `derive_modern_from_body.py` (adopt `chapter_vs_oracle.py` keys + per-session aggregation) | HIGH |
| #3 Harden early-roman parser under-reads (cov 0.5–0.8) — MUST preserve 1865-66=650 | HIGH |
| #1 Early-era printed-index-vs-oracle discrepancy table (oracle-decision artifact for Patrick) | HIGH |
| PowerShell tool shell wedged — using Bash; revisit | INFO |
| Oracle edits (the ~+642 early undercounts) are Patrick's call | GATE |

---

## Next Session Should Start With

1. Biennium-correct the modern body sweep → clean modern cross-check table.
2. Harden early-roman index parser (per-engine fields for italic index pages), preserving correct volumes.
3. Synthesize the discrepancy table for Patrick's oracle decision.

---

---

## Update 2026-06-17 (afternoon) — discrepancy table, oracle edits, holds

**Delivered:**
- **Discrepancy table** `docs/30_SYSTEM_DESIGN/sources/ORACLE_DISCREPANCY_EARLY_2026-06-17.md` (6 tiers).
- **Engine-union recall fix (analysis)** across 41 early volumes — recovered 1855/1857/1862/1869-70/1875-76/
  1877-78 from NO_INDEX to oracle MATCH. Canonical-tool merge owes Hans ×2 (deferred, classifier outage).
- **APPLIED 3 Patrick-approved oracle undercount corrections** to `ca_chapter_counts.tsv`: 1865-66 280→650,
  1887 51→188, 1883 23→96. Total **119,157→119,737 (+580)**. **Validated:** all 3 have dense-continuous
  index runs 1→N (structural check) — the edits stand.

**Held (no guessing — rigor over the table's optimism):**
- **1863** = a real MISSING session (14th, 1863; identity confirmed by approval-year histogram), but its index
  is gappy with an 800s block → COUNT unresolved (page-number contamination suspected). Do NOT add a row yet.
- **1860** over-count NOT confirmed after a full structural read (same 800s contamination); earlier "confirmed"
  RETRACTED. Held.
- **Method finding:** early index-derived counts are only trustworthy when **dense-continuous-from-1**; gappy
  indexes suffer **page-number-column contamination** — a precision gate to add in the Hans-gated merge.

**Tier 6 read directly (Patrick corrected my "exclude" call):** 1893 = MATCH (index 242 → resolutions, oracle
244, −2 clip); 1861 = 32 legible index pages with the chapter-number COLUMN dropped pg3+ (count `An Act` lines
or column-aware re-OCR); **1873-74-code = "Amendments to the Codes" — real code-amendment acts, MUST be counted
not excluded** (numbers reach 817 > main 679 → possible systematic code-amendment undercount; investigate
continuous-vs-separate numbering); 1850-54 = no front index but body has `Chapter N` headers → derive from body.

## Open Items at Close (updated)

| Item | Priority |
|------|----------|
| **1873-74-code numbering** — continuous vs separate (possible corpus-wide code-amendment undercount) | HIGH |
| **1863 / 1860** — read the 800s blocks page-by-page (contamination vs real acts) before any oracle edit | HIGH |
| 1850-54 body-derivation + 1861 An-Act line count | MED |
| Engine-union → canonical `rederive_index_counts.py` + **Hans ×2** | MED (classifier up) |
| Modern body-sweep biennium keying (polish; modern oracle already validated) | LOW |

---

## Update 2026-06-18 — A/B resolved, session-number remodel (P0/P1)

- **A (code amendments):** the 1873-74 `-code` volume shares the **same chapter sequence** as the general
  statutes (main body roman headers → 673 ≈ oracle 679; `-code` numbers within 1–679). Already counted; no
  undercount; no separate rows. "Are code changes counted?" = **yes.**
- **B (held volumes resolved by duplicate-title test):** 1860's & 1863's "800s" index entries are
  **page-number contamination** (1860: 20/22 dup titles; 1863: 18/20) — proven, not guessed.
  **Applied 1860 455→385** (oracle total **119,667**). 1863 = the **14th session** (~538), held only on a
  matcher mechanic.
- **Session-number remodel (Patrick: stop year-keying, model the canonical session):** plan written
  (`docs/30_SYSTEM_DESIGN/SESSION_NUMBER_REMODEL_PLAN.md`). P0/P1 built `build_session_reference.py`
  (corpus-derived, 61/222 ordinals). **1863 = 14th confirmed by the ordinal sequence (13↔15).** Modern era
  (~1905+) uses year-pair + extra/special, not ordinals → two-form (or continuous-ordinal) canonical id.
- **Method finding:** reliable early counts require a **dense-continuous-from-1** index run; gappy indexes
  suffer page-number contamination (precision gate for the canonical-tool merge).
- **Delegation (2026-06-18):** Patrick will NOT review the canonical-id table — I + Hans auditors drive the
  remodel (P2→P5) to completion, Hans-gating each phase.
- **P2 + Hans (2026-06-18):** `build_canonical_sessions.py` assigns ordinals to the 133 regular rows +
  validates vs corpus-declared ordinals. **Hans's 1st audit caught a real join bug** (declared keyed by
  leading-year, but the oracle's `session_year` uses START year for some biennia / END for others →
  biennial anchors like 1877-78 and 1900-01→34th silently lost), plus overreach and unfiltered
  extraordinary-session captures — **all fixed**. Re-run: the **`+1` offset is anchored CONTINUOUSLY
  1863-64 (15) → 1945 (56), ~30 anchors** → single missing 14th session strongly supported; the duplicate-"19th"
  resolved correctly (1873-74 = 20). Honest caveat (Hans): 1947+ has no ordinal anchors (modern year-pair
  regime) → "one missing session" confirmed 1863–1945, unverified after. Plan §3b.
- **Next:** fresh 2nd Hans pass on the corrected P2 (twice-for-denominator), then P3→P5 (oracle schema
  columns + matcher rewrite + add the 1863 row), each Hans-gated.

## Open Items at Close (updated 2026-06-18)

| Item | Priority |
|------|----------|
| **Remodel P2** — finalize `canonical_id` for every session (correct OCR ordinals via sequence; modern year-pair) | HIGH |
| **Remodel P3–P5** — add oracle columns, rewrite matchers, re-measure, add 1863 row — **Hans ×2** | HIGH |
| Engine-union → canonical `rederive_index_counts.py` + Hans ×2 (separate change) | MED |
| 1861 (32 legible index pages, column dropped) / 1850-54 body-derivation — Tier-6 tail | LOW |

---

## Update 2026-06-19 — remodel EXECUTED (P3–P5), orchestrated

The session-number remodel is **live**, done as an orchestration: I briefed subagents (opus for the careful
implementation, sonnet for narrow fixes) and gated each phase with Hans, rather than hand-coding it.
- **P3:** canonical columns (`session_number`/`session_kind`/`canonical_id`) backfilled into a draft oracle;
  validated at offset 0 (43 anchors). S14 reserved for 1863.
- **P4 (opus subagent):** rewrote `chapter_vs_oracle.py` + `find_oracle_match` + new `build_volume_canonical_map.py`
  to key on `canonical_id`. **Parity guard: 0 diffs vs legacy on all 222 volumes.** Hans found 2 legacy-path
  CRITICALs → sonnet fixed.
- **P5 (opus subagent):** went live (draft→oracle) + added the **1863/S14 row (538)**. Total **119,667→120,205**,
  216 rows. Final Hans gate cleared the DATA (contiguous S1..S134, 4 prior edits intact, reversible) but found 2
  collision bugs in map-BYPASS paths → sonnet fixed (`_SPECIAL_1863` both-directions; `_FALLBACK_1863` + missing-map
  warning). 5/5 re-verified.
- **Result:** oracle keyed on canonical session id; **1863 collision fixed (S14≠S15)**; biennium-bucketing bug class
  retired; denominator 120,205; reversible via backup. 4 Hans gates total.
- **Orchestration lesson (Patrick):** stay in the orchestrator lane — delegate drafting/coding to subagents, keep
  my context for briefing / review / gating / go-no-go. I was doing implementation myself for too long.

## State at close (2026-06-19) — what remains / next

**Where we are:** the chapter-completeness *denominator* (the oracle) is now on a sound, canonical footing —
session-number-keyed, early-era undercounts corrected (1865-66/1887/1883/1863 + the missing 14th session), 1860
over-count fixed, modern era validated via body-self-index. Denominator = **120,205**. Latest measured OCR-scope
completeness ≈ **92%** (~89,136 / 96,821), but this should be **re-run against the corrected canonical oracle** for
the first truly trustworthy per-era/per-session number.

**Next (in priority order):**
1. **Re-measure** completeness vs the canonical oracle → first trustworthy %, per era + per session; locate the real gaps.
2. **Denominator long tail:** Tier-6 (1861 — 32 legible index pages, chapter-number column dropped → count `An Act`
   lines or column-aware re-OCR; 1850–54 — derive from body `Chapter N` headers); fix the `1949-prior`→S59 known issue;
   sweep any remaining discrepancies the canonical re-measure surfaces.
3. **Engine-union merge** into canonical `rederive_index_counts.py` (Hans-gated) — currently applied in analysis only.
4. **Recover the missing chapters** (~7–8%): (a) still-text-recoverable (a header exists in some engine → engine-union /
   lenient printed-number read); (b) genuine re-OCR for the truly headerless (no engine ever read it → a NEW engine, VLM
   candidate, thermally-guarded on the 5090) — Patrick-gated, GPU-heavy.
5. **Merge + archive** the staged recovery outputs into one authoritative parse per volume; then (separately, Patrick-gated,
   NOT yet) ingest. Modern 2000+ is the leginfo-XML path, not OCR.

## Lessons Learned

- **READ THE VOLUME — again.** The 1865-66 "artifact" was a real undercount; the prior
  session filed it wrong while writing the very lesson that would have caught it. The
  printed index is the authoritative internal source; the clerk web index undercounts (now 3×).
- **The biennium `NNchapters` trap is real and easy to re-introduce.** Any fresh tool that
  keys on the label's leading year reintroduces it — use `chapter_vs_oracle.py`'s suffix-decode.
- **"On the 5090" needs the right *account*, and the data shouldn't live in a user profile.**
  Elevation worked, but a shared/non-profile data root (SMB) is the real fix.
- **Don't launch long jobs through a shell you then need responsive** — the PS tool shell
  wedged after a 10-min-timeout launch; keep heavy runs isolated (Bash) or backgrounded.
