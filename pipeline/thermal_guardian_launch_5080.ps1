# Launcher for the local RTX 5080 box.
# Pins the 5080 power limits. Run as the ACTION of Scheduled Task PatoLex_ThermalGuard_5080.
# telegram.ps1 lives in the repo on this box -> use it for alerts.
$tg = 'C:\Users\PatrickKolasinski\Documents\GitHub\PatoLex\.claude\scripts\telegram.ps1'
& "$PSScriptRoot\thermal_guardian.ps1" `
    -BoxName        '5080' `
    -DefaultWatts   360 `
    -CapWatts       290 `
    -CapTempC       75 `
    -RestoreTempC   65 `
    -WarnTempC      82 `
    -WorkerMatch    'python' `
    -TelegramScript $tg `
    -CsvPath        'C:\Users\PatrickKolasinski\PatoLex-scratch\thermal-guardian.csv' `
    -LogPath        'C:\Users\PatrickKolasinski\PatoLex-scratch\thermal-guardian.log'
