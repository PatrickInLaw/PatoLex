# SSH over Tailscale — canonical setup for the compute boxes

Purpose: let Claude Code sessions (and operators) drive the GPU boxes (5080 / 5090 / 3060) over Tailscale for distributed OCR/compute — with SSH reachable **only** over the tailnet, never the LAN or public internet.

> **Hard-won lesson (2026-06-02):** do **NOT** restrict access by binding `sshd` to the Tailscale IP via `ListenAddress`. On Windows, sshd fails to start ("Failed to start service") because it can't bind a listener to Tailscale's wintun adapter IP at boot. **Enforce Tailscale-only at the FIREWALL instead** (`RemoteAddress 100.64.0.0/10`). sshd listens on `0.0.0.0`; the firewall drops every connection that isn't from a tailnet peer. Same security, and it actually starts. Hit on both the 5090 and 5080.

> **Second hard-won lesson (2026-06-02): Azure AD-joined boxes need a LOCAL account for SSH.** The boxes are Entra/Azure-AD-joined (`azuread\patrickkolasinski`). The sshd **service runs as LocalSystem**, which **cannot build a logon token for an Azure AD account** — sshd logs `get_passwd: lookup_sid() failed: 1332` and the client gets `Connection reset` after a clean key exchange. (Running `sshd -d` foreground in the user's own session works, which masks the problem — but the service won't.) **Fix: create a dedicated LOCAL admin account and SSH as that:**
> ```powershell
> $pw = Read-Host -AsSecureString 'Password for local patolex account'
> New-LocalUser -Name 'patolex' -Password $pw -FullName 'PatoLex Compute' -PasswordNeverExpires
> Add-LocalGroupMember -Group 'Administrators' -Member 'patolex'
> ```
> Since `patolex` is a local admin, the key already in `administrators_authorized_keys` works for it — connect as `ssh -i <key> patolex@<tailscale-ip>`. (Verified working on the 5090: returns `PK_Alien_5090`.)

## 1. Install + enable + restrict (Admin PowerShell on the target box)

```powershell
# Install OpenSSH Server (from Windows Update). If the WU download hangs, Ctrl+C and use winget:
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
#   winget install --id Microsoft.OpenSSH.Beta -e --accept-source-agreements --accept-package-agreements

# Service: start + auto-start
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic

# Firewall: drop the broad default rule (opens 22 on ALL interfaces), allow 22 ONLY from the Tailscale range
Remove-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue
New-NetFirewallRule -Name 'sshd-tailscale-only' -DisplayName 'OpenSSH SSH Server (Tailscale only)' `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 22 -RemoteAddress 100.64.0.0/10

# (Optional) make PowerShell the default SSH shell
New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell `
  -Value 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -PropertyType String -Force | Out-Null

# Verify
Get-Service sshd | Format-Table Name,Status,StartType
Get-NetFirewallRule -Name 'sshd-tailscale-only' | Format-Table DisplayName,Enabled,Action
```

`100.64.0.0/10` is Tailscale's CGNAT range (every tailnet IP is a `100.x` in that block). Optional tightest layer: a Tailscale **ACL** in the admin console limiting port 22 to specific devices.

## 2. If you (mistakenly) set ListenAddress and sshd won't start — remove it

```powershell
$cfg = 'C:\ProgramData\ssh\sshd_config'
(Get-Content $cfg) -notmatch '^\s*ListenAddress' | Set-Content $cfg
Start-Service sshd
Get-Service sshd
```
If it still fails, get the real reason: `& 'C:\Windows\System32\OpenSSH\sshd.exe' -ddd` (foreground debug, Ctrl+C to exit). A fresh-install failure is usually missing host keys → `ssh-keygen -A`.

## 3. Key-based auth (so automated sessions connect without passwords)

On the **client** box (e.g. the 5080):
```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh" | Out-Null
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\<keyname>" -N '' -C "<label>" -q
Get-Content "$env:USERPROFILE\.ssh\<keyname>.pub"   # copy this public key
```
On the **target** box (Admin PowerShell) — for an **admin** user the key MUST go in `administrators_authorized_keys` with restricted ACLs (Windows OpenSSH ignores it otherwise):
```powershell
$pub = 'ssh-ed25519 AAAA... <label>'   # the public key from the client
$f = 'C:\ProgramData\ssh\administrators_authorized_keys'
Add-Content -Path $f -Value $pub
icacls $f /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F'
```
(For a non-admin user instead: `C:\Users\<user>\.ssh\authorized_keys`.)

Connect from the client: `ssh -i "$env:USERPROFILE\.ssh\<keyname>" <user>@<tailscale-ip>`

## Box reference
- 5090 Tailscale IP: `100.70.54.56`. Get any box's own IP via `& 'C:\Program Files\Tailscale\tailscale.exe' ip -4`.
- Credentials/connection details for the boxes also live in the `patoaudio` / `kolalawdb` repos.
