# Plan: On-chain layer — simulated → live (testnet)

**Owner:** TheDub-lab — github.com/TheDub-lab/safety-protocol
**Status:** SCOPE / DESIGN (not yet implemented)
**Goal:** replace the in-memory `OnChainBindingRegistry` / `OnChainAudit` with real
testnet transactions so "simulated" becomes "live (testnet)", and the binding +
key events are actually verifiable by anyone reading the chain.

This document scopes the work. It is deliberately honest about what live-testnet
buys you and what it does NOT.

---

## 0. Why do this (and what it actually proves)

Today `onchain.py` / `onchain_audit.py` fake tx hashes and block numbers in
memory. Anyone reading your repo can see the binding is **asserted**, not
**anchored**. Moving to testnet makes the binding + key audit events *real
cryptographic commitments anyone can verify* — that converts "we say it's
non-transferable and tamper-evident" into "here's the transaction, check it."

What live-testnet PROVES:
- The binding truly exists as a non-transferable on-chain record (SBT).
- Key events (binding, high-value, approval, kill switch, scope violation) are
  immutable commitments anyone can read.
- `verify_binding()` / `verify_integrity()` return *real* chain data, not a dict
  we made up.

What live-testnet does NOT get you (do not overclaim):
- It is **not mainnet**, not real money, not a real insurer. Testnet tokens are
  free; "verifiable on Sepolia" ≠ "insured."
- It does not make the *enforcement* stronger. The protocol still enforces in
  Python; the chain is an anchor/proof, not the gate. Keep saying that.
- It does not retire the audit "honest limits" note — it upgrades it from
  "simulated" to "live testnet (no mainnet value)."

So the public-claims move is: **"Binding + key events are anchored on Base
Sepolia (testnet) and verifiable by anyone"** — true and defensible. Not
"on-chain secured" (vague) or "insured" (separate gap).

---

## 1. Target chain

**Base Sepolia** (testnet). Rationale:
- The payment path (`payments.py`, `real_wallet.py`) already targets Base
  mainnet (`eip155:8453`, USDC `0x8335...`). Using Base Sepolia keeps one chain
  family, one wallet/provider stack, and the production path is a one-line
  network flip later.
- Cheap/free testnet ETH; safe for a public reference.
- ERC-5192 (soulbound) reference impls exist; ERC-8004 (agent registry) is
  newer — use ERC-5192 for the binding to stay boring and auditable.

---

## 2. Two minimal contracts (testnet)

### 2a. `SafetyBinding.sol` (ERC-5192 soulbound)
- `bind(agentId, userAddr, metadataHash) -> event Bound(agentId, userAddr, txHash)`
- `revoke(agentId, reason) -> event Revoked(agentId, reason)`
- `ownerOf(agentId) -> userAddr` (non-transferable: `transferFrom` reverts)
- `verify(agentId) -> (userAddr, bound, revoked, blockNumber)` — read method
  the SDK calls instead of the in-memory dict.
- `metadataHash` = keccak256 of the off-chain binding record, so the on-chain
  record commits to the full off-chain metadata without storing it.

### 2b. `SafetyEvents.sol` (append-only event log)
- `record(agentId, eventType, dataHash) -> event Recorded(txHash, blockNumber)`
- Read-only query helper (or just rely on `getLogs` by agentId topic).
- This is the on-chain subset of `DualAudit` (binding, high-value, approval,
  kill switch, scope violation).

Both are tiny, ~80–120 LOC total, and should be deployed once to a known address
on Base Sepolia; that address goes in `chains.json`.

---

## 3. Real client (replace the in-memory registries)

New module `onchain_web3.py` (import-guarded, like `real_wallet.py`):
- Uses `web3.py` + a provider (`INFURA_*` / `AlchemyHttpProvider` / `ANVIL` local).
- `OnChainBindingRegistryWeb3` implements the **same interface** as the simulated
  `OnChainBindingRegistry` (`bind_agent`, `verify_binding`, `revoke_binding`,
  `get_all_bindings`) but calls the contract. `verify_binding` reads chain state
  (no tx needed).
- `OnChainAuditWeb3` implements `OnChainAudit`'s interface (`record`, `query`,
  `get_*`, `verify_integrity`) — `record` sends a tx, `verify_integrity` replays
  `getLogs` and checks event hashes vs the off-chain mirror.
