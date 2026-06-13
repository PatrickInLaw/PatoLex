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

/* ---- CHANGE AUDIT: make dbo.ocr_queue a system-versioned TEMPORAL table -----------------
   Every UPDATE/DELETE is captured in dbo.ocr_queue_History with SysStartTime/SysEndTime, so you can ask
   "what did this row look like / when did it change" via FOR SYSTEM_TIME. (Complements dbo.state_history,
   which logs the semantic pass transitions with who+when.) NOTE: heartbeats also version rows -- expected. */
IF COL_LENGTH('dbo.ocr_queue','SysStartTime') IS NULL
BEGIN
    ALTER TABLE dbo.ocr_queue ADD
        SysStartTime datetime2(7) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL
            CONSTRAINT DF_ocrq_SysStart DEFAULT sysutcdatetime(),
        SysEndTime   datetime2(7) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL
            CONSTRAINT DF_ocrq_SysEnd   DEFAULT CONVERT(datetime2(7), '9999-12-31 23:59:59.9999999'),
        PERIOD FOR SYSTEM_TIME (SysStartTime, SysEndTime);
END
GO
IF OBJECTPROPERTY(OBJECT_ID('dbo.ocr_queue'),'TableTemporalType') = 0
    ALTER TABLE dbo.ocr_queue SET (SYSTEM_VERSIONING = ON (HISTORY_TABLE = dbo.ocr_queue_History));
GO

/* ---- authoritative source manifest (record of truth), system-versioned from creation ---- */
IF OBJECT_ID('dbo.volume_manifest','U') IS NULL
BEGIN
    CREATE TABLE dbo.volume_manifest (
        label       nvarchar(200) NOT NULL PRIMARY KEY,
        pdf         nvarchar(500) NOT NULL,
        yr          int           NOT NULL,
        sha256      char(64)      NULL,
        page_count  int           NULL,
        source      nvarchar(20)  NOT NULL,                                   -- explicit | derived | matched
        note        nvarchar(400) NULL,                                       -- provenance / ambiguous flag
        corpus      nvarchar(60)  NOT NULL DEFAULT 'patolex-historical',
        created_at  datetime2     NOT NULL DEFAULT sysutcdatetime(),
        SysStartTime datetime2(7) GENERATED ALWAYS AS ROW START NOT NULL,
        SysEndTime   datetime2(7) GENERATED ALWAYS AS ROW END   NOT NULL,
        PERIOD FOR SYSTEM_TIME (SysStartTime, SysEndTime)
    ) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = dbo.volume_manifest_History));
END
GO
