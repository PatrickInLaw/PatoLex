# Crowdsource Correction + The Reframed Launch Bar

**Status:** Design direction set by Patrick, 2026-06-01. Not yet gated; connection points to Gate H (web app), Gate I (public launch), and the VERIFICATION_TOOL.md mechanism. No code decisions here.

**Related:** `VERIFICATION_TOOL.md`, `LAW_AS_GIT.md`, `OCR_ACCURACY_VALIDATION.md`, `SCHEMA_DESIGN.md`, `ROADMAP.md`.

---

## The Reframe (read this first)

The prior stance: **no public launch until the full corpus is present and validated.** That remains the quality goal. What changes is the *mechanism*:

> **Old:** perfection before launch — validate everything internally, then publish.
> **New:** transparency + convergence — publish with visible confidence + source images + a correction path, then let accuracy converge over time via crowd and expert correction.

These are not in conflict. An attorney consulting PatoLex for professional work has always needed to verify against authoritative sources; PatoLex makes that easier, not unnecessary. As long as (a) the source-page image is shown alongside the processed text, (b) the OCR pipeline's per-token confidence is surfaced, and (c) a correction path exists, the corpus is **professionally usable** at launch even where OCR is imperfect. The standard is not "no errors"; it is "no silent errors" — every uncertain region is visible and correctable.

This does **not** relax the full-corpus requirement. The whole 1849-present timeline must be present before launch (the value of the product depends on it). What changes is that completeness and perfection no longer need to be reached at the same moment.

---

## Two Tiers

### Public (wiki) tier
- **Anyone** can read, search, and annotate.
- Every statute page shows: the **processed OCR text** and the **source-page image side by side**.
- Low-confidence tokens are highlighted in the text view (driven by pipeline confidence flags — see below).
- Readers can hit a **"random teleport"** button to jump to a region of the corpus that needs review; the landing is weighted toward low-confidence and high-disagreement regions.
- Corrections flow through a trust ladder (see Trust Model below); they are never applied invisibly.
- The public tier carries the **full historical corpus** (1849-present).

### Professional / attorney tier
- Operates on the **`expert_verified` and `crowd_confirmed` subsets** of the corpus — the parts that have cleared the trust ladder to a level defensible for professional reliance.
- The same source image + provenance + confidence data is always visible; the tier adds filtering so attorneys can scope queries to verified text only.
- Point-in-time queries work identically: "what did §187 say on March 15, 1893?" returns verified text where available, flagged-but-unverified text (with image) elsewhere.
- **The professional tier does not certify accuracy; it certifies provenance and process.** A clearly documented trust level + a source image is what makes it defensible, not a claim of perfection.

---

## Trust Model (anti-vandalism, since this is law)

This is not a general-purpose wiki. Errors in legal text can cause material harm. Crowd contributions are **never blindly trusted**, and the vandalism surface is actively narrow — most contributions are simple image-vs-text comparisons requiring no statutory knowledge.

### Trust levels (extends the schema's existing `trust_level` field)

| Level | Source | Description |
|-------|--------|-------------|
| `ocr_consensus` | Pipeline | Classical-engine consensus; the automated baseline. No human has touched it yet. |
| `ocr_uncertain` | Pipeline | Low-confidence or engine-disagreement flag; surfaced for review. |
| `crowd_proposed` | Contributor | A single contributor has submitted a correction. Displayed as pending; not yet applied to serving text. |
| `crowd_confirmed` | Multiple contributors | N independent contributors have reached the same reading against the source image (where N = 2 or 3, TBD). Applied to serving text; labeled with contributor count + date. |
| `human_verified` | WinUI3 outsourced tool | Resolved by the in-house / outsourced multi-reviewer mechanism (VERIFICATION_TOOL.md). |
| `expert_verified` | Steward or named expert | Reviewed by a steward or designated expert; the top tier. Used for dispute resolution. |

The **source-page image is the ground truth anchor** at every level. A contributor's job is always "does the text match the image?" — never "what should this law say?" A correction that changes meaning without a corresponding image reading is automatically suspect and escalates to expert review.

