/* ===========================================================================
   PatoLex SQL OCR pipeline -- queue schema (Step 1, Step-2-ready)
   Target: dedicated DB on PK_XPS\SQLEXPRESS (100.113.254.6) -- the 3060 file server, co-located with SMB shares.
   Authoritative design: docs/30_SYSTEM_DESIGN/SQL_PIPELINE_DESIGN_2026-06-03.md (REVISION 2 / R2.2).

   MODEL: ONE row per volume, ONE column-group per pass (KISS -- no child/dependency table).
   Consensus-readiness is a single-row predicate, never a cross-row join.
   The Step-2 engine passes (tess/doctr/surya/consensus) are built NOW but inert ('na')
   until enabled per-row at seed -> enabling Step 2 is a config flip, not a schema change.

   Run from any box with sqlcmd access to the 3060 (operator). Idempotent: safe to re-run.
   =========================================================================== */

IF DB_ID('PatoLexQueue') IS NULL
    CREATE DATABASE PatoLexQueue;
GO
USE PatoLexQueue;
GO

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

IF OBJECT_ID('dbo.ocr_queue', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ocr_queue (
        id    bigint IDENTITY(1,1) PRIMARY KEY,
        label nvarchar(200) NOT NULL UNIQUE,
        pdf   nvarchar(500) NOT NULL,
        yr    int           NOT NULL,          -- NOT NULL: NULL sorts last and would never run

        -- ===== PASS: prep (CPU render+preprocess+classify) -- used in BOTH steps =====
        prep_state        nvarchar(20) NOT NULL DEFAULT 'pending',  -- pending|working|done|failed|held|na
        prep_attempts     int          NOT NULL DEFAULT 0,
        prep_lease_token  uniqueidentifier NULL,
        prep_lease_expires_at datetime2 NULL,
        prep_claimed_by   nvarchar(100) NULL,
        prep_heartbeat_at datetime2 NULL,
        prep_done_at      datetime2 NULL,
        prep_error        nvarchar(max) NULL,

        -- ===== PASS: ocr (STEP-1 coarse: all 3 engines + consensus inline, today's behavior) =====
        ocr_state         nvarchar(20) NOT NULL DEFAULT 'pending',
        ocr_attempts      int          NOT NULL DEFAULT 0,
        ocr_lease_token   uniqueidentifier NULL,
        ocr_lease_expires_at datetime2 NULL,
        ocr_claimed_by    nvarchar(100) NULL,
        ocr_heartbeat_at  datetime2 NULL,
        ocr_done_at       datetime2 NULL,
        ocr_error         nvarchar(max) NULL,

        -- ===== STEP-2 PASSES -- built now, inert ('na') until enabled per-row at seed =====
        -- tesseract (CPU; 5080/3060)
        tess_state        nvarchar(20) NOT NULL DEFAULT 'na',
        tess_attempts     int          NOT NULL DEFAULT 0,
        tess_lease_token  uniqueidentifier NULL,
        tess_lease_expires_at datetime2 NULL,
        tess_claimed_by   nvarchar(100) NULL,
        tess_heartbeat_at datetime2 NULL,
        tess_done_at      datetime2 NULL,
        tess_error        nvarchar(max) NULL,
        -- docTR (light GPU; 5080/3060)
        doctr_state       nvarchar(20) NOT NULL DEFAULT 'na',
        doctr_attempts    int          NOT NULL DEFAULT 0,
        doctr_lease_token uniqueidentifier NULL,
        doctr_lease_expires_at datetime2 NULL,
        doctr_claimed_by  nvarchar(100) NULL,
        doctr_heartbeat_at datetime2 NULL,
        doctr_done_at     datetime2 NULL,
        doctr_error       nvarchar(max) NULL,
        -- Surya (heavy GPU; 5090)
        surya_state       nvarchar(20) NOT NULL DEFAULT 'na',
        surya_attempts    int          NOT NULL DEFAULT 0,
        surya_lease_token uniqueidentifier NULL,
        surya_lease_expires_at datetime2 NULL,
        surya_claimed_by  nvarchar(100) NULL,
        surya_heartbeat_at datetime2 NULL,
        surya_done_at     datetime2 NULL,
        surya_error       nvarchar(max) NULL,
        -- consensus merge (reads the 3 engine outputs, produces 2-of-3 canonical text)
        consensus_state   nvarchar(20) NOT NULL DEFAULT 'na',
        consensus_attempts int         NOT NULL DEFAULT 0,
        consensus_lease_token uniqueidentifier NULL,
        consensus_lease_expires_at datetime2 NULL,
        consensus_claimed_by nvarchar(100) NULL,
        consensus_heartbeat_at datetime2 NULL,
        consensus_done_at datetime2 NULL,
        consensus_error   nvarchar(max) NULL,

        -- experimental-VLM sandbox: throw N candidate disagreement-vector models at a page
        -- WITHOUT touching the canonical row/consensus; promote a proven one to its own column-group later.
        vlm_sandbox       nvarchar(max) NULL,        -- JSON: {model: {state, result_path, ...}}

        done_at           datetime2 NULL,            -- volume fully complete (mirrors OCR_COMPLETE marker)
        updated_at        datetime2 NOT NULL DEFAULT sysutcdatetime()
    );

    -- one filtered index per claimable pass keeps each role's claim scan tiny:
    CREATE INDEX ix_prep      ON dbo.ocr_queue(yr, id) WHERE prep_state      = 'pending';
    CREATE INDEX ix_ocr       ON dbo.ocr_queue(yr, id) WHERE ocr_state       = 'pending';
    CREATE INDEX ix_tess      ON dbo.ocr_queue(yr, id) WHERE tess_state      = 'pending';
    CREATE INDEX ix_doctr     ON dbo.ocr_queue(yr, id) WHERE doctr_state     = 'pending';
    CREATE INDEX ix_surya     ON dbo.ocr_queue(yr, id) WHERE surya_state     = 'pending';
    CREATE INDEX ix_consensus ON dbo.ocr_queue(yr, id) WHERE consensus_state = 'pending';
END
GO

IF OBJECT_ID('dbo.state_history', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.state_history (
        id         bigint IDENTITY(1,1) PRIMARY KEY,
        label      nvarchar(200) NOT NULL,
        pass       nvarchar(20)  NOT NULL,          -- prep|ocr|tess|doctr|surya|consensus
        from_state nvarchar(20)  NULL,
        to_state   nvarchar(20)  NOT NULL,
        at         datetime2     NOT NULL DEFAULT sysutcdatetime(),
        by_worker  nvarchar(100) NULL,
        note       nvarchar(400) NULL
    );
    CREATE INDEX ix_state_history_label ON dbo.state_history(label, at);
END
GO
