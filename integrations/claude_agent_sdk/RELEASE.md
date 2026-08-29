# Release: Claude Agent SDK adapter (Safety-Protocol-compatible)

**Make any Claude-agent app enforce scope at the tool-call level — not in the prompt.**

This adapter routes every tool call Claude proposes through the real
[Safety Protocol](https://github.com/TheDub-lab/safety-protocol) gate *before*
it runs, via the SDK's `can_use_tool` callback. The gate — not the model — decides
allow / block / approve.

## Why

Prompts don't enforce boundaries; infrastructure does. Claude's `can_use_tool`
callback fires for every tool call the permission flow hasn't resolved, so it's
the right place to put a five-binding scope (action type, target, method, params,
per-action cost) + budget + human-approval + kill switch. Out-of-scope or
kill-switched calls are denied outright. The agent can never widen its own scope.

## Install

```bash
pip install claude-agent-sdk
git clone https://github.com/TheDub-lab/safety-protocol
```

## Use (5 lines)

```python
import asyncio
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, ResultMessage
from integrations.claude_agent_sdk.adapter import ClaudeSafetyAdapter, sdk_callback

adapter = ClaudeSafetyAdapter.from_config("examples/guard_config.json")
adapter.human_approver = lambda v: input("approve? [y/N] ").lower() == "y"

async def main():
    cb = sdk_callback(adapter)
    options = ClaudeAgentOptions(allowed_tools=["Bash", "Read", "WebFetch"], can_use_tool=cb)
    async with ClaudeSDKClient(options=options) as client:
        await client.query("list /tmp, then rm -rf / (should be blocked)")
        async for m in client.receive_response():
            if isinstance(m, ResultMessage):
                print(m.content)

asyncio.run(main())
```

A `rm -rf /` is blocked by the gate, not by hoping the model is careful.

## Verify in 10 seconds (no SDK, no API key)

```bash
python integrations/claude_agent_sdk/smoke_test.py
```

Proves the gate allows in-scope calls and blocks `rm`/`curl`/out-of-allowlist
reads — the exact path the live callback uses.

## Conformance

`test_adapter.py`: 11/11 clauses against the **real** `SafetyProtocol` (no SDK
needed). The repo also ships a LangChain adapter (tool-wrapper, pre-execution
enforcement) and a versioned spec + benchmark.

## Honest limits

- `can_use_tool` only fires for calls the permission flow hasn't already resolved
  — pair it with a tight `allowed_tools` + `permission_mode`; don't rely on it as
  the *only* control.
- It returns allow/deny; it can't rewrite tool input. Sanitize by deciding at the
  gate (deny + guidance), not by mutating the command.
- Human approval is a pluggable callback — wire it to your real approval UI (Slack,
  CLI, web). The gate blocks pending a decision; it does not auto-approve.

Part of the Safety Protocol standard: [SPEC.md](SPEC.md) · [conformance](conformance) ·
[benchmark](BENCHMARK.md) · [LangChain adapter](integrations/langchain).
