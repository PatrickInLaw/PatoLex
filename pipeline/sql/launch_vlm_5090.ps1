<# Launch the VLM tiebreaker worker on the 5090. Self-gates: waits until the shape run is finished (no shape
   pending/working) before loading the 7B, so it never contends with the shape workers for VRAM. Drains
   dbo.vlm_queue (reconcile's ambiguous pages) using the persisted render PNGs. DSN from the local file. #>
param([string]$WorkerId = "5090-vlm-0", [double]$VramFrac = 0.85)
$ErrorActionPreference = 'Stop'
$dsnFile = 'C:\Users\patolex\.patolex_queue_dsn.txt'
$env:PATOLEX_QUEUE_DSN = (Get-Content -Raw $dsnFile).Trim()
$py = 'C:\Users\patolex\PatoLex-scratch\ocr-engines\surya-venv\Scripts\python.exe'
& $py 'C:\github\PatoLex\pipeline\sql\vlm_worker_sql.py' $WorkerId `
    --render-root 'C:\Users\patolex\PatoLex-scratch\page-renders' `
    --vram-frac $VramFrac --exit-when-drained
