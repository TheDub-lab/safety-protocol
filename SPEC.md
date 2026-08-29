# Safety Protocol — Specification

**Version: 0.1.0 (draft)**
**Status: open reference spec**
**Owner: TheDub-lab — github.com/TheDub-lab/safety-protocol**

This document is the authoritative contract for the Safety Protocol. Implementations that pass the conformance suite (`conformance/`) are **Safety-Protocol-compatible**. The reference implementation in this repository is one such implementation; the spec is the standard, not the code.

The core thesis: **agent safety is infrastructure, not prompts.** The agent operates freely *within* a perimeter that is enforced by code the agent cannot widen. The perimeter is defined by five bindings, and every action the agent proposes passes through a single gate that decides allow / block / approve.

---

## 1. Architecture

```
Agent ──proposes intent──▶ Guard (gate)
                                │
        ┌──────────────────────┼───────────────────────────────┐
        │ binding │ scope │ budget │ approval │ kill-switch │ audit │
        └──────────────────────┼───────────────────────────────┘
                                │
                   allow  ─────▶ execute
                   block  ─────▶ stop
                   approve ─────▶ wait for human, then retry
```

- **Agent** — proposes actions as *intents*. Never edits rules. Never widens scope.
- **Guard** — the enforcement boundary. A real agent calls the guard over HTTP/CLI; the guard holds the user-owned config and disposes of each intent. The agent cannot bypass it.
- **Audit** — immutable, append-only, per-agent decision log.

---

## 2. The Gate (single entry point)

Every agent action funnels through one function: `propose_action(action_type, target, …)` → `execute(request)`. Execution order is fixed:

1. **Binding** — agent still bound to a valid user? Else block.
2. **Kill switch** — protocol frozen? Else block everything.
3. **Scope** — does a rule *explicitly permit* this? Else deny (deny-by-default).
4. **Budget** — would this exceed the hard budget limit? Else block.
5. **Approval** — does this need human sign-off? Else pending.
6. **Allow** — all checks passed → execute and record.

The gate is **deny-by-default**: an action is allowed *only* if a rule explicitly permits it. There is no "allow because nothing forbade it."

---

## 3. Action vocabulary (closed verbs)

`allowed_action_types` is a closed set of verb strings. An `action_type` not in this set is blocked **before any rule is consulted**. This stops the model from inventing a verb (`internal_transfer`, `spawn_subagent_v2`) to slip past the rules.

Recommended baseline verbs (implementations may extend): `api_call`, `spend`, `payment`, `send_message`, `write_file`, `spawn_subagent`.

---

## 4. Scope — the five bindings

A least-privilege rule (`ScopeRule`) binds **five** things. Leaving any of them broad makes the other controls decorative.

| # | Binding | Field | Rule |
|---|---------|-------|------|
| 1 | **Action type** | `action_type` | From the closed vocabulary. `null`/`None` = applies to *every* verb (flagged by the linter — see §8). |
| 2 | **Target** | `allowed_targets` + `match` | Exact, narrow prefix/glob/regex. **Never a catch-all prefix** (`/v1/` also permits `/v1/admin`). |
| 3 | **Method** | `methods` | HTTP/transport verbs the rule permits (e.g. `["POST"]`). A read rule permitting `DELETE` is not least-privilege. |
| 4 | **Params** | `param_schema` | JSON-schema-style constraint (`required`, `properties` with `type`/`enum`/`minimum`/`maximum`/`pattern`, `additional_properties: false`). Unvalidated params let a "safe" endpoint do unsafe things (`?confirm=true`). |
| 5 | **Per-action cap** | `max_cost` | Per-rule hard spend cap. The real bound — the global budget only catches *volume*, not one oversized action. |

Plus `forbidden_targets` + `forbid_match` (deny tokens regardless of the allowlist).

### Target matching (`match`)

- `exact` — normalized target equals pattern.
- `prefix` — target starts with pattern + `/` (after normalization).
- `glob` — `fnmatch` against the normalized target.
- `regex` — `re.fullmatch` against the normalized target.
- `token` (forbidden only) — blocks if the pattern equals a whole path/label token (`admin` blocks `/api/admin` and `?role=admin`, but **not** `readmymind` or `administrator`).
- `substring` (forbidden only, legacy/loose) — raw containment.

### Target normalization (MUST)

Implementations MUST normalize targets before matching, resolving path traversal:

- Lowercase.
- Resolve `..` / `.` segments (`posixpath.normpath`), scheme-aware so traversal cannot escape the host: `https://x/v1/a/../../admin` → `https://x/admin`.
- A prefix rule on `/v1/` MUST NOT also permit `/v1/sub/../../admin` (it resolves outside the prefix and is denied).
- Collapse redundant slashes; strip a trailing slash.

Rationale: without traversal resolution, a prefix allowlist is escapable, which defeats the entire perimeter.

---

## 5. Cost (measured, not declared)

`ActionRequest` carries two cost fields:

- `estimated_cost` — **advisory**, supplied by the agent. MUST NOT be trusted for accounting.
- `measured_cost` — **authoritative**, set by the execution layer (or a real cost meter that observes the effect).

Enforcement (budget, per-rule cap, approval threshold) routes through `effective_cost()` = `measured_cost` if present, else `estimated_cost`. When `measured_cost` is absent, the gate still enforces on the estimate but MUST emit a `budget_advisory` audit event marking accounting as unverified.

**Interop rule:** a compatible implementation MUST provide an authoritative cost path before it may claim budget/approval enforcement. A guard that only accepts agent-declared cost is **non-conforming** for the budget/approval bindings.

---

## 6. Budget, approval, kill switch

