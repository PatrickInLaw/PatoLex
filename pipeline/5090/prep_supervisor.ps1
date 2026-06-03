param(
    [int]$Count = 2
)
# prep_supervisor.ps1 -- low-priority PREP-ahead worker supervisor for the 5090.
# Sibling of supervisor_5090.ps1 (which manages the GPU OCR pool). This one runs
# the CPU-bound prep stage (render + preprocess + classify) AHEAD of OCR, filling
# a buffer of 'prepped' volumes so the OCR workers never wait on prep.
#
# Distinct from the OCR supervisor so they never collide:
#   * worker-id prefix  5090p-   (OCR uses 5090-)
#   * config file       max_prep_workers.txt
#   * seq / pid files   prep_worker_seq.txt / prep_worker_pids.txt
#   * per-worker drain  STOP_WORKER_5090p-<id>.flag (sweep namespaced to 5090p-)
# Prep workers launch at BelowNormal priority (their queue_worker + child
# ocr_only inherit it on Windows) so prep yields CPU to OCR's Tesseract.
# The GLOBAL STOP_WORKER.flag still drains prep workers too (worker honors it).
# Scaling/drain/crash logic mirrors the OCR supervisor (already hardened).

$ErrorActionPreference = 'Continue'
$scratch  = 'C:\Users\patolex\PatoLex-scratch'
$py       = 'C:\Users\patolex\PatoLex-scratch\ocr-engines\surya-venv\Scripts\python.exe'
$script   = Join-Path $scratch 'queue_worker.py'
$suplog   = Join-Path $scratch 'prep_supervisor.log'
$cfgFile  = Join-Path $scratch 'max_prep_workers.txt'
$stopFlag = Join-Path $scratch 'STOP_WORKER.flag'
$queue    = Join-Path $scratch 'production_queue_state.json'
$seqFile  = Join-Path $scratch 'prep_worker_seq.txt'
$pidFile  = Join-Path $scratch 'prep_worker_pids.txt'

$STAGGER_SECONDS = 20    # prep loads no GPU models -> short stagger is fine
$LOOP_SECONDS    = 30
$CRASH_WINDOW    = 300
$CRASH_CAP       = 6

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

function Remaining-PrepWork {
    # Is there any prep-relevant work left (pending or in-flight prepping)?
    # Keeps the supervisor alive while OCR drains the buffer even if prep is
    # momentarily caught up. Returns a count; 0 => prep campaign complete.
    try {
        $qjson = Get-Content $queue -Raw | ConvertFrom-Json
        return @($qjson.volumes | Where-Object { $_.status -eq 'pending' -or $_.status -eq 'prepping' }).Count
    } catch {
        return 1   # conservative on transient read error
    }
}

function WorkerStopFlag([string]$id) { return (Join-Path $scratch ("STOP_WORKER_{0}.flag" -f $id)) }

function Clear-DrainFlag([string]$id) {
    $wf = WorkerStopFlag $id
    if (Test-Path $wf) { Remove-Item $wf -Force -ErrorAction SilentlyContinue }
}

function Read-Seq {
    if (Test-Path $seqFile) {
        try { $n = 0; if ([int]::TryParse((Get-Content $seqFile -Raw).Trim(), [ref]$n) -and $n -ge 0) { return $n } } catch { }
    }
    return 0
}
$script:seq = Read-Seq

$script:stall = 0   # consecutive loops with buffer full but nothing OCR'ing (OCR-pool-down watchdog)
$script:crashTimes = New-Object System.Collections.Generic.List[datetime]
function Recent-Crashes {
    $cut = (Get-Date).AddSeconds(-$CRASH_WINDOW)
    $script:crashTimes = [System.Collections.Generic.List[datetime]]@(
        $script:crashTimes | Where-Object { $_ -ge $cut })
    return $script:crashTimes.Count
}

