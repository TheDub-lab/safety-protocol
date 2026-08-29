"""Safety Protocol adapter for the Claude Agent SDK.

Makes a Claude-agent app **Safety-Protocol-compatible**: every tool call Claude
proposes is funneled through the real SafetyProtocol gate before it runs. The
SDK's own `can_use_tool` callback is the natural hook for this — it fires for
every tool call the permission flow hasn't already resolved, so we enforce our
five-binding scope there instead of relying on prompt-level "be careful."

Mapping (Claude tool -> Safety Protocol action):
    Bash            -> action_type="exec",      target=command string
    Write/Edit/...  -> action_type="write_file", target=file path
    WebFetch/...     -> action_type="api_call",   target=URL
    (anything else)  -> action_type=<tool_name>,  target=first string-ish arg

The gate decides allow / block / approve. On approve we block on a human
decision (the SDK's own `can_use_tool` contract — we return deny with guidance,
or, when a human-approval transport is wired, poll it). Out-of-scope or
kill-switched calls are denied outright. The agent can never widen its own scope.

This adapter is the reference integration for SPEC.md §9 (guard surface) and is
exercised by `conformance`-style checks in `test_adapter.py` (no SDK import
needed — it tests the mapping + gate wiring against the real SafetyProtocol).
"""
from __future__ import annotations
import os
import json
from typing import Any, Callable

from safety_protocol.core import ActionRequest, ActionOutcome
from safety_protocol.guard_service import GuardService, build_protocol_from_config
from safety_protocol.scope_linter import lint_rules, Severity


# ---------------------------------------------------------------------------
# Tool -> action mapping
# ---------------------------------------------------------------------------
# Claude tool name -> (action_type, key in tool_input that is the "target")
_TOOL_MAP = {
    "Bash": ("exec", "command"),
    "Write": ("write_file", "file_path"),
    "Edit": ("write_file", "file_path"),
    "NotebookEdit": ("write_file", "notebook_path"),
    "Read": ("read_file", "file_path"),
    "WebFetch": ("api_call", "url"),
    "WebSearch": ("api_call", "query"),
    "Slack": ("send_message", "channel"),
    "send_message": ("send_message", "channel"),
}


def _first_stringish(tool_input: dict) -> str | None:
    for v in tool_input.values():
        if isinstance(v, str) and v.strip():
            return v
    return None


