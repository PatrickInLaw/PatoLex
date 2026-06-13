# SSH Access (5090 + 3060) — for repo agents

Cross-box SSH for the PatoLex pipeline. Credentials live in **Windows Credential Manager** (DPAPI-encrypted,
per-user on the 5080/PKs_2025_Alien), read via `~/.claude/scripts/CredStore.ps1`.

## WCM credential targets
| Target | Contents |
|--------|----------|
| `PatoLex_SSH_patolex_key`  | the ed25519 **private key** for the `patolex` account (both boxes trust it) |
| `PatoLex_SSH_hosts`        | JSON: `{user, 5090, 5090_shell, 3060, 3060_shell, key_wcm_target}` |
| `PatitoSql_PatitoQBCache_PatitoSync` | SQL login `PatitoSync` (db_owner of `PatoLexQueue` on the 3060) |

## Hosts
| Box | Tailscale IP | SSH user | default remote shell |
|-----|--------------|----------|----------------------|
| 5090 (pk-alien-5090, GPU/compute) | `100.70.54.56`  | `patolex` | **cmd** (use `&`, `findstr`, `dir`) |
| 3060 (PK_XPS, SQL queue + file server) | `100.113.254.6` | `patolex` | **PowerShell** (use `;`, `Where-Object`) |

A file copy of the key is also at `C:\Users\PatrickKolasinski\.ssh\patolex_5090` on the 5080.

## Use from an agent (restore key from WCM, then ssh)
```powershell
. "$env:USERPROFILE\.claude\scripts\CredStore.ps1"
$kf = Join-Path $env:TEMP 'patolex_key'
Get-CredSecret -Target 'PatoLex_SSH_patolex_key' | Set-Content -Path $kf -NoNewline -Encoding ascii
icacls $kf /inheritance:r /grant:r "$env:USERNAME:R" | Out-Null   # ssh refuses world-readable keys
ssh -i $kf -o BatchMode=yes patolex@100.70.54.56 "hostname"        # 5090 (cmd shell)
ssh -i $kf -o BatchMode=yes patolex@100.113.254.6 "hostname"       # 3060 (powershell shell)
```

## SQL queue (3060) from any box that can reach 100.113.254.6:1433
```powershell
. "$env:USERPROFILE\.claude\scripts\CredStore.ps1"
$pw = Get-CredSecret -Target PatitoSql_PatitoQBCache_PatitoSync
# Server=100.113.254.6\SQLEXPRESS;Database=PatoLexQueue;User Id=PatitoSync;Password=$pw;TrustServerCertificate=True
```
