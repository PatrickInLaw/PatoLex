Spawn the `verify-auditor` agent to adversarially audit completed work. The agent runs in a separate context with no knowledge of the current session's reasoning or justifications.

**Argument:** `$ARGUMENTS` -- passed through as scope and context.
Format: `<phase|subgate|gate> [optional context]`

## Execution

1. Determine the model override based on scope:
   - `phase` or `subgate`: use `model: "sonnet"` (agent default, no override needed)
   - `gate`: use `model: "opus"` (override for full-depth analysis)

2. Spawn the **verify-auditor** agent with:
   - The model override (opus for gate scope only)
   - Prompt: `"Scope and context: $ARGUMENTS"`
   - The agent already knows its mandate, checklist, and execution strategy from its own definition and the /verify skill it will invoke

3. When the agent returns:
   - If verdict is **PASS**: report the result and proceed
   - If verdict is **FAIL**: list every finding and begin fixing them immediately. Do NOT proceed until all findings are resolved. After fixes, re-run `/verify` at the same scope to confirm.
   - If the agent itself fails (timeout, error): report the failure and fall back to invoking the `/verify` skill directly in the current session.

## Do Not

- Skip verification because "it looks fine"
- Mark findings as "will fix later"
- Proceed past a FAIL verdict without fixing and re-verifying
- Use opus for phase/subgate scope (wasteful)
- Use sonnet for gate scope when Codex is unavailable (insufficient depth)
