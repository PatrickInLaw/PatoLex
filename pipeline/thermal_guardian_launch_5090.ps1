# Launcher for the RTX 5090 box (patolex@100.70.54.56).
# Pins the 5090 power limits. Run as the ACTION of Scheduled Task PatoLex_ThermalGuard_5090.
# The 5090 has no telegram.ps1 deployed -> guardian POSTs to the bot API directly.
& "$PSScriptRoot\thermal_guardian.ps1" `
    -BoxName       '5090' `
    -DefaultWatts  575 `
    -CapWatts      460 `
    -CapTempC      75 `
    -RestoreTempC  65 `
    -WarnTempC     82 `
    -WorkerMatch   'python' `
    -CsvPath       'C:\Users\patolex\PatoLex-scratch\thermal-guardian.csv' `
    -LogPath       'C:\Users\patolex\PatoLex-scratch\thermal-guardian.log'
