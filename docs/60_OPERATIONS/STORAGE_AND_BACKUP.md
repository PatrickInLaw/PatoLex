# Storage & Backup Architecture (2026-06-15)

Single source of truth + tiered offsite backup for the PatoLex corpus data (OCR consensus, parsed acts, renders, source PDFs). Non-binary that belongs in git (code, docs, the `ca_chapter_counts.tsv` oracle, small result TSVs) lives in the **repo**; bulk data lives on the boxes per the tiers below.

## Topology (measured)
- **5080** (`PKs_2025_Alien`, this workstation) is at **HOME**; the **5090** and **3060** are together in the **OFFICE**, on the **same gigabit switch** (subnet `192.168.1.0/24`: 5090 = `.202`, 3060 = `.78`).
- Home↔office is WAN over Tailscale: **~7 MB/s** to the 3060 (DERP-relayed), ~10 MB/s to the 5090.
- 5090↔3060 same-LAN: **58.5 MB/s measured over Wi-Fi** (the 5090's wired NIC is currently **unplugged** — it runs on Wi-Fi 7, 721 Mbps link; the 3060 is wired at 1 Gbps). **Plug the 5090 into the switch for true gigabit (~110 MB/s).**

## Tiers
| Tier | Location | Holds | Why |
|------|----------|-------|-----|
| **HOT / canonical** | **5090** local SSD (`C:\Users\patolex\PatoLex-scratch`, 1.8 TB / ~318 GB free) | active corpus: `production-*/ocr_consensus` + `parsed_acts*`, `_cascade` | GPU work reads local SSD at full speed; the single source of truth |
| **WARM / backup** | **3060 `F:` SSD** share `\\192.168.1.78\plwarm` (F:\PatoLex, 2 TB / ~1 TB free) | full replica of the active corpus | offsite (8 mi) DR replica; SSD |
| **COLD / archive** | **3060 `D:` HDD** share `\\192.168.1.78\plcold` (D:\PatoLexCold, 1 TB / ~855 GB free) | `page-renders` (regenerable) and other keep-but-slow data | cheap bulk; HDD speed irrelevant (WAN/Wi-Fi-bound) |

Per-box tooling stays local and is NOT backed up: `ocr-engines` (model weights, downloadable), `__pycache__`, `_vram_probe`, smoke/scratch dirs.

## Credentials & access
- **`patolex`** on both the 5090 and 3060 is an **SSH-key-only automation account** (Patrick logs in interactively via AzureAD; `patolex` is never an interactive/autologon user — `AutoAdminLogon=0` on the 3060, so resetting its password is reboot-safe).
- SSH to all boxes uses the ed25519 key `C:\Users\PatrickKolasinski\.ssh\patolex_5090` (firewall-restricted to the Tailnet `100.64.0.0/10`; **not** reachable over the raw LAN).
- **SMB** between 5090↔3060 uses the LAN IPs (`\\192.168.1.78\plwarm|plcold`), authed as `PK_XPS\patolex`. The 3060 `patolex` Windows password is in `PatoLex-secrets.env` as **`PATOLEX_3060_PASSWORD`** (reset 2026-06-15 — the original setup value was generated and never recorded).
- **Gotcha:** `cmdkey` cannot save a credential from an SSH (network) logon ("cannot be saved from this logon session"). For unattended SMB, pass the password to the job via **stdin** (transient) or `net use` with explicit creds — do NOT write a plaintext password file.

## Backup mechanism
`pipeline`-external script on the 5090: `C:\Users\patolex\pl_backup.ps1` (reads the 3060 password from stdin; `net use` to `plwarm`/`plcold`; **robocopy `/E /Z` COPY-ONLY**, never deletes the source; logs to `pl_backup.log`). Run it from the 5080 by piping the password over SSH:
```
$pw | ssh -i <key> patolex@100.70.54.56 "powershell -File C:\Users\patolex\pl_backup.ps1"
```
robocopy `/Z` is restartable — re-run resumes after any link blip; re-runs are incremental (skip unchanged), so it doubles as the verification/fold-in pass.

## Status (2026-06-15, first full run)
- Canonical 5090: **1850–1999 complete** (early decade 1850–1860 gathered from the 5080).
- WARM `plwarm`: **529.6 GB, robocopy 0 failures, hash-verified** (sample SHA256 source==backup).
- COLD `plcold`: **84.88 GiB renders, exact size match** to source.

## Open / follow-on
- **Wire the 5090** to the switch for gigabit (currently Wi-Fi).
- `pubinfo_*` (leginfo XML, ~25 GB, modern source) is still **5080-only** — fold into canonical+backup if wanted.
- Optional space reclaim: delete `page-renders` from the 5090 **after** confirming they're on `plcold` (regenerable) — a deletion, do only on explicit go.
- Durable scheduling: an unattended SYSTEM scheduled-task backup needs a DPAPI-encrypted credential (not the stdin/held-session method) — deferred.
