# Haiku delegation nudge: Block Opus from doing excessive research work directly
# Fires on Read/Grep/Glob PreToolUse
# Tracks consecutive research calls per session in a temp file
# After 4+ consecutive research calls from Opus (not a subagent), blocks with delegation suggestion
#
# Reads JSON from stdin (Claude Code hook protocol)
# Exit 0 = allow or deny (via JSON output)
#
# NOT WIRED INTO settings.json BY DEFAULT. Enable when you want token-conservation enforcement.

try {
    $stdin = [Console]::In.ReadToEnd()
    $data = $stdin | ConvertFrom-Json
} catch {
    exit 0
}

$toolName = $data.tool_name
$agentId = $data.agent_id
$sessionId = $data.session_id

# If already inside a subagent, let it work -- don't block haiku-worker's own calls
if ($agentId -and $agentId -ne '' -and $agentId -ne 'null') {
    exit 0
}

# Track file per session
$trackDir = "$env:TEMP\claude-delegation"
if (-not (Test-Path $trackDir)) {
    New-Item -ItemType Directory -Path $trackDir -Force | Out-Null
}
$trackFile = Join-Path $trackDir "session-$sessionId.txt"

# Read current count
$count = 0
if (Test-Path $trackFile) {
    $raw = Get-Content $trackFile -Raw
    if ($raw -match '^\d+$') {
        $count = [int]$raw.Trim()
    }
}

# Increment
$count++
Set-Content -Path $trackFile -Value $count -NoNewline

$threshold = 4

if ($count -ge $threshold) {
    Set-Content -Path $trackFile -Value "0" -NoNewline

    $reason = "TOKEN CONSERVATION: You have made $count consecutive Read/Grep/Glob calls without delegating. " +
              "Per CLAUDE.md Token Conservation rules, research and search tasks should be delegated to haiku-worker subagents. " +
              "Spawn a haiku-worker with your research question instead of doing it yourself."

    $json = @{
        hookSpecificOutput = @{
            hookEventName = "PreToolUse"
            permissionDecision = "deny"
            permissionDecisionReason = $reason
        }
    } | ConvertTo-Json -Depth 3 -Compress

    Write-Output $json
    exit 0
}

exit 0
