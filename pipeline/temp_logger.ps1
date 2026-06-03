# temp_logger.ps1 -- durable GPU temp logger. GATED on OCR being active and the
# log is SIZE-CAPPED, so it does NOT accumulate forever / clog the drive.
#   * Samples ONLY when an OCR worker is running (ocr_only* / queue_worker*
#     python process present). When idle/gaming, it logs nothing.
#   * Self-trims gpu_temps.log to the last KeepLines once it passes MaxLogMB,
#     so the file is bounded regardless of how long the campaign runs.
# Runs as a SYSTEM Scheduled Task (at-startup, restart-on-failure) -> independent
# of any session, survives reboots.
param([int]$IntervalSec = 30, [int]$MaxLogMB = 5, [int]$KeepLines = 3000)

$ErrorActionPreference = 'Continue'
$dir = $PSScriptRoot
if (-not $dir) { $dir = Split-Path -Parent $MyInvocation.MyCommand.Definition }
$log = Join-Path $dir 'gpu_temps.log'

function Stamp { (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') }

function OcrActive {
    # OCR is "running" if any OCR worker / engine python process is alive.
    try {
        return (@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -match 'ocr_only|queue_worker' }).Count -gt 0)
    } catch {
        return $true   # on a query error, err toward logging (don't lose data during OCR)
    }
}

Add-Content -Path $log -Value ("[" + (Stamp) + "] === gpu temp logger online (pid $PID, ${IntervalSec}s, gated on OCR-active, cap ${MaxLogMB}MB) ===")
$n = 0
while ($true) {
    if (OcrActive) {
        try {
            $r = & nvidia-smi --query-gpu=index,temperature.gpu,utilization.gpu,power.draw,memory.used --format=csv,noheader,nounits 2>&1
            foreach ($line in @($r)) {
                Add-Content -Path $log -Value ("[" + (Stamp) + "] gpu " + ($line -replace '\s+',' ').Trim())
            }
        } catch {
            Add-Content -Path $log -Value ("[" + (Stamp) + "] ERROR: " + $_)
        }
        $n++
        # periodic size cap: trim to the last KeepLines once the file exceeds MaxLogMB
        if (($n % 20) -eq 0 -and (Test-Path $log) -and ((Get-Item $log).Length -gt ($MaxLogMB * 1MB))) {
            try {
                $tail = Get-Content $log -Tail $KeepLines
                Set-Content -Path $log -Value $tail
                Add-Content -Path $log -Value ("[" + (Stamp) + "] (log trimmed to last $KeepLines lines)")
            } catch { }
        }
    }
    Start-Sleep -Seconds $IntervalSec
}
