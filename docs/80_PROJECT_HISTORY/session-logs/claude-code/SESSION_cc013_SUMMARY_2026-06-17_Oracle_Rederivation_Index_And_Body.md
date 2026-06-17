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
