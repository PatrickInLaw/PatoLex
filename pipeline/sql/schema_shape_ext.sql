/* ===========================================================================
   PatoLex queue -- SHAPE-pass extension + authoritative volume_manifest.
   Adds the page-shape classification pass (Surya layout) as a first-class pass on dbo.ocr_queue,
   mirroring the existing pass column-group convention (lease/heartbeat/fence), plus a durable
   dbo.volume_manifest = the authoritative source-of-truth list of which PDF is each volume.

   Idempotent. Run against PatoLexQueue as a db_owner (PatitoSync).
   =========================================================================== */
USE PatoLexQueue;
GO
SET QUOTED_IDENTIFIER ON; SET ANSI_NULLS ON;
GO

/* ---- SHAPE pass columns on dbo.ocr_queue (one ALTER; table is empty so DEFAULTs are free) ---- */
IF COL_LENGTH('dbo.ocr_queue','shape_state') IS NULL
BEGIN
    ALTER TABLE dbo.ocr_queue ADD
        shape_state            nvarchar(20)     NOT NULL DEFAULT 'na',
        shape_attempts         int              NOT NULL DEFAULT 0,
        shape_lease_token      uniqueidentifier NULL,
        shape_lease_expires_at datetime2        NULL,
        shape_claimed_by       nvarchar(100)    NULL,
        shape_heartbeat_at     datetime2        NULL,
        shape_done_at          datetime2        NULL,
        shape_error            nvarchar(max)    NULL,
        shape_pages            int              NULL,   -- result: pages classified
        shape_summary          nvarchar(400)    NULL;   -- result: coarse-class histogram
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_shape' AND object_id=OBJECT_ID('dbo.ocr_queue'))
    CREATE INDEX ix_shape ON dbo.ocr_queue(yr, id) WHERE shape_state='pending';
GO

/* ---- authoritative source manifest (the "which PDF is each volume" record of truth) ---- */
IF OBJECT_ID('dbo.volume_manifest','U') IS NULL
BEGIN
    CREATE TABLE dbo.volume_manifest (
        label       nvarchar(200) NOT NULL PRIMARY KEY,
        pdf         nvarchar(500) NOT NULL,
        yr          int           NOT NULL,
        sha256      char(64)      NULL,
        page_count  int           NULL,
        source      nvarchar(20)  NOT NULL,                                   -- explicit | derived
        note        nvarchar(400) NULL,                                       -- provenance / ambiguous flag
        corpus      nvarchar(60)  NOT NULL DEFAULT 'patolex-historical',
        created_at  datetime2     NOT NULL DEFAULT sysutcdatetime()
    );
END
GO
