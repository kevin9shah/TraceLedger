"""Unit tests for token identity and base-unit arithmetic (G7, G8).

No network: metadata is constructed directly so the maths is tested in isolation.
"""
from __future__ import annotations

import pytest

from traceledger.chain.rpc import Provenance, ReadOnlyViolation, EvmRpc
from traceledger.chain.tokens import TokenMetadata, _decode_string, _decode_uint


def meta(decimals: int = 6, address: str = "0x" + "ab" * 20) -> TokenMetadata:
    return TokenMetadata(
        address=address, decimals=decimals, symbol="USDC", name="USD Coin",
        provenance=Provenance(rpc_url="http://test", chain_id=137, method="eth_call", read_at=0.0),
    )


class TestBaseUnits:
    def test_whole_amount(self):
        assert meta().base_units("1") == 1_000_000

    def test_full_precision(self):
        assert meta().base_units("0.000001") == 1

    def test_trailing_zeros_are_irrelevant(self):
        assert meta().base_units("1.000000") == meta().base_units("1")

    def test_no_float_drift(self):
        # 0.07 * 1e6 in binary floating point is 70000.00000000001; integer maths must not drift.
        assert meta().base_units("0.07") == 70_000
        assert meta().base_units("820.23") == 820_230_000

    def test_excess_precision_is_an_error_not_a_rounding(self):
        with pytest.raises(ValueError, match="more precision"):
            meta().base_units("0.0000001")

    def test_decimals_are_per_token(self):
        assert meta(decimals=18).base_units("1") == 10**18
        assert meta(decimals=0).base_units("5") == 5

    @pytest.mark.parametrize("amount", ["0", "1", "0.5", "999999.999999", "820.23"])
    def test_round_trip(self, amount):
        m = meta()
        assert m.format_units(m.base_units(amount)) == format(__import__("decimal").Decimal(amount), "f")

    def test_format_units_exact(self):
        assert meta().format_units(1) == "0.000001"
        assert meta().format_units(1_000_000) == "1"


class TestAbiDecoding:
    def test_decode_dynamic_string(self):
        encoded = ("0x" + "00" * 31 + "20" + "00" * 31 + "04"
                   + "55534443".ljust(64, "0"))  # "USDC"
        assert _decode_string(encoded) == "USDC"

    def test_decode_bytes32_style_string(self):
        assert _decode_string("0x" + "55534454".ljust(64, "0")) == "USDT"

    def test_decode_empty(self):
        assert _decode_string("0x") is None
        assert _decode_string("") is None

    def test_decode_uint(self):
        assert _decode_uint("0x06") == 6
        assert _decode_uint("0x" + "00" * 31 + "12") == 18


class TestReadOnly:
    @pytest.mark.parametrize("method", [
        "eth_sendTransaction", "eth_sendRawTransaction", "eth_sign",
        "eth_signTransaction", "personal_sign",
    ])
    def test_write_methods_are_refused_before_the_network(self, method):
        rpc = EvmRpc("http://127.0.0.1:1", 137)
        with pytest.raises(ReadOnlyViolation):
            rpc.call(method, [])
        assert rpc.request_count == 0, "a refused method must not have been sent"
