# Stop hook: hybrid hygiene backstop (non-blocking, advisory).
# Fires when the agent finishes a turn. Reminds to update the run/session log
# (and commit) when there is UNLOGGED substantive work AND the session log has
# not been touched in > THRESHOLD_MIN. Pairs with the event-driven enforcement
# in pre-bash-check.ps1 (which blocks commit/push without a current session log).
#
# Reads JSON from stdin (Claude Code Stop hook protocol). Always exit 0 (advisory).
$ErrorActionPreference = "SilentlyContinue"
$null = [Console]::In.ReadToEnd()

$THRESHOLD_MIN = 25

$repoRoot = git rev-parse --show-toplevel 2>$null
if (-not $repoRoot) { exit 0 }
Set-Location $repoRoot

$logDir = "docs/80_PROJECT_HISTORY/session-logs/claude-code"
if (-not (Test-Path $logDir)) { exit 0 }

# Is there unlogged substantive work? (uncommitted src/pipeline/docs/drizzle/scripts changes)
$dirty = git status --porcelain 2>$null | Where-Object {
    $_ -match '(src/|pipeline/|docs/|drizzle/|scripts/|\.claude/)'
}
$hasUnloggedWork = [bool]$dirty

$newest = Get-ChildItem -Path $logDir -Filter "*.md" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $newest) {
    if ($hasUnloggedWork) {
        $j = @{ systemMessage = "HYGIENE: No session log exists yet but there is uncommitted work. Create today's session log." } | ConvertTo-Json -Compress
        Write-Output $j
    }
    exit 0
}

$ageMin = [int]((Get-Date) - $newest.LastWriteTime).TotalMinutes

if ($hasUnloggedWork -and $ageMin -gt $THRESHOLD_MIN) {
    $msg = "Session log last updated $ageMin min ago and there is uncommitted src/pipeline/docs work. Update the run log + session log and consider committing. RULE: discovery findings must land in a design doc or memory, never only in a run/session log."
    $j = @{ systemMessage = "HYGIENE: $msg" } | ConvertTo-Json -Compress
    Write-Output $j
}
exit 0
