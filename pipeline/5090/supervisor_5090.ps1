param(
    [int]$Count = 3
)
# supervisor_5090.ps1 -- long-lived worker supervisor for the 5090.
# Designed to run as the ACTION of a Scheduled Task (principal: patolex, stored
# creds, RunLevel Highest). The task stays "Running" for the whole OCR campaign
# because this script BLOCKS in its management loop, so the workers are owned by
# the Task Scheduler service -- fully independent of any SSH/interactive session.
#
# ============================ SYMMETRIC LIVE SCALING ========================
# The worker count is the SINGLE KNOB max_workers.txt, re-read every loop. Both
# directions are live -- NO supervisor restart, NO kill-and-relaunch of the set:
#
#   * SCALE UP (raise the number): the supervisor launches the missing workers
#     ONE AT A TIME (staggered), as long as the queue still has claimable work.
#     Because each new worker joins an already-running, phase-DESYNCED set, the
#     workers do NOT lockstep (the failure mode of a cold all-at-once restart,
#     where every worker preprocesses together and the GPU sits idle).
#
#   * SCALE DOWN (lower the number): the supervisor writes a PER-WORKER stop
#     flag (STOP_WORKER_<id>.flag) for the NEWEST surplus worker(s). Each such
#     worker finishes its current volume, then exits (drain) -- NEVER killed
#     mid-volume. The SUPERVISOR owns that flag's entire lifecycle: it creates
#     it, CANCELS it (removes it if max_workers is raised back before the worker
#     exits), and clears it when it reaps the worker. The worker only READS the
#     flag -- it must not delete it (a worker-side delete races the cancel).
#
#   * STOP_WORKER.flag (global, unchanged) still pauses/drains ALL workers; when
#     all have drained the supervisor exits.
#
# Worker IDs are monotonic and PERSISTED (worker_seq.txt), so they are never
# reused across supervisor restarts. A crashed worker is replaced by the
# scale-up path (alive < max_workers); a CRASH-FREQUENCY guard pauses relaunches
# when a poison volume crashes workers repeatedly (does NOT throttle legitimate
# scale-ups).
#
# CUTOVER NOTE: this supervisor only manages workers IT launched. Before
# restarting it onto a box that already has workers running (deploy/cutover),
# DRAIN the old workers first (global STOP_WORKER.flag) -- otherwise the old
# workers keep running unmanaged alongside the new set (over-subscription). The
# supervisor logs a loud warning if it detects pre-existing worker PIDs.
# ===========================================================================

$ErrorActionPreference = 'Continue'
$scratch  = 'C:\Users\patolex\PatoLex-scratch'
$py       = 'C:\Users\patolex\PatoLex-scratch\ocr-engines\surya-venv\Scripts\python.exe'
$script   = Join-Path $scratch 'queue_worker.py'
$suplog   = Join-Path $scratch 'supervisor.log'
$cfgFile  = Join-Path $scratch 'max_workers.txt'
$stopFlag = Join-Path $scratch 'STOP_WORKER.flag'
$queue    = Join-Path $scratch 'production_queue_state.json'
$seqFile  = Join-Path $scratch 'worker_seq.txt'
$pidFile  = Join-Path $scratch 'worker_pids.txt'

$STAGGER_SECONDS = 45    # spacing between successive cold launches (cold model-load)
$LOOP_SECONDS    = 30    # supervisor poll interval
$CRASH_WINDOW    = 300   # crash-frequency guard: rolling window (seconds)
$CRASH_CAP       = 5     # crash-frequency guard: max unexpected exits within the window

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
    # COARSE over-estimate of claimable work (NOT the worker's exact claimability
    # rule -- it does not replicate stale-reclaim of in_progress). Used only to
    # decide whether scaling up is worthwhile; over-counting just keeps scale-up
    # armed, which is the safe direction.
    try {
        $qjson = Get-Content $queue -Raw | ConvertFrom-Json
        return @($qjson.volumes | Where-Object { $_.status -ne 'done' -and $_.status -ne 'held' }).Count
    } catch {
        return 1   # be conservative: assume work remains on transient read error
    }
}

function WorkerStopFlag([string]$id) { return (Join-Path $scratch ("STOP_WORKER_{0}.flag" -f $id)) }

function Clear-DrainFlag([string]$id) {
    $wf = WorkerStopFlag $id
    if (Test-Path $wf) { Remove-Item $wf -Force -ErrorAction SilentlyContinue }
}

# --- persisted monotonic worker-id sequence (never reused across restarts) ---
function Read-Seq {
    if (Test-Path $seqFile) {
        try { $n = 0; if ([int]::TryParse((Get-Content $seqFile -Raw).Trim(), [ref]$n) -and $n -ge 0) { return $n } } catch { }
    }
    return 0
}
$script:seq = Read-Seq

# --- crash-frequency guard state ---
$script:crashTimes = New-Object System.Collections.Generic.List[datetime]
function Recent-Crashes {
    $cut = (Get-Date).AddSeconds(-$CRASH_WINDOW)
    $script:crashTimes = [System.Collections.Generic.List[datetime]]@(
        $script:crashTimes | Where-Object { $_ -ge $cut })
    return $script:crashTimes.Count
}

