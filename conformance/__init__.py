"""Safety Protocol conformance suite — run with `python conformance/run.py`.

Maps directly to SPEC.md clauses C1..C10. A guard/implementation passes when
every clause holds. Importable: `from conformance import run_all` returns
(bool ok, list[result]).
"""
from __future__ import annotations
import sys
import copy
import os
import json

# Make the repo's src importable whether run from repo root or conformance/.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))

from safety_protocol.core import (
    ScopeRule, ActionRequest, AuditTrail, normalize_target, effective_cost,
)
from safety_protocol.protocol import SafetyProtocol
from safety_protocol.scope_linter import lint_rules, Severity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _proto(rules, **kw):
    kw.setdefault("budget_limit", 1000.0)
    kw.setdefault("approval_threshold_cost", 10.0)
    kw.setdefault("allowed_action_types", ["api_call", "spend", "payment", "send_message"])
    return SafetyProtocol("agent", "alice", scope_rules=rules, **kw)


def _g(path):
    return path


# ---------------------------------------------------------------------------
# Clause tests — each returns (clause, passed, detail)
# ---------------------------------------------------------------------------
def c1_deny_by_default():
    p = _proto([])
    r = p.execute(ActionRequest("api_call", "https://x/y", method="GET", params={}))
    return "C1", r.outcome.value == "blocked_scope", f"no-rule outcome={r.outcome.value}"


def c2_closed_vocabulary():
    p = _proto([ScopeRule(action_type="api_call", allowed_targets=["https://x/y"],
                          match="exact", methods=["GET"], max_cost=5.0)])
    r = p.execute(ActionRequest("internal_transfer", "https://x/y", method="GET", params={}))
    return "C2", r.outcome.value == "blocked_scope", f"invented-verb outcome={r.outcome.value}"


def c3_five_bindings():
    rule = ScopeRule(
        action_type="api_call", allowed_targets=["https://x/v1/search"], match="exact",
        methods=["POST"],
        param_schema={"required": ["q"], "properties": {"q": {"type": "string"}},
                      "additional_properties": False},
        max_cost=5.0)
    p = _proto([rule])
    allow = p.execute(ActionRequest("api_call", "https://x/v1/search", method="POST",
                                     params={"q": "hi"}, estimated_cost=1.0))
    method_block = p.execute(ActionRequest("api_call", "https://x/v1/search", method="DELETE",
                                            params={"q": "hi"}, estimated_cost=1.0))
    # Param violation: additional_properties=False rejects an unknown key.
    param_block = p.execute(ActionRequest("api_call", "https://x/v1/search", method="POST",
                                           params={"q": "hi", "evil": "x"}, estimated_cost=1.0))
    cap_block = p.execute(ActionRequest("api_call", "https://x/v1/search", method="POST",
                                         params={"q": "hi"}, estimated_cost=50.0))
    ok = (allow.outcome.value == "allowed"
          and method_block.outcome.value == "blocked_scope"
          and param_block.outcome.value == "blocked_scope"
          and cap_block.outcome.value == "blocked_scope")
    return "C3", ok, f"allow={allow.outcome.value} method={method_block.outcome.value} param={param_block.outcome.value} cap={cap_block.outcome.value}"


def c4_forbidden_tokens():
    from safety_protocol.core import target_matches
    # Token matching: 'admin' blocks /api/admin and ?role=admin, but NOT
    # lookalikes readmymind / administrator (whole-token, no false positives).
    blocks_admin = target_matches("admin", "https://x/api/admin", "token")
    blocks_role = target_matches("admin", "https://x/v1/ok?role=admin", "token")
    no_readmymind = not target_matches("admin", "https://x/readmymind", "token")
    no_administrator = not target_matches("admin", "https://x/administrator", "token")
    # And under a narrow allowlist, all four are scope-denied (deny-by-default).
    rule = ScopeRule(action_type="api_call", allowed_targets=["https://x/v1/ok"],
                     match="exact", methods=["GET"], max_cost=5.0,
                     forbidden_targets=["admin"], forbid_match="token")
    p = _proto([rule])
    denies = all(p.execute(ActionRequest("api_call", t, method="GET", params={})).outcome.value == "blocked_scope"
                 for t in ["https://x/api/admin", "https://x/v1/ok?role=admin",
                           "https://x/readmymind", "https://x/administrator"])
    ok = blocks_admin and blocks_role and no_readmymind and no_administrator and denies
    return "C4", ok, f"admin={blocks_admin} role={blocks_role} readmymind={no_readmymind} administrator={no_administrator} all_denied={denies}"


def c5_traversal():
    rule = ScopeRule(action_type="api_call", allowed_targets=["https://x/v1/"], match="prefix",
                     methods=["GET", "POST", "DELETE"], max_cost=100.0)
    p = _proto([rule])
    esc = p.execute(ActionRequest("api_call", "https://x/v1/sub/../../admin", method="DELETE",
                                   estimated_cost=1.0, params={}))
    legit = p.execute(ActionRequest("api_call", "https://x/v1/a/../search", method="GET",
                                     estimated_cost=1.0, params={}))
    ok = (esc.outcome.value == "blocked_scope"
          and normalize_target("https://x/v1/sub/../../admin") == "https://x/admin"
          and legit.outcome.value == "allowed")
    return "C5", ok, f"escape={esc.outcome.value} legit={legit.outcome.value}"


