# Run this ELEVATED (Administrator) ON EACH BOX to register the durable GPU temp
# logger as a SYSTEM scheduled task (survives reboots + any session). It points
# at temp_logger.ps1 sitting in the SAME folder (already deployed to each box's
# PatoLex-scratch). Same mechanism as the existing guardian/OCR tasks.
$dir = $PSScriptRoot
if (-not $dir) { $dir = Split-Path -Parent $MyInvocation.MyCommand.Definition }
$script = Join-Path $dir 'temp_logger.ps1'
if (-not (Test-Path $script)) { throw "temp_logger.ps1 not found next to this script ($script)" }

$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"{0}`"" -f $script)
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'PatoLex_TempLog' -Action $action -Trigger $trigger `
    -Settings $settings -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
# Stop any running (possibly old-script) instance so a re-run picks up edits cleanly.
Stop-ScheduledTask -TaskName 'PatoLex_TempLog' -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName 'PatoLex_TempLog'
Start-Sleep -Seconds 5
"Registered + started PatoLex_TempLog -> $script"
"State: " + (Get-ScheduledTask -TaskName 'PatoLex_TempLog').State
$log = Join-Path $dir 'gpu_temps.log'
if (Test-Path $log) { "log OK -> $log"; Get-Content $log -Tail 2 } else { "WARN: no gpu_temps.log yet" }
