<#
.SYNOPSIS
    PatoLex GPU Thermal Guardian -- durable native telemetry logger + power governor.

.DESCRIPTION
    Long-lived per-box guardian for the OCR GPU boxes (RTX 5090 / RTX 5080).

      1. DURABLE LOGGER -- every -IntervalSec (~10s) appends a CSV row of GPU
         telemetry (temp / util / power.draw / power.limit / mem.used / sm clock)
         to a rolling, size-capped on-box CSV. Uses local nvidia-smi (no remote poll).

      2. POWER GOVERNOR (the load-bearing hardware action) --
         * temp >= CapTempC      -> apply reduced power cap via `nvidia-smi -pl <CapWatts>`
                                    ONCE per crossing (no thrash), record + alert.
         * temp <= RestoreTempC for >= RestoreHoldSec -> restore DefaultWatts, record.
         * WARN >= WarnTempC      -> escalated Telegram alert (de-duped).
         * The governor only acts while a real OCR worker process is alive
           (-WorkerMatch). An idle card is logged but never capped.
         * On ANY exit (Ctrl-C, task stop, error, logoff) the FINALLY block
           ALWAYS restores DefaultWatts -- the card is never left capped.

    THIS SCRIPT CONTROLS GPU POWER (real hardware action). nvidia-smi -pl
    requires local admin (the 'patolex' account is a local admin on both boxes).

.NOTES
    Deployed to the repo at pipeline\thermal_guardian.ps1 and copied to each box's
    scratch dir. Run as a Scheduled Task (RunLevel Highest) so it survives session close.
#>

[CmdletBinding()]
param(
    # --- Per-box identity ---
    [string]$BoxName        = $env:COMPUTERNAME,

    # --- Thresholds (configurable) ---
    [int]$CapTempC          = 75,    # apply reduced cap at/above this
    [int]$RestoreTempC      = 65,    # restore default once cooled to/below this ...
    [int]$RestoreHoldSec    = 60,    #   ... sustained for this long
    [int]$WarnTempC         = 82,    # escalated WARN alert (approaching ~83-90C throttle)

    # --- Power limits (watts). Defaults overridden per box by the launcher. ---
    [int]$DefaultWatts      = 360,   # 5080 default; 5090 launcher passes 575
    [int]$CapWatts          = 290,   # 5080 ~80%;     5090 launcher passes 460

    # --- Logging / loop ---
    [int]$IntervalSec       = 10,
    [string]$CsvPath        = "$env:USERPROFILE\PatoLex-scratch\thermal-guardian.csv",
    [string]$LogPath        = "$env:USERPROFILE\PatoLex-scratch\thermal-guardian.log",
    [int]$MaxCsvBytes       = 25MB,  # rotate to .1 when exceeded

    # --- OCR-load detection: govern only when a matching worker is alive ---
    [string]$WorkerMatch    = "python",

    # --- Alerting ---
    [string]$TelegramScript = "",    # path to telegram.ps1 if present (5080/repo); else direct API
    [string]$BotToken       = "",    # resolved from Credential Manager (key PatoClaudeBotToken) if empty; see below
    [string]$ChatId         = "8525048490",

    # --- Test / utility modes ---
    [switch]$TestCap,                # set cap, read back, restore, read back; then exit
    [switch]$TestAlert,              # send one test Telegram, then exit
    [switch]$Once                    # single telemetry+govern pass, then exit (for verification)
)

$ErrorActionPreference = 'Continue'

# --------------------------------------------------------------------------
# Resolve Telegram bot token from Windows Credential Manager (key PatoClaudeBotToken)
# when not supplied explicitly. Falls back to env var PATOCLAUDE_BOT_TOKEN for
# SYSTEM/Scheduled-Task contexts where the CredStore profile path is unavailable.
# Direct-API alerting (no $TelegramScript) requires a resolved token.
# --------------------------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($BotToken)) {
    $credStore = Join-Path $env:USERPROFILE ".claude\scripts\CredStore.ps1"
    if (Test-Path $credStore) {
        try {
            . $credStore
            $BotToken = Get-CredSecret -Target PatoClaudeBotToken
        } catch { }
    }
    if ([string]::IsNullOrWhiteSpace($BotToken) -and $env:PATOCLAUDE_BOT_TOKEN) {
        $BotToken = $env:PATOCLAUDE_BOT_TOKEN
    }
}

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
function Write-GuardLog([string]$Msg) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$ts] [$BoxName] $Msg"
    try {
        $dir = Split-Path -Parent $LogPath
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Add-Content -Path $LogPath -Value $line -Encoding utf8 -ErrorAction SilentlyContinue
    } catch { }
    Write-Host $line
}

