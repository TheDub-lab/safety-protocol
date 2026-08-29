# Safety Protocol × Claude Agent SDK

Makes a Claude-agent app **Safety-Protocol-compatible**: every tool call Claude
proposes is funneled through the real `SafetyProtocol` gate *before* it runs.
The gate — not the prompt — decides allow / block / approve.

This is the reference integration for **[SPEC.md](../SPEC.md) §9** (the guard
surface). It uses the SDK's own `can_use_tool` callback, which fires for every
tool call the permission flow hasn't already resolved — exactly where
infrastructure-enforced scope belongs.

## What it does

| Claude tool | Safety Protocol action | Enforced by |
|---|---|---|
| `Bash` | `exec` (target = command) | scope tokens, budget, kill switch |
| `Write` / `Edit` / `NotebookEdit` | `write_file` (target = path) | path allowlist |
| `Read` | `read_file` (target = path) | path allowlist |
| `WebFetch` / `WebSearch` | `api_call` (target = URL/query) | URL allowlist + forbidden tokens |
| `Slack` / `send_message` | `send_message` (target = channel) | channel allowlist |
| *anything else* | `action_type = <tool_name>` | closed vocabulary → blocked unless permitted |

The mapping is the single translation point (`map_tool_call` in `adapter.py`) —
edit policy there, not in the gate.

## Install

```bash
pip install claude-agent-sdk
export ANTHROPIC_API_KEY=sk-...
```

## Use

```python
import asyncio
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, ResultMessage
from integrations.claude_agent_sdk.adapter import ClaudeSafetyAdapter, sdk_callback

adapter = ClaudeSafetyAdapter.from_config("examples/guard_config.json")
adapter.human_approver = lambda verdict: input("approve? [y/N] ").lower() == "y"

async def main():
    cb = sdk_callback(adapter)            # converts verdict -> PermissionResultAllow/Deny
    options = ClaudeAgentOptions(
        allowed_tools=["Bash", "Write", "Read", "WebFetch"],
        can_use_tool=cb,                  # <-- the gate
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query("do the thing")
        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                print(msg.content)

asyncio.run(main())
```

The agent can **never widen its own scope** — it only sends intents; the gate
disposes. A too-broad config fails closed (`from_config` refuses to start).

## Conformance

`test_adapter.py` checks the mapping + gate wiring against the **real**
`SafetyProtocol` (no SDK needed, runs in CI). 11/11 clauses:

```bash
python integrations/claude_agent_sdk/test_adapter.py
# A1 mapping · A2 closed vocabulary · A3 in-scope allow · A4 forbidden blocked
# A5 approval (no-approver deny / yes allow / no deny) · A6 kill switch · A7 fail-closed
```

`example_agent.py` is a runnable (SDK-backed) demo with a least-privilege
ruleset; without the SDK it prints a clear note and exits, since the gate
wiring is already proven by `test_adapter.py`.

## Notes / honest limits

- The SDK's `can_use_tool` only fires for calls the permission flow hasn't
  *already* resolved. Pair `allowed_tools` with a tight allowlist +
  `permission_mode` so the gate is your last line of defense, not your only one.
- `can_use_tool` returns allow/deny; it cannot rewrite tool input. To sanitize
  a command, decide at the gate (deny + guidance) rather than mutate it.
- Human approval here is a pluggable `human_approver` callback — wire it to your
  real approval UI (Slack, CLI, web). The gate blocks pending a decision; it
  does not auto-approve.
