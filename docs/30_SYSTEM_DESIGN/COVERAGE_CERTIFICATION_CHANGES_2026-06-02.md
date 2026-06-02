# Required pipeline + schema changes for Completeness Certification

**Date:** 2026-06-02 · **Status:** PROPOSED (pre-Hans) · Companion to `COVERAGE_CERTIFICATION.md`.

Grounded in the actual code (`src/lib/db/schema/*.ts`, `pipeline/`), not from memory.

---

## Current state (verified)

- **`change_event.provision_id` is `NOT NULL`** (FK → provision.id) — `change-event.ts:77-79`. **Consequence: the model literally cannot record an amendment whose target provision is not already in the corpus.** A dangling reference — the single most important gap signal — has nowhere to live today.
- **`change_action` enum exists** (`enact|amend|repeal|add|renumber|recodify|reserve`) — `enums.ts:34-42`. Action classification is modeled. ✓
- **No structured capture of the CLAIMED target** — the resolved `provision_id` is the *only* link to what an act changed. There is no field for "this amends §187 of the Penal Code, as printed," independent of resolution.
- **`lineage_edge`** provides resolution-through-recodification (renumber/transfer/split/merge/repeal_reenact) — `lineage-edge.ts`. The mechanism to resolve a reference to a *provision identity* across renumbers exists. ✓
- **Parser** (`ingest_from_ocr.py` STAGE5; the code-amendment path in `CODE_AMENDMENT_PARSE_DESIGN`) extracts chapter/date/title/text but does **not** emit a structured target reference and does **not** classify the action verb.

## Schema changes (new migration 0005)

1. **Make dangling references first-class on `change_event`:**
   - `provision_id` → **NULLABLE** (was NOT NULL). An unresolved amendment becomes a real, captured event with a null `provision_id` until resolved.
   - ADD `target_code` — the named target code (Civil/Penal/CCP/Political/Government/… or `uncodified`).
   - ADD `target_designation_raw` (text) — the section as printed/parsed ("751", "seven hundred and fifty-one") — faithful.
   - ADD `target_designation_normalized` (text) — canonical/numeric form for matching.
   - ADD `target_resolution_status` (new enum, below).
   - ADD CHECK: `provision_id IS NOT NULL` when status = `resolved`; null permitted when `unresolved|deferred|ambiguous`.
2. **New enum `reference_resolution_status`** = `resolved | unresolved | deferred | ambiguous`.
3. **Granularity:** the existing one-`change_event`-per-(enactment, provision) shape already models "act amends §751 and §756" as two events. Extend `change_event` (Option A) rather than add a separate reference table. *(Hans: confirm this holds for the unresolved case — two unresolved targets in one act become two change_events with null provision_id, distinguished by `in_act_order`.)*

## Pipeline changes

4. **Parser — emit structured targets + action.** Per directive: extract (a) target code (act title "of the Political Code" / anaphoric "of said Code"), (b) target section designation (spelled-out + printed numeral, cross-checked), (c) classify the action verb ("is hereby amended"→`amend`, "is hereby repealed"→`repeal`, "is added"→`add`, else `enact`). Applies to the Code-amendment volumes **and** to general-statute acts that amend codes.
5. **Ingest (`ingest_clean.py`) — write + resolve.** Write `target_code/target_designation_raw/normalized/action/status` into `change_event`. Run a resolution pass: look up the target provision by (code, designation) **as of `operative_date`** via `designation_history` + `lineage_edge` → set `provision_id` + status=`resolved`; else `unresolved`/`deferred`. (Each amendment volume ingests as its own `source_document`, already designed.)
6. **Unresolved-reference validator (new module).** Emits: (a) **dangling references** (status `unresolved` after the resolution pass); (b) **origination gaps** (code_section provisions with no `action='enact'` event); (c) at the anchor — **missing amendments** (authoritative §X@date with no matching event).
7. **Endgame reconciliation (new).** Load the leginfo current code + per-section legislative history as the authoritative anchor; run the global checksum (forward reconstruction must equal the current code, section for section); residuals localize gaps.

## Sequencing

- Schema + parser/ingest **capture** changes (1–5) should land **first** so data accrues correctly from now on — capture is cheap and must not wait for resolution/reconstruction.
- Validator (6) runs incrementally as ranges load, then globally at the anchor (7).
- Per existing discipline: **ingest stays frozen** until the parser changes are built + Hans-reviewed + a fresh DB backup is taken. Migration 0005 applies during that window.

## Open questions for review

- Does extending `change_event` (vs a separate `amendment_reference` table) hold up when an act references a target that is *also* unresolved at parse time but resolvable later (deferred)? Re-resolution cadence?
- `target_code` as a free-text vs an enum — codes are a closed-ish set but evolve (Family Code 1992); lean text + a controlled vocabulary.
- How does resolution interact with the not-yet-loaded 1872 baseline (every pre-baseline amendment is `deferred` until the baseline exists)?
- Repeal/`add` directives and multi-section "amend and also to repeal" acts (seen in 1875-76-code p.22) — confirm action classification covers them.