### Anti-vandalism controls

- **New account limits.** Fresh accounts can only propose corrections; they cannot confirm others' corrections until they have accumulated a track record. Reputation gates calibrated by per-contributor accuracy against consensus and image.
- **Per-contributor accuracy scoring.** Every contributor's history of approvals vs. reversals is tracked. An account that consistently proposes corrections that are later overturned loses weight and eventually loses propose rights. This mirrors the inter-rater scoring in VERIFICATION_TOOL.md — the same mechanism, now public-facing and gamified.
- **Sockpuppet resistance.** Crowd-confirmed requires N independent agreeing contributors. Accounts that share IP/device fingerprints do not count as independent for confirmation purposes. Rate limits apply. These are heuristics, not guarantees — expert review is the backstop.
- **No majority-overrides-expert.** `expert_verified` text can only be changed by another expert. Crowd contributions on that text enter a dispute queue, not the serving pipeline.
- **Audit trail is permanent.** Every proposed correction, every confirmation, every rejection is a `change_event` with contributor provenance. Nothing is silently overwritten. A legal researcher can always see the full correction history for a token or passage.
- **Dispute escalation.** When confirmed crowd readings disagree with each other, or when a contributor disputes an expert reading, a steward review is triggered. Stewards are named, trusted humans (law school faculty, librarians, designated volunteers).

---

## Integration with the Event-Sourced Schema and Law-as-Git

### A correction is a `change_event`

The schema (`SCHEMA_DESIGN.md`) already models all text evolution as append-only `change_event` records with `trust_level` and `source_document_id` provenance. A crowd correction fits exactly:

- **`action`:** `amend` (text correction) or `flag` (marks a region uncertain without replacing text).
- **`new_text`:** the contributor's proposed reading.
- **`trust_level`:** starts at `crowd_proposed`; advances to `crowd_confirmed` or `expert_verified` as the ladder is climbed.
- **`source_document_id`:** references the same `source_document` record (the scan) the original OCR used — the image crop is always traceable.
- **Contributor provenance:** an additional `contributor_id` field (or a foreign key to a `contributor` table) attached to crowd-sourced `change_event`s. This is the one schema addition required beyond what is already designed.

When a correction is accepted (reaches `crowd_confirmed` or higher), the `provision_version` read model is re-materialized for the affected provision and the serving layer is updated. The **Git artifact is also regenerated for that provision's relevant commits** — because the correction may change the text of a historical section, and the Git repo is a projection of the system of record. This is handled by the emitter, not by Git's own machinery.

### Citation stability and point-in-time integrity

This is the sharpest design tension (see Open Questions). The resolution:

- **A later correction creates a new version; it never rewrites a cited version.** If an attorney cited §187 "as of March 15, 1893" from PatoLex and a crowd correction is later accepted for that passage, the cited text does not change retroactively. The corrected text becomes a new `provision_version` row with a `valid_from` of the correction-acceptance date (or, for an OCR correction that was always wrong, a special `correction_applied_at` timestamp that distinguishes it from a legislative change). The original served text remains accessible via the audit trail.
- **Two classes of correction, different semantics:**
  1. **OCR corrections** ("the image says X but the pipeline read Y"): these fix what the law has always said. They are retroactively correct in fact but should be served transparently — showing both the original OCR reading and the correction, with dates, so a citation that predates the correction is reproducible. The `provision_version` row for the correction carries a `correction_of` back-reference to the row it supersedes.
  2. **Legislative corrections** ("this version should not have been served here"): rare, but possible if a reconstruction error (wrong act applied, wrong operative date) is discovered. These are escalated to expert review and are treated as reconstruction bugs, not crowd edits. They require a steward sign-off and generate an explicit correction notice.
- **The Git artifact follows.** When an OCR correction is accepted for a historical passage, the Git emitter regenerates the affected commit(s) — but with a commit note or git note recording the correction, so the audit trail is visible in the repo itself. The regeneration replaces the file content but the commit metadata (date, act citation) is unchanged. This is a known design tension with the "immutable history" principle of `LAW_AS_GIT.md`; the resolution is that OCR corrections are corrections of the *record* (improving fidelity to the source), not of the *law* (changing what the legislature enacted). The repo is a faithful record of what the legislature enacted; improving OCR fidelity is consistent with that faithfulness, not a violation of it.