function Start-Worker {
    $script:seq++
    Set-Content -Path $seqFile -Value $script:seq -Encoding ascii   # persist BEFORE launch
    $id  = "5090-$($script:seq)"
    Clear-DrainFlag $id   # never start a worker that has a leftover stop flag
    $out = Join-Path $scratch ("worker{0}.out.log" -f $script:seq)
    $err = Join-Path $scratch ("worker{0}.err.log" -f $script:seq)
    $p = Start-Process -FilePath $py -ArgumentList @($script, $id) `
        -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    Sup ("launched worker $id pid $($p.Id)")
    return @{ Proc = $p; Id = $id; Draining = $false }
}

function Update-Pids($procs) {
    ($procs.Values | ForEach-Object { $_.Proc.Id }) -join ',' |
        Set-Content -Path $pidFile -Encoding ascii
}

# Live worker registry, keyed by worker-id string.
$procs = @{}

# ------------------------- startup reconciliation --------------------------
Sup "=== supervisor online (pid $PID) requested Count=$Count seq-resume=$($script:seq) ==="
# Sweep orphaned PER-WORKER drain flags from a prior supervisor (the global
# STOP_WORKER.flag is intentionally NOT swept -- that is an operator decision).
Get-ChildItem (Join-Path $scratch 'STOP_WORKER_*.flag') -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue; Sup ("swept orphan flag " + $_.Name) }
# Warn loudly about a stale global STOP flag (would otherwise silently brick the campaign).
if (Test-Path $stopFlag) {
    Sup "WARNING: global STOP_WORKER.flag present at startup -- NOT launching workers; remove it to start the campaign."
}
# Warn about workers left running by a previous supervisor (cutover over-subscription hazard).
if (Test-Path $pidFile) {
    try {
        $oldPids = ((Get-Content $pidFile -Raw).Trim() -split ',') | Where-Object { $_ }
        $stillAlive = @($oldPids | Where-Object { try { Get-Process -Id ([int]$_) -ErrorAction Stop | Out-Null; $true } catch { $false } })
        if ($stillAlive.Count -gt 0) {
            Sup ("WARNING: $($stillAlive.Count) worker PID(s) from a previous supervisor still alive ($($stillAlive -join ',')) -- this supervisor does NOT manage them. Drain them (global STOP) before relying on max_workers.")
        }
    } catch { }
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

    # 1. Reap exited workers; clear their flags; count UNEXPECTED exits (crashes)
    #    toward the crash-frequency guard. A worker that exited while it was
    #    being drained is intentional and is NOT counted.
    foreach ($id in @($procs.Keys)) {
        $w = $procs[$id]
        if ($w.Proc.HasExited) {
            Clear-DrainFlag $id
            if ($w.Draining) {
                Sup ("worker $id exited (drained)")
            } else {
                $script:crashTimes.Add((Get-Date))
                Sup ("worker $id exited UNEXPECTEDLY -- counted toward crash guard")
            }
            $procs.Remove($id)
        }
    }

    # Live workers, oldest -> newest by monotonic sequence number.
    $aliveIds = @($procs.Keys | Sort-Object { [int]($_ -replace '^5090-','') })
    $alive    = $aliveIds.Count

    # 2. Global STOP: pause everything, let in-flight volumes drain, exit empty.
    if (Test-Path $stopFlag) {
        if ($alive -eq 0) { Sup "=== STOP_WORKER.flag set + all workers drained -- supervisor exiting ==="; break }
        Update-Pids $procs
        continue
    }

    $remaining = Remaining-Claimable

    if ($alive -gt $maxw) {
        # 3a. SCALE DOWN: drain the (alive - maxw) NEWEST workers via per-worker
        #     stop flags; ensure non-surplus workers have NO drain flag (cancel).
        $drainCount = $alive - $maxw
        $toDrain = @($aliveIds | Select-Object -Last $drainCount)
        foreach ($id in $aliveIds) {
            if ($toDrain -contains $id) {
                $wf = WorkerStopFlag $id
                if (-not (Test-Path $wf)) {
                    Set-Content -Path $wf -Value "drain" -Encoding ascii
                    Sup ("scale-down: draining $id (alive=$alive -> max_workers=$maxw)")
                }
                $procs[$id].Draining = $true
            } else {
                $procs[$id].Draining = $false
                Clear-DrainFlag $id
            }
        }
    }
    elseif ($alive -lt $maxw -and $remaining -gt 0) {
        # 3b. SCALE UP (explicit raise OR replacing a crash): cancel any pending
        #     drains, then launch the missing workers one at a time -- UNLESS the
        #     crash-frequency guard is tripped (poison-volume protection). Note:
        #     legitimate large scale-ups are NOT throttled (they aren't crashes).
        foreach ($id in $aliveIds) { $procs[$id].Draining = $false; Clear-DrainFlag $id }
        $crashes = Recent-Crashes
        if ($crashes -ge $CRASH_CAP) {
            Sup ("scale-up wanted (alive=$alive < max_workers=$maxw, $remaining claimable) but crash guard active ($crashes crashes in last ${CRASH_WINDOW}s) -- cooling down")
        } else {
            $need = $maxw - $alive
            Sup ("scale-up: alive=$alive < max_workers=$maxw, $remaining claimable -- launching $need worker(s)")
            for ($n = 1; $n -le $need; $n++) {
                $w = Start-Worker
                $procs[$w.Id] = $w
                Start-Sleep -Seconds $STAGGER_SECONDS
            }
        }
    }
    else {
        # 3c. Steady (alive == maxw) OR no claimable work: clear stray drain flags.
        foreach ($id in $aliveIds) { $procs[$id].Draining = $false; Clear-DrainFlag $id }
        if ($alive -eq 0 -and $remaining -eq 0) { Sup "=== no workers and queue drained -- supervisor exiting ==="; break }
    }

    Update-Pids $procs
}