def map_tool_call(tool_name: str, tool_input: dict) -> tuple[str, str, dict]:
    """Return (action_type, target, params) for a Claude tool call.

    This is the single translation point — change the policy here, not in the
    gate. Anything unmapped becomes action_type=<tool_name> so the closed
    vocabulary still blocks unknown verbs.
    """
    if tool_name in _TOOL_MAP:
        action_type, key = _TOOL_MAP[tool_name]
        target = tool_input.get(key)
        if not target:
            target = _first_stringish(tool_input) or f"<{tool_name}>"
        return action_type, target, dict(tool_input)
    # Unknown tool: verb = tool name, target = best guess. The closed
    # vocabulary + deny-by-default will block it unless a rule permits it.
    return tool_name, _first_stringish(tool_input) or f"<{tool_name}>", dict(tool_input)


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------
class ClaudeSafetyAdapter:
    """Wraps a GuardService and exposes a `can_use_tool` callback.

    Usage (with the real SDK):
        from claude_agent_sdk import ClaudeAgentOptions, PermissionResultAllow, PermissionResultDeny

        adapter = ClaudeSafetyAdapter.from_config("examples/guard_config.json")
        adapter.set_human_approver(my_approve_fn)  # optional; else deny-with-guidance

        def can_use_tool(tool_name, tool_input, context):
            return adapter.can_use_tool(tool_name, tool_input, context)

        options = ClaudeAgentOptions(
            allowed_tools=["Bash", "Write", "Read", "WebFetch"],
            can_use_tool=can_use_tool,
        )

    The callback is async in the SDK; wrap with `async def` + `await`
    `adapter.guard_async(...)` if you need to poll a remote human-approval
    transport. The sync `can_use_tool` here is what `test_adapter.py` checks.
    """

    def __init__(self, guard: GuardService, human_approver: Callable | None = None):
        self.guard = guard
        self.human_approver = human_approver  # (request) -> bool  (sync or async)

    @classmethod
    def from_config(cls, path: str, human_approver: Callable | None = None) -> "ClaudeSafetyAdapter":
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # Fail closed on a too-broad config — same contract as the guard service.
        # build_protocol_from_config() calls sys.exit() on a failing lint; convert
        # that into a catchable RuntimeError so callers (and tests) see a clean
        # refusal rather than process termination.
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

    @classmethod
    def from_config_string(cls, cfg: dict, human_approver: Callable | None = None) -> "ClaudeSafetyAdapter":
        """Build directly from an in-memory config dict (no temp file)."""
        import tempfile
        p = os.path.join(tempfile.gettempdir(), "claude_guard_cfg.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return cls.from_config(p, human_approver=human_approver)

    # -- core decision -----------------------------------------------------
    def decide(self, tool_name: str, tool_input: Any, context: Any = None) -> dict:
        """Run one tool call through the gate. Returns a normalized verdict:
        {"behavior": "allow"|"deny", "message": str, "request_id": str,
         "requires_approval": bool}.
        """
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
            # Need a human. If no approver wired, deny with guidance (safe default).
            if self.human_approver is None:
                return {
                    "behavior": "deny",
                    "message": (
                        f"Safety Protocol requires human approval for {action_type} on "
                        f"{target}, but no approver is configured. Denying by default "
                        f"(token={verdict.get('requires_approval_for')})."
                    ),
                    "request_id": verdict["request_id"],
                    "requires_approval": True,
                }
            approved = self.human_approver(verdict)
            if approved:
                # Honor the approval so the same intent proceeds.
                self.guard.approve(verdict["requires_approval_for"], True, "human")
                return {"behavior": "allow", "message": "", "request_id": verdict["request_id"],
                        "requires_approval": False}
            return {"behavior": "deny",
                    "message": f"Human denied {action_type} on {target}.",
                    "request_id": verdict["request_id"], "requires_approval": True}

        # blocked_scope / blocked_budget / blocked_killswitch
        return {"behavior": "deny",
                "message": f"Safety Protocol blocked: {verdict.get('block_reason')}",
                "request_id": verdict["request_id"], "requires_approval": False}

    # -- SDK-compatible callback (flexible arg shape; mirrors the official
    #    can_use_tool(tool_name, input_data, context) signature) -----------
    def can_use_tool(self, tool_name: str, tool_input: Any, context: Any = None, **kwargs) -> dict:
        return self.decide(tool_name, tool_input, context)

    async def guard_async(self, tool_name: str, tool_input: Any, context: Any = None, **kwargs) -> dict:
        return self.decide(tool_name, tool_input, context)


# ---------------------------------------------------------------------------
# SDK result helpers (import-guarded so this module loads without the SDK)
# ---------------------------------------------------------------------------
def _sdk_results():
    """Return (Allow, Deny) constructor classes if claude_agent_sdk is present."""
    try:
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
        return PermissionResultAllow, PermissionResultDeny
    except Exception:  # pragma: no cover - SDK optional at runtime
        return None, None


def sdk_callback(adapter: ClaudeSafetyAdapter):
    """Build an async `can_use_tool` for ClaudeAgentOptions from an adapter.

    Returns a coroutine that converts the adapter verdict into the SDK's
    PermissionResultAllow / PermissionResultDeny. If the SDK isn't installed,
    returns None so the caller can fall back to a local loop.
    """
    Allow, Deny = _sdk_results()
    if Allow is None:
        return None

    async def can_use_tool(tool_name, tool_input, context=None):
        v = await adapter.guard_async(tool_name, tool_input, context)
        if v["behavior"] == "allow":
            return Allow()
        return Deny(behavior="deny", message=v["message"], interrupt=False)

    return can_use_tool
