Subject: Stop agent incidents before they ship — a guard service, not a prompt

To the platform / agent-infrastructure team,

80% of Fortune 500 now run active AI agents (Microsoft Cyber Pulse, Feb
2026). The more agents you operate, the more a single out-of-scope action
scales into a real incident — and you can't hand-review every tool call
across thousands of agents.

We built a guard service your agents call *before* they act. Not a wrapper
around the model — infrastructure in front of the world:

  Agent --intent--> GUARD --allow/block--> World

- Deny-by-default scope, five bindings. An action is allowed only if a
  rule explicitly permits it. A catch-all prefix like /v1/ would also
  permit /v1/admin — so catch-all prefixes are rejected.
- A linter that fails closed. Broad or contradictory rules mean the guard
  refuses to start. The agent can never widen its own scope; it only
  sends intents. You own the config.
- Per-agent binding (on-chain SBT/ERC-8004), immutable audit trail, and a
  one-call kill switch.

The agent cannot bypass the guard. That's the entire point.

It's already runnable: a GuardService (HTTP + CLI) and a complete client.
One representative agent run through the real gate produces:

  scope_enforced:             True
  scope_violations_prevented: 55
  binding_on_chain:           True
  audit_trail_complete:       True

Across 1,000 simulated runs, controls cut mean loss from $62,514 to $252
— 99.6% exposure reduction.

The ask: point one agent class at the guard. We wire your real tool calls
through it, hand you the per-agent audit trail + binding proof, and show
the blocked-attack surface your current setup is missing. No model changes,
no rewrite — the agent just starts asking permission.

Attachments: PLATFORM_ONE_PAGER.md (full framework + deployment shape)

Michael
Safety Protocol Framework
https://github.com/TheDub-lab/safety-protocol
