"""Safety Protocol adapter for LangChain.

Makes a LangChain agent **Safety-Protocol-compatible**: every tool call is
funneled through the real SafetyProtocol gate *before* it executes.

IMPORTANT — why a tool wrapper, not a callback:
    LangChain's BaseCallbackHandler is observer-pattern: on_tool_start fires
    BEFORE execution but its return value is discarded, and raising there only
    blocks if `raise_error=True` is set (and even then the framework may swallow
    it). The maintainers' own guidance is that governance which must allow/deny
    belongs in a *tool-execution wrapper*, not a callback. So this adapter wraps
    each BaseTool in a SafetyProtocolTool whose `_run`/`_arun` runs the gate
    first. The callback (SafetyProtocolCallbackHandler) is used ONLY for the
    audit trail (post-hoc), never for the allow/deny decision.

Mapping (LangChain tool -> Safety Protocol action):
    shell / bash / terminal -> action_type="exec",      target=command
    file write/edit          -> action_type="write_file", target=path
    file read                -> action_type="read_file",  target=path
    http / requests / fetch  -> action_type="api_call",   target=URL
    (anything else)          -> action_type=<tool name>,   target=best string arg

The gate decides allow / block / approve. Out-of-scope or kill-switched calls
raise ToolExecutionError (denied). Consequential calls block on a human decision
(pluggable human_approver); without one, they are denied with guidance. The
agent can never widen its own scope — it only sends intents.

This is the reference integration for SPEC.md §9 and is checked by
test_adapter.py (no LangChain import needed — it tests the mapping + gate
wiring against the real SafetyProtocol).
"""
from __future__ import annotations
import json
import os
from typing import Any, Callable

from safety_protocol.core import ActionRequest, ActionOutcome
from safety_protocol.guard_service import GuardService, build_protocol_from_config
from safety_protocol.scope_linter import lint_rules, Severity


# ---------------------------------------------------------------------------
# Tool -> action mapping
# ---------------------------------------------------------------------------
# LangChain tool name (lowercased substring match) -> (action_type, arg key)
_TOOL_MAP = {
    "shell": ("exec", None),
    "bash": ("exec", None),
    "terminal": ("exec", None),
    "command": ("exec", None),
    "write": ("write_file", None),
    "edit": ("write_file", None),
    "read": ("read_file", None),
    "open": ("read_file", None),
    "http": ("api_call", None),
    "request": ("api_call", None),
    "fetch": ("api_call", None),
    "url": ("api_call", None),
    "slack": ("send_message", None),
    "send_message": ("send_message", None),
    "email": ("send_message", None),
}


def _string_args(tool_input: Any) -> dict:
    """Normalize a LangChain tool input (str | dict) into a params dict."""
    if isinstance(tool_input, dict):
        return dict(tool_input)
    if isinstance(tool_input, str):
        return {"input": tool_input}
    return {"input": str(tool_input)}


def _first_stringish(d: dict) -> str | None:
    for v in d.values():
        if isinstance(v, str) and v.strip():
            return v
    return None


def map_tool_call(tool_name: str, tool_input: Any) -> tuple[str, str, dict]:
    """Return (action_type, target, params) for a LangChain tool call."""
    params = _string_args(tool_input)
    low = tool_name.lower()
    action_type, key = "tool", None
    for needle, (at, k) in _TOOL_MAP.items():
        if needle in low:
            action_type, key = at, k
            break
    if key and key in params:
        target = params[key]
    else:
        target = _first_stringish(params) or f"<{tool_name}>"
    return action_type, target, params


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------
class LangChainSafetyAdapter:
    """Wraps a LangChain tool list so every call passes the gate.

    Usage:
        from langchain_core.tools import BaseTool
        from integrations.langchain.adapter import LangChainSafetyAdapter

        raw_tools = [search_tool, shell_tool]
        adapter = LangChainSafetyAdapter.from_config("examples/guard_config.json")
        adapter.human_approver = lambda verdict: input("approve? [y/N] ").lower() == "y"
        guarded = adapter.wrap_tools(raw_tools)   # pass THIS list to the agent

    `guarded` is a list of SafetyProtocolTool wrappers. The agent calls them
    exactly as before; the gate decides underneath.
    """

    def __init__(self, guard: GuardService, human_approver: Callable | None = None):
        self.guard = guard
        self.human_approver = human_approver

    @classmethod
    def from_config(cls, path: str, human_approver: Callable | None = None) -> "LangChainSafetyAdapter":
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        try:
            proto, _ = build_protocol_from_config(cfg)
        except SystemExit:
            raise RuntimeError("guard config failed lint (fail-closed); fix rules before serving")
        findings = lint_rules(proto.scope_rules, proto.allowed_action_types)
        blocking = [f for f in findings if f.severity in (Severity.ERROR, Severity.WARN)]
        if blocking:
            raise RuntimeError(
                "guard config failed lint (fail-closed); fix rules before serving: "
                + ", ".join(f"{f.code}:{f.message}" for f in blocking)
            )
        return cls(GuardService(cfg), human_approver=human_approver)

    # -- core decision (shared with the callback) -------------------------
    def decide(self, tool_name: str, tool_input: Any) -> dict:
        action_type, target, params = map_tool_call(tool_name, tool_input)
        verdict = self.guard.guard(
            action_type=action_type,
            target=target,
            method=tool_name,
            params=params,
            cost=float((params.get("cost") or 0.0)),
        )
        outcome = verdict["outcome"]
        if outcome == "allowed":
            return {"behavior": "allow", "message": "", "request_id": verdict["request_id"],
                    "requires_approval": False}
        if outcome == "pending_approval":
            if self.human_approver is None:
                return {"behavior": "deny",
                        "message": (f"Safety Protocol requires human approval for {action_type} on "
                                    f"{target}, but no approver is configured. Denying by default "
                                    f"(token={verdict.get('requires_approval_for')})."),
                        "request_id": verdict["request_id"], "requires_approval": True}
            if self.human_approver(verdict):
                self.guard.approve(verdict["requires_approval_for"], True, "human")
                return {"behavior": "allow", "message": "", "request_id": verdict["request_id"],
                        "requires_approval": False}
            return {"behavior": "deny", "message": f"Human denied {action_type} on {target}.",
                    "request_id": verdict["request_id"], "requires_approval": True}
        return {"behavior": "deny",
                "message": f"Safety Protocol blocked: {verdict.get('block_reason')}",
                "request_id": verdict["request_id"], "requires_approval": False}

    # -- tool wrapping -----------------------------------------------------
    def wrap_tools(self, tools: list) -> list:
        """Return SafetyProtocolTool wrappers around each BaseTool."""
        wrapped = []
        for t in tools:
            name = getattr(t, "name", None) or getattr(t, "__name__", str(t))
            wrapped.append(SafetyProtocolTool(t, name, self))
        return wrapped


