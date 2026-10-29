"""Parse an EVM transaction into verified ERC-20 transfer facts.

This is the deterministic ground truth the rest of TraceLedger is judged against. No LLM is
involved, every amount is an integer in base units (G8), and every fact carries the RPC source
it was read from (P6).

Two realities drive the design, both observed on live Polygon data:

* **A transaction can contain several Transfer events.** Real transfers routed through DEXes or
  intermediaries emit two or more (e.g. tx 0x7858...0963 has Transfer logs at index 794 and 796).
  So "the transfer in this transaction" is not a well-defined thing. A settling transfer must be
  selected by token contract *and* recipient, and if more than one matches, that ambiguity is
  reported rather than resolved by picking the first.
* **Token identity is the contract address.** Never the symbol (G7, D6, D14).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .rpc import EvmRpc, Provenance, RpcError

# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

ZERO_ADDRESS = "0x" + "0" * 40


class TransactionNotFound(RuntimeError):
    """The hash is not on this chain. Never treated as 'not yet confirmed' (G3)."""


class MalformedTransferLog(RuntimeError):
    pass


def _addr_from_topic(topic: str) -> str:
    """A 32-byte topic holding a left-padded address."""
    if not topic or len(topic) < 42:
        raise MalformedTransferLog(f"topic too short to hold an address: {topic!r}")
    return "0x" + topic[-40:].lower()


def normalise_hash(raw: str) -> str:
    """Accept a tx hash with or without 0x, any case; reject anything else loudly."""
    if not isinstance(raw, str):
        raise ValueError(f"transaction hash must be a string, got {type(raw).__name__}")
    h = raw.strip().lower()
    if h.startswith("0x"):
        h = h[2:]
    if len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
        raise ValueError(f"not a 32-byte transaction hash: {raw!r}")
    return "0x" + h


@dataclass(frozen=True)
class TransferEvent:
    """One ERC-20 Transfer event, exactly as the chain recorded it."""

    token: str          # contract address, lowercase - the only token identity (G7)
    sender: str
    recipient: str
    value: int          # integer base units, never a float (G8)
    log_index: int

    @property
    def is_mint(self) -> bool:
        return self.sender == ZERO_ADDRESS

    @property
    def is_burn(self) -> bool:
        return self.recipient == ZERO_ADDRESS

    def as_dict(self) -> dict[str, Any]:
        return {
            "token": self.token, "sender": self.sender, "recipient": self.recipient,
            "value": str(self.value),  # string, so no JSON consumer turns it into a float
            "log_index": self.log_index,
        }


@dataclass(frozen=True)
class TransactionFacts:
    """Everything the chain says about one transaction. Verified, not inferred."""

    tx_hash: str
    status: int                 # 1 = succeeded, 0 = reverted
    block_number: int
    chain_id: int
    sender: str                 # the EOA that signed it
    called_contract: str | None # tx.to - for a token transfer, the token contract
    transfers: tuple[TransferEvent, ...]
    confirmations: int
    provenance: Provenance
    simulated: bool = False     # always False here; real chain data only (G3)
    _notes: tuple[str, ...] = field(default=(), compare=False)

    @property
    def succeeded(self) -> bool:
        return self.status == 1

    def transfers_of(self, token: str) -> tuple[TransferEvent, ...]:
        token = token.strip().lower()
        return tuple(t for t in self.transfers if t.token == token)

    def transfers_to(self, recipient: str, token: str | None = None) -> tuple[TransferEvent, ...]:
        recipient = recipient.strip().lower()
        candidates = self.transfers if token is None else self.transfers_of(token)
        return tuple(t for t in candidates if t.recipient == recipient)

    def tokens_involved(self) -> tuple[str, ...]:
        seen: list[str] = []
        for t in self.transfers:
            if t.token not in seen:
                seen.append(t.token)
        return tuple(seen)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tx_hash": self.tx_hash, "status": self.status, "succeeded": self.succeeded,
            "block_number": self.block_number, "chain_id": self.chain_id,
            "sender": self.sender, "called_contract": self.called_contract,
            "confirmations": self.confirmations,
            "transfers": [t.as_dict() for t in self.transfers],
            "simulated": self.simulated,
            "provenance": self.provenance.as_dict(),
        }


def parse_transfer_logs(logs: list[dict[str, Any]]) -> tuple[TransferEvent, ...]:
    """Extract ERC-20 Transfer events from a receipt's logs, in log order.

    Non-Transfer logs are ignored. A log that claims to be a Transfer but is malformed raises,
    rather than being skipped: silently dropping a transfer would understate what moved.
    """
    events: list[TransferEvent] = []
    for log in logs:
        topics = log.get("topics") or []
        if not topics or topics[0].lower() != TRANSFER_TOPIC:
            continue
        # The standard event has 3 topics (signature + 2 indexed addresses). ERC-721 also uses
        # this signature but with a third indexed topic (tokenId), so 4 topics is not a fungible
        # transfer and must not be read as an amount.
        if len(topics) == 4:
            continue
        if len(topics) != 3:
            raise MalformedTransferLog(
                f"Transfer log with {len(topics)} topics at index {log.get('logIndex')}; "
                "expected 3 for a fungible token"
            )
        data = log.get("data") or "0x"
        try:
            value = 0 if data in ("", "0x") else int(data, 16)
        except ValueError as exc:
            raise MalformedTransferLog(f"Transfer log data is not hex: {data!r}") from exc
        if value < 0:
            raise MalformedTransferLog(f"negative transfer value decoded: {value}")
        events.append(TransferEvent(
            token=(log.get("address") or "").lower(),
            sender=_addr_from_topic(topics[1]),
            recipient=_addr_from_topic(topics[2]),
            value=value,
            log_index=int(log["logIndex"], 16) if isinstance(log["logIndex"], str) else int(log["logIndex"]),
        ))
    return tuple(sorted(events, key=lambda e: e.log_index))


def fetch_transaction_facts(rpc: EvmRpc, tx_hash: str) -> TransactionFacts:
    """Read one transaction from the chain and return its verified facts.

    Raises TransactionNotFound if the chain does not know the hash. A missing transaction is
    never reported as pending or assumed successful.
    """
    h = normalise_hash(tx_hash)
    chain_id = rpc.assert_chain()

    tx = rpc.call("eth_getTransactionByHash", [h])
    if tx is None:
        raise TransactionNotFound(
            f"{h} is not known to chain {chain_id} via {rpc.rpc_url}. "
            "It may be on a different network, or never broadcast."
        )
    receipt = rpc.call("eth_getTransactionReceipt", [h])
    if receipt is None:
        raise TransactionNotFound(
            f"{h} exists but has no receipt yet (still pending). "
            "Pending transactions are not evidence of settlement."
        )

    status_raw = receipt.get("status")
    if status_raw is None:
        raise RpcError(f"receipt for {h} has no status field; refusing to assume success")
    status = int(status_raw, 16) if isinstance(status_raw, str) else int(status_raw)

    block_number = int(receipt["blockNumber"], 16)
    head = int(rpc.call("eth_blockNumber"), 16)
    # A transaction in the head block has 1 confirmation, not 0.
    confirmations = max(0, head - block_number + 1)

    transfers = parse_transfer_logs(receipt.get("logs") or [])

    return TransactionFacts(
        tx_hash=h,
        status=status,
        block_number=block_number,
        chain_id=chain_id,
        sender=(tx.get("from") or "").lower(),
        called_contract=(tx.get("to") or "").lower() or None,
        transfers=transfers,
        confirmations=confirmations,
        provenance=rpc.provenance("eth_getTransactionReceipt"),
    )
