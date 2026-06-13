<# Apply the shape schema extension + seed the manifest into the 3060 PatoLexQueue, from the 5090.
   Reads the DSN (with the PatitoSync secret) from the gitignored local file -- never from the repo. #>
$ErrorActionPreference = 'Stop'
$dsnFile = 'C:\Users\patolex\.patolex_queue_dsn.txt'
if (-not (Test-Path $dsnFile)) { throw "DSN file missing: $dsnFile" }
$env:PATOLEX_QUEUE_DSN = (Get-Content -Raw $dsnFile).Trim()
$py = 'C:\Users\patolex\PatoLex-scratch\ocr-engines\surya-venv\Scripts\python.exe'
& $py 'C:\github\PatoLex\pipeline\sql\setup_shape_3060.py' `
    --manifest 'C:\Users\patolex\PatoLex-scratch\_cascade\manifest.tsv' `
    --schema   'C:\github\PatoLex\pipeline\sql\schema_shape_ext.sql'
