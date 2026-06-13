<#
launch_shape_workers_5090.ps1 -- start N detached page-shape workers on the 5090. Each claims volumes from the
3060 PatoLexQueue (lease-based -> workers self-distribute, no static sharding) and runs surya_page_shapes per
volume with the hard VRAM cap. Start-Process detaches them so they survive this launcher exiting AND the 5080
session/reset (they run independently on the 5090; only a 5090 reboot would stop them).

Stacking rule: Workers * VramFrac <= ~0.80 (32GB GPU). Default 4 * 0.15 = 0.60 (measured peak well under).

Usage (run as patolex on the 5090):
  powershell -ExecutionPolicy Bypass -File launch_shape_workers_5090.ps1 -Workers 4
#>
param([int]$Workers = 4, [double]$VramFrac = 0.15, [int]$Threads = 4)
$ErrorActionPreference = 'Stop'

$py         = 'C:\Users\patolex\PatoLex-scratch\ocr-engines\surya-venv\Scripts\python.exe'
$worker     = 'C:\github\PatoLex\pipeline\sql\shape_worker_sql.py'
$dsnFile    = 'C:\Users\patolex\.patolex_queue_dsn.txt'
$archive    = 'C:\Users\patolex\PatoLex-scratch\chief-clerk-archive'
$renderRoot = 'C:\Users\patolex\PatoLex-scratch\page-renders'
$outDir     = 'C:\Users\patolex\PatoLex-scratch\page-shapes'
$logDir     = 'C:\Users\patolex\PatoLex-scratch\_cascade'

if (-not (Test-Path $dsnFile)) { throw "DSN file not found: $dsnFile" }
$env:PATOLEX_QUEUE_DSN = (Get-Content -Raw $dsnFile).Trim()
New-Item -ItemType Directory -Force $renderRoot, $outDir, $logDir | Out-Null

for ($i = 0; $i -lt $Workers; $i++) {
    $wid = "5090-shape-$i"
    $a = @($worker, $wid, '--archive', $archive, '--render-root', $renderRoot,
           '--out-dir', $outDir, '--vram-frac', $VramFrac, '--render-threads', $Threads)
    Start-Process -FilePath $py -ArgumentList $a -WindowStyle Hidden `
        -RedirectStandardOutput "$logDir\shape_worker_$i.out.log" `
        -RedirectStandardError  "$logDir\shape_worker_$i.err.log"
    Write-Output "started $wid"
    Start-Sleep -Seconds 3
}
Write-Output "launched $Workers detached shape workers (vram-frac=$VramFrac each)"
