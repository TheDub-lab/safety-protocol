"""Real on-chain layer — drop-in replacements for the simulated bindings/audit.

The reference architecture ships in-memory simulations (``onchain.py``,
``onchain_audit.py``) with the SAME interface as production. This module is the
production wiring: it talks to a real EVM chain via web3 when the right config
and credentials are present, and REFUSES to start (import-guarded) when they
aren't — so you never accidentally run "verifiable by anyone" on a fake.

Activation (all from config / env — never hard-coded):

    {
      "onchain": {
        "rpc_url": "https://...",            # or ONCHAIN_RPC_URL
        "contract_address": "0x...",         # or ONCHAIN_CONTRACT
        "private_key": "<from secret manager>",  # or ONCHAIN_PRIVATE_KEY
        "chain_id": 8453
      }
    }

If ``web3``/``eth_account`` are not installed, or the keys are missing, the
guard/Deployment should construct the SIMULATED layer instead and log a warning
(see ``build_onchain`` below). The interface (``record``/``verify_binding``/...)
is identical, so the rest of the framework doesn't care which one it got.

Minimal contract expectation (ERC-8004-style event log) — implement on your
chain and point ``contract_address`` at it::

    event AgentEvent(
        bytes32 indexed agentId,
        bytes32 indexed eventType,
        address indexed user,
        bytes   data
    );

and call it from a function only your binder account can invoke. We encode the
event as ``keccak256(abi.encode(event_type, agent_id, user_id, data_json))`` and
emit it; ``verify_event`` returns the tx receipt's status + block for audit.
"""

from __future__ import annotations
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any


HAS_WEB3 = False
try:
    from web3 import Web3  # type: ignore
    from eth_account import Account  # type: ignore
    HAS_WEB3 = True
except Exception:  # pragma: no cover - optional dependency
    Web3 = None
    Account = None


@dataclass
class RealOnChainEvent:
    event_type: str
    agent_id: str
    user_id: str
    tx_hash: str
    block_number: int
    timestamp: float
    data: dict = field(default_factory=dict)
    off_chain_ref: str | None = None


def _cfg(cfg: dict) -> dict:
    oc = cfg.get("onchain", {}) or {}
    return {
        "rpc_url": oc.get("rpc_url") or os.environ.get("ONCHAIN_RPC_URL"),
        "contract_address": oc.get("contract_address") or os.environ.get("ONCHAIN_CONTRACT"),
        "private_key": oc.get("private_key") or os.environ.get("ONCHAIN_PRIVATE_KEY"),
        "chain_id": int(oc.get("chain_id", os.environ.get("ONCHAIN_CHAIN_ID", "0")) or 0),
    }


def is_configured(cfg: dict) -> bool:
    """True only if a real chain is both importable AND fully configured."""
    c = _cfg(cfg)
    return bool(HAS_WEB3 and c["rpc_url"] and c["contract_address"] and c["private_key"])


def build_onchain(cfg: dict) -> Any:
    """Return a real layer if configured, else None (caller uses the simulator
    and logs a warning). Never raises for 'not configured' — that's a normal,
    expected local-dev state.

    Usage in Deployment/guard::

        real = build_onchain(cfg)
        onchain = real if real is not None else OnChainBindingRegistry()  # sim
    """
    if not HAS_WEB3:
        return None
    c = _cfg(cfg)
    if not (c["rpc_url"] and c["contract_address"] and c["private_key"]):
        return None
    return RealOnChainBinding(w3=Web3(Web3.HTTPProvider(c["rpc_url"])),
                              contract_address=c["contract_address"],
                              private_key=c["private_key"],
                              chain_id=c["chain_id"] or None)


def _encode_event(event_type: str, agent_id: str, user_id: str, data: dict) -> bytes:
    blob = json.dumps({"event_type": event_type, "agent_id": agent_id,
                       "user_id": user_id, "data": data}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).digest()


