@echo off
REM Pass C extended to freq>=2 (clean the 2-9 band). Same scored pipeline.
set PASSC_MIN_FREQ=2
"C:\Users\patolex\AppData\Local\Programs\Python\Python312\python.exe" "C:\Users\patolex\PatoLex-scratch\correction_passes.py" > "C:\Users\patolex\PatoLex-scratch\_vocab\correction_freq2_stdout.txt" 2>&1
