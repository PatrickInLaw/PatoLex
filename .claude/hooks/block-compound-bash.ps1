# block-compound-bash.ps1
# PreToolUse hook on the Bash tool.
# Blocks compound bash commands that Patrick has explicitly forbidden:
#   - `cd ` at start of command or after a separator
#   - ` && ` (command chaining)
#   - `; ` or ` ;` (semicolon command separator)
#   - ` || ` (command chaining)
#
# Exits 2 (block) with stderr message shown back to Claude.
# Simple regex-based -- false positives on semicolons inside quoted strings
# are acceptable per explicit user instruction.

$ErrorActionPreference = 'Stop'

try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $payload = $raw | ConvertFrom-Json
} catch {
    # If stdin can't be parsed, don't block -- fail open so the hook itself
    # never becomes a blocker for unrelated reasons.
    exit 0
}

$command = $payload.tool_input.command
if ([string]::IsNullOrWhiteSpace($command)) { exit 0 }

$violations = @()

# 1. `cd` at start of command, or after a separator. Tab-tolerant.
if ($command -match '^\s*cd(\s|$)') {
    $violations += "command starts with 'cd' -- working directory is already correct; use absolute paths"
}
if ($command -match '[;&|]\s*cd(\s|$)') {
    $violations += "'cd' appears after a separator -- chaining through cd is forbidden"
}

# 2. && chaining
if ($command -match '\s&&\s') {
    $violations += "' && ' command chaining -- run commands separately"
}

# 3. || chaining
if ($command -match '\s\|\|\s') {
    $violations += "' || ' command chaining -- run commands separately"
}

# 4. Semicolon command separator. Block `; ` or ` ;` which almost always
# indicates chaining. False positive risk on semicolons inside quoted strings
# is accepted.
if ($command -match ';\s' -or $command -match '\s;') {
    $violations += "semicolon command chaining -- run commands separately"
}

if ($violations.Count -gt 0) {
    [Console]::Error.WriteLine("BLOCKED: compound bash command detected. Run one command, then the next separately. Use absolute paths, not cd.")
    foreach ($v in $violations) {
        [Console]::Error.WriteLine("  - $v")
    }
    [Console]::Error.WriteLine("Command: $command")
    exit 2
}

exit 0
