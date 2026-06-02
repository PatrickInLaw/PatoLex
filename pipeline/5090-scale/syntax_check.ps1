$ErrorActionPreference = 'Stop'
$files = @(
    'C:\Users\patolex\PatoLex-scratch\supervisor_5090.ps1',
    'C:\Users\patolex\PatoLex-scratch\scale_to_one_5090.ps1'
)
foreach ($f in $files) {
    $errs = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$null, [ref]$errs)
    if ($errs -and $errs.Count -gt 0) {
        Write-Output ("PARSE FAIL: {0}" -f $f)
        $errs | ForEach-Object { Write-Output ("  " + $_.Message) }
    } else {
        Write-Output ("PARSE OK: {0}" -f $f)
    }
}
