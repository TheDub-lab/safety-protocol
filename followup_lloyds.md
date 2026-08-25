To: supplychainmanagement@lloyds.com
Subject: Re: Evidence package for pricing AI-agent liability

Hi,

Following up on the evidence package I sent earlier this week. Quick recap
of what's attached and why it's relevant to your desk — and to be precise
about where we sit: we are not an insurer or MGA. We build the
**enforcement + evidence layer** that makes autonomous agents *insurable*;
the carrier bears the risk, we make it bounded and recorded.

- A real LLM run through our guard on live traffic: the model tried a
  forbidden admin endpoint 4 times, the gate blocked every one, and every
  decision landed in an immutable, on-chain-verifiable audit trail.

- Across 1,000 simulated runs (200 events), controls cut mean *retained*
  loss from $62,514 to $252 — 99.6% exposure reduction. The honest
  residual (authorized misuse) is exactly what the policy + kill switch
  backstop — your number to price, not ours.

The differentiator for underwriting: the same layer that enforces safety
also produces your claims-ready evidence and underwriter package as a side
effect of normal operation — scope enforced, violations prevented (count),
binding provable on-chain, audit trail complete. That's the loss data you
need to quote the risk, available before a single real claim exists.

We don't set the premium; we supply the telemetry your underwriters price
against. Happy to walk your team through a live demo or pilot it against
one real agent deployment — the same interface runs on your agents' actual
tool calls, so you price from observed loss, not synthetic.

Michael
Safety Protocol Framework
https://github.com/TheDub-lab/safety-protocol
