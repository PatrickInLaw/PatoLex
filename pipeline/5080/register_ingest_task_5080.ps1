# register_ingest_task_5080.ps1 -- register the 5080 ingest supervisor as a
# session-independent Scheduled Task running as SYSTEM.
#
# SYSTEM tasks run in session 0, survive logoff / SSH-session close / Claude
# process death entirely. Parent process is the Task Scheduler service
# (svchost), NOT any interactive or SSH session. Postgres access works under
# SYSTEM because psql uses PGPASSWORD + "-U postgres" TCP auth, which is
# independent of the Windows logon account.
#
# MUST be run ELEVATED (admin). Creating a SYSTEM / "run whether logged on or
# not" task requires elevation.

$ErrorActionPreference = 'Continue'
$taskName = 'PatoLex_Ingest_5080'
$sup      = 'C:\Users\PatrickKolasinski\PatoLex-scratch\ingest_supervisor.ps1'
$pwsh     = 'powershell.exe'
$action   = "-NoProfile -ExecutionPolicy Bypass -File `"$sup`""

& schtasks /Delete /TN $taskName /F 2>&1 | Out-Null
$global:LASTEXITCODE = 0

# /RU SYSTEM => session 0, no password, runs whether logged on or not.
# /SC ONCE /ST 00:00 is a nominal trigger; we /Run it immediately below and the
# supervisor blocks for the whole campaign (relaunching the watcher on crash).
& schtasks /Create /TN $taskName /TR "$pwsh $action" /SC ONCE /ST 00:00 `
    /RU 'SYSTEM' /RL HIGHEST /F
"create rc=$LASTEXITCODE" | Out-Host

& schtasks /Run /TN $taskName
"run rc=$LASTEXITCODE" | Out-Host

Start-Sleep -Seconds 4
& schtasks /Query /TN $taskName /V /FO LIST |
    Select-String 'TaskName|Status|Logon Mode|Run As User|Scheduled Task State' | Out-Host
