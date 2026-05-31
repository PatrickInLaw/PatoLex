# Telegram Chat Skill

Bidirectional Telegram communication via @PatoClaude_bot.

## Bot Credentials
- Bot token: `8132154225:AAES0aP7B2Vmwykfu6VDtZqLHLSGHiwpRpw`
- Chat ID: `8525048490`

## Modes

### send (default)
Send a message to Patrick via Telegram.

Usage: `/telegram-chat send <message>`

Example: `/telegram-chat send [plx-cc01] Build complete, all tests pass.`

### check
Check for new messages from Patrick.

Usage: `/telegram-chat check`

### listen (standard ramp)
Poll for new messages using the standard ramp timing:
1. Check every **1 minute** for the first **10 checks**
2. Then every **10 minutes** for the next **5 checks**
3. Then every **30 minutes** indefinitely

If a message from Patrick is received, **reset the ramp** to step 1.

Usage: `/telegram-chat listen`

### monitor
Send a status update and then enter listen mode with standard ramp.

Usage: `/telegram-chat monitor <initial status message>`

## Implementation Notes

All calls use curl with `--data-urlencode` for sending and the getUpdates API for receiving.

### Send a message:
```bash
curl -s -X POST "https://api.telegram.org/bot8132154225:AAES0aP7B2Vmwykfu6VDtZqLHLSGHiwpRpw/sendMessage" \
  --data-urlencode "chat_id=8525048490" \
  --data-urlencode "text=<message>" 2>&1 | head -5
```

### Check for messages:
```bash
curl -s "https://api.telegram.org/bot8132154225:AAES0aP7B2Vmwykfu6VDtZqLHLSGHiwpRpw/getUpdates?offset=-5&limit=5" 2>&1 | head -20
```

### Standard Ramp Timing
When told to "run the telegram skill with the standard ramp" or "listen with standard ramp":
1. Send the initial status message
2. Sleep 60 seconds, check for messages -- repeat 10 times
3. Sleep 600 seconds, check for messages -- repeat 5 times
4. Sleep 1800 seconds, check for messages -- repeat indefinitely
5. On any message from Patrick (chat_id 8525048490, is_bot: false), reset to step 2

### Tips
- Use `head -5` on curl output to avoid SSL renegotiation stderr noise
- Session-tag messages with `[plx-ccNN]` for multi-session identification (PatoLex prefix)
- Can be used to ask Patrick questions when blocked on a task
