"""Cost metering — measure what an action ACTUALLY cost, don't trust the agent.

The protocol routes budget / per-rule cap / approval-threshold through
``effective_cost()``, which prefers ``ActionRequest.measured_cost`` over the
agent's advisory ``estimated_cost``. But something has to SET ``measured_cost``.
That is the job of a CostMeter: the execution layer (the thing that actually
performs the action) reports the real cost back, and we stamp it onto the
request before it is accounted for.

This module provides a small, dependency-free meter interface. You bring the
"how do I know the real cost" — a billing API, a token counter, a price list —
by subclassing ``CostMeter`` and implementing ``measure(action_type, target,
params, result) -> float | None``. The protocol calls it (if you register it)
after each ALLOWED action and updates ``measured_cost`` + re-checks the cap and
budget against the real number. If your meter returns ``None`` (it can't price
this action), the protocol keeps the advisory estimate but logs ``budget_advisory``
so you know accounting was unverified for that action.

Activate by passing ``cost_meter=MyMeter()`` to ``SafetyProtocol`` or by setting
``"cost_meter"`` in the guard config to a registered meter name. See
``register_meter`` below for the config-driven path.
"""

from __future__ import annotations
from typing import Any, Callable


class CostMeter:
    """Measure the real cost of an executed action.

    Override ``measure``. Return the authoritative cost in the same currency
    units as the budget/caps, or ``None`` to fall back to the agent estimate.
    """

    name = "base"

    def measure(
        self,
        action_type: str,
        target: str,
        params: dict,
        result: Any,
    ) -> float | None:
        return None


# ---------------------------------------------------------------------------
# Registry: lets the guard config name a meter instead of importing it.
# ---------------------------------------------------------------------------
_REGISTRY: dict[str, type[CostMeter]] = {}


def register_meter(cls: type[CostMeter]) -> type[CostMeter]:
    """Decorator: register a meter class under ``cls.name`` for config lookup."""
    _REGISTRY[cls.name] = cls
    return cls


def get_meter(name: str) -> CostMeter | None:
    cls = _REGISTRY.get(name)
    return cls() if cls else None


# ---------------------------------------------------------------------------
# A concrete, no-dependency example: a static price table.
# Real deployments swap this for a billing-API-backed meter.
# ---------------------------------------------------------------------------
@register_meter
class PriceTableMeter(CostMeter):
    """Flat per-action-type price table. Config: {"api_call": 0.01, ...}.

    The execution layer knows the real price of each verb; the agent's
    declared estimate is irrelevant. Returns None for unknown verbs (falls
    back to the estimate + logs advisory).
    """

    name = "price_table"

    def __init__(self, prices: dict[str, float] | None = None):
        self.prices = prices or {"api_call": 0.01, "spend": 0.0, "send_message": 0.0}

    def measure(self, action_type, target, params, result) -> float | None:
        return self.prices.get(action_type)


class MeasuredCostCallback:
    """Callable hook the protocol invokes to stamp measured_cost on a request."""

    def __init__(self, meter: CostMeter | None):
        self.meter = meter

    def __call__(self, request, result) -> None:
        if self.meter is None or request.outcome is None:
            return
        cost = self.meter.measure(request.action_type, request.target, request.params, result)
        if cost is not None:
            request.measured_cost = cost
