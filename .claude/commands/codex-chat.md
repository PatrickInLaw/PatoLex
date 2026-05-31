# Codex Chat Skill

Bidirectional communication with Codex CLI via file-based message passing + AHK nudge.

## Protocol

Messages go through files in `docs/00_Inbox/comms/`. A transcript watcher (run by Patrick in a separate terminal via `comms-watcher.ps1`) auto-captures everything.

## Modes

### send (default)
Send a message to Codex CLI.

Usage: `/codex-chat send <message>`

Steps:
1. Write the message to `docs/00_Inbox/comms/to-codex.md` (overwrite the file)
2. Format the file with a header: `# Message to Codex CLI`, `**From:** Claude Code`, `**Date:** <timestamp>`, then `---`, then the message body
3. Run the AHK nudge:
```bash
"C:/Program Files/AutoHotkey/v2/AutoHotkey64.exe" .claude/scripts/send_to_codex.ahk
```
4. Report to the user that the message was sent

### check
Read the latest response from Codex.

Usage: `/codex-chat check`

Steps:
1. Read `docs/00_Inbox/comms/from-codex.md`
2. Display the content to the user

### wait
Send a message and poll for a response.

Usage: `/codex-chat wait <message>`

Steps:
1. Perform the `send` steps above
2. Poll `docs/00_Inbox/comms/from-codex.md` every 30 seconds for up to 5 minutes
3. Detect a response by checking if the file content has changed from its pre-send state
4. When a new response appears, display it to the user
5. If no response after 5 minutes, report timeout

## File Locations

- Outbox: `docs/00_Inbox/comms/to-codex.md` (CC writes, Codex reads)
- Inbox: `docs/00_Inbox/comms/from-codex.md` (Codex writes, CC reads)
- Transcript: `docs/00_Inbox/comms/transcript.md` (auto-captured, do not edit)
- AHK script: `.claude/scripts/send_to_codex.ahk`
- Transcript watcher: `.claude/scripts/comms-watcher.ps1` (run by Patrick)

## Important Notes

- The AHK script targets a terminal tab titled `PatoLex_Codex` -- it must be open
- The transcript watcher must be running for history capture
- Always overwrite the comms file, never append -- the watcher handles history
- Codex may take time to respond depending on what it's working on
