# stop_5080_worker.ps1 -- graceful-stop signal for the 5080 OCR worker.
# Run by the daily 08:00 Scheduled Task. Writes the STOP flag the worker
# checks BETWEEN volumes; the in-flight volume always finishes first so no
# banked OCR is lost. Does NOT kill the process.
$flag = 'C:\Users\PatrickKolasinski\PatoLex-scratch\STOP_5080_WORKER.flag'
$log  = 'C:\Users\PatrickKolasinski\Documents\GitHub\patolex\docs\80_PROJECT_HISTORY\run-logs\worker-5080-run.log'
$ts   = (Get-Date).ToString('yyyy-MM-dd HH:mm PT')
Set-Content -Path $flag -Value $ts -Encoding utf8
Add-Content -Path $log -Value "[$ts] BACKOFF | 08:00 graceful-stop flag written; worker will exit after current volume | OK"
