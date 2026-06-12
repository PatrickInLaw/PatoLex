# ============================================================================================
#  Canonical PatoLex launcher template (PowerShell).
#  config.py is the SINGLE source of truth for paths. A shell launcher cannot `import config`,
#  so it shells OUT to it: `python -m config <name> [subpath]` prints the resolved path.
#  Nothing data-path is hardcoded -- only the python binary (a box fact) and $PSScriptRoot,
#  the deploy anchor where config.py lives (so PYTHONPATH can find it).
#
#  Usage:  .\_TEMPLATE_run.ps1 ocrcorrect.correction_cascade [args...]
#  stdout/stderr are redirected into the config-resolved vocab_dir, named after this script.
# ============================================================================================
$ErrorActionPreference = "Stop"
$Py = "C:\Users\patolex\AppData\Local\Programs\Python\Python312\python.exe"
$env:PYTHONPATH = $PSScriptRoot                    # config.py lives here
$logDir = (& $Py -m config vocab_dir).Trim()       # single source, not hardcoded
$name   = [System.IO.Path]::GetFileNameWithoutExtension($MyInvocation.MyCommand.Path)
$out    = Join-Path $logDir "$($name)_stdout.txt"
& $Py -m @args *> $out
