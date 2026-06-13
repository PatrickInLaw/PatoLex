/* VLM tiebreaker -- PAGE-level worklist. The reconcile pass routes only its AMBIGUOUS pages here; the local
   7B VLM on the 5090 drains them and records a per-page verdict. Idempotent. db_owner (PatitoSync). */
USE PatoLexQueue;
GO
IF OBJECT_ID('dbo.vlm_queue','U') IS NULL
BEGIN
    CREATE TABLE dbo.vlm_queue (
        id           bigint IDENTITY(1,1) PRIMARY KEY,
        label        nvarchar(200) NOT NULL,
        pdf          nvarchar(500) NOT NULL,
        pidx         int           NOT NULL,
        surya_class  nvarchar(30)  NULL,
        surya_conf   float         NULL,
        state        nvarchar(20)  NOT NULL DEFAULT 'pending',   -- pending|working|done|failed
        verdict      nvarchar(20)  NULL,                         -- BODY|ROSTER|INDEX_TOC|REPRINT|OTHER
        attempts     int           NOT NULL DEFAULT 0,
        lease_token  uniqueidentifier NULL,
        lease_expires_at datetime2 NULL,
        claimed_by   nvarchar(100) NULL,
        heartbeat_at datetime2     NULL,
        done_at      datetime2     NULL,
        error        nvarchar(400) NULL,
        CONSTRAINT uq_vlm UNIQUE(label, pidx)
    );
    CREATE INDEX ix_vlm_pending ON dbo.vlm_queue(id) WHERE state='pending';
END
GO
