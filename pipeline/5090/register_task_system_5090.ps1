param(
    [int]$Count = 3
)
# register_task_system_5090.ps1 -- register + start the OCR supervisor as a
# Scheduled Task running as SYSTEM (no password needed). SYSTEM tasks run in
# session 0 and survive logoff / SSH-session close entirely. GPU/CUDA access
# under SYSTEM is verified separately (gpu_smoketest).

$ErrorActionPreference = 'Continue'
$taskName = 'PatoLex_OCR_5090'
$scratch  = 'C:\Users\patolex\PatoLex-scratch'
$sup      = Join-Path $scratch 'supervisor_5090.ps1'
$pwsh     = 'powershell.exe'
$action   = "-NoProfile -ExecutionPolicy Bypass -File `"$sup`" -Count $Count"

& schtasks /Delete /TN $taskName /F 2>&1 | Out-Null
$global:LASTEXITCODE = 0

& schtasks /Create /TN $taskName /TR "$pwsh $action" /SC ONCE /ST 00:00 `
    /RU 'SYSTEM' /RL HIGHEST /F
Write-Output ("create rc=$LASTEXITCODE")

& schtasks /Run /TN $taskName
Write-Output ("run rc=$LASTEXITCODE")

Start-Sleep -Seconds 3
& schtasks /Query /TN $taskName /FO LIST | Select-String 'TaskName|Status'
