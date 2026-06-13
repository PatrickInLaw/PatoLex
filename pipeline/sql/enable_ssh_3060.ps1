<#
enable_ssh_3060.ps1 -- one-time setup: enable OpenSSH on the 3060 (PK_XPS), locked to the Tailnet, and
authorize the Claude key for the `patolex` account so the box becomes the durable pipeline hub (SQL queue
already lives here; SMB source/render store can follow). RUN IN AN ELEVATED PowerShell ON THE 3060.

Recipe notes: restrict via the FIREWALL RemoteAddress (100.64.0.0/10 = Tailscale CGNAT range), NOT
sshd ListenAddress (which fails to bind on the Tailscale wintun NIC). Admin accounts use the shared
administrators_authorized_keys with locked ACLs -- the user's ~/.ssh/authorized_keys is ignored for them.
#>

# 1. Install + auto-start OpenSSH Server
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-Service sshd -StartupType Automatic
Start-Service sshd

# 2. Restrict SSH to the Tailnet only; drop the default allow-all rule
Remove-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue
New-NetFirewallRule -Name 'sshd-tailnet' -DisplayName 'OpenSSH SSH Server (Tailnet only)' `
    -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -RemoteAddress 100.64.0.0/10

# 3. Authorize the Claude key for patolex (admin vs non-admin handled)
$pub = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIH3f1aAwVe1Qrx2NI2sOnazC8WzZuMUMqzteOI12MJFe patolex-claude-5080'
$isAdmin = [bool](Get-LocalGroupMember -Group 'Administrators' -ErrorAction SilentlyContinue |
                  Where-Object { $_.Name -like '*\patolex' -or $_.Name -eq 'patolex' })
if ($isAdmin) {
    $akf = "$env:ProgramData\ssh\administrators_authorized_keys"
    Add-Content -Path $akf -Value $pub
    icacls $akf /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F'
} else {
    New-Item -ItemType Directory -Force 'C:\Users\patolex\.ssh' | Out-Null
    Add-Content -Path 'C:\Users\patolex\.ssh\authorized_keys' -Value $pub
    icacls 'C:\Users\patolex\.ssh\authorized_keys' /inheritance:r /grant 'patolex:F' /grant 'SYSTEM:F' /grant 'Administrators:F'
}

# 4. Apply
Restart-Service sshd
Write-Output "OpenSSH enabled on the 3060, Tailnet-only, patolex key authorized (admin=$isAdmin)."
