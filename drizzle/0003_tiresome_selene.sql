-- ============================================================================
-- 0003 — capture-ALL-signals persistence (S1-B + S2-A + full signal capture)
-- ============================================================================
-- APPLY ORDER (READ BEFORE APPLYING — version-A ingest data may exist):
--
--   SAFE ANYTIME (statements 1-4 below): the four nullable / defaulted column
--   adds are non-blocking-safe on the live DB. `confident` is NOT NULL DEFAULT
--   false so existing rows backfill to false (honest: an unscored legacy row is
--   not asserted confident). No data rewrite, no uniqueness assumption.
--
--   NOT SAFE UNTIL CLEAN RE-INGEST (statement 5 — the UNIQUE index): existing
--   version-A change_event rows MAY contain duplicate (source_document_id,
--   in_act_order) pairs, which would make this CREATE UNIQUE INDEX FAIL. Apply
--   statement 5 ONLY AFTER the clean re-ingest purges per source_document (so
--   the canonical key is unique), OR after verifying no dups, e.g.:
--     SELECT source_document_id, in_act_order, count(*)
--     FROM change_event GROUP BY 1,2 HAVING count(*) > 1;
--   If that returns zero rows, statement 5 is safe to run as-is.
-- ============================================================================

ALTER TABLE "change_event" ADD COLUMN "confident" boolean DEFAULT false NOT NULL;--> statement-breakpoint
ALTER TABLE "change_event" ADD COLUMN "confidence" real;--> statement-breakpoint
ALTER TABLE "change_event" ADD COLUMN "ocr_provenance" jsonb;--> statement-breakpoint
ALTER TABLE "source_document" ADD COLUMN "ocr_stats" jsonb;--> statement-breakpoint
-- ↑ statements 1-4: SAFE ANYTIME.  ↓ statement 5: APPLY ONLY AFTER CLEAN RE-INGEST / dup-check (see header).
CREATE UNIQUE INDEX "uq_change_event_src_doc_in_act_order" ON "change_event" USING btree ("source_document_id","in_act_order");