/* RECONCILE pass -- procedural text-reconcile of Surya non-body flags (runs on the 5080, CPU/text).
   Claimable once shape_state='done'. Idempotent. Run against PatoLexQueue as db_owner (PatitoSync). */
USE PatoLexQueue;
GO
IF COL_LENGTH('dbo.ocr_queue','reconcile_state') IS NULL
BEGIN
    ALTER TABLE dbo.ocr_queue ADD
        reconcile_state            nvarchar(20)     NOT NULL DEFAULT 'na',
        reconcile_attempts         int              NOT NULL DEFAULT 0,
        reconcile_lease_token      uniqueidentifier NULL,
        reconcile_lease_expires_at datetime2        NULL,
        reconcile_claimed_by       nvarchar(100)    NULL,
        reconcile_heartbeat_at     datetime2        NULL,
        reconcile_done_at          datetime2        NULL,
        reconcile_error            nvarchar(max)    NULL,
        reconcile_rescued          int              NULL,   -- non-body pages rescued -> body (text said statute)
        reconcile_confirmed        int              NULL,   -- non-body confirmed (text said index)
        reconcile_ambiguous        int              NULL;   -- routed to the VLM tiebreaker
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_reconcile' AND object_id=OBJECT_ID('dbo.ocr_queue'))
    CREATE INDEX ix_reconcile ON dbo.ocr_queue(yr, id) WHERE reconcile_state='pending';
GO
-- enable the reconcile pass for every seeded volume (it gates on shape_state='done' at claim time)
UPDATE dbo.ocr_queue SET reconcile_state='pending' WHERE reconcile_state='na';
GO
