#!/usr/bin/env python3
"""
Scope enforcement test — proves the perimeter is real, not decorative.

Run:  python examples/scope_test.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from safety_protocol.core import (
    ActionRequest, AuditTrail, ScopeRule, target_matches, normalize_target,
)
from safety_protocol.protocol import SafetyProtocol

PASS = 0
FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")

# ── Unit: target matching primitives ──
print("\n[1] Target matching primitives")
check("normalize lowercases + strips slash",
      normalize_target("HTTPS://API.X/V1/Users/") == "https://api.x/v1/users")
check("prefix matches subpath",
      target_matches("https://api.x/v1", "https://api.x/v1/search", "prefix"))
check("prefix rejects sibling",
      not target_matches("https://api.x/v1", "https://api.x/v2/search", "prefix"))
check("glob matches wildcard",
      target_matches("https://api.x/v1/*", "https://api.x/v1/search", "glob"))
check("token blocks /api/admin",
      target_matches("admin", "https://api.x/api/admin/users", "token"))
check("token does NOT block readmymind",
      not target_matches("admin", "readmymind", "token"))
check("token does NOT block administrator (whole-token only)",
      not target_matches("admin", "administrator", "token"))
check("token blocks role=admin query",
      target_matches("admin", "https://x/v1/users?role=admin", "token"))
check("token does NOT block radmin (whole-token only)",
      not target_matches("admin", "https://x/v1/radmin/tools", "token"))
check("substring (legacy) over-blocks 'administrator' — the gap token fixes",
      target_matches("admin", "administrator", "substring"))

# ── Build a deny-by-default protocol with a full ruleset ──
print("\n[2] Deny-by-default protocol")
rules = [
    ScopeRule(
        action_type="api_call",
        allowed_targets=[
            "https://api.research.example/v1/search",
            "https://api.research.example/v1/summarize",
            "https://api.research.example/v1/analyze",
            "https://api.research.example/v1/users",
        ],
        match="prefix",
        forbidden_targets=["admin", "billing", "production", "internal", "config"],
        forbid_match="token",
        max_cost=5.0,
    ),
    ScopeRule(
        action_type="spend",
        allowed_targets=["compute", "storage"],
        max_cost=20.0,
        requires_approval=True,
    ),
    ScopeRule(
        action_type="send_message",
        allowed_targets=["alice", "team-channel"],
        max_cost=0.0,
    ),
]
protocol = SafetyProtocol(
    agent_id="a1", user_id="alice", scope_rules=rules,
    budget_limit=50.0, approval_threshold_cost=10.0,
    allowed_action_types=["api_call", "spend", "send_message"],
)

def res(action_type, target, cost=0.0, **kw):
    return protocol.execute(ActionRequest(
        action_type=action_type, target=target, estimated_cost=cost, **kw))

print("\n[3] Allowed path")
r = res("api_call", "https://api.research.example/v1/search", 3.0)
check("known-good api_call ALLOWED",
      r.outcome.value == "allowed", r.block_reason)

print("\n[4] The old holes — now closed")
# (a) invented verb -> blocked even though no rule forbids it
r = res("internal_transfer", "anything")
check("invented verb 'internal_transfer' DENIED (not in vocabulary)",
      r.outcome.value == "blocked_scope", r.block_reason)
# (b) unlisted target -> blocked by default-deny
r = res("api_call", "https://api.research.example/v1/delete")
check("unlisted api endpoint DENIED by default",
      r.outcome.value == "blocked_scope", r.block_reason)
# (c) forbidden token blocks real admin path
r = res("api_call", "https://api.research.example/v1/admin/users")
check("admin path DENIED (token match)",
      r.outcome.value == "blocked_scope", r.block_reason)
# (d) casing/encoding cannot sneak past allowlist
r = res("api_call", "HTTPS://API.RESEARCH.EXAMPLE/V1/SEARCH/", 3.0)
check("case-mismatched known target ALLOWED (normalized)",
      r.outcome.value == "allowed", r.block_reason)
# (e) a safe token that substring matching would have wrongly blocked
r = res("api_call", "https://api.research.example/v1/administrator/list")
check("'administrator' token != 'admin' -> DENIED only by allowlist, not forbidden",
      r.outcome.value == "blocked_scope", r.block_reason)
# (f) radmin is NOT in the allowlist -> default-deny blocks it (correct)
r = res("api_call", "https://api.research.example/v1/radmin/tools")
check("'radmin' not in allowlist -> DENIED by default (no false ALLOW)",
      r.outcome.value == "blocked_scope", r.block_reason)
# (g) a genuinely safe, listed endpoint is allowed
r = res("api_call", "https://api.research.example/v1/users")
check("listed 'users' endpoint ALLOWED (no false block)",
      r.outcome.value == "allowed", r.block_reason)

print("\n[5] Budget + approval still gate on allowed actions")
r = res("api_call", "https://api.research.example/v1/search", 99.0)
check("per-action cost cap blocks allowed target when over cap",
      r.outcome.value == "blocked_scope", r.block_reason)
r = res("spend", "compute", 20.0)
check("spend over approval threshold goes PENDING_APPROVAL",
      r.outcome.value == "pending_approval", r.block_reason)

print("\n[6] Default-deny is the global fallback")
loose = SafetyProtocol(
    agent_id="a2", user_id="alice", scope_rules=[],
    allowed_action_types=["api_call"],
)
r = loose.execute(ActionRequest(action_type="api_call", target="anything"))
check("empty ruleset + known verb still DENIED (no allowlist)",
      r.outcome.value == "blocked_scope", r.block_reason)

print("\n" + "=" * 60)
print(f"RESULT: {PASS} passed, {FAIL} failed")
print("=" * 60)
sys.exit(1 if FAIL else 0)
