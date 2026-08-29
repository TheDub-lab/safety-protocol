# Safety Protocol × LangChain

Makes a LangChain agent **Safety-Protocol-compatible**: every tool call is
funneled through the real `SafetyProtocol` gate *before* it executes. The gate
— not the prompt — decides allow / block / approve.

This is the reference integration for **[SPEC.md](../SPEC.md) §9** (the guard
surface).

## Critical design note: wrapper, not callback

LangChain's `BaseCallbackHandler.on_tool_start` fires *before* a tool runs, but
its return value is **discarded** and raising there only blocks if
`raise_error=True` is set — and even then the framework may swallow it. The
LangChain maintainers' own guidance: governance that must allow/deny belongs in
a **tool-execution wrapper**, not a callback. So this adapter wraps each
`BaseTool` in a `SafetyProtocolTool` whose `_run`/`_arun` runs the gate first.
The callback (`make_audit_callback`) is used ONLY for the post-hoc audit trail,
never for the allow/deny decision.

This is why the integration actually *enforces* rather than merely *observes*.

## Mapping

| LangChain tool (by name) | Safety Protocol action | Enforced by |
|---|---|---|
| `shell` / `bash` / `terminal` / `command` | `exec` (target = command) | scope tokens, budget, kill switch |
| `write` / `edit` / `file_write` | `write_file` (target = path) | path allowlist |
| `read` / `open` / `file_read` | `read_file` (target = path) | path allowlist |
| `http` / `request` / `fetch` / `url` | `api_call` (target = URL) | URL allowlist + forbidden tokens |
| `slack` / `email` / `send_message` | `send_message` (target = channel) | channel allowlist |
| *anything else* | `action_type = <tool name>` | closed vocabulary → blocked unless permitted |

The mapping is the single translation point (`map_tool_call` in `adapter.py`).

## Install

```bash
pip install langchain-core langchain-openai
export OPENAI_API_KEY=sk-...
```

## Use

```python
from langchain_core.tools import Tool
from integrations.langchain.adapter import LangChainSafetyAdapter

adapter = LangChainSafetyAdapter.from_config("examples/guard_config.json")
adapter.human_approver = lambda verdict: input("approve? [y/N] ").lower() == "y"

raw_tools = [Tool(name="shell", func=run_cmd, description="Run a shell command"),
             Tool(name="http_request", func=get_url, description="HTTP GET")]
guarded = adapter.wrap_tools(raw_tools)     # pass THIS to the agent, not raw_tools

# ... build your agent with `guarded` as the tool list ...
```

A denied call raises (or returns) `Blocked by Safety Protocol: <reason>`; the
agent sees it as a normal tool error and can react. A too-broad config fails
closed (`from_config` refuses to start).

## Conformance

`test_adapter.py` checks the mapping + gate wiring against the **real**
`SafetyProtocol` (no LangChain needed, runs in CI). 14/14 clauses, including
**L8** which proves a blocked call does NOT invoke the wrapped tool at all
(pre-execution enforcement):

```bash
python integrations/langchain/test_adapter.py
# L1 mapping · L2 closed vocabulary · L3 in-scope allow · L4 forbidden blocked
# L5 approval (3 paths) · L6 kill switch · L7 fail-closed · L8 wrapper blocks pre-execution
```

`example_agent.py` is a runnable (LangChain-backed) demo with a least-privilege
ruleset; without LangChain it prints a clear note and exits.

## Honest limits

- The wrapper enforces for calls routed through the guarded tool list. A tool
  the agent reaches via a *different* path (e.g. a tool you forgot to wrap, or a
  background tool) is not gated — wrap every tool you hand the agent.
- `can`-style agents that call tools through other mechanisms should go through
  the same `wrap_tools` step; there is no complete mediation claim.
- Human approval is a pluggable `human_approver` callback — wire it to your real
  approval UI. The gate blocks pending a decision; it does not auto-approve.
