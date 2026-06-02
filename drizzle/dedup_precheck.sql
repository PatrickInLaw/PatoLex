-- ============================================================================
-- dedup_precheck.sql — Hans pass-3 C5: REAL idempotent duplicate-purge check
-- ============================================================================
-- Purpose: BEFORE creating the UNIQUE index in migration 0004, prove that no
-- change_event rows share a (source_document_id, in_act_order) pair. The clean
-- re-ingest (ingest_clean.py --commit) already purges + reinserts per volume
-- (Hans C1), so after a full re-ingest this MUST report zero duplicates. This
-- script verifies that invariant. It is READ-ONLY by default and SAFE TO RUN
-- REPEATEDLY — running it changes nothing.
--
-- USAGE (psql):
--   psql "$PATOLEX_PG_DSN" -v ON_ERROR_STOP=1 -f drizzle/dedup_precheck.sql
--
-- INTERPRETATION:
--   * "duplicate_pairs" report empty  -> 0004 is safe to apply.
--   * any rows                        -> DO NOT apply 0004. Finish/redo the
--                                        re-ingest for the listed source_documents
--                                        (their per-volume purge eliminates dups),
--                                        then re-run this check.
--
-- This script makes NO writes. The DELETE-based purge of version-A duplicates is
-- performed exclusively by ingest_clean.commit_volume's per-volume scoped purge
-- (the system-of-record path), NOT here — so there is exactly one purge
-- implementation to audit. (See the OPTIONAL emergency block at the bottom,
-- left commented, for a manual last-resort purge of the stale 1850 id=1
-- skeleton only.)
-- ============================================================================

\echo '== (a) duplicate (source_document_id, in_act_order) pairs in change_event =='
SELECT source_document_id,
       in_act_order,
       count(*) AS n
FROM change_event
GROUP BY source_document_id, in_act_order
HAVING count(*) > 1
ORDER BY source_document_id, in_act_order;

\echo '== (b) ASSERTION: total number of duplicate pairs (MUST be 0 before 0004) =='
SELECT count(*) AS duplicate_pair_count
FROM (
  SELECT source_document_id, in_act_order
  FROM change_event
  GROUP BY source_document_id, in_act_order
  HAVING count(*) > 1
) d;

-- Hard gate: raise (and abort under ON_ERROR_STOP=1) if any duplicate remains,
-- so this file can be used as a precondition in an automated runbook step.
DO $$
DECLARE
  dup_count integer;
BEGIN
  SELECT count(*) INTO dup_count
  FROM (
    SELECT source_document_id, in_act_order
    FROM change_event
    GROUP BY source_document_id, in_act_order
    HAVING count(*) > 1
  ) d;
  IF dup_count > 0 THEN
    RAISE EXCEPTION
      'dedup_precheck FAILED: % duplicate (source_document_id, in_act_order) pair(s) remain. Do NOT apply 0004 — re-run the clean re-ingest first.',
      dup_count;
  END IF;
  RAISE NOTICE 'dedup_precheck OK: zero duplicate pairs — migration 0004 is safe to apply.';
END $$;

\echo '== (c) stale 1850 skeleton source_document id=1 detector (informational) =='
-- The known stale duplicate (Hans C3). If this returns a row, the 1850 re-ingest
-- will REFUSE to run (the resolver guards against id=1). Purge id=1 manually
-- (see the OPTIONAL block below) before re-ingesting 1850.
SELECT id, citation, content_sha256, page_count
FROM source_document
WHERE id = 1 AND citation LIKE 'CA Statutes 1850%';

-- ============================================================================
-- OPTIONAL — MANUAL emergency purge of the stale 1850 id=1 skeleton ONLY.
-- Left COMMENTED. Run by hand, reviewed, ONLY if (c) above returns id=1 and you
-- have confirmed the real 1850 production source_document exists under a
-- different id (resolved by content_sha256). This removes the 26 skeleton rows
-- so the 1850 re-ingest can proceed. It is scoped strictly to id=1.
-- ----------------------------------------------------------------------------
-- BEGIN;
--   DELETE FROM provision_version
--    WHERE source_document_id = 1
--       OR source_change_event_id IN (SELECT id FROM change_event WHERE source_document_id = 1);
--   DELETE FROM designation_history dh USING provision p, change_event ce
--    WHERE dh.provision_id = p.id AND ce.provision_id = p.id AND ce.source_document_id = 1;
--   DELETE FROM change_event WHERE source_document_id = 1;
--   DELETE FROM provision p
--    WHERE p.jurisdiction = 'CA' AND p.unit_type = 'act_section'
--      AND p.current_designation LIKE 'Stats. 1850 %'
--      AND NOT EXISTS (SELECT 1 FROM change_event ce WHERE ce.provision_id = p.id)
--      AND NOT EXISTS (SELECT 1 FROM designation_history dh WHERE dh.provision_id = p.id);
--   DELETE FROM enactment WHERE source_document_id = 1;
--   DELETE FROM source_document WHERE id = 1 AND citation LIKE 'CA Statutes 1850%';
-- COMMIT;
-- ============================================================================
