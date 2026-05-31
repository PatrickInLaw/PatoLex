param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("send", "send-file", "check")]
    [string]$Mode,

    [Parameter(Position = 1)]
    [string]$Text,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingText,

    [string]$SessionTag = "[plx-cc]",

    [string]$StatePath = "",

    [string]$MessagePath = ""
)

$ErrorActionPreference = "Stop"

# @PatoClaude_bot (shared across Patrick's repos -- replace if using a different bot)
$botToken = "8132154225:AAES0aP7B2Vmwykfu6VDtZqLHLSGHiwpRpw"
$chatId = "8525048490"
$apiBase = "https://api.telegram.org/bot$botToken"

if ([string]::IsNullOrWhiteSpace($StatePath)) {
    $StatePath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\telegram-state.json"))
}

if ((-not [string]::IsNullOrWhiteSpace($Text)) -and $RemainingText.Count -gt 0) {
    $Text = (@($Text) + $RemainingText) -join " "
} elseif ([string]::IsNullOrWhiteSpace($Text) -and $RemainingText.Count -gt 0) {
    $Text = $RemainingText -join " "
}

function Get-State {
    if (Test-Path $StatePath) {
        return Get-Content $StatePath -Raw | ConvertFrom-Json
    }
    return [pscustomobject]@{ last_seen_update_id = 0 }
}

function Save-State($state) {
    $dir = Split-Path -Parent $StatePath
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
    }
    $state | ConvertTo-Json | Set-Content -Path $StatePath
}

if ($Mode -eq "send-file") {
    if ([string]::IsNullOrWhiteSpace($MessagePath) -and -not [string]::IsNullOrWhiteSpace($Text)) {
        $MessagePath = $Text
        $Text = ""
    }
    if ([string]::IsNullOrWhiteSpace($MessagePath)) {
        throw "MessagePath is required for send-file mode."
    }
    if (-not (Test-Path $MessagePath)) {
        throw "Message file not found: $MessagePath"
    }
    $Text = Get-Content $MessagePath -Raw
}

if ($Mode -eq "send" -or $Mode -eq "send-file") {
    if ([string]::IsNullOrWhiteSpace($Text)) {
        throw "Text is required for send mode."
    }

    $sendResultJson = curl.exe -s -X POST "$apiBase/sendMessage" `
        --data-urlencode "chat_id=$chatId" `
        --data-urlencode "text=$SessionTag $Text"

    if ([string]::IsNullOrWhiteSpace($sendResultJson)) {
        throw "Telegram sendMessage returned no response."
    }

    $sendResult = $sendResultJson | ConvertFrom-Json
    if (-not $sendResult.ok) {
        throw "Telegram sendMessage failed."
    }

    Write-Output $sendResultJson
    exit 0
}

$state = Get-State
$resultJson = curl.exe -s -X POST "$apiBase/getUpdates"
$result = $resultJson | ConvertFrom-Json

if (-not $result.ok) {
    throw "Telegram getUpdates failed."
}

$updates = @($result.result)
if ($updates.Count -eq 0) {
    Write-Output "[]"
    exit 0
}

$newMessages = @()
$highestSeen = [int64]$state.last_seen_update_id

foreach ($update in $updates) {
    if ($update.update_id -gt $highestSeen) {
        $highestSeen = $update.update_id
    }
    if ($update.update_id -le $state.last_seen_update_id) { continue }
    if ($null -eq $update.message) { continue }
    if ($update.message.chat.id -ne [int64]$chatId) { continue }
    if ($update.message.from.is_bot) { continue }

    $newMessages += [pscustomobject]@{
        update_id = $update.update_id
        message_id = $update.message.message_id
        date = $update.message.date
        text = $update.message.text
    }
}

$state.last_seen_update_id = $highestSeen
Save-State $state

$newMessages | ConvertTo-Json -Compress
