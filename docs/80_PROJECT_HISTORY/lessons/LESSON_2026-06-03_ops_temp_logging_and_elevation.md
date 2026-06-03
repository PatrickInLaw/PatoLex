# Lessons: temp logging + the OS-elevation wall (ops, 2026-06-03)

## 1. The thermal guardian is NOT a temperature logger
`thermal_guardian.ps1` / the `PatoLex_ThermalGuard_5090` task is a power **governor**: it
reads telemetry internally but only WRITES `thermal-guardian.log` when it *acts* (caps power,
fires an alert, errors). It does **not** produce a continuous temperature trace. Do not treat
it as the temp log. Continuous temp logging is a separate concern -> `temp_logger.ps1`.

## 2. A durable temp logger must be GATED-on-OCR + SIZE-CAPPED
An always-on logger sampling every 30s, left running for the months-long campaign, **clogs the
drive** (no rotation = unbounded growth; the SSDs are already tight, hence the rolling archiver).
`pipeline/temp_logger.ps1` therefore: (a) samples ONLY when an OCR worker process
(`ocr_only*`/`queue_worker*`) is alive, and (b) self-trims `gpu_temps.log` to the last N lines
once it passes a size cap. "Extra data is harmless" was wrong -- bound every long-lived log.

## 3. Scheduled-task registration needs OS admin elevation (UAC) -- separate from Claude Code permissions
The agent's PowerShell session is **not elevated**, so `Register-ScheduledTask` / `schtasks /create`
return **"Access is denied"**, and processes launched over SSH are **killed when the SSH session
closes**. Flipping Claude Code tool-permissions (the per-command prompt setting) does NOT grant
OS admin. So durable Scheduled Tasks (temp logger, guardian, OCR supervisors) must be registered
**elevated by the operator** (or Claude Code launched as Administrator). Pattern: deploy the
script + a `register_*.ps1`, the operator runs the registrar elevated once per box.
Corollary: a `schtasks /query` returning "Access is denied" (not "not found") CONFIRMS a SYSTEM
task exists -- the non-elevated session just can't read it.

## 4. Campaign autonomy is real, but watch for session-coupled stragglers
The OCR campaign runs via box-local Scheduled Tasks, independent of the agent session, so it kept
producing through an overnight auth-block (41 -> 54 volumes). BUT the 5080 OCR worker stopped
~07:41 around a session reset (task left "Ready", not "Running") and had to be restarted via
`schtasks /run PatoLex_OCR_5080`. Check BOTH boxes are actually `Running` after any session reset.

**ROOT CAUSE (found 2026-06-03):** the `PatoLex_OCR_5080` task runs as `PatrickKolasinski` with
**`LogonType=Interactive`** — so it only runs while that user is logged on and dies on logoff /
session reset. That is the mechanism behind the "07:41 straggler," not bad luck. The 5080's
interactive account is `azuread\patrickkolasinski` (Azure-AD; absent from `Get-LocalUser`), and
**no local `patolex` account exists on the 5080** (unlike the 3060/5090). Fix (folded into the
SQL-pipeline Step-1 setup): create a local `patolex` on the 5080 and re-register ALL 5080 PatoLex
tasks to run as it with a **stored password / "run whether user is logged on or not"** (non-
interactive) logon — which also enables `cmdkey` SMB auth that SYSTEM/interactive-only tasks can't
use. Lesson: **a Scheduled Task with `LogonType=Interactive` is NOT a durable service** — it is
session-coupled; durable box-local services need the password/S4U logon type.
