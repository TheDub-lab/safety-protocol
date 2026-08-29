# Where to post + what to say

The adapter is shipped and pushed:
https://github.com/TheDub-lab/safety-protocol  (see integrations/claude_agent_sdk/)

One command for a skeptic to verify it works (no SDK, no API key):
    git clone https://github.com/TheDub-lab/safety-protocol && cd safety-protocol && python integrations/claude_agent_sdk/smoke_test.py

---

## Post 1 — r/ClaudeAI (or r/Anthropic / Claude Discord #tooling)

Subject: I built a tool-call gate for the Claude Agent SDK — scope enforced in
infrastructure, not prompts

If you're running Claude Agent SDK apps and trusting `can_use_tool` prompts to
keep them safe, here's a drop-in that routes every tool call through a real
scope gate (action type / target / method / params / per-action cost) + budget +
human-approval + kill switch. `rm -rf /` gets blocked by code, not by hoping the
model is careful.

5-line wiring:
    adapter = ClaudeSafetyAdapter.from_config("examples/guard_config.json")
    adapter.human_approver = lambda v: input("approve? [y/N] ").lower() == "y"
    cb = sdk_callback(adapter)
    options = ClaudeAgentOptions(allowed_tools=["Bash","Read","WebFetch"], can_use_tool=cb)

Verify in 10s (no SDK/key): `python integrations/claude_agent_sdk/smoke_test.py`
Conformance: 11/11 against the real gate. Also ships a LangChain adapter + a
versioned spec.

Repo: https://github.com/TheDub-lab/safety-protocol
Honest limit: `can_use_tool` only fires for unresolved calls, so pair it with a
tight allowlist — it's your last line of defense, not your only one. Feedback /
PRs welcome.

---

## Post 2 — LangChain Discord (#general or #integrations) + r/LangChain

Subject: Safety-Protocol adapter for agent tool-call governance (Claude SDK +
LangChain)

We open-sourced a framework-neutral safety gate and just shipped adapters for
both Claude Agent SDK and LangChain. The LangChain one wraps each BaseTool so the
gate runs *before* execution (callbacks can't reliably block — on_tool_start's
return is discarded), which is the part most "governance" attempts get wrong.

- Claude: can_use_tool callback
- LangChain: tool wrapper (pre-execution enforcement, proven by test L8 — a
  blocked call never invokes the wrapped tool)

Both route through the same gate: five-binding scope + budget + approval +
kill switch. Conformance suites included (Claude 11/11, LangChain 14/14).

Repo + spec: https://github.com/TheDub-lab/safety-protocol
Try the Claude smoke test in 10s: clone, then
`python integrations/claude_agent_sdk/smoke_test.py`

---

## Post 3 — Hacker News (Show HN) or Twitter/X

Show HN: Safety Protocol — enforce agent scope in infrastructure, not prompts

Agents spend money, call APIs, and run shell commands. System prompts don't
enforce boundaries; code does. Safety Protocol is an open reference
implementation + spec for that enforcement layer: five-binding least-privilege
scope, a linter that fails closed, measured (not declared) cost, tamper-evident
audit, and a kill switch. We just shipped Claude Agent SDK + LangChain adapters so
any agent app can route tool calls through the gate.

- Repo: https://github.com/TheDub-lab/safety-protocol
- Spec: SPEC.md  Benchmark: BENCHMARK.md (99.6% exposure reduction, reproducible)
- Verify the Claude adapter in 10s, no SDK/key:
  `python integrations/claude_agent_sdk/smoke_test.py`

Not claiming it's a silver bullet — the on-chain binding is testnet, cost
measurement is the deployer's job, and the wrappers don't mediate every path.
But the perimeter is real and the spec is checkable.

---

## What "try it" looks like for that one person

The lowest-friction ask: "clone it and run the smoke test — if `rm -rf /`
isn't blocked, tell me." That's a 20-second action with a visible pass/fail, and
it's the conversation starter that gets a real user.
