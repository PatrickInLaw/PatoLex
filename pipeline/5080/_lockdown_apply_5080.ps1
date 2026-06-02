# _lockdown_apply_5080.ps1 -- boot-resilience task edits for the 5080.
# Idempotent. Must run elevated (SYSTEM-principal changes require admin).
# - PatoLex_Ingest_5080 + PatoLex_OCR_5080:
#     * ADD an At-Startup (boot) trigger (60s delay) alongside existing triggers
#     * set principal to SYSTEM / ServiceAccount / Highest, run-whether-logged-on
#     * AllowStartIfOnBatteries + DontStopIfGoingOnBatteries + StartWhenAvailable
#     * no execution time limit
#   Does NOT unregister -> running instances are not killed by Set-ScheduledTask.
# - PatoLex_OCR_5080_Backoff_0800:
#     * keep its DAILY 8AM trigger; only clear battery restrictions for consistency
$ErrorActionPreference = 'Stop'
$report = @()

function Ensure-BootTrigger($triggers) {
    $hasBoot = $false
    foreach ($t in $triggers) { if ($t.CimClass.CimClassName -eq 'MSFT_TaskBootTrigger') { $hasBoot = $true } }
    if ($hasBoot) { return @($triggers) }
    $b = New-ScheduledTaskTrigger -AtStartup
    $b.Delay = 'PT60S'
    return @($triggers) + $b
}

foreach ($n in @('PatoLex_Ingest_5080','PatoLex_OCR_5080')) {
    $task = Get-ScheduledTask -TaskName $n
    $nt = Ensure-BootTrigger $task.Triggers
    $p  = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $s  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
    Set-ScheduledTask -TaskName $n -Trigger $nt -Principal $p -Settings $s | Out-Null
    $report += "UPDATED $n (boot trigger + SYSTEM + no-battery)"
}

# Backoff: keep daily trigger; only clear battery restrictions.
$bk = Get-ScheduledTask -TaskName 'PatoLex_OCR_5080_Backoff_0800'
$bs = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
# preserve its existing principal (cmd echo flag, low-priv is fine) and trigger
Set-ScheduledTask -TaskName 'PatoLex_OCR_5080_Backoff_0800' -Settings $bs | Out-Null
$report += "UPDATED PatoLex_OCR_5080_Backoff_0800 (battery cleared, daily trigger kept)"

$report | Set-Content -Path 'C:\Users\PatrickKolasinski\PatoLex-scratch\_lockdown_apply_5080.result.txt' -Encoding utf8
