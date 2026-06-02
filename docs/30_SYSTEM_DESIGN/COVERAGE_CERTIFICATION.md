# Completeness Certification — Reverse Verification via Referential Closure

**Date:** 2026-06-02 · **Status:** ADOPTED design (cc002, Patrick) · **Scope:** how PatoLex *proves* its historical corpus is complete.

---

## 1. The problem this solves

PatoLex's launch bar is **completeness** — the corpus must contain *all* of California's statutory law, 1850→present, with no silent gaps. The hard question is not "is the text accurate" (that's the OCR/confidence/verification layer) but **"how do we know we didn't miss an act, an amendment, or a whole volume?"**

Counting parsed acts against each volume's printed index is weak: it depends on OCR'ing the index correctly and a manual per-volume cross-check, and it can't catch a section that was renumbered or a volume that was skipped entirely. We need a **deterministic, corpus-wide oracle.**

## 2. The principle: build forward, certify backward

- **Construction runs FORWARD (1850 →).** The actual historical *text* exists only in the historical record, and the historical signals (OCR'd dates, references) are too noisy to *build from*. So we reconstruct forward, capturing text act by act. This is why we do **not** start at today's code and work backward.
- **Certification runs BACKWARD.** California's **current codified law** (from the authoritative leginfo PUBINFO bulk data — see `DATA_SOURCES.md`) is complete and ground-truth. The current code, plus the **amendment-reference graph** that every statute carries, is effectively a **checksum for the entire historical corpus.**

The two directions are complementary: forward = *construction*, backward = *certification*. The modern-era signals are **not** good enough to build the corpus *from*, but they are **rock-solid verifiers** that catch anything we missed.

> **Confidence triages human review; referential closure certifies coverage.** Two different jobs. Confidence (parse + OCR-agreement) tells us *where to look*; it cannot tell us whether we *have everything*. Referential closure can.

## 3. The authoritative anchor

The leginfo current codified law is the complete, authoritative set of: every code section that exists today, and (via legislative-history / chaptered-bill records back to 1993-94) the dates of its origin and each amendment. This is the fixed endpoint the historical reconstruction must reconcile against. It is authoritative because it *is* the law in force — not an OCR artifact.

## 4. The two deterministic gap detectors

1. **Origination gap.** Every code section in the authoritative current code must trace to an **enacting event** in our corpus. A section that exists today with no origin in our data → **we skipped its enacting statute** (or its enacting volume).
2. **Amendment gap.** 
   - *Dangling reference:* an amendment in our corpus that targets a code section (or a prior amendment/version) **not present in the corpus** → we missed the thing it depends on.
   - *Missing amendment:* the authoritative legislative history says section X was amended on date D, but our corpus has **no event** for (X, D) → we missed that amendment.

## 5. The global checksum (strongest form)

**Forward-reconstruct through every captured amendment and the result at "today" must equal the current authoritative code, section for section.** Any residual (a section we can't reproduce, or extra/missing text) **localizes a gap** to a specific provision and date range. Because the endpoint is ground truth, a clean match is a proof of completeness for the codified stream.

## 6. Precision requirement: resolve references through lineage, not section numbers

References must resolve to a **provision identity**, traversing the lineage/recodification graph (`lineage_edge`) — **not** literal section-number equality. An 1880 act amends "§751 of the Political Code," but renumbering, section splits, and the major recodifications (1872, 1943) mean that provision's *identity* travels under different designations over time. A naive number-match validator would throw a false gap at every renumber. The dangling-reference detector therefore resolves "§751 of the Political Code, as of date D" → the provision identity valid on D, via `designation_history` + `lineage_edge`. This is precisely why provisions carry synthetic identity rather than encoding their section number.

## 7. What the pipeline MUST capture (the requirement)

For the certification to be possible, **every ingested act must record, in structured form:**
- **Action(s)** it performs: `enact` / `amend` / `repeal` / `repeal_and_reenact` / `add` / `renumber`.
- **Target reference(s):** the named target code (Civil/Penal/CCP/Political/…) and the target section designation(s) — captured **as printed** (faithful), even when the target provision is not yet resolvable.
- **Operative/effective date** of the action.
- A **resolution status** per target: resolved-to-provision-id, unresolved (dangling), or deferred (target expected from a not-yet-processed volume).

These are captured at ingest whether or not the reconstruction read-model is built yet — capture is cheap and must not wait for resolution. The **unresolved-reference validator** then runs (a) incrementally at ingest and (b) globally at the modern anchor, emitting the gap lists from §4.

## 8. Phasing

- **Now / near-term:** the pipeline begins **capturing** the structured targets + dates on every act (statutes and especially code-amendment volumes). Without capture, certification is impossible later; with it, the data accrues correctly even before the validator/reconstruction runs.
- **Mid-term:** incremental closure checks within the loaded range (e.g., once the 1872 baseline + its amendments are loaded, dangling-reference checks run against that subset).
- **Endgame:** when the corpus reaches the digital era / current state, run the global checksum (§5) against the authoritative current code → **certify complete.**

## 9. Relationship to other designs

- **Confidence / OCR verification** (`OCR_ACCURACY_VALIDATION.md`, `CROWDSOURCE_CORRECTION.md`): triage of *text accuracy*. Orthogonal to this doc, which certifies *coverage*.
- **Schema** (`SCHEMA_DESIGN.md`): the event-sourced log + synthetic provision identity + `lineage_edge` are what make reference-resolution-through-lineage possible. This doc adds a structured-target-reference capture requirement (see the companion change list).
- **Method A reconstruction** (`CODE_AMENDMENT_PARSE_DESIGN_2026-06-02.md`): the forward application of amendments; its output is what the global checksum validates.
- **Data sources** (`DATA_SOURCES.md`): the leginfo current code is the authoritative anchor.
