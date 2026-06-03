<#
  setup_3060.ps1 -- ELEVATED one-time setup of the 3060 as file server + queue-DB host.
  Operator runs this ONCE, elevated (Run as Administrator). The agent's SSH/PowerShell session
  is NOT elevated (UAC wall), so it cannot do this -- hence a hand-run registrar.

  Authoritative design: docs/30_SYSTEM_DESIGN/SQL_PIPELINE_DESIGN_2026-06-03.md (REVISION 2 / R2.1, R2.2).

  Creates: inbox/midbox/outbox dirs + SMB shares granted to the EXISTING <host>\patolex account
  (NO new user -- Patrick's constraint), Tailnet-only firewall exposure, and the queue DB/tables.

  Re-runnable: shares/dirs/firewall are create-if-absent; schema.sql is idempotent.
#>
[CmdletBinding()]
param(
    [string]$Root      = 'D:\PatoLex-pipeline',     # SSD or HDD -- either is fine
    [string]$Account   = "$env:COMPUTERNAME\patolex",
    [string]$Tailnet   = '100.64.0.0/10',
    [Parameter(Mandatory=$true)]
    [string]$SqlServer,                             # the 3060's MSSQL instance (see PatoAudio config), e.g. '.\SQLEXPRESS' or '.'
    [string]$SqlUser   = '',                         # SQL-auth login (R2.8: SQL auth expected). Empty => Windows (-E) auth.
    [string]$SqlPass   = '',
    [string]$SchemaSql = (Join-Path $PSScriptRoot 'schema.sql')
)

$ErrorActionPreference = 'Stop'

# --- must be elevated ---
$admin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw "Run this ELEVATED (Run as Administrator)." }

Write-Host "== PatoLex 3060 setup ==  root=$Root  account=$Account  tailnet=$Tailnet"

# --- 1. directories ---
foreach ($s in 'inbox','midbox','outbox') {
    $p = Join-Path $Root $s
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null; Write-Host "  created $p" }
}

# --- 2. shares + NTFS ACL, granted to the existing patolex account ---
foreach ($s in 'inbox','midbox','outbox') {
    $p = Join-Path $Root $s
    $share = "patolex_$s"
    if (-not (Get-SmbShare -Name $share -ErrorAction SilentlyContinue)) {
        New-SmbShare -Name $share -Path $p -FullAccess $Account | Out-Null
        Write-Host "  shared $share -> $p (FullAccess $Account)"
    }
    icacls $p /grant "${Account}:(OI)(CI)F" | Out-Null   # NTFS ACL (both share AND NTFS matter)
}

# --- 3. firewall: SMB inbound from the Tailnet ONLY (never public) ---
# Hans SERIOUS-7: scoping ONE rule leaves other SMB rules world-open, and Windows Firewall is
# allow-wins for inbound. So scope the WHOLE File-and-Printer-Sharing group AND add an explicit
# Block for 445 from non-Tailnet (Block overrides Allow), as defense-in-depth.
try {
    Get-NetFirewallRule -Group '@FirewallAPI.dll,-28502' -ErrorAction Stop |
        Set-NetFirewallRule -RemoteAddress $Tailnet
    Write-Host "  File-and-Printer-Sharing group scoped to $Tailnet"
} catch {
    Write-Warning "  could not scope the FPS group by GUID ($_). Falling back to FPS-SMB-In-TCP only -- VERIFY 445 is not otherwise open."
    Set-NetFirewallRule -Name 'FPS-SMB-In-TCP' -Enabled True -RemoteAddress $Tailnet
}
if (-not (Get-NetFirewallRule -Name 'BlockSMB-NonTailnet' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'BlockSMB-NonTailnet' -DisplayName 'Block SMB 445 (non-Tailnet)' `
        -Direction Inbound -Protocol TCP -LocalPort 445 -Action Block `
        -RemoteAddress 'Any' -Enabled True | Out-Null
}
# the Block rule denies 445 broadly; the scoped allow-group permits ONLY the Tailnet. Net: 445 = Tailnet-only.
Write-Host "  added Block-SMB-445-non-Tailnet (Block overrides Allow)"

# --- 4. queue DB + tables (idempotent schema.sql) ---
# Hans SERIOUS-8: R2.8 expects SQL auth. Use -U/-P if given, else fall back to Windows (-E).
# Whichever account is used MUST have dbcreator/sysadmin (CREATE DATABASE) on the instance.
if (-not (Test-Path $SchemaSql)) { throw "schema.sql not found at $SchemaSql" }
if ($SqlUser) {
    & sqlcmd -S $SqlServer -U $SqlUser -P $SqlPass -b -i $SchemaSql
} else {
    Write-Warning "  no -SqlUser given -> using Windows auth (-E). Ensure this elevated user is sysadmin/dbcreator."
    & sqlcmd -S $SqlServer -E -b -i $SchemaSql
}
if ($LASTEXITCODE -ne 0) { throw "sqlcmd failed applying $SchemaSql (exit $LASTEXITCODE) -- check CREATE DATABASE privilege" }
Write-Host "  schema applied via $SqlServer"

Write-Host "== done.  Next: on each worker box, store the patolex@3060 credential:"
Write-Host "   cmdkey /add:<3060-tailscale-ip> /user:$Account /pass:<PATOLEX-PASS>"
Write-Host "   and put PATOLEX_QUEUE_DSN in each box's gitignored dotenv (MSSQL conn, SQL-auth)."
