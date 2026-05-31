<#
.SYNOPSIS
    Build (npm run build), commit, and push for PatoLex.
.PARAMETER Message
    Commit message (required).
.PARAMETER SkipBuild
    Skip npm run build (e.g., docs-only commits, or before Next.js project is scaffolded).
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Message,

    [Parameter()]
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = git rev-parse --show-toplevel

# Detect whether Next.js project exists (package.json with build script)
$packageJson = Join-Path $repoRoot "package.json"
$hasNextProject = $false
if (Test-Path $packageJson) {
    $pkg = Get-Content $packageJson -Raw | ConvertFrom-Json
    if ($pkg.scripts -and $pkg.scripts.build) {
        $hasNextProject = $true
    }
}

# --- Build ---
if (-not $SkipBuild -and $hasNextProject) {
    Write-Host "Building Next.js app..."
    & npm run build 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Build failed. Fix build errors before shipping."
        exit 1
    }
    Write-Host "Build OK"
} elseif (-not $hasNextProject) {
    Write-Host "No package.json with build script found -- skipping build (pre-scaffold mode)."
}

# --- Stage ---
$statusLines = git status --porcelain
if (-not $statusLines) {
    Write-Host "No changes to commit."
    exit 0
}

$filesToAdd = @()
foreach ($line in $statusLines) {
    $file = $line.Substring(3).Trim()
    if ($file -match " -> (.+)$") { $file = $Matches[1] }
    if ($file -match "\.(env|credentials|secret)$" -or
        $file -match "secrets\.env$" -or
        $file -match "^project-archives/[^/]+\.(7z|zip)$" -or
        $file -match "^pipeline/(data|raw|cache)/") {
        Write-Host "  Skipping: $file"
        continue
    }
    $filesToAdd += $file
}

if ($filesToAdd.Count -eq 0) {
    Write-Host "No files to stage."
    exit 0
}

Write-Host "Staging $($filesToAdd.Count) files..."
git add @filesToAdd

# --- Commit ---
$fullMessage = $Message + "`n`nCo-Authored-By: Claude Code <ClaudeCode@Kolasinski-Law.com>"
git commit -m $fullMessage
if ($LASTEXITCODE -ne 0) {
    Write-Error "Commit failed"
    exit 1
}
$hash = git rev-parse --short HEAD

# --- Push ---
git push
if ($LASTEXITCODE -ne 0) {
    Write-Error "Push failed"
    exit 1
}

Write-Host "$hash | pushed"
