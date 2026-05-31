# Consolidated pre-Bash hook: runs all checks in a single PowerShell process
# Reads JSON from stdin (Claude Code hook protocol)
# Exit 0 = allow, exit 2 = block (with JSON error message)
# Outputs JSON with systemMessage as warning when applicable
#
# PatoLex adaptation: No dotnet version enforcement (web project, no VersionInfo.cs).
# Codex (Hans) reminder and session-log enforcement are active.

# Resolve repo root so relative paths work from any subdirectory
$repoRoot = git rev-parse --show-toplevel 2>$null
if ($repoRoot) { Set-Location $repoRoot }

$rawInput = [Console]::In.ReadToEnd()
$data = $rawInput | ConvertFrom-Json
$command = $data.tool_input.command
$warnings = @()

# --- Check 1: Codex (Hans) review reminder (git push only) ---
if ($command -match 'git push') {
    $unpushed = git log --oneline "@{u}..HEAD" 2>$null
    if ($unpushed) {
        $changedFiles = git diff --name-only "@{u}..HEAD" 2>$null
        $productChanges = $changedFiles | Where-Object {
            $_ -and (($_ -match '^src/') -or ($_ -match '^pipeline/')) -and ($_ -notmatch 'VersionInfo\.cs$')
        }
        if ($productChanges -and $productChanges.Count -gt 0) {
            $toCodexPath = "docs/00_Inbox/comms/to-codex.md"
            $fromCodexPath = "docs/00_Inbox/comms/from-codex.md"
            $codexReplied = $false
            if ((Test-Path $fromCodexPath) -and (Test-Path $toCodexPath)) {
                $fromTime = (Get-Item $fromCodexPath).LastWriteTime
                $toTime = (Get-Item $toCodexPath).LastWriteTime
                if ($fromTime -gt $toTime) { $codexReplied = $true }
            }
            if (-not $codexReplied) {
                $commitCount = ($unpushed | Measure-Object).Count
                $fileCount = ($productChanges | Measure-Object).Count
                $warnings += "Pushing $commitCount commit(s) with $fileCount product code file(s) changed. Hans (Codex) has not reviewed since last outbound message."
            }
        }
    }
}

# --- Check 2: Telegram inbox check (sendMessage only) ---
if ($command -match 'api\.telegram\.org.*sendMessage') {
    $warnings += "Check for incoming Telegram messages BEFORE sending."
}

# --- BLOCKING Check: Session log must be updated today before push ---
if ($command -match 'git push') {
    $sessionLogDir = "docs/80_PROJECT_HISTORY/session-logs/claude-code"
    if (Test-Path $sessionLogDir) {
        $today = (Get-Date).ToString("yyyy-MM-dd")
        $todayLogs = Get-ChildItem -Path $sessionLogDir -Filter "*.md" | Where-Object {
            $_.LastWriteTime.ToString("yyyy-MM-dd") -eq $today
        }
        if (-not $todayLogs -or $todayLogs.Count -eq 0) {
            $json = @{ error = "BLOCKED: No session log updated today. Update the session log before pushing." } | ConvertTo-Json -Compress
            Write-Output $json
            exit 2
        }
    } else {
        $json = @{ error = "BLOCKED: Session log directory not found at $sessionLogDir." } | ConvertTo-Json -Compress
        Write-Output $json
        exit 2
    }
}

# --- BLOCKING Check: Session log must be staged on git commit ---
# Bypass: include "[skip-session-log]" in the commit message to override.
if ($command -match 'git commit' -and $command -notmatch 'skip-session-log') {
    $sessionLogDir = "docs/80_PROJECT_HISTORY/session-logs/claude-code"
    $stagedSessionLog = git diff --cached --name-only -- $sessionLogDir 2>$null
    if (-not $stagedSessionLog) {
        $allStaged = git diff --cached --name-only 2>$null
        if ($allStaged -and @($allStaged).Count -gt 0) {
            $json = @{ error = "BLOCKED: No session log staged. Update the session log in claude-code/ before committing. Add [skip-session-log] to commit message to override." } | ConvertTo-Json -Compress
            Write-Output $json
            exit 2
        }
    }
}

# Output combined warnings if any
if ($warnings.Count -gt 0) {
    $combined = $warnings -join " | "
    $json = @{ systemMessage = "WARNING: $combined" } | ConvertTo-Json -Compress
    Write-Output $json
}

exit 0
