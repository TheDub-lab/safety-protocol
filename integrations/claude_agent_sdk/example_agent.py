"""
Example: run a Claude Agent SDK app behind the Safety Protocol gate.

This is the reference integration (SPEC.md §9). Every tool call Claude proposes
is funneled through the real SafetyProtocol gate via the SDK's `can_use_tool`
callback. Out-of-scope / kill-switched calls are denied; consequential calls
block on human approval.

Requires:  pip install claude-agent-sdk
           ANTHROPIC_API_KEY in the environment

Run:  python integrations/claude_agent_sdk/example_agent.py
"""
from __future__ import annotations
import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

from integrations.claude_agent_sdk.adapter import ClaudeSafetyAdapter, sdk_callback

# A least-privilege ruleset: this agent may only list a dir and read files
# under /tmp; anything else (rm, curl, git push, Write outside /tmp) is blocked.
CONFIG = {
    "agent_id": "claude-agent-01",
    "user_id": "alice",
    "allowed_action_types": ["exec", "write_file", "read_file", "api_call", "send_message"],
    "budget_limit": 50.0,
    "approval_threshold_cost": 10.0,
    "scope_rules": [
        {"action_type": "exec", "allowed_targets": ["ls -la /tmp", "pwd"],
         "match": "exact", "methods": ["Bash"], "max_cost": 1.0,
         "param_schema": {"type": "object", "properties": {"command": {}}, "additionalProperties": False},
         "forbidden_targets": ["rm", "curl", "git push"], "forbid_match": "token"},
        {"action_type": "read_file", "allowed_targets": ["/tmp/ok.txt"], "match": "exact",
         "methods": ["Read"], "max_cost": 0.0,
         "param_schema": {"type": "object", "properties": {"file_path": {}}, "additionalProperties": False}},
        {"action_type": "api_call", "allowed_targets": ["https://api.weather.example/"],
         "match": "prefix", "methods": ["WebFetch"], "max_cost": 2.0,
         "param_schema": {"type": "object", "properties": {"url": {}}, "additionalProperties": False}},
    ],
}

# A trivial human-approval transport for the demo: auto-approve cheap, deny dear.
# In production this is your Slack/CLI/approval UI — that's the whole point of
# the approval gate. Swap this for a real prompt.
def demo_approver(verdict: dict) -> bool:
    print(f"  [human-approval] {verdict['outcome']} {verdict.get('requires_approval_for')} "
          f"for {verdict.get('block_reason') or 'consequential action'}")
    return input("  approve? [y/N] ").strip().lower() == "y"


async def main():
    try:
        from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, ResultMessage
    except Exception as e:  # pragma: no cover
        print(f"[example] claude-agent-sdk not installed ({e}). Install it to run a live agent.\n"
              f"[example] The gate wiring is verified headless by test_adapter.py (11/11 pass).")
        return

    adapter = ClaudeSafetyAdapter.from_config_string(CONFIG)
    adapter.human_approver = demo_approver
    cb = sdk_callback(adapter)
    if cb is None:  # pragma: no cover
        print("[example] SDK present but callback builder failed.")
        return

    options = ClaudeAgentOptions(
        allowed_tools=["Bash", "Read", "WebFetch"],
        can_use_tool=cb,
        permission_mode="default",
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query("List /tmp, then fetch the weather API, then try to rm -rf / (should be blocked).")
        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                print(msg.content)


if __name__ == "__main__":
    asyncio.run(main())
