<# Stop the running page-shape worker processes on the 5090 (graceful-ish: SIGKILL the python procs).
   Safe to use -- the lease queue means killed in-flight volumes expire/reset to pending and re-run (--reuse
   skips already-rendered pages). Targets ONLY shape_worker_sql / surya_page_shapes python; leaves others. #>
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'shape_worker_sql|surya_page_shapes' }
foreach ($p in $procs) {
    Write-Output ("stopping PID " + $p.ProcessId)
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Write-Output ("stopped " + @($procs).Count + " shape processes")
