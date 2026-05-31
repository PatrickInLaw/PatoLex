<#
.SYNOPSIS
    Bump version in VersionInfo.cs.
.PARAMETER BumpType
    show (read-only), iteration (default), phase, subgate, gate:NN, or set:x.x.x.x.x
.NOTES
    Tolerant of VersionInfo.cs not existing yet (pre-scaffold). In that case it
    creates the bump-token sentinel only, so dotnet build/test enforcement works
    once a project is added.
.EXAMPLES
    bump.ps1                     # bump iteration (II++)
    bump.ps1 -BumpType phase     # bump phase (PP++, II=1)
    bump.ps1 -BumpType subgate   # bump subgate (SS++, PP=1, II=1)
    bump.ps1 -BumpType gate:15   # set gate GG=15 (SS=1, PP=1, II=1)
    bump.ps1 -BumpType set:0.01.01.01.01  # set exact version
    bump.ps1 -BumpType show      # print current version without changing
#>
param(
    [Parameter()]
    [string]$BumpType = "iteration"
)

$ErrorActionPreference = "Stop"
$repoRoot = git rev-parse --show-toplevel
$bumpLog = Join-Path $repoRoot ".claude/scripts/bump.log"
$bumpToken = Join-Path $repoRoot ".claude/.bump-token"

# Locate VersionInfo.cs anywhere under src/
$versionFile = Get-ChildItem -Path (Join-Path $repoRoot "src") -Filter "VersionInfo.cs" -Recurse -File -ErrorAction SilentlyContinue |
               Select-Object -First 1

if (-not $versionFile) {
    Write-Host "No VersionInfo.cs found under src/. Pre-scaffold mode -- writing bump-token only."
    Set-Content $bumpToken "0.00.00.00.00" -NoNewline
    $timestamp = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, "Pacific Standard Time").ToString("2026-05-31 HH:mm:ss")
    Add-Content $bumpLog "$timestamp PT | $BumpType | (no VersionInfo.cs) -> token written"
    exit 0
}

$content = Get-Content $versionFile.FullName -Raw
if ($content -notmatch 'Version = "([^"]+)"') {
    Write-Error "Could not parse version from $($versionFile.FullName)"
    exit 1
}

$oldVersion = $Matches[1]
$parts = $oldVersion.Split('.')
if ($parts.Count -ne 5) {
    Write-Error "Version format unexpected: $oldVersion (need 5-part dotted)"
    exit 1
}

# Show mode: just print and exit
if ($BumpType -eq "show") {
    Write-Host $oldVersion
    exit 0
}

$prefix = [int]$parts[0]; $gg = [int]$parts[1]; $ss = [int]$parts[2]; $pp = [int]$parts[3]; $ii = [int]$parts[4]

switch -Regex ($BumpType) {
    "^(iteration|ii|build)$" { $ii++ }
    "^(phase|pp)$"           { $pp++; $ii = 1 }
    "^(subgate|ss)$"         { $ss++; $pp = 1; $ii = 1 }
    "^gate:(\d+)$"           { $gg = [int]$Matches[1]; $ss = 1; $pp = 1; $ii = 1 }
    "^set:(.+)$"             {
        $newVersion = $Matches[1]
        $content = $content -replace 'Version = "[^"]+"', "Version = `"$newVersion`""
        Set-Content $versionFile.FullName $content -NoNewline
        $timestamp = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, "Pacific Standard Time").ToString("2026-05-31 HH:mm:ss")
        Add-Content $bumpLog "$timestamp PT | set | $oldVersion -> $newVersion"
        Set-Content $bumpToken $newVersion -NoNewline
        Write-Host "Version: $oldVersion -> $newVersion"
        exit 0
    }
    default { Write-Error "Unknown bump type: $BumpType. Valid: show, iteration, phase, subgate, gate:NN, set:x.x.x.x.x"; exit 1 }
}

$newVersion = "{0}.{1:D2}.{2:D2}.{3:D2}.{4:D2}" -f $prefix, $gg, $ss, $pp, $ii
$content = $content -replace 'Version = "[^"]+"', "Version = `"$newVersion`""
Set-Content $versionFile.FullName $content -NoNewline

$timestamp = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, "Pacific Standard Time").ToString("2026-05-31 HH:mm:ss")
Add-Content $bumpLog "$timestamp PT | $BumpType | $oldVersion -> $newVersion"

Set-Content $bumpToken $newVersion -NoNewline

Write-Host "Version: $oldVersion -> $newVersion"
