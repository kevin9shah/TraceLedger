"""ERC-20 metadata read straight from the contract.

Guardrail G7: a token is identified by its contract address, and decimals are read from the
contract. Symbols are recorded for display only and are never used to decide identity -- on
Polygon the canonical Tether contract reports `USDT0`, and two distinct live contracts both
report `USDC`, so a symbol match is actively wrong (see DECISIONS.md D6).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .rpc import EvmRpc, Provenance, RpcError

# Function selectors (first 4 bytes of keccak of the signature).
SELECTOR_DECIMALS = "0x313ce567"  # decimals()
SELECTOR_SYMBOL = "0x95d89b41"    # symbol()
SELECTOR_NAME = "0x06fdde03"      # name()

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


class TokenMetadataError(RuntimeError):
    pass


def _decode_string(hex_result: str) -> str | None:
    """Decode an ABI-encoded string, tolerating the bytes32 style some old tokens use."""
    if not hex_result or not hex_result.startswith("0x"):
        return None
    raw = bytes.fromhex(hex_result[2:])
    if len(raw) >= 64:
        length = int.from_bytes(raw[32:64], "big")
        if 0 < length <= len(raw) - 64:
            return raw[64:64 + length].decode("utf-8", errors="replace")
    stripped = raw.rstrip(b"\x00")
    return stripped.decode("utf-8", errors="replace") if stripped else None


def _decode_uint(hex_result: str) -> int:
    if not hex_result or not hex_result.startswith("0x"):
        raise TokenMetadataError(f"expected a uint return value, got {hex_result!r}")
    return int(hex_result, 16)


@dataclass(frozen=True)
class TokenMetadata:
    """Verified on-chain identity of a token contract."""

    address: str          # lowercase, the only identity that matters (G7)
    decimals: int         # read from the contract, never hardcoded (G7)
    symbol: str | None    # display only
    name: str | None      # display only
    provenance: Provenance

    def base_units(self, human_amount: str) -> int:
        """Convert a decimal string to integer base units exactly, no floats (G8)."""
        from decimal import Decimal, localcontext
        with localcontext() as ctx:
            ctx.prec = 60
            scaled = Decimal(str(human_amount)) * (Decimal(10) ** self.decimals)
        if scaled != scaled.to_integral_value():
            raise ValueError(
                f"{human_amount} has more precision than {self.decimals} decimals allows "
                f"for token {self.address}"
            )
        return int(scaled)

    def format_units(self, base_units: int) -> str:
        """Render base units as a decimal string exactly, no floats (G8)."""
        from decimal import Decimal, localcontext
        with localcontext() as ctx:
            ctx.prec = 60
            value = Decimal(base_units) / (Decimal(10) ** self.decimals)
        return format(value, "f")

    def as_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "decimals": self.decimals,
            "symbol": self.symbol,
            "name": self.name,
            "provenance": self.provenance.as_dict(),
        }


def read_token_metadata(rpc: EvmRpc, address: str) -> TokenMetadata:
    """Read a token's identity from the chain. Raises if the address holds no contract."""
    addr = address.strip().lower()
    if not (addr.startswith("0x") and len(addr) == 42):
        raise TokenMetadataError(f"not a 20-byte hex address: {address!r}")
    rpc.assert_chain()
    if not rpc.is_contract(addr):
        raise TokenMetadataError(
            f"{addr} holds no contract code on chain {rpc.expected_chain_id} -- "
            "it cannot be a token contract."
        )
    try:
        decimals = _decode_uint(rpc.call("eth_call", [{"to": addr, "data": SELECTOR_DECIMALS}, "latest"]))
    except (RpcError, TokenMetadataError) as exc:
        raise TokenMetadataError(f"{addr} did not answer decimals(): {exc}") from exc
    if not 0 <= decimals <= 36:
        raise TokenMetadataError(f"{addr} reported implausible decimals={decimals}")

    def _optional_string(selector: str) -> str | None:
        try:
            return _decode_string(rpc.call("eth_call", [{"to": addr, "data": selector}, "latest"]))
        except RpcError:
            return None

    return TokenMetadata(
        address=addr,
        decimals=decimals,
        symbol=_optional_string(SELECTOR_SYMBOL),
        name=_optional_string(SELECTOR_NAME),
        provenance=rpc.provenance("eth_call"),
    )
