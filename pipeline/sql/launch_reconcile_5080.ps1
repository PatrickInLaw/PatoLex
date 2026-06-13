<# Launch the page-shape RECONCILE worker on the 5080 (CPU/text). Builds PATOLEX_QUEUE_DSN from the WCM
   PatitoSync secret, then runs the worker which claims shape-done volumes, pulls each shape TSV live from the
   5090, and procedurally reconciles non-body flags against the local out_context text. CPU-only, no GPU. #>
param([string]$WorkerId = "5080-reconcile-0")
$ErrorActionPreference = 'Stop'
. "$env:USERPROFILE\.claude\scripts\CredStore.ps1"
$pw = Get-CredSecret -Target PatitoSql_PatitoQBCache_PatitoSync
$env:PATOLEX_QUEUE_DSN = "Driver={ODBC Driver 18 for SQL Server};Server=100.113.254.6\SQLEXPRESS;Database=PatoLexQueue;UID=PatitoSync;PWD={$pw};Encrypt=yes;TrustServerCertificate=yes"
$py   = "C:\Users\PatrickKolasinski\AppData\Local\Programs\Python\Python312\python.exe"
$base = "C:\Users\PatrickKolasinski\PatoLex-scratch\_cascade"
New-Item -ItemType Directory -Force "$base\reconciled" | Out-Null
& $py "C:\Users\PatrickKolasinski\Documents\GitHub\patolex\pipeline\sql\reconcile_worker_sql.py" $WorkerId `
    --key "C:\Users\PatrickKolasinski\.ssh\patolex_5090" `
    --out-context "$base\out_context" `
    --reconciled-dir "$base\reconciled" `
    --ambiguous "$base\vlm_worklist.tsv"
