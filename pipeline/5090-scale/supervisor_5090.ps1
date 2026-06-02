param(
    [int]$Count = 3
)
# supervisor_5090.ps1 -- long-lived worker supervisor for the 5090.
# Designed to run as the ACTION of a Scheduled Task (principal: patolex, stored
# creds, RunLevel Highest). The task stays "Running" for the whole OCR campaign
# because this script BLOCKS on the workers, so the workers are owned by the
# Task Scheduler service -- fully independent of any SSH/interactive session.
#
# It launches up to MAX_WORKERS queue_worker.py children, waits on them, and
# relaunches a dead worker if the queue still has claimable volumes (bounded
# restarts) so a transient crash does not strand the campaign.
#
# --- DYNAMIC WORKER COUNT (cc003 scale-to-1 support) ---
# The effective worker count is read from max_workers.txt EACH loop iteration
# (falls back to -Count if the file is absent/invalid). This makes the desired
# worker count tunable at runtime without restarting the supervisor:
#   * If max_workers DROPS, the supervisor stops RELAUNCHING surplus slots and
#     lets already-running workers finish their current volume and exit (drain)
#     -- it never kills an in-flight volume.
#   * The supervisor never runs MORE than max_workers concurrent workers.
# A STOP_WORKER.flag file makes the supervisor refuse to (re)launch any worker
# (used for a full pause/drain). queue_worker.py also checks this flag between
# volumes and exits gracefully.

$ErrorActionPreference = 'Continue'
$scratch  = 'C:\Users\patolex\PatoLex-scratch'
$py       = 'C:\Users\patolex\PatoLex-scratch\ocr-engines\surya-venv\Scripts\python.exe'
$script   = Join-Path $scratch 'queue_worker.py'
$suplog   = Join-Path $scratch 'supervisor.log'
$cfgFile  = Join-Path $scratch 'max_workers.txt'
$stopFlag = Join-Path $scratch 'STOP_WORKER.flag'
$queue    = Join-Path $scratch 'production_queue_state.json'

function Sup($m) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $suplog -Value ("[$ts] $m") -Encoding utf8
}

function Get-MaxWorkers([int]$fallback) {
    if (Test-Path $cfgFile) {
        try {
            $raw = (Get-Content $cfgFile -Raw).Trim()
            $n = 0
            if ([int]::TryParse($raw, [ref]$n) -and $n -ge 0) { return $n }
        } catch { }
    }
    return $fallback
}

function Remaining-Claimable {
    try {
        $qjson = Get-Content $queue -Raw | ConvertFrom-Json
        return @($qjson.volumes | Where-Object { $_.status -ne 'done' -and $_.status -ne 'held' }).Count
    } catch {
        return 1   # be conservative: assume work remains on transient read error
    }
}

$desired = Get-MaxWorkers $Count
Sup "=== supervisor online (pid $PID) requested Count=$Count effective max_workers=$desired ==="

function Start-Worker([int]$slot) {
    $out = Join-Path $scratch ("worker{0}.out.log" -f $slot)
    $err = Join-Path $scratch ("worker{0}.err.log" -f $slot)
    $p = Start-Process -FilePath $py -ArgumentList @($script, ("5090-$slot")) `
        -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    Sup ("launched worker 5090-$slot pid $($p.Id)")
    return @{ Proc = $p; Restarts = 0; Out = $out; Err = $err; Slot = $slot }
}

$procs = @{}
$initial = Get-MaxWorkers $Count
for ($i = 1; $i -le $initial; $i++) {
    if (Test-Path $stopFlag) { Sup "STOP_WORKER.flag present at startup -- not launching slot $i"; break }
    $procs[$i] = Start-Worker $i
    Start-Sleep -Seconds 3
}
($procs.Values | ForEach-Object { $_.Proc.Id }) -join ',' |
    Set-Content -Path (Join-Path $scratch 'worker_pids.txt') -Encoding ascii

$MAX_RESTARTS = 3

while ($true) {
    Start-Sleep -Seconds 30
    $maxw = Get-MaxWorkers $Count

    # current live count
    $alive = @($procs.Values | Where-Object { -not $_.Proc.HasExited }).Count

    foreach ($i in @($procs.Keys)) {
        $w = $procs[$i]
        if (-not $w.Proc.HasExited) { continue }

        # this slot's worker exited.
        if (Test-Path $stopFlag) {
            Sup ("worker 5090-$i exited; STOP flag set -- not relaunching")
            continue
        }
        # never exceed max_workers: if we already have >= maxw alive, this slot drains.
        $aliveNow = @($procs.Values | Where-Object { -not $_.Proc.HasExited }).Count
        if ($aliveNow -ge $maxw) {
            Sup ("worker 5090-$i exited; alive=$aliveNow >= max_workers=$maxw -- draining (no relaunch)")
            continue
        }
        $remaining = Remaining-Claimable
        if ($remaining -eq 0) {
            Sup ("worker 5090-$i exited; queue drained ($remaining claimable)")
            continue
        }
        if ($w.Restarts -ge $MAX_RESTARTS) {
            Sup ("worker 5090-$i exited; $remaining claimable but restart cap hit")
            continue
        }
        $nw = Start-Worker $i
        $nw.Restarts = $w.Restarts + 1
        $procs[$i] = $nw
        Sup ("RELAUNCHED worker 5090-$i pid $($nw.Proc.Id) (restart $($nw.Restarts), $remaining claimable, max_workers=$maxw)")
    }

    $anyAlive = @($procs.Values | Where-Object { -not $_.Proc.HasExited }).Count -gt 0
    if (-not $anyAlive) {
        # If max_workers>0, the queue still has claimable work, and no stop flag,
        # bring slots back up to max_workers (covers a full drain that should not
        # be terminal). Otherwise the campaign is done / paused.
        $maxw = Get-MaxWorkers $Count
        if (-not (Test-Path $stopFlag) -and $maxw -gt 0 -and (Remaining-Claimable) -gt 0) {
            Sup ("all workers exited but max_workers=$maxw and work remains -- relaunching $maxw slot(s)")
            for ($i = 1; $i -le $maxw; $i++) {
                $procs[$i] = Start-Worker $i
                Start-Sleep -Seconds 3
            }
            ($procs.Values | ForEach-Object { $_.Proc.Id }) -join ',' |
                Set-Content -Path (Join-Path $scratch 'worker_pids.txt') -Encoding ascii
            continue
        }
        Sup "=== all workers exited and no relaunch needed -- supervisor done ==="
        break
    }
}
