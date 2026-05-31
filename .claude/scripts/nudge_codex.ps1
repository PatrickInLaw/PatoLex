# nudge_codex.ps1 -- PowerShell nudge for stalled Codex CLI
# Finds window with "PatoLex_Codex" in title, sends "continue" + Enter
# Exit codes: 0=success, 1=window not found, 2=error
#
# Uses WScript.Shell SendKeys (COM) which delivers keystrokes to the
# active window's input queue -- works with Windows Terminal.

Add-Type -AssemblyName Microsoft.VisualBasic

$logFile = Join-Path $PSScriptRoot "nudge.log"
$timestamp = Get-Date -Format "2026-05-31 HH:mm:ss"

try {
    $procs = Get-Process | Where-Object { $_.MainWindowTitle -like '*PatoLex_Codex*' }
    if (-not $procs) {
        $entry = "$timestamp | WINDOW_NOT_FOUND | No window matching 'PatoLex_Codex'"
        Add-Content -Path $logFile -Value $entry
        Write-Host $entry
        exit 1
    }

    $proc = $procs | Select-Object -First 1
    $title = $proc.MainWindowTitle
    $procId = $proc.Id

    [Microsoft.VisualBasic.Interaction]::AppActivate($procId)
    Start-Sleep -Milliseconds 1000

    $wshell = New-Object -ComObject WScript.Shell
    $wshell.SendKeys("continue")
    Start-Sleep -Milliseconds 200
    $wshell.SendKeys("{ENTER}")

    $entry = "$timestamp | NUDGE_SENT | Sent 'continue' + Enter via WScript.Shell to '$title' (PID: $procId)"
    Add-Content -Path $logFile -Value $entry
    Write-Host $entry
    exit 0
} catch {
    $entry = "$timestamp | ERROR | $($_.Exception.Message)"
    Add-Content -Path $logFile -Value $entry
    Write-Host $entry
    exit 2
}