function Send-Alert([string]$Msg) {
    $full = "[ThermalGuard $BoxName] $Msg"
    try {
        if ($TelegramScript -and (Test-Path $TelegramScript)) {
            & $TelegramScript send $full | Out-Null
        } else {
            $api = "https://api.telegram.org/bot$BotToken/sendMessage"
            curl.exe -s -X POST $api `
                --data-urlencode "chat_id=$ChatId" `
                --data-urlencode "text=$full" | Out-Null
        }
        Write-GuardLog "ALERT SENT: $Msg"
    } catch {
        Write-GuardLog "ALERT FAILED: $($_.Exception.Message)"
    }
}

# Query GPU 0. Returns a hashtable or $null on failure.
function Get-GpuTelemetry {
    $q = 'temperature.gpu,utilization.gpu,power.draw,power.limit,memory.used,clocks.sm'
    try {
        $raw = & nvidia-smi --query-gpu=$q --format=csv,noheader,nounits -i 0 2>$null
        if (-not $raw) { return $null }
        $line = ($raw | Select-Object -First 1).Trim()
        if (-not $line) { return $null }
        $f = $line -split '\s*,\s*'
        if ($f.Count -lt 6) { return $null }
        return @{
            TempC     = [int][double]$f[0]
            UtilPct   = [int][double]$f[1]
            PowerDraw = [double]$f[2]
            PowerLim  = [double]$f[3]
            MemUsedMB = [int][double]$f[4]
            ClockSm   = [int][double]$f[5]
        }
    } catch {
        return $null
    }
}

# Apply a power limit; verify it took by reading power.limit back. Returns $true on success.
function Set-PowerLimit([int]$Watts) {
    try {
        $out = & nvidia-smi -pl $Watts -i 0 2>&1
        Start-Sleep -Milliseconds 400
        $t = Get-GpuTelemetry
        if ($null -eq $t) {
            Write-GuardLog "Set-PowerLimit($Watts): could not read back power.limit. nvidia-smi said: $out"
            return $false
        }
        $applied = [Math]::Round($t.PowerLim)
        if ([Math]::Abs($applied - $Watts) -le 2) {
            Write-GuardLog "Set-PowerLimit OK: requested ${Watts}W, read back ${applied}W"
            return $true
        }
        Write-GuardLog "Set-PowerLimit MISMATCH: requested ${Watts}W, read back ${applied}W. nvidia-smi said: $out"
        return $false
    } catch {
        Write-GuardLog "Set-PowerLimit($Watts) FAILED: $($_.Exception.Message)"
        return $false
    }
}

function Test-OcrLoad {
    try {
        $p = @(Get-Process -Name $WorkerMatch -ErrorAction SilentlyContinue)
        return ($p.Count -gt 0)
    } catch {
        return $false
    }
}

function Rotate-Csv {
    try {
        if ((Test-Path $CsvPath) -and ((Get-Item $CsvPath).Length -gt $MaxCsvBytes)) {
            $bak = "$CsvPath.1"
            if (Test-Path $bak) { Remove-Item $bak -Force -ErrorAction SilentlyContinue }
            Move-Item $CsvPath $bak -Force -ErrorAction SilentlyContinue
        }
    } catch { }
}

