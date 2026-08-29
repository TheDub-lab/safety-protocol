import sys
sys.path.insert(0, "src")
from safety_protocol.core import (
    ScopeRule, ActionRequest, AuditTrail, normalize_target, effective_cost,
)
from safety_protocol.protocol import SafetyProtocol
from safety_protocol.scope_linter import lint_rules, Severity

PREFIX = "alpha/"
SEARCH = "alpha/search"
ADMIN = "alpha/x/../../admin"

fails = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)

print("=== FIX 2: path traversal now denied ===")
prule = ScopeRule(action_type="api_call", allowed_targets=[PREFIX], match="prefix",
                  methods=["GET", "POST", "DELETE"], max_cost=100.0)
pp = SafetyProtocol("a", "alice", scope_rules=[prule], allowed_action_types=["api_call"])
check("traversal normalized past root to 'admin'", normalize_target(ADMIN) == "admin")
esc = pp.execute(ActionRequest("api_call", ADMIN, method="DELETE", estimated_cost=1.0, params={}))
check("traversal DELETE now BLOCKED", esc.outcome.value == "blocked_scope")
# legitimate in-prefix traversal still allowed
ok = pp.execute(ActionRequest("api_call", "alpha/x/../search", method="GET", estimated_cost=1.0, params={}))
check("in-prefix traversal 'alpha/search' still ALLOWED", ok.outcome.value == "allowed")

print("\n=== FIX 1: cost is not blindly trusted ===")
# Agent declares 0 for a $10000 action, but execution layer measured 10000.
rule = ScopeRule(action_type="api_call", allowed_targets=[SEARCH], match="exact",
                 methods=["POST"], param_schema={"required": ["q"], "properties": {"q": {"type": "string"}}, "additional_properties": False},
                 max_cost=5.0)
proto = SafetyProtocol("a", "alice", scope_rules=[rule], budget_limit=50.0, approval_threshold_cost=10.0,
                       allowed_action_types=["api_call"])
declared_zero = proto.execute(ActionRequest("api_call", SEARCH, method="POST",
                                             estimated_cost=0.0, measured_cost=10000.0, params={"q": "hi"}))
check("measured_cost=10000 -> BLOCKED by per-rule cap", declared_zero.outcome.value == "blocked_scope")
check("block reason mentions per-rule cap", "per-rule cap" in (declared_zero.block_reason or ""))
# Without a cost meter: estimate still enforced, and an advisory warning is
# logged. (estimated_cost=40 >= threshold -> pending_approval, which is fine;
# the assertion is only that the advisory warning fired.)
adv_rule = ScopeRule(action_type="api_call", allowed_targets=[SEARCH], match="exact",
                     methods=["POST"], param_schema={"required": ["q"], "properties": {"q": {"type": "string"}}, "additional_properties": False},
                     max_cost=None)
adv_proto = SafetyProtocol("a2", "alice", scope_rules=[adv_rule], budget_limit=50.0, approval_threshold_cost=10.0,
                           allowed_action_types=["api_call"])
adv_proto.execute(ActionRequest("api_call", SEARCH, method="POST", estimated_cost=40.0, params={"q": "hi"}))
check("no measured_cost -> budget_advisory logged",
      any(e["event_type"] == "budget_advisory" for e in adv_proto.audit.get_full_history("a2")))

print("\n=== FIX 3: linter now flags blanket action_type=None broad rule ===")
blanket = ScopeRule(action_type=None, allowed_targets=[PREFIX], match="prefix",
                    methods=None, param_schema=None, max_cost=None)
finds = lint_rules([blanket], ["api_call"])
codes = {(f.severity.value, f.code) for f in finds}
check("CATCH_ALL_PREFIX raised on None-rule", ("ERROR", "CATCH_ALL_PREFIX") in codes)
check("BLANKET_VERB WARN raised", ("WARN", "BLANKET_VERB") in codes)
check("NOT rated clean", bool(finds))

print("\n=== FIX 4: audit tamper-evidence (keyed mode) ===")
import copy
tr = AuditTrail(auth_key=b"supersecret")
for i in range(5):
    tr.append("action_allowed", "a", {"n": i})
check("keyed chain verifies clean", tr.verify_integrity() == [])
check("is_tamper_evident True", tr.is_tamper_evident())
root = tr.root_mac()
# tamper: rewrite an entry's data
tampered = copy.deepcopy(tr)
tampered._entries[2]["data"]["n"] = 999
check("tampering detected under key", tampered.verify_integrity() != [])
# unkeyed: old behavior, internal-consistency only
tu = AuditTrail()
for i in range(5):
    tu.append("action_allowed", "a", {"n": i})
check("unkeyed still verifies", tu.verify_integrity() == [])

print("\n=== RESULT:", "ALL PASS" if not fails else f"FAILURES: {fails}")
sys.exit(1 if fails else 0)
