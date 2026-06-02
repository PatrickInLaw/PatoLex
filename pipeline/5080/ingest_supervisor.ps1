# ingest_supervisor.ps1 -- long-lived ingest supervisor for the 5080.
# ====================================================================
# Designed to run as the ACTION of a Scheduled Task (principal: SYSTEM,
# RunLevel Highest), mirroring the 5090's PatoLex_OCR_5090 task. This script
# BLOCKS on the ingest_watcher.py child for the whole campaign, so the watcher
# is owned by the Task Scheduler service (svchost) and is fully independent of
# any SSH / interactive / Claude session -- it survives logoff and process death.
#
# It (re)launches ingest_watcher.py and waits on it. If the watcher exits for
# any reason while work may remain, it relaunches (bounded backoff) so a
# transient crash (e.g. a flaky SSH poll) does not strand the DB fill.

$ErrorActionPreference = 'Continue'
$scratch = 'C:\Users\PatrickKolasinski\PatoLex-scratch'
$py      = 'C:\Users\PatrickKolasinski\AppData\Local\Programs\Python\Python312\python.exe'
$script  = Join-Path $scratch 'ingest_watcher.py'
$suplog  = Join-Path $scratch 'ingest_supervisor.log'
$stop    = Join-Path $scratch 'STOP_INGEST.flag'

function Sup($m) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $suplog -Value ("[$ts] $m") -Encoding utf8
}

Sup "=== ingest supervisor online (pid $PID) ==="

while ($true) {
    if (Test-Path $stop) { Sup 'STOP_INGEST.flag present -- supervisor exiting'; break }

    $out = Join-Path $scratch 'ingest_watcher.out.log'
    $err = Join-Path $scratch 'ingest_watcher.err.log'
    $p = Start-Process -FilePath $py -ArgumentList @($script) `
        -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    Sup "launched ingest_watcher pid $($p.Id)"
    $p.Id | Set-Content -Path (Join-Path $scratch 'ingest_watcher_pid.txt') -Encoding ascii

    $p.WaitForExit()
    Sup "ingest_watcher pid $($p.Id) exited (code $($p.ExitCode))"

    if (Test-Path $stop) { Sup 'STOP flag set after exit -- not relaunching'; break }
    Start-Sleep -Seconds 15
    Sup 'relaunching ingest_watcher after 15s backoff'
}
Sup '=== ingest supervisor done ==='