- **Budget** — `budget_limit` (float | null = unlimited). Hard block when `spent + effective_cost > limit`.
- **Approval** — required when (a) a rule sets `requires_approval`, (b) `effective_cost >= approval_threshold_cost`, or (c) `urgency == "critical"`. Pending actions return a token; a human calls `decide_approval(token, approved, approver)`. A prior approval whitelists the *exact* (target, cost-cents) intent for a short window; a different target or cost still requires approval.
- **Kill switch** — `engage_killswitch(reason)` freezes all actions (state `FROZEN`). Disengage does not restore a revoked binding.

---

## 7. Audit trail

Per-agent, append-only. Each entry:

```
{
  "seq": int,
  "event_type": str,
  "agent_id": str,
  "data": dict,
  "timestamp": float,
  "prev_hash": str | null,
  "entry_hash": str            # sha256[:16] (unkeyed) or HMAC[:32] (keyed)
}
```

Event types include (non-exhaustive): `protocol_initialized`, `action_allowed`, `action_blocked`, `action_pending_approval`, `action_executed`, `approval_requested`, `approval_decision`, `killswitch_engaged`, `binding_revoked`, `budget_advisory`, `scope_violation`.

### Integrity

- **Unkeyed** — `prev_hash` chain. Detects *accidental* corruption only; a process that rewrites the whole list can recompute every hash and self-verify clean. Not tamper-evident across a trust boundary.
- **Keyed** (`auth_key` set) — each link is `HMAC(key, prev_mac | sha256(entry))`. Rewriting any entry without the key is detectable. `root_mac()` returns the head MAC to snapshot/anchor externally (e.g. on-chain).

A compatible implementation MUST support keyed mode for the audit to be claimed tamper-evident.

---

## 8. Scope linter (fail-closed)

`lint_rules(rules, allowed_action_types)` is a static check run before deploy. Any `ERROR` or `WARN` MUST block startup (fail-closed).

| Code | Severity | Meaning |
|------|----------|---------|
| `CATCH_ALL_PREFIX` | ERROR | prefix match on a broad/root target — permits everything beneath it |
| `ALLOW_FORBID_CONFLICT` | ERROR | same token in both allow and forbid lists |
| `BLANKET_ALLOW` | ERROR (verb=null) / WARN (verb set) | rule with no `allowed_targets` permits every target |
| `BLANKET_VERB` | WARN | `action_type=null` permits every verb in the vocabulary |
| `NO_METHOD` | WARN | rule allows any HTTP verb |
| `NO_PARAM_SCHEMA` | WARN | rule allows any params |
| `NO_PER_RULE_CAP` | WARN | rule (spend/payment/api_call/null) has no `max_cost` |
| `DEAD_VERB` | INFO | verb in vocabulary with no permitting rule (intentional deny) |

A compatible implementation MUST ship a linter that at minimum raises `CATCH_ALL_PREFIX`, `ALLOW_FORBID_CONFLICT`, `BLANKET_ALLOW`, `BLANKET_VERB`, `NO_METHOD`, `NO_PARAM_SCHEMA`, `NO_PER_RULE_CAP` and fails closed on ERROR/WARN.

---

## 9. Guard HTTP surface

The guard exposes (when `guard_token` is unset it runs open and MUST warn; when set, state-changing routes require `Authorization: Bearer <token>`, constant-time compare, 401 otherwise):

```
POST /guard      {action_type, target, method?, params?, cost?}   -> {outcome, allowed, block_reason?, requires_approval_for?, request_id}
POST /pay        {recipient, usd, resource?}                      -> {outcome, allowed, block_reason?, approval_token?, signed?}
POST /approve    {token, approved, approver}                      -> {approved}
POST /killswitch {reason}                                         -> {engaged, reason}
GET  /audit      -> {events: [ … ]}
GET  /health     -> {agent_id, user_id, state, lint, monitor, allowed_action_types}
```

- `outcome` ∈ `{allowed, blocked_scope, blocked_budget, pending_approval, blocked_killswitch}`.
- The agent sends **intents only**. It never reads or edits the config, the rules, or the approval state.

---

## 10. Conformance

`conformance/` is the compatibility harness. A guard passes when it satisfies, at minimum:

- **C1 Deny-by-default** — unknown verb blocked; no matching rule blocked.
- **C2 Closed vocabulary** — invented verb blocked before rules are consulted.
- **C3 Five bindings** — exact+method+param+cap rule allows the intended call and blocks method/param/cost violations.
- **C4 Forbidden tokens** — `admin` blocks `/api/admin` and `?role=admin`; not `readmymind`/`administrator`.
- **C5 Traversal** — prefix rule does NOT permit `…/../../admin` (resolves out of prefix → blocked).
- **C6 Linter fail-closed** — catch-all prefix / blanket-null rule is flagged ERROR/WARN and blocks startup.
- **C7 Cost authority** — `measured_cost` (not `estimated_cost`) drives cap/approval; unmeasured path emits `budget_advisory`.
- **C8 Audit integrity** — keyed mode detects tampering; `root_mac()` snapshottable.
- **C9 Guard auth** — state-changing routes 401 without a valid bearer token.
- **C10 Kill switch** — `FROZEN` blocks all actions.

Run: `python conformance/run.py` (or `pytest conformance/`).

---

## 11. Open items (not part of v0.1 conformance)

- On-chain binding/audit is **simulated** in the reference impl (in-memory, same interface). Real ERC-5192/ERC-8004 is a deployment step, not required for conformance.
- Insurance interface provides evidence/reports; it is not connected to a real insurer.
- A real cost meter (authoritative `measured_cost`) is an integration responsibility of the deployer.

This spec defines the *contract*. Build to it; the reference implementation is just the first compliant one.