function Ensure-CsvHeader {
    $dir = Split-Path -Parent $CsvPath
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    if (-not (Test-Path $CsvPath)) {
        Set-Content -Path $CsvPath -Encoding utf8 `
            -Value 'timestamp,box,temperature_gpu_c,utilization_gpu_pct,power_draw_w,power_limit_w,memory_used_mb,clocks_sm_mhz,ocr_active,governor_state'
    }
}

# --------------------------------------------------------------------------
# TEST / UTILITY MODES (exit early; never enter the loop)
# --------------------------------------------------------------------------
if ($TestAlert) {
    Send-Alert "TEST alert -- thermal guardian alert path OK (default ${DefaultWatts}W, cap ${CapWatts}W @ ${CapTempC}C)."
    return
}

if ($TestCap) {
    Write-GuardLog "=== TEST CAP: proving nvidia-smi -pl set+restore ==="
    $before = Get-GpuTelemetry
    Write-GuardLog ("BEFORE: power.limit={0}W temp={1}C" -f $before.PowerLim, $before.TempC)
    $okCap = Set-PowerLimit $CapWatts
    $capped = Get-GpuTelemetry
    Write-GuardLog ("AFTER CAP: power.limit={0}W (requested {1}W) set-ok={2}" -f $capped.PowerLim, $CapWatts, $okCap)
    $okRestore = Set-PowerLimit $DefaultWatts
    $restored = Get-GpuTelemetry
    Write-GuardLog ("AFTER RESTORE: power.limit={0}W (requested {1}W) restore-ok={2}" -f $restored.PowerLim, $DefaultWatts, $okRestore)
    $verdict = if ($okCap -and $okRestore) { 'PASS' } else { 'FAIL' }
    Write-GuardLog "=== TEST CAP $verdict ==="
    return
}

# --------------------------------------------------------------------------
# MAIN GUARDIAN LOOP
# --------------------------------------------------------------------------
Ensure-CsvHeader
Write-GuardLog "=== guardian online (pid $PID) box=$BoxName default=${DefaultWatts}W cap=${CapWatts}W capTemp=${CapTempC}C restoreTemp=${RestoreTempC}C warn=${WarnTempC}C interval=${IntervalSec}s ==="

# Governor state machine
$state          = 'NORMAL'      # NORMAL | CAPPED
$warnActive     = $false         # de-dupe WARN alerts
$coolStart      = $null          # when temp first dropped <= RestoreTempC while CAPPED

try {
    do {
        $t = Get-GpuTelemetry
        $ocr = Test-OcrLoad

        if ($null -ne $t) {
            Rotate-Csv
            $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
            $row = "{0},{1},{2},{3},{4:F1},{5:F0},{6},{7},{8},{9}" -f `
                $ts, $BoxName, $t.TempC, $t.UtilPct, $t.PowerDraw, $t.PowerLim, `
                $t.MemUsedMB, $t.ClockSm, $(if ($ocr) {1} else {0}), $state
            Add-Content -Path $CsvPath -Value $row -Encoding utf8 -ErrorAction SilentlyContinue

            # ---- GOVERNOR (only while real OCR load is present) ----
            if ($ocr) {
                # WARN escalation (de-duped)
                if ($t.TempC -ge $WarnTempC -and -not $warnActive) {
                    $warnActive = $true
                    Send-Alert ("WARN: GPU at {0}C (>= {1}C, approaching throttle). power.limit={2}W draw={3}W util={4}%" -f $t.TempC, $WarnTempC, [Math]::Round($t.PowerLim), [Math]::Round($t.PowerDraw), $t.UtilPct)
                } elseif ($t.TempC -lt $WarnTempC -and $warnActive) {
                    $warnActive = $false
                    Write-GuardLog ("WARN cleared: {0}C < {1}C" -f $t.TempC, $WarnTempC)
                }

                if ($state -eq 'NORMAL') {
                    if ($t.TempC -ge $CapTempC) {
                        Write-GuardLog ("CAP TRIGGER: {0}C >= {1}C -- applying {2}W cap" -f $t.TempC, $CapTempC, $CapWatts)
                        $ok = Set-PowerLimit $CapWatts
                        $state = 'CAPPED'
                        $coolStart = $null
                        Send-Alert ("CAP APPLIED: {0}C >= {1}C -- power cap {2}W (was {3}W). set-ok={4}" -f $t.TempC, $CapTempC, $CapWatts, $DefaultWatts, $ok)
                    }
                }
                elseif ($state -eq 'CAPPED') {
                    if ($t.TempC -le $RestoreTempC) {
                        if ($null -eq $coolStart) {
                            $coolStart = Get-Date
                            Write-GuardLog ("cooling: {0}C <= {1}C, hold timer started ({2}s)" -f $t.TempC, $RestoreTempC, $RestoreHoldSec)
                        } elseif (((Get-Date) - $coolStart).TotalSeconds -ge $RestoreHoldSec) {
                            Write-GuardLog ("RESTORE TRIGGER: {0}C <= {1}C held {2}s -- restoring {3}W" -f $t.TempC, $RestoreTempC, $RestoreHoldSec, $DefaultWatts)
                            $ok = Set-PowerLimit $DefaultWatts
                            $state = 'NORMAL'
                            $coolStart = $null
                            Send-Alert ("RESTORED: cooled to {0}C -- power restored to {1}W. set-ok={2}" -f $t.TempC, $DefaultWatts, $ok)
                        }
                    } else {
                        # temp rose back above restore threshold -- reset the hold timer
                        if ($null -ne $coolStart) {
                            Write-GuardLog ("cooling aborted: {0}C > {1}C, hold reset" -f $t.TempC, $RestoreTempC)
                        }
                        $coolStart = $null
                    }
                }
            }
        } else {
            Write-GuardLog "telemetry read failed (nvidia-smi returned nothing)"
        }

        if (-not $Once) { Start-Sleep -Seconds $IntervalSec }
    } while (-not $Once)
}
finally {
    # ALWAYS restore default power limit on exit -- never leave the card capped.
    Write-GuardLog "shutdown: ensuring default power limit (${DefaultWatts}W) is restored"
    $r = Set-PowerLimit $DefaultWatts
    Write-GuardLog "shutdown restore set-ok=$r. guardian (pid $PID) exiting."
}
