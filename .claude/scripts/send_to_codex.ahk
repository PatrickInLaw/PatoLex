; send_to_codex.ahk -- AutoHotkey v2 script
;
; PURPOSE:
;   Send a short message to the Codex CLI terminal to trigger it to
;   read a comms file. This is one half of a bidirectional message-
;   passing protocol between Claude Code and Codex CLI.
;
;   PROTOCOL:
;     1. Claude Code writes the full message to docs/00_Inbox/comms/to-codex.md
;     2. Claude Code runs this script to nudge Codex with a short fixed string
;     3. Codex reads docs/00_Inbox/comms/to-codex.md for the actual content
;     4. Codex writes its response to docs/00_Inbox/comms/from-codex.md
;     5. Claude Code reads docs/00_Inbox/comms/from-codex.md
;
; USAGE:
;   "C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe" send_to_codex.ahk
;   "C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe" send_to_codex.ahk "custom message"
;
;   If no argument is provided, the default message is:
;     "check docs/00_Inbox/comms/to-codex.md"
;
; PREREQUISITES:
;   - AutoHotkey v2.0+ installed
;   - A Windows Terminal tab with title containing "PatoLex_Codex"
;   - Codex CLI must be in an input-waiting state
;
; EXIT CODES:
;   0 = success (message sent)
;   1 = target window not found
;   2 = error during execution

#Requires AutoHotkey v2.0
#SingleInstance Force

A_IconHidden := true

logFile := A_ScriptDir "\comms.log"

LogEntry(message) {
    global logFile
    timestamp := FormatTime(, "2026-05-31 HH:mm:ss")
    try {
        FileAppend(timestamp " | " message "`n", logFile)
    }
}

try {
    SetTitleMatchMode(2)
    targetTitle := "PatoLex_Codex"

    messageToSend := "check docs/00_Inbox/comms/to-codex.md, do any review Claude asks for, and communicate a response back to Claude"
    if A_Args.Length > 0 {
        messageToSend := A_Args[1]
    }

    if !WinExist(targetTitle) {
        LogEntry("WINDOW_NOT_FOUND | No window matching '" targetTitle "' found")
        ExitApp(1)
    }

    WinActivate(targetTitle)
    if !WinWaitActive(targetTitle, , 5) {
        LogEntry("ACTIVATION_FAILED | Window found but could not activate within 5 seconds")
        ExitApp(2)
    }

    Sleep(500)
    SendText(messageToSend)
    Sleep(500)
    Send("{Enter}")
    Sleep(200)
    Send("{Enter}")

    LogEntry("SENT | '" messageToSend "' -> '" targetTitle "'")
    ExitApp(0)

} catch as err {
    LogEntry("ERROR | " err.Message " (line " err.Line ")")
    ExitApp(2)
}
