# Hans Adversarial Audit — Pass 3 (EXTRA thorough, end-to-end canonical re-ingest, 2026-06-02)

Patrick ordered an extra-thorough pass on the WHOLE path that produces the canonical 1850-1875 corpus (not modules in isolation). It caught a system-of-record catastrophe passes 1-2 could not see. **VERDICT: NO-GO** on running `ingest_clean.py --commit` until items 1-5 land.

## CRITICAL
- **C1 — the re-ingest is a silent no-op (worst case).** `ingest_clean.py:786-838` `commit_volume` is INSERT-only with skip-on-existing (`EXISTS_SQL` → skip; `ON CONFLICT DO NOTHING`). It **never purges version-A**. On the live DB, every existing act is SKIPPED → the consensus text is **silently discarded**, version-A's single-engine/lossy/fabricated-date rows STAY, and it **logs success**. The old `ingest_from_ocr.py:366-381` had the scoped purge (provision_version, designation_history, change_event, orphan provision, enactment); the rewrite deleted it. FIX: add that scoped per-source_document purge INSIDE the volume transaction, BEFORE inserts; remove the skip-on-existing.
- **C2 — apply-order circular dependency.** `ON CONFLICT (source_document_id, in_act_order)` (`ingest_clean.py:540`) requires the unique index to EXIST, but migration `0003` header says create it AFTER re-ingest. No order satisfies both → crash or wedged. FIX: dup-purge → create index → then --commit.
- **C3 — resolver lands on the stale 1850 dup.** `_resolve_source_document_id` (`:747-760`) uses `citation LIKE ... ORDER BY id LIMIT 1` → picks the LOWEST id = the stale 1850 `source_document` id=1 (26 rows) → split-brain 1850 corpus. Old path resolved by `content_sha256`. FIX: resolve by sha256, FAIL on ambiguity, explicitly handle/purge the stale id=1.
- **C4 — `in_act_order` is not a stable identity across the version-A→B parse change** (moot once C1 purge lands; drop the "cross-version-stable key" doc claim).
- **C5 — no real dup-purge step** (it's a comment) → the unique index (statement 5) will FAIL on version-A dups → half-migrated schema. FIX: an actual idempotent dup-purge that drives the HAVING-count>1 query to zero before the index is created.

## HIGH
- **H1** — half-migrated state reachable + unguarded (0003 not transactional around the index; `change-event.ts` declares the index as present while the DB may lack it). FIX: split the index into 0004, applied post-purge; keep schema/migration consistent.
- **H2** — `consensus_output.json` is banked BEFORE the DB txn; a rolled-back volume leaves an orphan file with no DB anchor (dangling `ocr_stats.consensus_output_path`).
- **H3** — per-act `confidence` = the single source-page proxy; multi-page acts understate uncertainty. FIX: aggregate confidence + low-conf tokens across ALL pages an act spans (or document the limitation).

## MEDIUM (consensus.py post-spine-fix — mostly sound)
- Spine median-fix + merge-pass verified correct, deterministic, faithful-surface (committed token always from a real engine); S1-A genuinely fixed (test proves it).
- **M2** — no test asserts `capture_candidates=True` (the path production runs) yields byte-identical committed_text to False. Add it.
- **M3** — `single`-engine path stamps `confidence=1.0` for every token (dishonest — zero corroboration). FIX: emit an honest low value, never 1.0.

## VERIFIED CORRECT
Parameterized UTF-8 inserts (F5 — §/long-s/em-dash survive); operative_date NULL-not-fabricated (F13); ocr_cer_estimate NULL-not-(-1.0); whole-volume transaction rollback mechanism (F6/S2-B) — though moot until C1 adds something destructive to roll back.

## ORDERED FIX LIST (all before any --commit; re-run Hans pass 4 after 1-5)
1. **C1** scoped per-source_document purge inside the txn before inserts; remove skip-on-existing.
2. **C3** resolve by content_sha256 + fail on ambiguity + handle stale 1850 id=1.
3. **C5** real idempotent dup-purge → HAVING-count>1 == 0 before the index.
4. **C2/H1** apply order: dup-purge → unique index (own migration 0004, transactional) → --commit; make schema/migration consistent.
5. **C4** drop the cross-version-stable-key doc claim (resolved by C1).
6. **M3** honest single-engine confidence (not 1.0).
7. **H3** aggregate per-act confidence across all spanned pages (or document).
8. **M2** capture_candidates byte-identical regression test.
9. **H2** decide/doc consensus_output banking order vs the txn.

Banked OCR + version-A DB are intact; this is an offline code+migration fix, no re-OCR. version-A (single-engine) stays as the A/B baseline until the fixed re-ingest produces version-B.
