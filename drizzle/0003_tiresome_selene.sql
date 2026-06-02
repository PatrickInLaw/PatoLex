-- ============================================================================
-- 0003 — capture-ALL-signals persistence (S1-B + full signal capture)
-- ============================================================================
-- SAFE ANYTIME. These four nullable / defaulted column adds are
-- non-blocking-safe on the live DB. `confident` is NOT NULL DEFAULT false so
-- existing rows backfill to false (honest: an unscored legacy row is not
-- asserted confident). No data rewrite, no uniqueness assumption.
--
-- Hans pass-3 C2/H1: the UNIQUE index that previously lived here (statement 5)
-- has been MOVED to migration 0004. Reason: a unique index over
-- (source_document_id, in_act_order) would FAIL on the live DB while version-A
-- duplicate rows still exist, and keeping it in the same migration as the safe
-- column adds created a half-migration hazard (0003 partially applied, wedged).
--
-- DOCUMENTED APPLY ORDER (the only valid order):
--   1. Apply 0003 (these column adds — safe anytime).
--   2. Run the clean re-ingest (ingest_clean.py --commit). Its per-volume
--      scoped purge + reinsert (C1) REPLACES version-A, eliminating duplicate
--      (source_document_id, in_act_order) pairs.
--   3. Run drizzle/dedup_precheck.sql and confirm the HAVING count(*)>1 query
--      returns ZERO rows.
--   4. Apply 0004 (the UNIQUE index). It now succeeds because step 2 made the
--      key unique and step 3 verified it.
-- ============================================================================

ALTER TABLE "change_event" ADD COLUMN "confident" boolean DEFAULT false NOT NULL;--> statement-breakpoint
ALTER TABLE "change_event" ADD COLUMN "confidence" real;--> statement-breakpoint
ALTER TABLE "change_event" ADD COLUMN "ocr_provenance" jsonb;--> statement-breakpoint
ALTER TABLE "source_document" ADD COLUMN "ocr_stats" jsonb;