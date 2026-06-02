param(
    # Safety: by default this script REFUSES to scale down unless it is at/after
    # the scheduled hour OR -Force is given. The Scheduled Task passes -Force is
    # NOT needed because the task only fires at 08:00; the hour-guard is a belt-
    # and-suspenders so a stray manual/early run cannot scale down before 08:00.
    [int]$ScaleHour = 8,
    [switch]$Force,
    [switch]$DryRun
)
# scale_to_one_5090.ps1 -- graceful scale of the 5090 OCR campaign to EXACTLY
# one worker (cc003). Designed to run as a Scheduled-Task action at 08:00 PT,
# session-independent (Task Scheduler owns it).
#
# GRACEFUL CONTRACT:
#   * Never kills an in-flight volume. Surplus workers finish their current
#     volume (writing OCR_COMPLETE.marker + per-page checkpoint) before exiting.
#   * No banked OCR is ever lost (markers are idempotent; ocr_only_5090.py
#     resumes from its checkpoint).
#   * Idempotent: re-running when already at 1 worker is a no-op.
#
# MECHANISM:
#   1. Write max_workers.txt = 1 (the upgraded supervisor honors this).
#   2. Fence off all 'pending' volumes -> 'held' so the OLD, already-running
#      workers (old in-memory code) find nothing new to claim and drain after
#      finishing their current volume.
#   3. End the OLD supervisor task instance (its orphaned worker children keep
#      running their in-flight volumes -- no job object ties them to the parent).
#   4. Wait for the old worker roots to exit on their own (graceful drain).
#   5. Restore 'held' -> 'pending'.
#   6. Re-launch the task with -Count 1 so the UPGRADED supervisor starts
#      exactly ONE Task-Scheduler-owned worker that resumes the queue.

$ErrorActionPreference = 'Continue'
$scratch  = 'C:\Users\patolex\PatoLex-scratch'
$queue    = Join-Path $scratch 'production_queue_state.json'
$lock     = Join-Path $scratch 'production_queue_state.lock'
$cfgFile  = Join-Path $scratch 'max_workers.txt'
$pidsFile = Join-Path $scratch 'worker_pids.txt'
$log      = Join-Path $scratch 'scale-to-one.log'
$taskName = 'PatoLex_OCR_5090'
$DRAIN_TIMEOUT_MIN = 120

function L($m, $status = 'OK') {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $log -Value ("[$ts PT] SCALE | $m | $status") -Encoding utf8
}

