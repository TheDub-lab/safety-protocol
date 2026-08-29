"""Adapter conformance for the Claude Agent SDK integration.

Checks the mapping + gate wiring against the REAL SafetyProtocol (no SDK needed,
so it runs in CI). Mirrors the SPEC.md conformance style: each case is a clause.

Run:  python integrations/claude_agent_sdk/test_adapter.py
"""
from __future__ import annotations
import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, os.path.join(_ROOT, "examples"))

from integrations.claude_agent_sdk.adapter import (
    ClaudeSafetyAdapter, map_tool_call,
)
from safety_protocol.core import ActionRequest
from safety_protocol.protocol import SafetyProtocol
from safety_protocol.core import ScopeRule


def _adapter(rules, **kw):
    kw.setdefault("budget_limit", 1000.0)
    kw.setdefault("approval_threshold_cost", 10.0)
    kw.setdefault("allowed_action_types", ["api_call", "exec", "write_file", "send_message"])
    rules = rules if isinstance(rules, list) else [rules]
    p = SafetyProtocol("claude_agent", "alice", scope_rules=rules, **kw)
    # Wrap a minimal guard-like object exposing .guard / .approve
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
    return ClaudeSafetyAdapter(_G(p))


results = []


def _narrow():
    return ScopeRule(action_type="exec", allowed_targets=["ls -la"], match="exact",
                     methods=["Bash"], max_cost=1.0)


def chk(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")


# A1 — mapping: Bash -> exec, Write -> write_file, WebFetch -> api_call
at, tg, _ = map_tool_call("Bash", {"command": "rm -rf /"})
chk("A1", at == "exec" and "rm -rf" in tg, f"exec/{tg}")
at, tg, _ = map_tool_call("Write", {"file_path": "/tmp/x", "content": "y"})
chk("A1", at == "write_file" and tg == "/tmp/x", f"write_file/{tg}")
at, tg, _ = map_tool_call("WebFetch", {"url": "https://evil/x"})
chk("A1", at == "api_call" and tg == "https://evil/x", f"api_call/{tg}")

# A2 — closed vocabulary: unknown tool verb blocked by deny-by-default
rules = [_narrow()]
adapter = _adapter(_narrow())
v = adapter.decide("MysteryTool", {"foo": "bar"})
chk("A2", v["behavior"] == "deny", f"unknown-verb -> {v['behavior']}")

# A3 — in-scope Bash allowed
adapter = _adapter([ScopeRule(action_type="exec", allowed_targets=["ls -la"], match="exact",
                              methods=["Bash"], max_cost=1.0)])
v = adapter.decide("Bash", {"command": "ls -la"})
chk("A3", v["behavior"] == "allow", f"in-scope Bash -> {v['behavior']}")

# A4 — forbidden Bash command blocked (scope token)
adapter = _adapter([ScopeRule(action_type="exec", allowed_targets=["ls -la"], match="exact",
                              methods=["Bash"], max_cost=1.0,
                              forbidden_targets=["rm"], forbid_match="token")])
v = adapter.decide("Bash", {"command": "rm -rf /"})
chk("A4", v["behavior"] == "deny", f"rm blocked -> {v['behavior']} ({v['message'][:40]})")

# A5 — approval path: high-cost action requires human; deny-with-guidance when none wired
adapter = _adapter([ScopeRule(action_type="exec", allowed_targets=["deploy"], match="exact",
                              methods=["Bash"], max_cost=100.0)], approval_threshold_cost=2.0)
v = adapter.decide("Bash", {"command": "deploy", "cost": 50.0})
chk("A5", v["behavior"] == "deny" and v["requires_approval"], f"no-approver -> {v['behavior']} needs_approval={v['requires_approval']}")
# with approver wired, human yes -> allow
adapter.human_approver = lambda r: True
v = adapter.decide("Bash", {"command": "deploy", "cost": 50.0})
chk("A5", v["behavior"] == "allow", f"approver=yes -> {v['behavior']}")
# human no -> deny (fresh adapter so the prior approval whitelist doesn't carry over)
adapter2 = _adapter([ScopeRule(action_type="exec", allowed_targets=["deploy"], match="exact",
                                methods=["Bash"], max_cost=100.0)], approval_threshold_cost=2.0)
adapter2.human_approver = lambda r: False
v = adapter2.decide("Bash", {"command": "deploy", "cost": 50.0})
chk("A5", v["behavior"] == "deny", f"approver=no -> {v['behavior']}")

# A6 — kill switch freezes everything
adapter = _adapter([ScopeRule(action_type="exec", allowed_targets=["ls -la"], match="exact",
                              methods=["Bash"], max_cost=1.0)])
adapter.guard.proto.engage_killswitch("test")
v = adapter.decide("Bash", {"command": "ls -la"})
chk("A6", v["behavior"] == "deny", f"frozen -> {v['behavior']} ({v['message'][:30]})")

# A7 — from_config fails closed on a too-broad ruleset
broad_cfg = {"agent_id": "x", "user_id": "a", "allowed_action_types": ["exec"],
             "scope_rules": [{"action_type": "exec", "allowed_targets": ["/"], "match": "prefix",
                              "methods": None, "param_schema": None, "max_cost": None}]}
import tempfile
path = os.path.join(tempfile.gettempdir(), "broad_guard.json")
with open(path, "w") as f:
    json.dump(broad_cfg, f)
try:
    ClaudeSafetyAdapter.from_config(path)
    chk("A7", False, "broad config was NOT rejected")
except RuntimeError as e:
    chk("A7", True, "broad config rejected (fail-closed)")


def _narrow():
    return ScopeRule(action_type="exec", allowed_targets=["ls -la"], match="exact",
                     methods=["Bash"], max_cost=1.0)


ok = all(c for _, c, _ in results)
print(f"\nADAPTER CONFORMANCE: {'PASS' if ok else 'FAIL'}  ({sum(c for _,c,_ in results)}/{len(results)})")
sys.exit(0 if ok else 1)
