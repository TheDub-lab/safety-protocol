"""
Safety Protocol Framework for LLM Agents

A framework for building safe, accountable AI agents that operate
through enforced safety protocols rather than relying on the model's
good behavior.

The core principle: the user is accountable for their agents. Every
agent action passes through a safety protocol that enforces binding,
scope, budget, approval gates, monitoring, audit trail, and kill switch.

The agent operates freely WITHIN these bounds. The bounds are enforced
by infrastructure, not by hoping the agent behaves.

When the agent messes up, the audit trail tells you what happened, the
binding tells you who's accountable, and the next iteration has tighter
scope.

Installation:
    pip install safety-protocol

Quick start:

    from safety_protocol import SafetyProtocol, BoundAgent, AuditTrail

    # Create audit trail
    audit = AuditTrail()

    # Create safety protocol with scope rules and budget
    protocol = SafetyProtocol(
        agent_id="agent-001",
        user_id="alice",
        scope_rules=[
            ScopeRule(
                action_type="api_call",
                allowed_targets=["https://api.example.com/v1/*"],
                forbidden_targets=["admin", "billing"],
                max_cost=5.0,
            ),
        ],
        budget_limit=50.0,
        approval_threshold_cost=10.0,
        audit=audit,
    )

    # Create a bound agent
    agent = BoundAgent(
        agent_id="agent-001",
        user_id="alice",
        safety_protocol=protocol,
    )

    # Agent proposes an action — protocol decides
    result = agent.propose_action(
        action_type="api_call",
        target="https://api.example.com/v1/search",
        params={"query": "test"},
        estimated_cost=2.50,
    )

    print(result.outcome)  # ActionOutcome.ALLOWED

    # Agent CANNOT bypass the protocol. Period.
    # The protocol enforces: binding, scope, budget, approval, kill switch.
"""

from .core import (
    ActionOutcome,
    ProtocolState,
    ActionRequest,
    ActionResult,
    ApprovalRecord,
    ScopeRule,
    AuditTrail,
    Monitor,
    SafetyProtocol,
    BoundAgent,
)

__version__ = "0.1.0"
__all__ = [
    "ActionOutcome",
    "ProtocolState",
    "ActionRequest",
    "ActionResult",
    "ApprovalRecord",
    "ScopeRule",
    "AuditTrail",
    "Monitor",
    "SafetyProtocol",
    "BoundAgent",
    "__version__",
]
