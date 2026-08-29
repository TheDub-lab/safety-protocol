"""Adapter conformance for the LangChain integration.

Checks the mapping + gate wiring against the REAL SafetyProtocol (no LangChain
needed, so it runs in CI). Mirrors the SPEC.md conformance style. The tool
WRAPPER path (pre-execution enforcement) is exercised with a fake callable tool.

Run:  python integrations/langchain/test_adapter.py
"""
from __future__ import annotations
import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

from integrations.langchain.adapter import LangChainSafetyAdapter, map_tool_call
from safety_protocol.core import ActionRequest
from safety_protocol.protocol import SafetyProtocol
from safety_protocol.core import ScopeRule


class FakeTool:
    """Minimal stand-in for a LangChain BaseTool (callable + .name)."""
    def __init__(self, name, fn):
        self.name = name
        self._fn = fn
    def func(self, *a, **k):
        return self._fn(*a, **k)


def _adapter(rules, **kw):
    kw.setdefault("budget_limit", 1000.0)
    kw.setdefault("approval_threshold_cost", 10.0)
    kw.setdefault("allowed_action_types", ["api_call", "exec", "write_file", "read_file", "send_message"])
    rules = rules if isinstance(rules, list) else [rules]
    p = SafetyProtocol("lc_agent", "alice", scope_rules=rules, **kw)
    class _G:
        def __init__(self, proto):
            self.proto = proto
        def guard(self, action_type, target, method=None, params=None, cost=0.0):
            req = ActionRequest(action_type=action_type, target=target, method=method,
                                 estimated_cost=cost, params=params or {})
            res = self.proto.execute(req)
            return {"outcome": res.outcome.value, "allowed": res.outcome.value == "allowed",
                    "block_reason": res.block_reason, "requires_approval_for": res.requires_approval_for,
                    "request_id": res.request_id}
        def approve(self, token, approved, approver):
            return self.proto.decide_approval(token, approved, approver)
    return LangChainSafetyAdapter(_G(p))


results = []


def chk(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")


# L1 — mapping: shell->exec, write->write_file, http->api_call
at, tg, _ = map_tool_call("shell", {"command": "rm -rf /"})
chk("L1", at == "exec" and "rm -rf" in tg, f"exec/{tg}")
at, tg, _ = map_tool_call("file_write", {"file_path": "/tmp/x", "content": "y"})
chk("L1", at == "write_file" and tg == "/tmp/x", f"write_file/{tg}")
at, tg, _ = map_tool_call("http_request", {"url": "https://evil/x"})
chk("L1", at == "api_call" and tg == "https://evil/x", f"api_call/{tg}")
# string-input normalization
at, tg, _ = map_tool_call("shell", "ls -la")
chk("L1", at == "exec" and tg == "ls -la", f"exec-str/{tg}")

# L2 — closed vocabulary: unknown tool verb blocked by deny-by-default
adapter = _adapter([ScopeRule(action_type="exec", allowed_targets=["ls -la"], match="exact",
                              methods=["shell"], max_cost=1.0)])
v = adapter.decide("MysteryTool", {"foo": "bar"})
chk("L2", v["behavior"] == "deny", f"unknown-verb -> {v['behavior']}")

# L3 — in-scope shell allowed
adapter = _adapter([ScopeRule(action_type="exec", allowed_targets=["ls -la"], match="exact",
                              methods=["shell"], max_cost=1.0)])
v = adapter.decide("shell", {"command": "ls -la"})
chk("L3", v["behavior"] == "allow", f"in-scope -> {v['behavior']}")

# L4 — forbidden shell command blocked (scope token)
adapter = _adapter([ScopeRule(action_type="exec", allowed_targets=["ls -la"], match="exact",
                              methods=["shell"], max_cost=1.0,
                              forbidden_targets=["rm"], forbid_match="token")])
v = adapter.decide("shell", {"command": "rm -rf /"})
chk("L4", v["behavior"] == "deny", f"rm blocked -> {v['behavior']}")

# L5 — approval path
adapter = _adapter([ScopeRule(action_type="exec", allowed_targets=["deploy"], match="exact",
                              methods=["shell"], max_cost=100.0)], approval_threshold_cost=2.0)
v = adapter.decide("shell", {"command": "deploy", "cost": 50.0})
chk("L5", v["behavior"] == "deny" and v["requires_approval"], f"no-approver -> {v['behavior']} needs_approval={v['requires_approval']}")
adapter.human_approver = lambda r: True
v = adapter.decide("shell", {"command": "deploy", "cost": 50.0})
chk("L5", v["behavior"] == "allow", f"approver=yes -> {v['behavior']}")
adapter2 = _adapter([ScopeRule(action_type="exec", allowed_targets=["deploy"], match="exact",
                               methods=["shell"], max_cost=100.0)], approval_threshold_cost=2.0)
adapter2.human_approver = lambda r: False
v = adapter2.decide("shell", {"command": "deploy", "cost": 50.0})
chk("L5", v["behavior"] == "deny", f"approver=no -> {v['behavior']}")

# L6 — kill switch freezes everything
adapter = _adapter([ScopeRule(action_type="exec", allowed_targets=["ls -la"], match="exact",
                              methods=["shell"], max_cost=1.0)])
adapter.guard.proto.engage_killswitch("test")
v = adapter.decide("shell", {"command": "ls -la"})
chk("L6", v["behavior"] == "deny", f"frozen -> {v['behavior']}")

# L7 — fail-closed on broad config
broad_cfg = {"agent_id": "x", "user_id": "a", "allowed_action_types": ["exec"],
             "scope_rules": [{"action_type": "exec", "allowed_targets": ["/"], "match": "prefix",
                              "methods": None, "param_schema": None, "max_cost": None}]}
path = os.path.join(os.environ.get("TMPDIR", "/tmp"), "broad_lc.json")
with open(path, "w") as f:
    json.dump(broad_cfg, f)
try:
    LangChainSafetyAdapter.from_config(path)
    chk("L7", False, "broad config was NOT rejected")
except RuntimeError:
    chk("L7", True, "broad config rejected (fail-closed)")

# L8 — WRAPPER enforces pre-execution: a blocked call must NOT invoke the tool
executed = {"hit": False}
def _danger():
    executed["hit"] = True
    return "BOOM"
tool = FakeTool("shell", _danger)
adapter = _adapter([ScopeRule(action_type="exec", allowed_targets=["ls -la"], match="exact",
                              methods=["shell"], max_cost=1.0,
                              forbidden_targets=["rm"], forbid_match="token")])
wrapped = adapter.wrap_tools([tool])[0]
out = wrapped._run(command="rm -rf /")
chk("L8", executed["hit"] is False, f"dangerous tool NOT executed -> out={out[:40]!r}")
# allowed call DOES execute
executed2 = {"hit": False}
tool2 = FakeTool("shell", lambda **k: executed2.__setitem__("hit", True) or "ok")
adapter2 = _adapter([ScopeRule(action_type="exec", allowed_targets=["ls -la"], match="exact",
                               methods=["shell"], max_cost=1.0)])
wrapped2 = adapter2.wrap_tools([tool2])[0]
out2 = wrapped2._run(command="ls -la")
chk("L8", executed2["hit"] is True and out2 == "ok", f"allowed tool executed -> {out2!r}")


ok = all(c for _, c, _ in results)
print(f"\nLANGCHAIN ADAPTER CONFORMANCE: {'PASS' if ok else 'FAIL'}  ({sum(c for _,c,_ in results)}/{len(results)})")
sys.exit(0 if ok else 1)