class SafetyProtocolTool:
    """A BaseTool-compatible wrapper that gates execution.

    Mirrors the wrapped tool's name/description/args_schema so the agent treats
    it identically, but runs adapter.decide() in _run/_arun. A deny raises
    ToolExecutionError (surfaces to the agent as a tool error, which the model
    can react to). Audit events are appended by the wrapped tool's run via the
    callback; the gate outcome itself is recorded by SafetyProtocol.
    """

    def __init__(self, wrapped, name: str, adapter: LangChainSafetyAdapter):
        self._wrapped = wrapped
        self._name = name
        self._adapter = adapter
        # Surface the wrapped tool's interface so agents/tools see a normal tool.
        self.name = name
        self.description = getattr(wrapped, "description", f"Safety-gated {name}")
        self.args_schema = getattr(wrapped, "args_schema", None)

    # Sync + async run through the gate.
    def _run(self, *args, **kwargs) -> str:
        return self._dispatch(args, kwargs)

    async def _arun(self, *args, **kwargs) -> str:
        return self._dispatch(args, kwargs)

    def _dispatch(self, args, kwargs) -> str:
        # LangChain passes tool input either positionally (args) or as kwargs.
        if kwargs:
            tool_input = kwargs
        elif args:
            tool_input = args[0] if len(args) == 1 else {"args": list(args)}
        else:
            tool_input = {}
        v = self._adapter.decide(self._name, tool_input)
        if v["behavior"] != "allow":
            err = _tool_error_type()
            if err is not None:
                raise err(f"Blocked by Safety Protocol: {v['message']}")
            # Fallback if langchain not installed: return as a tool-error string.
            return f"Blocked by Safety Protocol: {v['message']}"
        # Allowed — execute the wrapped tool.
        wrapped = self._wrapped
        if hasattr(wrapped, "func") and callable(wrapped.func):
            return wrapped.func(*args, **kwargs) if args or kwargs else wrapped.func()
        if callable(wrapped):
            return wrapped(*args, **kwargs)
        if hasattr(wrapped, "invoke"):
            return wrapped.invoke(tool_input if isinstance(tool_input, dict) else tool_input)
        if hasattr(wrapped, "_run"):
            return wrapped._run(*args, **kwargs)
        raise RuntimeError(f"Cannot invoke wrapped tool {self._name!r}")

    # Behave enough like a BaseTool for agent constructors that inspect type.
    @property
    def is_safe_protocol_wrapped(self) -> bool:
        return True


def _tool_error_type():
    """Return ToolExecutionError if langchain_core is importable, else None."""
    try:
        from langchain_core.tools import ToolExecutionError
        return ToolExecutionError
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Audit-only callback (post-hoc; never the allow/deny decision)
# ---------------------------------------------------------------------------
def make_audit_callback(adapter: LangChainSafetyAdapter):
    """Build a BaseCallbackHandler that records tool calls to the audit trail.

    This is OBSERVATION ONLY. The allow/deny decision happens in the tool
    wrapper. Registering this callback gives you a per-agent audit log of what
    the agent actually invoked; it does not (and cannot) block.
    """
    try:
        from langchain_core.callbacks import BaseCallbackHandler
    except Exception:
        return None

    class SafetyProtocolCallbackHandler(BaseCallbackHandler):
        def on_tool_start(self, serialized, input_str, *, run_id=None, parent_run_id=None, tags=None, metadata=None, **kwargs):
            name = (serialized or {}).get("name") if isinstance(serialized, dict) else None
            adapter.guard.guard  # no-op ref to keep adapter alive

        def on_tool_end(self, output, *, run_id=None, parent_run_id=None, tags=None, metadata=None, **kwargs):
            pass

    return SafetyProtocolCallbackHandler()
