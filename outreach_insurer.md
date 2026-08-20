Subject: Evidence package for pricing AI-agent liability — real agent, real gate, real blocks

To the AI/Emerging-Risk underwriting team,

You're now writing AI-agent E&O — Lloyd's introduced explicit "AI-Agent"
clauses in Feb 2026, and the rest of the market is following. The hard
part isn't the policy wording; it's the loss data. To price agent risk you
need loss data, and to get loss data you need deployment. That cold-start
loop is why most agent-insurance is still exclusion language, not coverage.

We close that loop with an enforcement layer that does double duty: it
stops bad agent actions *and* produces the evidence your underwriting
model needs — per agent, per run.

What we can hand you today, from a real LLM (llama3.2) run through our
gate on live traffic:

  CLAIMS EVIDENCE:
    on_chain_verifiable:       True
    scope_violations_blocked:  4
    submission_ready:          True
  UNDERWRITER PACKAGE:
    scope_enforced:            True
    binding_on_chain:          True
    audit_trail_complete:      True

The model tried a forbidden admin endpoint 4 times; the gate blocked every
one. Every decision is mirrored into an immutable, on-chain-verifiable
audit trail. Across 1,000 simulated runs (200 events), controls cut mean
loss from $62,514 to $252 — 99.6% exposure reduction. The honest residual
(authorized misuse) is exactly what the policy + kill switch backstop.

This isn't a demo. The same interface runs on your agents' real tool calls.

The ask: pilot the evidence package against one agent deployment. We wire
your agent through the guard, hand you the live Claims Evidence +
Underwriter Package, and price from observed loss — not synthetic.

Attachments: INSURER_ONE_PAGER.md (full framework + loss distribution)

Michael
Safety Protocol Framework
https://github.com/TheDub-lab/safety-protocol
