"""Parser verified against REAL Polygon transactions (RISKS.md P6).

Fixtures in tests/fixtures/ are genuine chain data captured by scripts/capture_fixtures.py --
not invented JSON (G3). Tests run offline so they are reproducible, but nothing here is synthetic.

The three fixtures were chosen because they cover the real shapes:
  tx_5e857c89 : one clean USDT transfer            (the simple case)
  tx_7858560a : USDT in and USDC out, 4 transfers  (both tokens move in ONE transaction)
  tx_094b7da1 : 41 logs, 19 transfers, 4 tokens    (routed swap; the messy case)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from traceledger.chain.transfers import (
    TRANSFER_TOPIC,
    MalformedTransferLog,
    TransactionNotFound,
    normalise_hash,
    parse_transfer_logs,
    fetch_transaction_facts,
)
from traceledger.chain.rpc import EvmRpc

FIXTURES = Path(__file__).parent / "fixtures"

USDT = "0xc2132d05d31c914a87c6611c10748aeb04b58e8f"
USDC_NATIVE = "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


class FakeRpc(EvmRpc):
    """Replays a captured fixture. Subclasses the real client so the code path is identical."""

    def __init__(self, data: dict, head: int | None = None):
        super().__init__(data["rpc_url"], data["chain_id"])
        self._data = data
        self._head = head if head is not None else data["captured_at_head_block"]
        self._verified_chain_id = data["chain_id"]

    def call(self, method, params=None):
        self._request_count += 1
        if method == "eth_chainId":
            return hex(self._data["chain_id"])
        if method == "eth_blockNumber":
            return hex(self._head)
        if method == "eth_getTransactionByHash":
            return self._data["tx"]
        if method == "eth_getTransactionReceipt":
            return self._data["receipt"]
        raise AssertionError(f"unexpected RPC call in test: {method}")


# --------------------------------------------------------------------------- hash normalising

class TestNormaliseHash:
    H = "0x5e857c89f092901403c91fc634d84ff531b795303d448b9e6c1b25af251f5a05"

    def test_accepts_canonical(self):
        assert normalise_hash(self.H) == self.H

    def test_accepts_without_prefix_and_uppercase(self):
        assert normalise_hash(self.H[2:].upper()) == self.H

    def test_accepts_surrounding_whitespace(self):
        assert normalise_hash(f"  {self.H}  ") == self.H

    @pytest.mark.parametrize("bad", [
        "0x123", "", "not a hash", "0x" + "g" * 64, "0x" + "a" * 63, "0x" + "a" * 65,
    ])
    def test_rejects_malformed(self, bad):
        with pytest.raises(ValueError):
            normalise_hash(bad)

    def test_rejects_non_string(self):
        with pytest.raises(ValueError):
            normalise_hash(12345)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- real fixtures

class TestSimpleRealTransfer:
    """tx_5e857c89: a single USDT transfer of 94.951335 USDT."""

    def setup_method(self):
        self.facts = fetch_transaction_facts(
            FakeRpc(fixture("tx_5e857c89")),
            "0x5e857c89f092901403c91fc634d84ff531b795303d448b9e6c1b25af251f5a05",
        )

    def test_succeeded(self):
        assert self.facts.status == 1 and self.facts.succeeded

    def test_exactly_one_transfer(self):
        assert len(self.facts.transfers) == 1

    def test_amount_is_exact_base_units(self):
        # 94.951335 USDT at 6 decimals. Integer, never a float.
        transfer = self.facts.transfers[0]
        assert transfer.value == 94_951_335
        assert isinstance(transfer.value, int)

    def test_token_is_the_contract_address(self):
        assert self.facts.transfers[0].token == USDT

    def test_parties(self):
        t = self.facts.transfers[0]
        assert t.sender == "0x0d0707963952f2fba59dd06f2b425ace40b492fe"
        assert t.recipient == "0x5f6d2b112c2d0ebe87d0d95d08ce47e13e01866a"

    def test_block_and_chain(self):
        assert self.facts.block_number == 96_369_410
        assert self.facts.chain_id == 137

    def test_not_simulated(self):
        assert self.facts.simulated is False

    def test_provenance_records_the_source(self):
        assert self.facts.provenance.rpc_url
        assert self.facts.provenance.chain_id == 137


class TestTwoTokensInOneTransaction:
    """tx_7858560a moves BOTH USDT and USDC. This is why a transaction cannot be said to have
    'paid' a token without naming the contract and the recipient."""

    def setup_method(self):
        self.facts = fetch_transaction_facts(
            FakeRpc(fixture("tx_7858560a")),
            "0x7858560afe25b850ce458695bdc001cb48fc52b1eeeadf1fe21d034510770963",
        )

    def test_four_transfers_across_two_tokens(self):
        assert len(self.facts.transfers) == 4
        assert set(self.facts.tokens_involved()) == {USDT, USDC_NATIVE}

    def test_usdt_and_usdc_legs_have_different_amounts(self):
        usdt = self.facts.transfers_of(USDT)
        usdc = self.facts.transfers_of(USDC_NATIVE)
        assert len(usdt) == 2 and len(usdc) == 2
        assert usdt[0].value == 5_072_557_260
        assert usdc[0].value == 5_067_462_894
        # The legs differ, so "the amount of this transaction" is meaningless on its own.
        assert usdt[0].value != usdc[0].value

    def test_selecting_by_token_alone_is_still_ambiguous(self):
        """Two USDT transfers means token alone does not identify a settling payment."""
        assert len(self.facts.transfers_of(USDT)) == 2

    def test_selecting_by_token_and_recipient_disambiguates(self):
        matches = self.facts.transfers_to("0x67366782805870060151383f4bbff9dab53e5cd6", USDT)
        assert len(matches) == 1
        assert matches[0].value == 5_072_557_260

    def test_transfers_are_in_log_order(self):
        indexes = [t.log_index for t in self.facts.transfers]
        assert indexes == sorted(indexes) == [794, 796, 798, 800]


class TestRoutedSwapWithManyTransfers:
    """tx_094b7da1: 41 logs, 19 Transfer events, 4 distinct tokens."""

    def setup_method(self):
        self.facts = fetch_transaction_facts(
            FakeRpc(fixture("tx_094b7da1")),
            "0x094b7da1b90a0b2201c362a6ac2b6e0ec686c74b78bf954f5d9c79d38f9bc1d7",
        )

    def test_all_transfers_parsed(self):
        assert len(self.facts.transfers) == 19

    def test_four_tokens(self):
        assert len(self.facts.tokens_involved()) == 4

    def test_non_transfer_logs_ignored(self):
        raw_logs = len(fixture("tx_094b7da1")["receipt"]["logs"])
        assert raw_logs == 41 and len(self.facts.transfers) < raw_logs

    def test_every_value_is_a_non_negative_int(self):
        assert all(isinstance(t.value, int) and t.value >= 0 for t in self.facts.transfers)

    def test_unrelated_token_yields_no_match(self):
        assert self.facts.transfers_of("0x" + "ff" * 20) == ()


class TestConfirmations:
    def test_head_block_counts_as_one_confirmation(self):
        data = fixture("tx_5e857c89")
        facts = fetch_transaction_facts(
            FakeRpc(data, head=96_369_410),
            "0x5e857c89f092901403c91fc634d84ff531b795303d448b9e6c1b25af251f5a05",
        )
        assert facts.confirmations == 1

    def test_confirmations_grow_with_head(self):
        data = fixture("tx_5e857c89")
        facts = fetch_transaction_facts(
            FakeRpc(data, head=96_369_460),
            "0x5e857c89f092901403c91fc634d84ff531b795303d448b9e6c1b25af251f5a05",
        )
        assert facts.confirmations == 51


# --------------------------------------------------------------------------- failure modes

class TestMissingTransaction:
    def test_unknown_hash_raises_rather_than_reporting_pending(self):
        data = fixture("tx_5e857c89")

        class NoTx(FakeRpc):
            def call(self, method, params=None):
                if method == "eth_getTransactionByHash":
                    return None
                return super().call(method, params)

        with pytest.raises(TransactionNotFound, match="not known to chain"):
            fetch_transaction_facts(NoTx(data), "0x" + "ab" * 32)

    def test_pending_transaction_is_not_settlement(self):
        data = fixture("tx_5e857c89")

        class NoReceipt(FakeRpc):
            def call(self, method, params=None):
                if method == "eth_getTransactionReceipt":
                    return None
                return super().call(method, params)

        with pytest.raises(TransactionNotFound, match="not evidence of settlement"):
            fetch_transaction_facts(NoReceipt(data), "0x" + "ab" * 32)


class TestLogDecoding:
    def test_reverted_status_is_preserved(self):
        data = fixture("tx_5e857c89")
        data["receipt"] = {**data["receipt"], "status": "0x0"}
        facts = fetch_transaction_facts(
            FakeRpc(data), "0x5e857c89f092901403c91fc634d84ff531b795303d448b9e6c1b25af251f5a05")
        assert facts.status == 0 and not facts.succeeded

    def test_erc721_transfer_is_not_read_as_an_amount(self):
        """ERC-721 uses the same event signature with a third indexed topic (tokenId).
        Reading that as a fungible amount would invent a transfer."""
        logs = [{
            "address": "0x" + "11" * 20,
            "topics": [TRANSFER_TOPIC, "0x" + "0" * 24 + "aa" * 20,
                       "0x" + "0" * 24 + "bb" * 20, "0x" + "0" * 63 + "1"],
            "data": "0x", "logIndex": "0x1",
        }]
        assert parse_transfer_logs(logs) == ()

    def test_malformed_transfer_log_raises_rather_than_being_skipped(self):
        logs = [{
            "address": "0x" + "11" * 20,
            "topics": [TRANSFER_TOPIC, "0x" + "0" * 24 + "aa" * 20],  # only 2 topics
            "data": "0x01", "logIndex": "0x1",
        }]
        with pytest.raises(MalformedTransferLog, match="expected 3"):
            parse_transfer_logs(logs)

    def test_non_transfer_logs_are_ignored(self):
        logs = [{"address": "0x" + "11" * 20, "topics": ["0x" + "de" * 32],
                 "data": "0x", "logIndex": "0x0"}]
        assert parse_transfer_logs(logs) == ()

    def test_zero_value_transfer_is_kept(self):
        """A zero-value transfer is a real event and must not be dropped."""
        logs = [{
            "address": "0x" + "11" * 20,
            "topics": [TRANSFER_TOPIC, "0x" + "0" * 24 + "aa" * 20, "0x" + "0" * 24 + "bb" * 20],
            "data": "0x0", "logIndex": "0x0",
        }]
        events = parse_transfer_logs(logs)
        assert len(events) == 1 and events[0].value == 0
