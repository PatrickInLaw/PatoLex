$ErrorActionPreference = 'Continue'
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='powershell.exe'"
foreach ($p in $procs) {
    $cl = $p.CommandLine
    if ($null -eq $cl) { continue }
    if ($cl -match 'queue_worker|supervisor_5090|ocr_only_5090') {
        $short = $cl
        if ($short.Length -gt 110) { $short = $short.Substring(0,110) }
        Write-Output ("PID={0} PPID={1} :: {2}" -f $p.ProcessId, $p.ParentProcessId, $short)
    }
}
