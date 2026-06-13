<# Feed dbo.vlm_queue from reconcile's growing ambiguous worklist (5080). --watch re-loads every 60s until the
   reconcile pass is finished, then does a final sweep. DSN from the WCM PatitoSync secret. #>
$ErrorActionPreference = 'Stop'
. "$env:USERPROFILE\.claude\scripts\CredStore.ps1"
$pw = Get-CredSecret -Target PatitoSql_PatitoQBCache_PatitoSync
$env:PATOLEX_QUEUE_DSN = "Driver={ODBC Driver 18 for SQL Server};Server=100.113.254.6\SQLEXPRESS;Database=PatoLexQueue;UID=PatitoSync;PWD={$pw};Encrypt=yes;TrustServerCertificate=yes"
$py = "C:\Users\PatrickKolasinski\AppData\Local\Programs\Python\Python312\python.exe"
& $py "C:\Users\PatrickKolasinski\Documents\GitHub\patolex\pipeline\sql\load_vlm_queue.py" `
    "C:\Users\PatrickKolasinski\PatoLex-scratch\_cascade\vlm_worklist.tsv" --watch