- A `binding_tx` / `tx_hash` is now a **real** 32-byte hash; `block_number` real.

The protocol wiring (`OnChainBoundProtocol`, `DualAudit`) changes only at
construction: if `LIVE_TESTNET=True` and `web3` + `contract_address` present, use
the web3 registries; else fall back to the simulated ones. **Fail closed if
`LIVE_TESTNET=True` but deps/address missing** — never silently simulate when
"live" was requested.

---

## 4. Keyed audit already done — reuse it

The `AuditTrail(auth_key=...)` HMAC work from the hardening pass is the off-chain
tamper-evidence. For testnet, the *on-chain* `dataHash` is `keccak256` of the
same entry. So integrity = off-chain HMAC chain (already implemented) + on-chain
commitment (this plan). `root_mac()` can be anchored as the final `dataHash` in
`SafetyEvents` — that's the real "snapshot externally" path the README promises.

---

## 5. Keys / secrets (do NOT commit)

- A **deployer key** (funds the two contract deploys once) — ephemeral testnet
  key, never the mainnet key, never committed.
- An **agent-binding key** per deployment, or reuse the deployer for tests.
- Provider URL in env (`BASE_SEPOLIA_RPC`), never in the repo.
- `chains.json` (contract addresses + chain id) IS committable — addresses are
  public by nature.

---

## 6. Testnet flow (what `examples/onchain_testnet_demo.py` shows)

1. Connect to Base Sepolia (env RPC).
2. Deploy (or reuse) `SafetyBinding` + `SafetyEvents`; print addresses.
3. `bind_agent("agent-001", user_addr, metadataHash)` → real tx; print hash +
   BaseScan(Sepolia) link.
4. `verify_binding` reads chain → proves non-transferable + bound.
5. Run a few gated actions; each key event `record()`s a real tx.
6. `get_claims_evidence` now includes real tx hashes + block numbers + a
   BaseScan link per event.
7. `revoke_binding` → real tx; `verify_binding` shows revoked.

A `--verify-only` mode that skips sending tx and just reads the deployed
contracts (so CI / a skeptic can verify without spending gas).

---

## 7. Scope / effort (honest)

| Item | Effort | Notes |
|---|---|---|
| `SafetyBinding.sol` (ERC-5192) | S (0.5d) | Boring, audited pattern |
| `SafetyEvents.sol` | S (0.5d) | Append-only log |
| Deploy + verify on Sepolia | S | One-time, scripted |
| `onchain_web3.py` client | M (1–2d) | web3.py, same interface |
| Wire `OnChainBoundProtocol` / `DualAudit` selection | S | LIVE_TESTNET flag |
| `examples/onchain_testnet_demo.py` | S | End-to-end |
| Conformance: `verify_binding` returns real chain data; `record` emits real tx | S | Add to a `conformance/onchain_*` test (needs RPC or `--verify-only`) |
| README: "simulated" → "live testnet (Base Sepolia)" | S | Update claims precisely |

Total: ~1 focused week, one person, stdlib + web3.py + Solidity basics. No mainnet, no real funds.

---

## 8. What you can then say publicly (and what you can't)

CAN say:
- "Agent binding is a non-transferable on-chain record (ERC-5192) on Base
  Sepolia; verifiable by anyone via the contract at <address>."
- "Key audit events (binding, high-value, approval, kill switch, scope
  violation) are anchored on-chain and tamper-evident."
- "Insurance evidence package includes real on-chain tx hashes + block numbers."

CANNOT say (yet):
- "Secured on mainnet" / "insured" / "production on-chain" — it's testnet.
- That the chain *enforces* anything — it anchors; Python enforces. Keep that line.
- That this replaces the audit "honest limits" entirely — it upgrades one bullet.

---

## 9. Risks / guardrails

- **Don't overclaim in the same breath as the insurer outreach.** Testnet
  binding is real proof-of-concept; the carrier conversation is about *coverage*,
  which is untouched by this. Keep them separate so neither undermines the other.
- **Fail-closed on misconfig.** `LIVE_TESTNET=True` without RPC/address/key must
  raise, never fall back to simulating and printing "live."
- **Don't commit keys.** Testnet deployer key is single-use and discarded;
  provider URL is env-only.
- **Keep the simulated path.** Reference users without web3 installed must still
  run untouched. The default stays simulated; testnet is opt-in.
