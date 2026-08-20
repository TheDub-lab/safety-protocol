# Run Agents at Scale Without Betting the Company

**For: platforms operating many autonomous agents.**
**From: Safety Protocol Framework**

---

## The problem you actually have

You're shipping agents that call APIs, move money, send messages, spawn
subagents. The model is not reliable enough to build on — and the more
agents you run, the more a single bad action scales into a real
incident. The failure modes are concrete:

- An agent drifts out of scope and hits an endpoint it shouldn't.
- An agent invents a verb (`internal_transfer`) the rules never covered.
- An agent spends past budget or approves its own payments.
- Nobody can reconstruct what an agent did after something breaks.

Prompt engineering doesn't fix any of this. "Be careful" is not an
enforcement layer. And you can't hand-review every tool call across
thousands of agents.

## What we give you

A **guard service** your agents call *before* they act. Not a wrapper
around the model — infrastructure in front of the world.

```
Agent --intent--> GUARD --allow/block--> World
                  (scope, budget, approval,
                   audit, kill switch)
```

- **Deny-by-default scope, five bindings.** An action is allowed only if
  a rule explicitly permits it. Rules bind action type, target, method,
  params, and per-action cost cap. A catch-all prefix (`/v1/`) also
  permits `/v1/admin` — so we don't allow catch-all prefixes.
- **A linter that fails closed.** Broad or self-contradictory rules mean
  the guard **refuses to start**. The agent can never widen its own
  scope; it only sends intents. You own the config.
- **Per-agent binding.** Every action is attributable to a user. On-chain
  (SBT / ERC-8004) so anyone can verify *this agent is bound to this
  user*.
- **Immutable audit trail.** Hashed, append-only, complete
  reconstruction of everything an agent did.
- **Kill switch.** One call freezes an agent instantly.

**The agent cannot bypass the guard. That is the entire point.**

## It's already runnable

This isn't a spec. The framework ships a `GuardService` (HTTP + CLI) and
a complete client (`agent_client.py`). Config is user-owned and
linted on startup. The agent proposes; the guard disposes.

A single representative agent run through the real gate produces:

```
scope_enforced:            True
scope_violations_prevented:55
binding_on_chain:          True
audit_trail_complete:      True
on_chain_verifiable:       True
submission_ready:          True
```

Across 1,000 simulated runs (200 events each), controls cut mean loss
from **$62,514 to $252 — 99.6% exposure reduction** — and that's with the
honest residual of *authorized misuse* (in-scope but harmful actions the
gate can't see intent on) left in.

## Why not just prompt the model?

Because the model's good behavior is the thing that fails. The guard
enforces what it enforces regardless of what the model wants. When the
agent messes up, the audit trail tells you what happened, the binding
tells you who's accountable, and the next iteration gets tighter scope.
That's how you run agents at scale without every incident being a
discovery.

## Deployment shape

- Guard runs as a sidecar (HTTP) or CLI next to your agent runtime.
- You ship least-privilege rules per agent class; CI lints them and
  fails the deploy on anything broad.
- Agents route tool calls / payments through the guard. Blocked actions
  never reach the world.
- Audit trail + binding feed your compliance and (optionally) insurance.

## What's real vs. simulated

- **Real:** the enforcement layer, binding enforcement, the immutable
  audit trail, the guard service, the fail-closed linter, the insurance
  evidence interface.
- **Simulated (same interface as production):** on-chain binding and
  on-chain audit are in-memory. USDC settlement signing is HMAC-sim by
  default; the production EIP-3009 path exists and goes live only with
  `LIVE=True` + a funded key.

## The ask

Point one agent class at the guard. We wire your agent's real tool calls
through it, hand you the per-agent audit trail + binding proof, and show
you the blocked-attack surface your current setup is missing. No model
changes, no rewrite — the agent just starts asking permission.

---
*Safety Protocol Framework — agent safety as infrastructure, not prompts.*
