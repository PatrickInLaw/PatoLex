@echo off
rem ============================================================================================
rem  Canonical PatoLex launcher template (.bat).
rem  config.py is the SINGLE source of truth for paths. A shell launcher cannot `import config`,
rem  so it shells OUT to it: `python -m config <name> [subpath]` prints the resolved path.
rem  NOTHING data-path is hardcoded here -- only the python binary (a box fact) and %~dp0, the
rem  deploy anchor where config.py lives (so PYTHONPATH can find it).
rem
rem  Usage:  _TEMPLATE_run.bat <module.name> [args...]
rem    e.g.  _TEMPLATE_run.bat ocrcorrect.correction_cascade
rem  stdout/stderr are redirected into the config-resolved vocab_dir, named after this script.
rem ============================================================================================
setlocal enabledelayedexpansion
set "PY=C:\Users\patolex\AppData\Local\Programs\Python\Python312\python.exe"
set "PYTHONPATH=%~dp0"
rem --- ask config for the log location (single source, not hardcoded) ---
for /f "usebackq delims=" %%i in (`"%PY%" -m config vocab_dir`) do set "LOGDIR=%%i"
"%PY%" -m %* > "%LOGDIR%\%~n0_stdout.txt" 2>&1