def c6_linter_fail_closed():
    broad = ScopeRule(action_type="api_call", allowed_targets=["https://x/v1/"], match="prefix",
                      methods=None, param_schema=None, max_cost=None)
    blanket = ScopeRule(action_type=None, allowed_targets=["https://x/v1/"], match="prefix",
                        methods=None, param_schema=None, max_cost=None)
    f_broad = lint_rules([broad], ["api_call"])
    f_blanket = lint_rules([blanket], ["api_call"])
    blocking = lambda fs: any(x.severity in (Severity.ERROR, Severity.WARN) for x in fs)
    codes = {(x.severity.value, x.code) for x in f_broad + f_blanket}
    ok = (blocking(f_broad) and blocking(f_blanket)
          and ("ERROR", "CATCH_ALL_PREFIX") in codes
          and ("WARN", "BLANKET_VERB") in codes)
    return "C6", ok, f"codes={sorted(codes)}"


def c7_cost_authority():
    rule = ScopeRule(action_type="api_call", allowed_targets=["https://x/v1/search"], match="exact",
                     methods=["POST"], param_schema={"required": ["q"], "properties": {"q": {"type": "string"}},
                                                      "additional_properties": False}, max_cost=5.0)
    p = _proto([rule])
    lied = p.execute(ActionRequest("api_call", "https://x/v1/search", method="POST",
                                   estimated_cost=0.0, measured_cost=10000.0, params={"q": "hi"}))
    unmeasured = _proto([ScopeRule(action_type="api_call", allowed_targets=["https://x/v1/search"],
                                    match="exact", methods=["POST"], max_cost=None,
                                    param_schema={"required": ["q"], "properties": {"q": {"type": "string"}},
                                                  "additional_properties": False})])
    u = unmeasured.execute(ActionRequest("api_call", "https://x/v1/search", method="POST",
                                          estimated_cost=40.0, params={"q": "hi"}))
    adv = any(e["event_type"] == "budget_advisory" for e in unmeasured.audit.get_full_history("agent"))
    ok = (lied.outcome.value == "blocked_scope" and adv)
    return "C7", ok, f"lie_outcome={lied.outcome.value} unmeasured_advisory={adv}"


def c8_audit_integrity():
    tr = AuditTrail(auth_key=b"k")
    for i in range(5):
        tr.append("action_allowed", "agent", {"n": i})
    clean = tr.verify_integrity() == []
    tampered = copy.deepcopy(tr)
    tampered._entries[2]["data"]["n"] = 999
    detected = tampered.verify_integrity() != []
    ok = clean and detected and tr.is_tamper_evident() and tr.root_mac() is not None
    return "C8", ok, f"clean={clean} detected={detected} root={tr.root_mac() is not None}"


def c9_guard_auth():
    # Guard auth is exercised in regression_guard_auth.py (live HTTP). Here we
    # assert the contract object exists and refuses when enabled + no token.
    from safety_protocol.guard_service import GuardAuth
    g = GuardAuth("s3cret")
    denied = not g.check({"Authorization": "Bearer wrong"})
    allowed = g.check({"Authorization": "Bearer s3cret"})
    ok = g.enabled and denied and allowed
    return "C9", ok, f"enabled={g.enabled} denied_wrong={denied} allowed_right={allowed}"


def c10_kill_switch():
    p = _proto([ScopeRule(action_type="api_call", allowed_targets=["https://x/y"], match="exact",
                          methods=["GET"], max_cost=5.0)])
    p.engage_killswitch("test")
    r = p.execute(ActionRequest("api_call", "https://x/y", method="GET", params={}))
    return "C10", r.outcome.value == "blocked_killswitch", f"frozen_outcome={r.outcome.value}"


CLAUSES = [c1_deny_by_default, c2_closed_vocabulary, c3_five_bindings, c4_forbidden_tokens,
           c5_traversal, c6_linter_fail_closed, c7_cost_authority, c8_audit_integrity,
           c9_guard_auth, c10_kill_switch]


def run_all():
    results = []
    for fn in CLAUSES:
        try:
            clause, passed, detail = fn()
        except Exception as e:  # noqa
            clause, passed, detail = fn.__name__, False, f"EXCEPTION: {e}"
        results.append((clause, passed, detail))
    return results


def _main():
    results = run_all()
    ok = all(p for _, p, _ in results)
    for clause, passed, detail in results:
        print(f"[{'PASS' if passed else 'FAIL'}] {clause}  {detail}")
    print(f"\nCONFORMANCE: {'PASS — Safety-Protocol-compatible' if ok else 'FAIL'}"
          f"  ({sum(p for _, p, _ in results)}/{len(results)} clauses)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_main())
