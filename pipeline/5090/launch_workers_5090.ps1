param(
    [int]$Count = 3
)
# launch_workers_5090.ps1 -- spawn N DETACHED queue workers on the 5090.
# Each worker runs queue_worker.py under the surya-venv python, hidden, with
# its own stdout/stderr log. Start-Process without -Wait returns immediately,
# so the workers are NOT children of the SSH session's process tree and
# survive SSH disconnect + Claude session close.

$ErrorActionPreference = 'Stop'
$scratch = 'C:\Users\patolex\PatoLex-scratch'
$py      = 'C:\Users\patolex\PatoLex-scratch\ocr-engines\surya-venv\Scripts\python.exe'
$script  = Join-Path $scratch 'queue_worker.py'

$pids = @()
for ($i = 1; $i -le $Count; $i++) {
    $out = Join-Path $scratch ("worker{0}.out.log" -f $i)
    $err = Join-Path $scratch ("worker{0}.err.log" -f $i)
    $p = Start-Process -FilePath $py `
        -ArgumentList @($script, ("5090-$i")) `
        -WindowStyle Hidden `
        -RedirectStandardOutput $out `
        -RedirectStandardError  $err `
        -PassThru
    $pids += $p.Id
    Write-Output ("launched worker 5090-{0} pid {1} -> {2}" -f $i, $p.Id, $out)
    Start-Sleep -Seconds 2
}
$pids -join ',' | Set-Content -Path (Join-Path $scratch 'worker_pids.txt') -Encoding ascii
Write-Output ("PIDS: " + ($pids -join ','))
