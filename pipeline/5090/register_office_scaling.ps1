# Registers the 5090 office-hours auto-scaling tasks. Run ONCE on the 5090.
# Idempotent (-Force overwrites). Runs as SYSTEM (no stored creds needed; SYSTEM
# can write max_workers.txt). The scale scripts just edit max_workers.txt; the
# OCR supervisor picks up the change within ~30s.
$scratch = 'C:\Users\patolex\PatoLex-scratch'
$down = Join-Path $scratch 'scale_down_office.ps1'
$up   = Join-Path $scratch 'scale_up_office.ps1'
$days = 'Monday','Tuesday','Wednesday','Thursday','Friday'

# Scale DOWN to 1 at 07:30 Mon-Fri (30-min lead before 08:00 office hours).
$aDown = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`"" -f $down)
$tDown = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At ([datetime]'07:30')
Register-ScheduledTask -TaskName 'PatoLex_ScaleDown_Office' -Action $aDown -Trigger $tDown `
    -User 'SYSTEM' -RunLevel Highest -Force | Out-Null

# Scale UP at 17:00 Mon-Fri (end of office hours).
$aUp = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`"" -f $up)
$tUp = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At ([datetime]'17:00')
Register-ScheduledTask -TaskName 'PatoLex_ScaleUp_Office' -Action $aUp -Trigger $tUp `
    -User 'SYSTEM' -RunLevel Highest -Force | Out-Null

Get-ScheduledTask -TaskName 'PatoLex_Scale*' |
    Select-Object TaskName, State, @{n='NextRun';e={ (Get-ScheduledTaskInfo $_.TaskName).NextRunTime }} |
    Format-Table -Auto
