"""Read-only EVM JSON-RPC client.

Deliberately supports only `eth_` read methods. There is no signing, no sending and no
transaction construction anywhere in TraceLedger (G1). Every returned fact carries the RPC
source and the time it was read, so a stale or wrong-network endpoint is traceable (P6).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import requests

# Allow-list of RPC methods. Anything not listed is refused before it reaches the network,
# so no code path can grow into eth_sendTransaction / eth_sign (G1).
READ_ONLY_METHODS = frozenset({
    "eth_chainId",
    "eth_blockNumber",
    "eth_call",
    "eth_getCode",
    "eth_getBalance",
    "eth_getTransactionByHash",
    "eth_getTransactionReceipt",
    "eth_getBlockByNumber",
    "eth_getBlockByHash",
})


class RpcError(RuntimeError):
    pass


class ReadOnlyViolation(RuntimeError):
    """Raised when a caller asks for a non-read RPC method."""


@dataclass(frozen=True)
class Provenance:
    """Where a fact came from. Attached to every verified chain fact (P6)."""

    rpc_url: str
    chain_id: int
    method: str
    read_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rpc_url": self.rpc_url,
            "chain_id": self.chain_id,
            "method": self.method,
            "read_at": self.read_at,
        }


class EvmRpc:
    def __init__(self, rpc_url: str, expected_chain_id: int, timeout: float = 20.0,
                 session: requests.Session | None = None) -> None:
        self.rpc_url = rpc_url
        self.expected_chain_id = expected_chain_id
        self.timeout = timeout
        self._session = session or requests.Session()
        self._request_count = 0
        self._verified_chain_id: int | None = None

    @property
    def request_count(self) -> int:
        """Used by the tool/query-efficiency metric at CP8."""
        return self._request_count

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        if method not in READ_ONLY_METHODS:
            raise ReadOnlyViolation(
                f"{method} is not an allowed read-only method. TraceLedger never writes to a chain (G1)."
            )
        payload = {"jsonrpc": "2.0", "id": self._request_count + 1, "method": method,
                   "params": params or []}
        self._request_count += 1
        try:
            response = self._session.post(self.rpc_url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise RpcError(f"RPC transport error calling {method} on {self.rpc_url}: {exc}") from exc
        if response.status_code != 200:
            raise RpcError(f"RPC HTTP {response.status_code} from {self.rpc_url}: {response.text[:200]}")
        body = response.json()
        if "error" in body:
            raise RpcError(f"RPC error from {self.rpc_url} on {method}: {body['error']}")
        return body.get("result")

    def provenance(self, method: str) -> Provenance:
        return Provenance(rpc_url=self.rpc_url, chain_id=self.expected_chain_id, method=method)

    def assert_chain(self) -> int:
        """Confirm the endpoint really is the chain we were configured for.

        A silently wrong network is one of the easiest ways to produce confident
        nonsense (RISKS.md P6), so this is called before any fact is trusted.
        """
        if self._verified_chain_id is not None:
            return self._verified_chain_id
        actual = int(self.call("eth_chainId"), 16)
        if actual != self.expected_chain_id:
            raise RpcError(
                f"Wrong network: {self.rpc_url} reports chain id {actual}, "
                f"expected {self.expected_chain_id}."
            )
        self._verified_chain_id = actual
        return actual

    def is_contract(self, address: str) -> bool:
        code = self.call("eth_getCode", [address, "latest"])
        return bool(code) and code != "0x"
