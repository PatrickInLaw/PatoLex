# One-shot ELEVATED installer for the 5080 guardian task.
# Run this from an elevated PowerShell:  Right-click > Run as administrator, or
#   Start-Process pwsh -Verb RunAs -ArgumentList '-File C:\Users\PatrickKolasinski\Documents\GitHub\PatoLex\pipeline\thermal_guardian_install_5080.ps1'
# Creates PatoLex_ThermalGuard_5080 (SYSTEM, HIGHEST, ONSTART), starts it, writes a result marker.

$ErrorActionPreference = 'Continue'
$marker = 'C:\Users\PatrickKolasinski\PatoLex-scratch\thermal-guard-install-5080.txt'
$tr = 'powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\Users\PatrickKolasinski\Documents\GitHub\PatoLex\pipeline\thermal_guardian_launch_5080.ps1'

$create = schtasks /create /tn PatoLex_ThermalGuard_5080 /ru SYSTEM /rl HIGHEST /sc ONSTART /tr $tr /f 2>&1
$run    = schtasks /run /tn PatoLex_ThermalGuard_5080 2>&1

$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Set-Content -Path $marker -Encoding utf8 -Value @(
    "[$ts] thermal_guardian_install_5080 ran ELEVATED"
    "CREATE: $create"
    "RUN:    $run"
)
Write-Host "Install marker written to $marker"
