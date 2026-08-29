# Reply template: "how is this different from permission_mode / allowed_tools?"

This is the question that decides whether the post lands. Answer it precisely
and without hype — the moment you overclaim, a skeptic tears it down and the
thread dies. The honest answer is: **permission_mode is a prompt-level allowlist
for the SDK's own CLI; this is a separate enforcement layer with budget, cost,
approval, and kill-switch semantics that permission_mode doesn't have, and it
sits *behind* permission_mode, not instead of it.**

---

## Short version (paste this)

`permission_mode` / `allowed_tools` are the SDK's *own* permission rules — they
decide what the CLI will run. Safety Protocol is a *separate* gate that wraps
those calls and adds five-binding scope + budget caps + per-action cost limits +
human approval for consequential calls + a kill switch. They're layered, not
competing:

- `allowed_tools=["Bash"]` says "Bash may run."
- Safety Protocol says "Bash may run *only* `ls -la /tmp`, never `rm`, and any
  call over $10 needs a human, and the whole agent freezes if it drifts."

`permission_mode="bypass"` would blow past both — that's why the README says
never use bypass, and why the adapter pairs with a tight allowlist. The gate is
your last line of defense, not your only one.

---

## If they push ("but can_use_tool already does this"

Right, `can_use_tool` is the *hook* — and it's exactly where we plug in. The
value isn't the hook (you could write that yourself in 10 lines); it's the
*policy engine* behind it:

1. **Five-binding least-privilege scope** (action type, target, method, params,
   per-action cost) with a **linter that fails closed** — a broad rule
   (`prefix: /`) is rejected before the agent ever starts. `permission_mode`
   has no notion of "this prefix is too wide."
2. **Measured cost, not declared.** Budget and approval gate on a cost the
   *execution layer* sets, not what the agent claims. Declaring $0 doesn't dodge
   the cap. (This was a real gap; fixed in the reference impl.)
3. **Human approval as a first-class state**, not a yes/no prompt — pending
   calls block on a pluggable approver and the gate remembers the decision.
4. **Kill switch** that freezes the agent on drift (e.g. 3 consecutive
   in-scope-but-harmful actions the scope can't see).
5. **Tamper-evident audit** + a versioned **spec** other tools implement against.

So: same hook, different — and reusable — brain behind it.

---

## If they push "callbacks can be bypassed / swallowed"

Correct, and we don't claim otherwise. Two honest points:

- `can_use_tool` only fires for calls the SDK's own flow hasn't already resolved,
  so we document: pair the adapter with a tight `allowed_tools` +
  `permission_mode`. The gate is defense-in-depth, not complete mediation — the
  README says this explicitly.
- For LangChain we used a **tool wrapper**, not a callback, precisely because
  `on_tool_start` can't reliably block. The LangChain adapter's test (L8) proves
  a blocked call never invokes the wrapped tool. Claude's `can_use_tool` *can*
  block, which is why the callback is the right seam there.

We're not selling "unbreakable." We're shipping a checkable perimeter + a spec.

---

## If they push "why not just write the rules in the prompt"

Because prompts are not infrastructure. The model is the thing you're protecting
*against* — it can be prompt-injected, distracted, or just wrong. Scope that
lives only in the system prompt is enforced by the entity it's supposed to
constrain. Safety Protocol moves the decision to code the agent can't rewrite,
and records it in an audit trail an underwriter or reviewer can read afterward.
That's the whole point of the project.

---

## Closing line (if the thread is going well)

"If you clone it and `rm -rf /` isn't blocked, that's a bug and I'll fix it —
that's the test the smoke test runs. Repo's at
github.com/TheDub-lab/safety-protocol."
