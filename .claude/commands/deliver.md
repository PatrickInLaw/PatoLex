Bump version, build, commit, push -- all via scripts. Minimal token usage.

Argument: `<commit message>`. Optionally prefix with `phase:`, `subgate:`, `gate:NN:`, or `skipbump:`.

Run these two commands in sequence. Report output only:

1. `powershell -ExecutionPolicy Bypass -File .claude/scripts/bump.ps1 -BumpType "<type or iteration>"`
   (skip if `skipbump:` prefix)
2. `powershell -ExecutionPolicy Bypass -File .claude/scripts/ship.ps1 -Message "<commit message>"`

If either fails, stop and show the error.