---

## How the Pipeline Feeds the Correction Queue

The multi-vector OCR cascade (`OCR_ACCURACY_VALIDATION.md`) already produces exactly what the correction wiki needs:

| Pipeline output | Correction wiki consumer |
|-----------------|--------------------------|
| Per-token confidence scores (classical-engine consensus) | Drives the "low-confidence" highlight in the public UI |
| Disagreement queue (where engines diverge, incl. VLM vector dissent) | **IS** the "needs review" queue; drives random-teleport weighting |
| Per-token bounding boxes (docTR/Surya) | Powers the source-image crop shown to contributors |
| Source-page image (stored at ingest) | Ground truth anchor for all contributor reviews |
| `trust_level = ocr_uncertain` events | Directly map to `crowd_proposed`-eligible items |

The disagreement queue is not new infrastructure for the correction wiki — it is the same queue VERIFICATION_TOOL.md's WinUI3 tool reads, now with two consumers:

1. **In-house / outsourced WinUI3 tool** — fast, expert-paced, processes backlog at scale.
2. **Public correction wiki** — crowd-paced, gamified, processes the long tail.

Both write results back as `change_event`s at the appropriate trust level. The pipeline does not need to know which consumer resolved a given item; it only surfaces disagreements and accepts resolutions.

**Random-teleport weighting algorithm (sketch):**
- Weight = f(confidence_score, reviewer_coverage, page_age)
- Lower confidence → higher weight (prioritize uncertain regions)
- Lower reviewer_coverage → higher weight (unseen regions before already-reviewed ones)
- Optional: weight by "interesting" — controversial statutes, frequently-queried sections — to attract expert reviewers via social/curiosity pull rather than pure efficiency.

---

## Gamification + Viral Mechanics

The goal is to attract law students, legal historians, and interested citizens as a **hobby community** — not just to extract labor but to build stewardship.

- **Attribution.** Every accepted correction is attributed to its contributor, permanently, in the `change_event` record and the Git commit note. "Corrected by @username, 2027-03-15" is part of the corpus provenance.
- **Leaderboard.** Public-facing: corrections accepted, accuracy rate, sections reviewed. Per-institution leaderboard for law school adoption.
- **Reputation badges.** Milestone badges (first correction, 100 corrections, 99%+ accuracy rate, "code expert" for a given code). Reputation unlocks the ability to confirm others' corrections (the ladder that drives toward `crowd_confirmed`).
- **Law school integration.** Historical legal research + paleography = genuine law school curriculum value. A professor can assign "review 50 items from the 1850s session-law corpus." The random-teleport + attribution model makes this trackable and citable.
- **"Law explorer" framing.** The public tier is not just a correction tool — it is a legal history archive anyone can explore. The random-teleport is a discovery mechanic as much as a review mechanic. Finding and correcting an error in an 1867 statute is genuinely interesting; the UI should make that feel like finding something, not doing a chore.

---

## Perpetuity Tie-In

The convergence model + open-source + crowd stewardship + the Git artifact reinforce each other directly:

- **Open-source tooling** means the crowd correction machinery itself can be forked and maintained by a law school or nonprofit even if PatoLex's serving infrastructure goes dark. The correction event log + the Git repo are the durable artifacts.
- **Distributed stewardship.** A modest steward does not need to validate the whole corpus alone. The crowd and the expert-verified layer produce an expanding verified subset over time; the steward inherits a self-improving archive, not a static one.
- **The Git repo as the handoff vehicle** (`LAW_AS_GIT.md`) gains a trust-level annotation in commit trailers. A law school cloning the repo can filter by trust level — "show me only `expert_verified` text" — without running PatoLex at all.
- **CC0 / public domain framing.** Statutory text is unencumbered public domain (Gov. Code §10248.5). Crowd contributions to the OCR layer of that text are also unencumbered — contributors are correcting facts (what the image says), not creating new copyrightable expression. This is the contribution licensing argument for CC0 (see Open Questions for nuance).