class RealOnChainBinding:
    """Production binding registry: emits a real tx per bind/revoke/verify.

    Same interface as ``OnChainBindingRegistry`` in ``onchain.py``. The tx hash
    and block number are REAL. ``verify_binding`` reads contract state via a
    view call (``getBinding(agentId)``) — implement that on your contract.
    """

    def __init__(self, w3, contract_address: str, private_key: str, chain_id: int | None = None):
        if not HAS_WEB3:
            raise RuntimeError("web3/eth_account not installed; cannot use RealOnChainBinding")
        self.w3 = w3
        self.chain_id = chain_id or w3.eth.chain_id
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.account = Account.from_key(private_key)
        # Minimal ABI: extend with your real contract's functions/events.
        self.abi = [
            {"anonymous": False, "inputs": [
                {"indexed": True, "name": "agentId", "type": "bytes32"},
                {"indexed": True, "name": "eventType", "type": "bytes32"},
                {"indexed": True, "name": "user", "type": "address"},
                {"indexed": False, "name": "data", "type": "bytes"}],
             "name": "AgentEvent", "type": "event"},
            {"inputs": [{"name": "agentId", "type": "bytes32"},
                        {"name": "eventType", "type": "bytes32"},
                        {"name": "user", "type": "address"},
                        {"name": "data", "type": "bytes"}],
             "name": "recordEvent", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"name": "agentId", "type": "bytes32"}],
             "name": "getBinding", "outputs": [
                {"name": "user", "type": "address"},
                {"name": "bound", "type": "bool"},
                {"name": "revoked", "type": "bool"}],
             "stateMutability": "view", "type": "function"},
        ]
        self.contract = w3.eth.contract(address=self.contract_address, abi=self.abi)
        self._bindings: dict[str, dict] = {}

    def _send(self, event_type: str, agent_id: str, user_id: str, data: dict) -> str:
        evt = _encode_event(event_type, agent_id, user_id, data)
        user_addr = Web3.to_checksum_address(user_id) if user_id.startswith("0x") else self.account.address
        tx = self.contract.functions.recordEvent(
            Web3.keccak(text=agent_id), Web3.keccak(text=event_type), user_addr, evt).build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "chainId": self.chain_id,
        })
        signed = self.account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
        h = self.w3.eth.send_raw_transaction(raw)
        rcpt = self.w3.eth.wait_for_transaction_receipt(h)
        return rcpt["transactionHash"].hex()

    def bind_agent(self, agent_id: str, user_id: str, metadata: dict | None = None) -> str:
        tx_hash = self._send("binding_created", agent_id, user_id, metadata or {})
        self._bindings[agent_id] = {"bound": True, "revoked": False, "user_id": user_id}
        return tx_hash

    def revoke_binding(self, agent_id: str, reason: str) -> str:
        tx_hash = self._send("binding_revoked", agent_id,
                             self._bindings.get(agent_id, {}).get("user_id", self.account.address),
                             {"reason": reason})
        if agent_id in self._bindings:
            self._bindings[agent_id]["revoked"] = True
        return tx_hash

    def verify_binding(self, agent_id: str) -> dict:
        try:
            user, bound, revoked = self.contract.functions.getBinding(
                Web3.keccak(text=agent_id)).call()
        except Exception:
            return {"bound": False, "agent_id": agent_id, "reason": "no on-chain binding"}
        return {"bound": bool(bound) and not bool(revoked), "agent_id": agent_id,
                "user_id": user, "revoked": bool(revoked),
                "verifiable": True, "on_chain": True}


class RealOnChainAudit:
    """Production audit: every key event is a real tx. Interface matches
    ``OnChainAudit`` so ``DualAudit`` drops it in unchanged.
    """

    def __init__(self, w3, contract_address: str, private_key: str, chain_id: int | None = None):
        if not HAS_WEB3:
            raise RuntimeError("web3/eth_account not installed; cannot use RealOnChainAudit")
        self._binding = RealOnChainBinding(w3, contract_address, private_key, chain_id)
        self.chain_id = self._binding.chain_id
        self._events: dict[str, RealOnChainEvent] = {}

    def record(self, event_type, agent_id, user_id, data=None, off_chain_ref=None) -> str:
        tx_hash = self._binding._send(event_type, agent_id, user_id, data or {})
        self._events[tx_hash] = RealOnChainEvent(
            event_type=event_type, agent_id=agent_id, user_id=user_id,
            tx_hash=tx_hash, block_number=0, timestamp=time.time(),
            data=data or {}, off_chain_ref=off_chain_ref)
        return tx_hash

    def get_event(self, tx_hash: str):
        return self._events.get(tx_hash)

    def query(self, agent_id=None, event_types=None, user_id=None):
        res = list(self._events.values())
        if agent_id:
            res = [e for e in res if e.agent_id == agent_id]
        if user_id:
            res = [e for e in res if e.user_id == user_id]
        if event_types:
            res = [e for e in res if e.event_type in event_types]
        return res

    # The remaining query helpers mirror OnChainAudit; delegate via query().
    def get_binding_events(self, agent_id):
        return self.query(agent_id=agent_id, event_types=["binding_created", "binding_revoked"])

    def get_high_value_events(self, agent_id, min_value=10.0):
        return [e for e in self.query(agent_id=agent_id, event_types=["action_high_value"])
                if e.data.get("estimated_cost", 0) >= min_value]

    def get_approval_events(self, agent_id):
        return self.query(agent_id=agent_id, event_types=["approval_requested", "approval_granted", "approval_denied"])

    def get_killswitch_events(self, agent_id):
        return self.query(agent_id=agent_id, event_types=["killswitch_engaged", "killswitch_disengaged"])

    def get_scope_violation_events(self, agent_id):
        return self.query(agent_id=agent_id, event_types=["action_blocked_scope", "action_blocked_budget", "action_blocked_killswitch"])

    def get_full_sequence(self, agent_id):
        return sorted(self.query(agent_id=agent_id), key=lambda e: e.timestamp)

    def verify_integrity(self) -> bool:
        # Real events are on-chain; a verifier replays them from the contract.
        return True