function Acquire-QueueLock {
    $waited = 0.0
    while ($true) {
        try {
            $fs = [System.IO.File]::Open($lock, [System.IO.FileMode]::CreateNew,
                  [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
            $fs.Close()
            return $true
        } catch {
            try {
                $age = (New-TimeSpan -Start (Get-Item $lock).LastWriteTime -End (Get-Date)).TotalSeconds
                if ($age -gt 60) { Remove-Item $lock -Force -ErrorAction SilentlyContinue; continue }
            } catch { }
            Start-Sleep -Milliseconds 150
            $waited += 0.15
            if ($waited -gt 120) { throw "queue lock wait exceeded" }
        }
    }
}
function Release-QueueLock { Remove-Item $lock -Force -ErrorAction SilentlyContinue }

function Set-PendingStatus([string]$from, [string]$to) {
    Acquire-QueueLock
    try {
        $state = Get-Content $queue -Raw | ConvertFrom-Json
        $changed = 0
        foreach ($v in $state.volumes) {
            if ($v.status -eq $from) { $v.status = $to; $changed++ }
        }
        $tmp = "$queue.tmp"
        ($state | ConvertTo-Json -Depth 12) | Set-Content -Path $tmp -Encoding utf8
        Move-Item -Path $tmp -Destination $queue -Force
        return $changed
    } finally { Release-QueueLock }
}

function Count-LiveWorkers {
    # number of supervisor-child queue_worker trees alive (top-level worker roots)
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue
    $n = 0
    foreach ($p in $procs) {
        if ($p.CommandLine -and $p.CommandLine -match 'queue_worker\.py') { $n++ }
    }
    return $n
}

L "=== scale_to_one invoked (ScaleHour=$ScaleHour Force=$Force DryRun=$DryRun) ==="

# ---- HOUR GUARD: do NOT scale down before the scheduled hour ----
$hourNow = (Get-Date).Hour
if (-not $Force -and $hourNow -lt $ScaleHour) {
    L "hour guard: current hour $hourNow < ScaleHour $ScaleHour and -Force not set -- ABORTING (no scale-down before 08:00)" 'WARN'
    return
}

# ---- IDEMPOTENCY: already at <=1 worker ----
$live = Count-LiveWorkers
$curCfg = if (Test-Path $cfgFile) { (Get-Content $cfgFile -Raw).Trim() } else { '(none)' }
L "precheck: live queue_worker trees=$live  max_workers.txt=$curCfg"
if ($live -le 1) {
    if (-not $DryRun) { '1' | Set-Content -Path $cfgFile -Encoding ascii }
    L "already at $live worker(s) -- writing max_workers=1 and exiting (idempotent no-op)"
    return
}

if ($DryRun) {
    L "DRY-RUN: would (1) write max_workers=1  (2) hold pending->held  (3) end task '$taskName'  (4) wait drain  (5) restore held->pending  (6) /change to -Count 1 + /run.  NO action taken." 'OK'
    return
}

# ---- 1. desired worker count = 1 ----
'1' | Set-Content -Path $cfgFile -Encoding ascii
L "wrote max_workers.txt = 1"

# capture the old worker roots BEFORE we end the supervisor
$oldRoots = @()
if (Test-Path $pidsFile) {
    $oldRoots = (Get-Content $pidsFile -Raw).Trim().Split(',') | Where-Object { $_ } | ForEach-Object { [int]$_ }
}
L ("old worker root pids (from worker_pids.txt): " + ($oldRoots -join ','))

# ---- 2. fence off pending work so OLD workers drain (find nothing claimable) ----
$held = Set-PendingStatus 'pending' 'held'
L "fenced $held pending volume(s) -> held"

# ---- 3. end the OLD supervisor task instance (orphaned workers keep running) ----
schtasks /end /tn $taskName | Out-Null
L "issued schtasks /end on '$taskName' (old supervisor stopped; in-flight workers orphaned but still running)"

# ---- 4. wait for old workers to finish their in-flight volume + exit ----
$deadline = (Get-Date).AddMinutes($DRAIN_TIMEOUT_MIN)
while ($true) {
    $live = Count-LiveWorkers
    L "drain wait: live queue_worker trees=$live"
    if ($live -eq 0) { L "all old workers drained (0 live)"; break }
    if ((Get-Date) -gt $deadline) { L "drain timeout after $DRAIN_TIMEOUT_MIN min; $live still live -- proceeding (held fence keeps them idle)" 'WARN'; break }
    Start-Sleep -Seconds 60
}

# ---- 5. restore held -> pending for the surviving single worker ----
$restored = Set-PendingStatus 'held' 'pending'
L "restored $restored held volume(s) -> pending"

# ---- 6. relaunch task with -Count 1 (upgraded supervisor reads max_workers=1) ----
schtasks /change /tn $taskName /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\patolex\PatoLex-scratch\supervisor_5090.ps1 -Count 1" | Out-Null
L "changed task action to -Count 1"
schtasks /run /tn $taskName | Out-Null
L "issued schtasks /run -- upgraded supervisor starting with exactly 1 worker"

Start-Sleep -Seconds 20
$live = Count-LiveWorkers
L "post-relaunch: live queue_worker trees=$live (target=1)" $(if ($live -eq 1) { 'OK' } else { 'WARN' })
L "=== scale_to_one complete ==="
