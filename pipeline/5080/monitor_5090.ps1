# monitor_5090.ps1 -- watch the 5090's GPU under load from the 5080 box over SSH.
# Polls nvidia-smi every IntervalSec; logs temp/util/power/VRAM. Detects a crash the way
# Patrick described: when the box "disappears" (SSH unreachable for MissThreshold consecutive
# polls), it records the LAST good reading before the loss and EXITS, so the launching agent
# is notified immediately. Also alerts if temp crosses TempCeilingC.
param(
    [int]$IntervalSec   = 60,
    [int]$TempCeilingC  = 85,
    [int]$MissThreshold = 3
)
$ssh = "C:\Windows\System32\OpenSSH\ssh.exe"
$key = "C:\Users\PatrickKolasinski\.ssh\patolex_5090"
$kh  = "C:\Users\PatrickKolasinski\.ssh\known_hosts"
$rem = "patolex@100.70.54.56"
$log = "C:\Users\PatrickKolasinski\Documents\GitHub\patolex\docs\80_PROJECT_HISTORY\run-logs\monitor-5090-run.log"

function Now { (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') }
function Log($m) { $line = "[" + (Now) + "] " + $m; Add-Content -Path $log -Value $line; Write-Output $line }

Log "=== 5090 GPU monitor online (interval ${IntervalSec}s, ceiling ${TempCeilingC}C, miss-threshold ${MissThreshold}, driver-stability watch) ==="
$misses = 0
$lastGood = "(none yet)"
$lastGoodTime = "(none yet)"
$peak = 0
while ($true) {
    $out = & $ssh -i $key -o BatchMode=yes -o ConnectTimeout=12 -o UserKnownHostsFile=$kh -o StrictHostKeyChecking=yes $rem `
        "nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,power.draw,memory.used --format=csv,noheader" 2>$null
    if ($LASTEXITCODE -eq 0 -and $out) {
        $misses = 0
        $line = ($out | Select-Object -First 1).Trim()
        $lastGood = $line; $lastGoodTime = (Now)
        $t = $null
        if ($line -match '^\s*(\d+)\s*,') { $t = [int]$Matches[1] }
        if ($null -ne $t -and $t -gt $peak) { $peak = $t }
        if ($null -ne $t -and $t -ge $TempCeilingC) {
            Log "ALERT HOT: ${t}C >= ${TempCeilingC}C (peak ${peak}C) | $line"
        } else {
            Log "ok (peak ${peak}C) | $line"
        }
    } else {
        $misses++
        Log "MISS ${misses}/${MissThreshold}: 5090 unreachable (ssh rc=$LASTEXITCODE)"
        if ($misses -ge $MissThreshold) {
            Log "=== 5090 DISAPPEARED at ~$(Now) -- LIKELY CRASH ==="
            Log "=== last contact ${lastGoodTime}; last reading (temp,util,power,mem): ${lastGood} ; peak temp this run ${peak}C ==="
            exit 7
        }
    }
    Start-Sleep -Seconds $IntervalSec
}