function Start-Worker {
    $script:seq++
    Set-Content -Path $seqFile -Value $script:seq -Encoding ascii
    $id  = "5090p-$($script:seq)"
    Clear-DrainFlag $id
    $out = Join-Path $scratch ("prepworker{0}.out.log" -f $script:seq)
    $err = Join-Path $scratch ("prepworker{0}.err.log" -f $script:seq)
    $p = Start-Process -FilePath $py -ArgumentList @($script, $id, '--role', 'prep') `
        -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    try { $p.PriorityClass = 'BelowNormal' } catch { Sup ("WARN: could not set BelowNormal on $id : $_") }
    Sup ("launched prep worker $id pid $($p.Id) (BelowNormal)")
    return @{ Proc = $p; Id = $id; Draining = $false }
}

function Update-Pids($procs) {
    ($procs.Values | ForEach-Object { $_.Proc.Id }) -join ',' |
        Set-Content -Path $pidFile -Encoding ascii
}

$procs = @{}

# ------------------------- startup reconciliation --------------------------
Sup "=== prep supervisor online (pid $PID) requested Count=$Count seq-resume=$($script:seq) ==="
# Sweep orphaned 5090p- per-worker drain flags from a prior prep supervisor.
Get-ChildItem (Join-Path $scratch 'STOP_WORKER_5090p-*.flag') -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue; Sup ("swept orphan flag " + $_.Name) }
if (Test-Path $stopFlag) {
    Sup "WARNING: global STOP_WORKER.flag present at startup -- NOT launching prep workers; remove it to start."
}

# ------------------------------ initial launch -----------------------------
$initial = Get-MaxWorkers $Count
for ($i = 1; $i -le $initial; $i++) {
    if (Test-Path $stopFlag) { Sup "STOP_WORKER.flag present at startup -- not launching more"; break }
    $w = Start-Worker
    $procs[$w.Id] = $w
    Start-Sleep -Seconds $STAGGER_SECONDS
}
Update-Pids $procs

# --------------------------- management loop -------------------------------
while ($true) {
    Start-Sleep -Seconds $LOOP_SECONDS
    $maxw = Get-MaxWorkers $Count

    foreach ($id in @($procs.Keys)) {
        $w = $procs[$id]
        if ($w.Proc.HasExited) {
            Clear-DrainFlag $id
            $code = $null
            try { $code = $w.Proc.ExitCode } catch { }
            if ($w.Draining) {
                Sup ("prep worker $id exited (drained)")
            } elseif (($null -ne $code) -and ($code -ne 0)) {
                $script:crashTimes.Add((Get-Date))
                Sup ("prep worker $id exited UNEXPECTEDLY (exit $code) -- counted toward crash guard")
            } else {
                Sup ("prep worker $id exited cleanly (exit $code)")
            }
            $procs.Remove($id)
        }
    }

    $aliveIds = @($procs.Keys | Sort-Object { [int]($_ -replace '^5090p-','') })
    $alive    = $aliveIds.Count

    if (Test-Path $stopFlag) {
        if ($alive -eq 0) { Sup "=== STOP_WORKER.flag set + all prep workers drained -- prep supervisor exiting ==="; break }
        Update-Pids $procs
        continue
    }

    $remaining = Remaining-PrepWork

    # Liveness watchdog: if the buffer holds prepped volumes but NOTHING is OCR'ing
    # for ~5 min, the OCR pool is likely down and prep is idle-waiting silently.
    try {
        $qd = Get-Content $queue -Raw | ConvertFrom-Json
        $preppedCnt = @($qd.volumes | Where-Object { $_.status -eq 'prepped' }).Count
        $ocringCnt  = @($qd.volumes | Where-Object { $_.status -eq 'ocring' }).Count
        if ($preppedCnt -ge 1 -and $ocringCnt -eq 0) { $script:stall++ } else { $script:stall = 0 }
        if ($script:stall -ge 10) {
            Sup ("WARNING: $preppedCnt prepped but 0 OCR'ing for ~$([int]($script:stall*$LOOP_SECONDS/60)) min -- OCR supervisor may be DOWN; prep idle-waiting.")
            $script:stall = 0
        }
    } catch { }

    if ($alive -gt $maxw) {
        # SCALE DOWN: drain the newest surplus prep workers via per-worker flags.
        $drainCount = $alive - $maxw
        $toDrain = @($aliveIds | Select-Object -Last $drainCount)
        foreach ($id in $aliveIds) {
            if ($toDrain -contains $id) {
                $wf = WorkerStopFlag $id
                if (-not (Test-Path $wf)) {
                    Set-Content -Path $wf -Value "drain" -Encoding ascii
                    Sup ("scale-down: draining $id (alive=$alive -> max_prep_workers=$maxw)")
                }
                $procs[$id].Draining = $true
            } else {
                $procs[$id].Draining = $false
                Clear-DrainFlag $id
            }
        }
    }
    elseif ($alive -lt $maxw -and $remaining -gt 0) {
        foreach ($id in $aliveIds) { $procs[$id].Draining = $false; Clear-DrainFlag $id }
        $crashes = Recent-Crashes
        if ($crashes -ge $CRASH_CAP) {
            Sup ("scale-up wanted (alive=$alive < max=$maxw) but crash guard active ($crashes in ${CRASH_WINDOW}s) -- cooling down")
        } else {
            $need = $maxw - $alive
            Sup ("scale-up: alive=$alive < max_prep_workers=$maxw, $remaining prep-work -- launching $need worker(s)")
            for ($n = 1; $n -le $need; $n++) {
                $w = Start-Worker
                $procs[$w.Id] = $w
                Start-Sleep -Seconds $STAGGER_SECONDS
            }
        }
    }
    else {
        foreach ($id in $aliveIds) { $procs[$id].Draining = $false; Clear-DrainFlag $id }
        if ($alive -eq 0 -and $remaining -eq 0) { Sup "=== no prep workers and no prep work left -- prep supervisor exiting ==="; break }
    }

    Update-Pids $procs
}