---

## Open Questions

These are genuine unresolved tensions, flagged for the orchestrator and future gate reviews.

**1. Citation stability vs. live crowd correction (the hardest tension)**
The design above (corrections create new versions, never rewrite cited ones) handles the common case cleanly. The hard case: a systematic OCR error that affected thousands of sections (e.g., the `e→o` classical-engine confusion in 1850s typefaces). Correcting those retroactively without breaking citations requires either (a) a migration that creates thousands of new `provision_version` rows, or (b) a "correction batch" mechanism that bulk-applies a correction rule and notates it. Neither is designed yet. Decision needed before Gate H.

**2. Launch-bar evolution vs. "validate-before-launch"**
The reframe is explicitly an evolution, not a reversal. But the ROADMAP still reads "No public launch until the full corpus is present and validated." That language needs updating to distinguish:
- **Completeness requirement** (1849-present must be present): unchanged.
- **Pre-launch validation requirement**: now "validated to OCR-confidence + source-image display standard," not "expert-verified throughout." Gate I description should be updated to reflect this.

**3. Contribution licensing (CC0 vs. attribution-required)**
Arguments for CC0: contributions correct public-domain text; CC0 makes the archive permanently unencumbered; no license friction for the perpetuity handoff. Arguments for attribution-required (CC BY): contributors have a legitimate interest in credit; attribution drives the gamification model. Middle ground: CC0 for the text corpus; separate contributor attribution in the metadata layer (not in the license). Recommended for review by a law school IP contact before Gate H.

**4. Sockpuppet and coordination attack resistance**
The controls above (IP fingerprinting, rate limits, accuracy scoring) are heuristics. A determined coordinated attack (e.g., multiple accounts confirming a deliberately wrong reading of a politically sensitive statute) could in theory advance a vandalized version to `crowd_confirmed`. The backstop is: `crowd_confirmed` is still clearly labeled in the UI, and attorneys using the professional tier see `expert_verified` only. But the attack risk for the public tier is real and worth a formal threat model before launch.

**5. Reviewer onboarding and reputation thresholds**
What accuracy rate, over how many items, is required to unlock confirmation rights? What is the confirmation quorum (2-of-3? 3-of-5)? These numbers should be empirically calibrated once a beta reviewer pool exists, not guessed upfront. Placeholder: 80% accuracy over 25 items to unlock confirmation; 3 independent confirmations required. These are starting points only.

**6. Dispute resolution governance**
Who are the stewards? How are they appointed? What is the appeals path when a contributor disagrees with an expert ruling? This is a governance question that touches the perpetuity model — the law school / nonprofit steward needs a governance charter, not just code. Out of scope for Gate H, but must be resolved before launch (Gate I).

**7. Random-teleport confidence weighting vs. coverage gaps**
Routing contributors to the lowest-confidence regions is efficient for quality but may leave large swaths of moderate-confidence text unreviewed (the classic "exploit vs. explore" tradeoff). The weighting algorithm needs a coverage-gap term to avoid indefinitely deferring mid-confidence regions. Design detail for Gate H.

**8. Legal disclaimer and professional liability**
PatoLex is not a law firm and does not give legal advice. The professional tier is a research tool, not a certified authority. Even `expert_verified` text is a transcription; attorneys must still verify against official sources for formal legal work. This disclaimer needs to be prominent, persistent, and reviewed by a qualified attorney before launch.

**9. How the professional tier certifies "verified" subsets**
The professional tier is currently defined as "routes to `expert_verified` and `crowd_confirmed` text." But what does that mean for a provision that is 80% `expert_verified` and 20% `ocr_uncertain`? The professional tier needs a display rule for mixed-trust provisions (probably: show the text with inline confidence annotations, not a binary verified/unverified gate). Gate H design.

---

## Revision History

| Date | Change |
|------|--------|
| 2026-06-01 | cc002: Initial design. Launch-bar reframe, two-tier model, trust ladder, pipeline integration, citation-stability resolution, perpetuity tie-in, open questions. |
