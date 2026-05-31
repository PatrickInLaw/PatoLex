# UCP: Update session log, Commit, Push

Do all three steps in sequence without asking for confirmation.

## Step 1: Update Session Log

Find the current session's log file in `docs/80_PROJECT_HISTORY/session-logs/claude-code/`.
The file follows the naming convention: `SESSION_ccNNN_SUMMARY_2026-05-31_Title.md`

Update these sections with current progress:
- **What Was Done**: Add any new items completed since the last update
- **Decisions Made**: Add any new decisions
- **Files Changed**: Update file lists
- **Open Items at Close**: Update with current state

If no session log exists yet for this session, ask which session number to use.

## Step 2: Commit

Stage all modified files (the session log plus any other uncommitted work).
Write a descriptive commit message prefixed with the session ID (e.g., `cc001: ...`).
Include the co-author line:
```
Co-Authored-By: Claude Code <ClaudeCode@Kolasinski-Law.com>
```

## Step 3: Push

Push to origin immediately. Do not ask for confirmation.

## Notes

- If the working tree is clean (nothing to commit), say so and skip.
- If there are only session log updates, that's fine -- commit just the log.
- This is a routine workflow shorthand. No confirmation needed at any step.
