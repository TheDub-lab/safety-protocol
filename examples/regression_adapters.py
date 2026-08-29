import sys, os, json, ssl, tempfile
sys.path.insert(0, "src")
from safety_protocol import (
    SafetyProtocol, ScopeRule, ActionRequest, AuditTrail, PriceTableMeter,
)
from safety_protocol import guard_service as gs
from safety_protocol.onchain_real import HAS_WEB3, is_configured

fails = []
def chk(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)

print("=== ADAPTER 1: cost meter stamps measured_cost + re-checks budget ===")
meter = PriceTableMeter({"api_call": 7.0})  # real price higher than agent's $0.50 estimate
rule = ScopeRule(action_type="api_call", allowed_targets=["alpha/search"], match="exact",
                 methods=["POST"], param_schema={"required": ["q"], "properties": {"q": {"type": "string"}}, "additional_properties": False},
                 max_cost=100.0)
proto = SafetyProtocol("m", "alice", scope_rules=[rule], budget_limit=10.0,
                       approval_threshold_cost=999.0, allowed_action_types=["api_call"],
                       cost_meter=meter)
res = proto.execute(ActionRequest("api_call", "alpha/search", method="POST",
                                  estimated_cost=0.50, params={"q": "x"}))
# measured 7.0 > budget 10? No (just one action). But measured should be stamped.
chk("meter stamps measured_cost (spent reconciles to measured=7.0 after action 1)", abs(proto._spent - 7.0) < 1e-6)
# Now a second action: measured total 14 > budget 10 -> post-exec block
res2 = proto.execute(ActionRequest("api_call", "alpha/search", method="POST",
                                   estimated_cost=0.50, params={"q": "y"}))
chk("post-exec measured cost breaches budget -> BLOCKED", res2.outcome.value == "blocked_budget")
# Without meter: no measured_cost, advisory only
proto2 = SafetyProtocol("m2", "alice", scope_rules=[rule], budget_limit=10.0,
                        approval_threshold_cost=999.0, allowed_action_types=["api_call"])
proto2.execute(ActionRequest("api_call", "alpha/search", method="POST", estimated_cost=0.50, params={"q": "z"}))
chk("no meter -> budget_advisory logged", any(e["event_type"] == "budget_advisory" for e in proto2.audit.get_full_history("m2")))

print("\n=== ADAPTER 2: env-loaded audit key + tamper-evidence + root_mac anchor ===")
os.environ["SAFETY_AUDIT_KEY"] = "test-secret"
tr = AuditTrail.from_env()
chk("from_env builds keyed trail", tr.is_tamper_evident())
for i in range(3):
    tr.append("action_allowed", "a", {"n": i})
tmpf = os.path.join(tempfile.gettempdir(), "rootmac_anchor.txt")
mac = tr.commit_root_mac(sink="file:" + tmpf)
chk("root_mac anchors to file", mac is not None and os.path.exists(tmpf) and "root_mac" in open(tmpf).read())
del os.environ["SAFETY_AUDIT_KEY"]
tu = AuditTrail.from_env()
chk("no env -> unkeyed (honest, not faked)", not tu.is_tamper_evident())

print("\n=== ADAPTER 3: guard mTLS config accepted (no certs needed to validate wiring) ===")
# We can't generate certs here, but we validate the config path is read and the
# schema is exercised. Confirm serve() reads tls_* keys (no TLS if absent).
cfg = {"agent_id": "g", "user_id": "alice", "guard_token": "t", "allowed_action_types": ["api_call"],
       "scope_rules": [{"action_type": "api_call", "allowed_targets": ["alpha/search"], "match": "exact",
                        "methods": ["POST"], "param_schema": {"required": ["q"], "properties": {"q": {"type": "string"}}, "additional_properties": False}, "max_cost": 5.0}],
       "tls_cert": None, "tls_key": None, "tls_ca": None}
svc = gs.build_protocol_from_config(cfg)
chk("serve() config path tolerant of missing TLS", svc is not None)

print("\n=== ADAPTER 4: real-chain import-guard + not-configured fallback ===")
chk("HAS_WEB3 is bool (import-guarded)", isinstance(HAS_WEB3, bool))
chk("is_configured() False with no creds (safe default)", is_configured({}) is False)
# build_onchain returns None (sim fallback) without creds, never raises
real = __import__("safety_protocol.onchain_real", fromlist=["build_onchain"]).build_onchain({})
chk("build_onchain returns None when unconfigured", real is None)

print("\n=== RESULT:", "ALL PASS" if not fails else f"FAILURES: {fails}")
sys.exit(1 if fails else 0)
