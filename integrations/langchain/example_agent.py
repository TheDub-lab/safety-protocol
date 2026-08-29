"""
Example: run a LangChain agent behind the Safety Protocol gate.

This is the reference integration (SPEC.md §9). Every tool call is funneled
through the real SafetyProtocol gate via a tool WRAPPER (not a callback — see
integrations/langchain/README.md for why). Out-of-scope / kill-switched calls
are denied before execution; consequential calls block on human approval.

Requires:  pip install langchain-core langchain-openai
           OPENAI_API_KEY in the environment

Run:  python integrations/langchain/example_agent.py
"""
from __future__ import annotations
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

from integrations.langchain.adapter import LangChainSafetyAdapter


CONFIG = {
    "agent_id": "lc-agent-01",
    "user_id": "alice",
    "allowed_action_types": ["exec", "write_file", "read_file", "api_call", "send_message"],
    "budget_limit": 50.0,
    "approval_threshold_cost": 10.0,
    "scope_rules": [
        {"action_type": "exec", "allowed_targets": ["ls -la /tmp"], "match": "exact",
         "methods": ["shell"], "max_cost": 1.0},
        {"action_type": "read_file", "allowed_targets": ["/tmp/"], "match": "prefix",
         "methods": ["read"], "max_cost": 0.0},
        {"action_type": "api_call", "allowed_targets": ["https://api.weather.example/"],
         "match": "prefix", "methods": ["http"], "max_cost": 2.0},
    ],
}


def _adapter_from_dict(cfg: dict) -> LangChainSafetyAdapter:
    import json
    import tempfile
    p = os.path.join(tempfile.gettempdir(), "lc_guard_cfg.json")
    with open(p, "w") as f:
        json.dump(cfg, f)
    return LangChainSafetyAdapter.from_config(p)


def demo_approver(verdict: dict) -> bool:
    print(f"  [human-approval] {verdict['outcome']} {verdict.get('requires_approval_for')}")
    return input("  approve? [y/N] ").strip().lower() == "y"


def main():
    try:
        from langchain_core.tools import Tool
        from langchain_openai import ChatOpenAI
        from langchain.agents import AgentExecutor, create_openai_tools_agent
        from langchain_core.prompts import ChatPromptTemplate
    except Exception as e:  # pragma: no cover
        print(f"[example] langchain not installed ({e}). Install to run a live agent.\n"
              f"[example] The gate wiring is verified headless by test_adapter.py (14/14 pass).")
        return

    adapter = _adapter_from_dict(CONFIG)
    adapter.human_approver = demo_approver

    # Raw tools, then GATE them — pass `guarded` to the agent, not `raw_tools`.
    raw_tools = [
        Tool(name="shell", func=lambda cmd: f"ran: {cmd}", description="Run a shell command"),
        Tool(name="file_read", func=lambda p: f"read {p}", description="Read a file"),
        Tool(name="http_request", func=lambda u: f"fetched {u}", description="HTTP GET"),
    ]
    guarded = adapter.wrap_tools(raw_tools)

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    prompt = ChatPromptTemplate.from_messages([("system", "You are a helpful agent."),
                                               ("human", "{input}"), ("placeholder", "{agent_scratchpad}")])
    agent = create_openai_tools_agent(llm, guarded, prompt)
    runner = AgentExecutor(agent=agent, tools=guarded, verbose=True)
    runner.invoke({"input": "List /tmp, fetch the weather API, then try rm -rf / (should be blocked)."})


if __name__ == "__main__":
    main()
