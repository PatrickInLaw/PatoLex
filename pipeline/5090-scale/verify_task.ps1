$t = Get-ScheduledTask -TaskName 'PatoLex_OCR_5090_ScaleTo1_0800'
$i = Get-ScheduledTaskInfo -TaskName 'PatoLex_OCR_5090_ScaleTo1_0800'
Write-Output ("TaskName     : " + $t.TaskName)
Write-Output ("State        : " + $t.State)
Write-Output ("Principal    : " + $t.Principal.UserId + " / " + $t.Principal.RunLevel + " / " + $t.Principal.LogonType)
Write-Output ("NextRunTime  : " + $i.NextRunTime)
Write-Output ("LastRunTime  : " + $i.LastRunTime)
Write-Output ("LastResult   : " + $i.LastTaskResult)
foreach ($trg in $t.Triggers) {
    Write-Output ("Trigger      : " + $trg.CimClass.CimClassName + " StartBoundary=" + $trg.StartBoundary)
}
