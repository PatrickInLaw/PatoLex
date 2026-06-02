# Registers the daily 08:00 scale-to-1 task on the 5090, session-independent
# (Task Scheduler service owns it; runs whether or not a user is logged on).
$ErrorActionPreference = 'Stop'
$taskName = 'PatoLex_OCR_5090_ScaleTo1_0800'
$script   = 'C:\Users\patolex\PatoLex-scratch\scale_to_one_5090.ps1'

$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 08:00
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
# Run as SYSTEM (S-1-5-18), HIGHEST -- matches PatoLex_OCR_5090 principal,
# session-independent, no stored password needed.
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Output "Registered task: $taskName"
