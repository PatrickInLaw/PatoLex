# Verification Tool + Multi-Vector OCR Ensemble (human-in-the-loop accuracy)

**Status:** Design (cc002, 2026-06-02). The mechanism that makes legal-grade OCR accuracy affordable at corpus scale — "no line-by-line human review; humans only resolve *flagged disagreements*." Build target: a **WinUI3** desktop verification app (Microsoft-aligned). Design now; build when production OCR generates the disagreement queue (after the engine pick + first production run).

**Sister mechanism:** `CROWDSOURCE_CORRECTION.md`. The WinUI3 tool (in-house / outsourced reviewers) and the public crowd-correction wiki are sibling consumers of the same pipeline disagreement queue. Both write `change_event`s at the appropriate `trust_level`. The WinUI3 tool handles bulk backlog at speed and scale; the public wiki handles the long tail and ongoing corrections with gamified community participation. Same trust engine; different audiences and operational modes.

## The principle
Accuracy comes from **automated multi-engine disagreement detection** + **cheap, multi-reviewer human resolution of only the disagreements** — never wholesale human re-reading. (See memory `patolex-historical-first` QA standard.)

## Multi-vector ensemble (decided cc002)
Run multiple OCR engines per page and treat them as independent vectors:
- **Faithful engines = the text source.** Literal transcription (no modernizing). *Original candidate pool: Tesseract / docTR / Surya / PaddleOCR.* **As built (2026-06-02): the production committed text is a token-majority CONSENSUS of 3 engines — Tesseract + docTR + Surya** (`pipeline/consensus.py`, `N_MAX_ENGINES=3`), not a single gold-ranked winner. **PaddleOCR was dropped (Windows-box install/runtime failures) and is NOT a consensus voter.**
- **VLM engines = disagreement vectors ONLY.** qwen2.5vl (on the 5090 via Ollama), GOT-OCR, etc. They modernize/editorialize, so their output is **NEVER committed as text** — but they're valuable *because* they're "smart": where a VLM diverges from the faithful engines it often flags a real faithful-OCR error (e.g. GOT "treagzon"→"treason"). More independent vectors → better error detection.
- **Word-level alignment:** align all engines' outputs token-by-token. Where engines **agree** (consensus) → auto-accept, `trust_level = derived`/`consensus`. Where they **disagree** → emit a **review item** (no text is committed there until a human resolves it).

## Review item (the unit of human work)
`{ page_id, token_position, word_image_crop (zoomed, in-context), candidate strings (deduped, per-engine), surrounding-text context, source provenance }`.
Only disagreements become review items — typically a small fraction of words — which is what keeps human cost low.

## The WinUI3 tool (captcha-style)
For each review item, show:
- the **cropped, zoomed word image** in its line context (so the reviewer sees exactly the printed word),
- the **candidate readings** from the engines as big clickable buttons,
- a **"none of these → type it"** field, and an **"illegible/flag"** option.
Reviewer clicks the correct reading (or types it) → next item. Fast, low-skill, no statutory knowledge required — just "match the picture."

## Quality control via multiple reviewers (decided cc002)
- Each item is reviewed by **N independent reviewers**; **inter-rater agreement** yields the accepted answer (`trust_level = human_verified`).
- Items where reviewers **disagree** escalate (a 3rd reviewer / an expert pass).
- **Per-reviewer accuracy is tracked** against gold + consensus → vet/weight reviewers, catch bad actors. This is what makes **cheap outsourced labor** (e.g. Philippines/Africa, pennies per item) trustworthy: redundancy + scoring, not blind trust.

## Data flow
production OCR (multi-engine) → align → consensus auto-accepts / disagreements → **review queue** → WinUI3 tool (multi-reviewer) → verified words → write back into the corpus as `trust_level = human_verified` with reviewer provenance → re-materialize.

## Stack + integration
- **WinUI3 / .NET** desktop app (offline-capable for outsourced reviewers; syncs the queue + results). Microsoft-aligned.
- Reads the disagreement queue + word-crops; writes verified results back to the staging DB (the event-sourced model already carries `trust_level` + provenance per `change_event`/`provision_version`).
- Reviewer-management + inter-rater scoring lives alongside.

## Sequencing
1. **Now:** small gold review by hand (text files) → ranks engines, validates the approach.
2. **Add VLM vectors** to the ensemble (qwen on the 5090, GOT) for richer disagreement detection — cheap, no new infra.
3. **Build the WinUI3 tool** once the engine is picked and the first production OCR run produces a real disagreement queue at scale.
4. **Scale human verification** via the tool (self + outsourced, multi-reviewer).

## Open questions
- Queue transport for offline/outsourced reviewers (sync protocol, batching).
- Word-crop generation (bounding boxes from which engine? docTR/Surya give boxes).
- Reviewer onboarding/scoring thresholds; consensus rule (2-of-3? weighted?).
- Whether line-level (not just word-level) review is sometimes needed (segmentation errors).
