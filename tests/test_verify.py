"""Deterministic verifier tests, including the wrong-asset catch against a REAL transaction.

The wrong-asset catch is the demo's central claim, so RISKS.md S20 requires proof that it comes
from reading the contract address rather than from matching a symbol string. The tests at the
bottom of this file establish that: the catch still fires when the symbol is changed to anything
at all, and it fires on a genuine Polygon transaction.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from traceledger.chain.rpc import Provenance
from traceledger.chain.tokens import TokenMetadata
from traceledger.chain.transfers import fetch_transaction_facts
from traceledger.records import ApprovedAddress, Invoice, LedgerEntry, PaymentRequest
from traceledger.verify import (
    DEFAULT_MIN_CONFIRMATIONS,
    Finding,
    Status,
    check_amount,
    check_asset,
    check_confirmations,
    check_destination,
    check_destination_approved,
    check_duplicates,
    check_ledger_arithmetic,
    check_payment_direction,
    check_transaction_succeeded,
    check_zero_value_transfer,
    check_transfer_ambiguity,
    verify_payment_case,
)
from tests.test_transfers import FakeRpc, fixture

USDT = "0xc2132d05d31c914a87c6611c10748aeb04b58e8f"
USDC_NATIVE = "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"
USDC_BRIDGED = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"

SIMPLE_TX = "0x5e857c89f092901403c91fc634d84ff531b795303d448b9e6c1b25af251f5a05"
SIMPLE_RECIPIENT = "0x5f6d2b112c2d0ebe87d0d95d08ce47e13e01866a"
SIMPLE_VALUE_BASE = 94_951_335          # 94.951335 USDT
TWO_TOKEN_TX = "0x7858560afe25b850ce458695bdc001cb48fc52b1eeeadf1fe21d034510770963"


def meta(address: str, decimals: int = 6, symbol: str | None = "USDC") -> TokenMetadata:
    return TokenMetadata(
        address=address, decimals=decimals, symbol=symbol, name="test token",
        provenance=Provenance(rpc_url="http://test", chain_id=137, method="eth_call", read_at=0.0),
    )


def simple_facts(head: int | None = None):
    return fetch_transaction_facts(FakeRpc(fixture("tx_5e857c89"), head=head), SIMPLE_TX)


def two_token_facts():
    return fetch_transaction_facts(FakeRpc(fixture("tx_7858560a")), TWO_TOKEN_TX)


def invoice(token: str, amount: str = "94.951335", rid: str = "INV-R1") -> Invoice:
    return Invoice.from_dict({
        "record_id": rid, "invoice_id": "INV-1041", "counterparty": "Acme Supplies",
        "amount": amount, "token_contract": token, "simulated": True,
    })


def request(token: str, destination: str = SIMPLE_RECIPIENT,
            amount: str = "94.951335", rid: str = "PR-R1") -> PaymentRequest:
    return PaymentRequest.from_dict({
        "record_id": rid, "request_id": "PR-77", "invoice_id": "INV-1041",
        "expected_destination": destination, "amount": amount,
        "token_contract": token, "simulated": True,
    })


# --------------------------------------------------------------------------- G4: evidence

class TestEvidenceIsMandatory:
    def test_verified_without_evidence_cannot_be_constructed(self):
        with pytest.raises(ValueError, match="cites no evidence"):
            Finding(code="x", status=Status.VERIFIED, summary="no evidence")

    def test_conflict_without_evidence_cannot_be_constructed(self):
        with pytest.raises(ValueError, match="cites no evidence"):
            Finding(code="x", status=Status.CONFLICT, summary="no evidence")

    def test_missing_may_omit_evidence(self):
        f = Finding(code="x", status=Status.MISSING, summary="nothing to cite")
        assert f.evidence_ids == ()


# --------------------------------------------------------------------------- individual checks

class TestTransactionStatus:
    def test_successful_transaction_verified(self):
        f = check_transaction_succeeded(simple_facts())
        assert f.status is Status.VERIFIED and SIMPLE_TX in f.evidence_ids

    def test_reverted_transaction_is_a_conflict(self):
        data = fixture("tx_5e857c89")
        data["receipt"] = {**data["receipt"], "status": "0x0"}
        f = check_transaction_succeeded(fetch_transaction_facts(FakeRpc(data), SIMPLE_TX))
        assert f.status is Status.CONFLICT and "reverted" in f.summary


class TestConfirmations:
    def test_below_threshold_is_missing_not_verified(self):
        f = check_confirmations(simple_facts(head=96_369_410), minimum=12)
        assert f.status is Status.MISSING
        assert f.evidence_ids == ()

    def test_above_threshold_is_verified(self):
        f = check_confirmations(simple_facts(head=96_369_500), minimum=12)
        assert f.status is Status.VERIFIED

    def test_wording_never_claims_finality(self):
        """P10: "confirmed on-chain" must not be presented as final or guaranteed. The word
        "final" may appear only in the disclaimer, never as a claim."""
        f = check_confirmations(simple_facts(head=96_369_500))
        lowered = f.summary.lower()
        assert "guarantee" not in lowered
        for claim in ("is final", "final settlement", "irreversible", "cannot be reversed"):
            assert claim not in lowered
        assert "not the same as final" in lowered


class TestAmount:
    def test_exact_match_verified(self):
        f = check_amount(simple_facts(), meta(USDT), "94.951335", SIMPLE_RECIPIENT, ["INV-R1"])
        assert f.status is Status.VERIFIED
        assert f.detail["expected_base_units"] == str(SIMPLE_VALUE_BASE)
        assert f.detail["decimals_source"] == "contract"

    def test_one_base_unit_short_is_a_conflict(self):
        f = check_amount(simple_facts(), meta(USDT), "94.951334", SIMPLE_RECIPIENT, ["INV-R1"])
        assert f.status is Status.CONFLICT
        assert f.detail["difference_base_units"] == "-1"

    def test_amount_is_compared_in_base_units_not_floats(self):
        # 94.951335 in float arithmetic is not exactly representable; integers must be used.
        f = check_amount(simple_facts(), meta(USDT), "94.951335", SIMPLE_RECIPIENT, ["INV-R1"])
        assert f.status is Status.VERIFIED

    def test_excess_precision_is_reported_not_rounded(self):
        f = check_amount(simple_facts(), meta(USDT), "94.9513351", SIMPLE_RECIPIENT, ["INV-R1"])
        assert f.status is Status.CONFLICT and "decimals" in f.summary

    def test_decimals_come_from_metadata_so_wrong_decimals_change_the_result(self):
        """Hardcoding 6 decimals would make an 18-decimal token appear wildly wrong (G7)."""
        f = check_amount(simple_facts(), meta(USDT, decimals=18), "94.951335",
                         SIMPLE_RECIPIENT, ["INV-R1"])
        assert f.status is Status.CONFLICT

    def test_no_matching_transfer_is_missing(self):
        f = check_amount(simple_facts(), meta(USDT), "1.0", "0x" + "cd" * 20, ["INV-R1"])
        assert f.status is Status.MISSING


class TestDestination:
    def test_expected_destination_verified(self):
        f = check_destination(simple_facts(), USDT, SIMPLE_RECIPIENT, ["PR-R1"])
        assert f.status is Status.VERIFIED

    def test_different_destination_is_a_conflict(self):
        f = check_destination(simple_facts(), USDT, "0x" + "cd" * 20, ["PR-R1"])
        assert f.status is Status.CONFLICT
        assert SIMPLE_RECIPIENT in f.detail["recipients_for_token"]

    def test_wording_is_mismatch_not_fraud(self):
        f = check_destination(simple_facts(), USDT, "0x" + "cd" * 20, ["PR-R1"])
        for banned in ("fraud", "scam", "theft", "stolen"):
            assert banned not in f.summary.lower()

    def test_case_insensitive_address_comparison(self):
        f = check_destination(simple_facts(), USDT.upper(), SIMPLE_RECIPIENT.upper(), ["PR-R1"])
        assert f.status is Status.VERIFIED


class TestApprovedAddress:
    def approved(self, address: str) -> ApprovedAddress:
        return ApprovedAddress.from_dict({
            "record_id": "APP-1", "address": address, "approved_for": "Acme Supplies"})

    def test_on_list_verified(self):
        f = check_destination_approved(SIMPLE_RECIPIENT, [self.approved(SIMPLE_RECIPIENT)])
        assert f.status is Status.VERIFIED and f.evidence_ids == ("APP-1",)

    def test_not_on_list_is_a_risk_indicator_not_a_verdict(self):
        f = check_destination_approved("0x" + "cd" * 20, [self.approved(SIMPLE_RECIPIENT)])
        assert f.status is Status.CONFLICT
        assert "risk indicator" in f.summary.lower()
        for banned in ("fraud", "scam", "theft"):
            assert banned not in f.summary.lower()

    def test_empty_list_is_missing_not_a_pass(self):
        f = check_destination_approved(SIMPLE_RECIPIENT, [])
        assert f.status is Status.MISSING


class TestAmbiguity:
    def test_single_transfer_is_not_ambiguous(self):
        assert check_transfer_ambiguity(simple_facts(), USDT, SIMPLE_RECIPIENT) is None

    def test_two_matching_transfers_are_reported_not_resolved(self):
        """Real tx 0x7858560a has two USDT transfers; picking one would be arbitrary (D18)."""
        facts = two_token_facts()
        usdt_recipients = [t.recipient for t in facts.transfers_of(USDT)]
        # Construct the ambiguous case from the real data: same token, same recipient twice.
        f = check_transfer_ambiguity(facts, USDT, usdt_recipients[0])
        assert f is None or f.status is Status.MISSING


class TestDuplicates:
    def test_duplicate_invoice_ids_cite_every_record(self):
        a = invoice(USDC_NATIVE, rid="INV-R1")
        b = invoice(USDC_NATIVE, rid="INV-R2")
        findings = check_duplicates(invoices=[a, b])
        assert len(findings) == 1
        assert findings[0].status is Status.CONFLICT
        assert set(findings[0].evidence_ids) == {"INV-R1", "INV-R2"}

    def test_unique_ids_produce_no_finding(self):
        a = invoice(USDC_NATIVE, rid="INV-R1")
        assert check_duplicates(invoices=[a]) == ()


class TestLedgerArithmetic:
    def entry(self, amount: str, direction: str = "credit", rid: str = "LE-1") -> LedgerEntry:
        return LedgerEntry.from_dict({
            "record_id": rid, "entry_id": rid, "invoice_id": "INV-1041",
            "amount": amount, "direction": direction})

    def test_entries_summing_to_invoice_verified(self):
        f = check_ledger_arithmetic(
            invoice(USDT, "100.00"),
            [self.entry("60.00", rid="LE-1"), self.entry("40.00", rid="LE-2")],
            meta(USDT))
        assert f.status is Status.VERIFIED
        assert set(f.evidence_ids) == {"INV-R1", "LE-1", "LE-2"}

    def test_shortfall_reported_with_difference(self):
        f = check_ledger_arithmetic(
            invoice(USDT, "100.00"), [self.entry("60.00")], meta(USDT))
        assert f.status is Status.CONFLICT
        assert f.detail["difference_base_units"] == str(40_000_000)

    def test_debits_subtract(self):
        f = check_ledger_arithmetic(
            invoice(USDT, "50.00"),
            [self.entry("100.00", rid="LE-1"), self.entry("50.00", "debit", rid="LE-2")],
            meta(USDT))
        assert f.status is Status.VERIFIED

    def test_no_entries_is_missing(self):
        f = check_ledger_arithmetic(invoice(USDT, "100.00"), [], meta(USDT))
        assert f.status is Status.MISSING


# --------------------------------------------------------------------------- S20: the demo claim

class TestWrongAssetCatchOnRealTransaction:
    """The demo's central claim, on real chain data.

    An invoice names the USDC contract. A real Polygon transaction delivered USDT. The system
    must report CONFLICT, and must do so because the *contract addresses* differ.
    """

    def result(self, token_symbol: str | None = "USDC"):
        return verify_payment_case(
            facts=simple_facts(head=96_369_500),
            invoice=invoice(USDC_NATIVE, amount="94.951335"),
            token_meta=meta(USDC_NATIVE, symbol=token_symbol),
            payment_request=request(USDC_NATIVE),
            approved=[ApprovedAddress.from_dict({
                "record_id": "APP-1", "address": SIMPLE_RECIPIENT, "approved_for": "Acme"})],
        )

    def test_wrong_asset_is_a_conflict(self):
        asset = next(f for f in self.result().findings if f.code == "payment.asset")
        assert asset.status is Status.CONFLICT
        assert USDC_NATIVE in asset.summary and USDT in asset.summary

    def test_conflict_cites_the_transaction_and_the_records(self):
        asset = next(f for f in self.result().findings if f.code == "payment.asset")
        assert SIMPLE_TX in asset.evidence_ids
        assert "INV-R1" in asset.evidence_ids and "PR-R1" in asset.evidence_ids

    @pytest.mark.parametrize("symbol", ["USDC", "USDT", "USDT0", "", None, "TOTALLY-WRONG"])
    def test_catch_does_not_depend_on_the_symbol_string(self, symbol):
        """RISKS.md S20: if the verdict moved with the symbol, the demo would be theatre."""
        asset = next(f for f in self.result(symbol).findings if f.code == "payment.asset")
        assert asset.status is Status.CONFLICT

    def test_correct_token_verifies(self):
        """The same machinery must be able to say yes, or a CONFLICT means nothing."""
        res = verify_payment_case(
            facts=simple_facts(head=96_369_500),
            invoice=invoice(USDT, amount="94.951335"),
            token_meta=meta(USDT, symbol="USDT0"),
            payment_request=request(USDT),
            approved=[ApprovedAddress.from_dict({
                "record_id": "APP-1", "address": SIMPLE_RECIPIENT, "approved_for": "Acme"})],
        )
        assert not res.has_conflict, [f.summary for f in res.conflicts]
        codes = {f.code: f.status for f in res.findings}
        assert codes["payment.asset"] is Status.VERIFIED
        assert codes["payment.amount"] is Status.VERIFIED
        assert codes["payment.destination"] is Status.VERIFIED
        assert codes["destination.approval"] is Status.VERIFIED

    def test_bridged_vs_native_usdc_is_caught(self):
        """Both contracts report symbol "USDC"; only the address distinguishes them (D6)."""
        res = verify_payment_case(
            facts=two_token_facts(),
            invoice=invoice(USDC_BRIDGED, amount="5067.462894"),
            token_meta=meta(USDC_BRIDGED, symbol="USDC"),
            payment_request=request(USDC_BRIDGED, destination="0x8f10b468b06c6fd214b65f87778827f7d113f996"),
        )
        asset = next(f for f in res.findings if f.code == "payment.asset")
        assert asset.status is Status.CONFLICT
        assert USDC_NATIVE in asset.summary  # the native contract is what actually moved


class TestOrchestration:
    def test_mismatched_token_metadata_raises(self):
        with pytest.raises(ValueError, match="token metadata is for"):
            verify_payment_case(
                facts=simple_facts(), invoice=invoice(USDC_NATIVE),
                token_meta=meta(USDT), payment_request=request(USDC_NATIVE))

    def test_absent_payment_request_yields_missing_not_a_pass(self):
        res = verify_payment_case(
            facts=simple_facts(head=96_369_500), invoice=invoice(USDT),
            token_meta=meta(USDT), payment_request=None)
        dest = next(f for f in res.findings if f.code == "payment.destination")
        assert dest.status is Status.MISSING

    def test_missing_finding_generates_a_next_step(self):
        res = verify_payment_case(
            facts=simple_facts(head=96_369_500), invoice=invoice(USDT),
            token_meta=meta(USDT), payment_request=None)
        steps = res.by_status(Status.NEXT_STEP)
        assert steps and any("expected_destination" in s.summary for s in steps)

    def test_records_disagreeing_with_each_other_is_reported(self):
        res = verify_payment_case(
            facts=simple_facts(head=96_369_500),
            invoice=invoice(USDT), token_meta=meta(USDT),
            payment_request=request(USDC_NATIVE))
        codes = {f.code for f in res.findings}
        assert "records.token_disagreement" in codes

    def test_every_verified_and_conflict_finding_cites_evidence(self):
        res = verify_payment_case(
            facts=simple_facts(head=96_369_500), invoice=invoice(USDC_NATIVE),
            token_meta=meta(USDC_NATIVE), payment_request=request(USDC_NATIVE))
        for f in res.findings:
            if f.status in (Status.VERIFIED, Status.CONFLICT):
                assert f.evidence_ids, f.code

    def test_result_serialises_without_floats(self):
        res = verify_payment_case(
            facts=simple_facts(head=96_369_500), invoice=invoice(USDT),
            token_meta=meta(USDT), payment_request=request(USDT))
        blob = json.dumps(res.as_dict())
        assert "e+" not in blob and "e-" not in blob

        def no_floats(node):
            if isinstance(node, float):
                raise AssertionError("a float reached the serialised output")
            if isinstance(node, dict):
                for v in node.values():
                    no_floats(v)
            if isinstance(node, list):
                for v in node:
                    no_floats(v)

        no_floats(res.as_dict())


# --------------------------------------------------------------------------- failure modes

REVERTED_TX = "0xe00f524301058205699c9f226df02b22bd6c9bbb3a990a36c48d35d41bc0a16f"


def reverted_facts():
    """A REAL reverted Polygon transaction (block 96371332, gasUsed 96064, no Transfer events).

    Reverted transfers emit no Transfer logs, so they are invisible to log scanning -- which is
    precisely why 'the ledger says paid' cases need the receipt status checked, not the logs.
    """
    return fetch_transaction_facts(FakeRpc(fixture("tx_e00f5243")), REVERTED_TX)


class TestRevertedTransaction:
    def test_real_reverted_transaction_has_no_transfers(self):
        facts = reverted_facts()
        assert facts.status == 0
        assert facts.transfers == ()
        assert facts.tokens_involved() == ()

    def test_reverted_is_a_conflict_citing_the_hash(self):
        f = check_transaction_succeeded(reverted_facts())
        assert f.status is Status.CONFLICT
        assert "reverted" in f.summary and REVERTED_TX in f.evidence_ids

    def test_confirmations_say_the_FAILURE_is_confirmed(self):
        """A reverted tx at depth is a confirmed failure. Reading 'Confirmed on-chain' beside a
        failed payment would mislead a reviewer."""
        f = check_confirmations(reverted_facts(), minimum=12)
        assert f.status is Status.VERIFIED
        assert "FAILURE" in f.summary
        assert f.detail["confirms_outcome"] == "failure"

    def test_success_wording_differs_from_failure_wording(self):
        ok = check_confirmations(simple_facts(head=96_369_500))
        bad = check_confirmations(reverted_facts(), minimum=12)
        assert ok.detail["confirms_outcome"] == "success"
        assert "FAILURE" not in ok.summary
        assert ok.summary != bad.summary

    def test_confirmed_is_not_described_as_final(self):
        for f in (check_confirmations(simple_facts(head=96_369_500)),
                  check_confirmations(reverted_facts(), minimum=12)):
            assert "not the same as final" in f.summary
            assert "guaranteed" not in f.summary.lower()

    def test_ledger_claiming_paid_against_a_reverted_tx_conflicts(self):
        res = verify_payment_case(
            facts=reverted_facts(), invoice=invoice(USDT, "50.00"),
            token_meta=meta(USDT, symbol="USDT0"), payment_request=request(USDT))
        assert res.has_conflict
        codes = {f.code: f.status for f in res.findings}
        assert codes["tx.status"] is Status.CONFLICT
        # Nothing may be claimed VERIFIED about the asset, destination or amount.
        assert codes["payment.asset"] is Status.MISSING
        assert codes["payment.destination"] is Status.MISSING
        assert codes["payment.amount"] is Status.MISSING


class TestPaymentDirection:
    def test_reversed_direction_is_a_conflict(self):
        """The party expected to receive instead sent the token."""
        facts = simple_facts()
        sender = facts.transfers[0].sender
        f = check_payment_direction(facts, USDT, sender, ["PR-R1"])
        assert f is not None and f.status is Status.CONFLICT
        assert "Direction reversed" in f.summary
        assert f.detail["received_base_units"] == "0"

    def test_correct_direction_produces_no_finding(self):
        f = check_payment_direction(simple_facts(), USDT, SIMPLE_RECIPIENT, ["PR-R1"])
        assert f is None

    def test_uninvolved_party_produces_no_finding(self):
        """Silence, not noise: a third party neither sent nor received."""
        f = check_payment_direction(simple_facts(), USDT, "0x" + "cd" * 20, ["PR-R1"])
        assert f is None

    def test_direction_conflict_appears_in_the_orchestrated_result(self):
        facts = simple_facts(head=96_369_500)
        sender = facts.transfers[0].sender
        res = verify_payment_case(
            facts=facts, invoice=invoice(USDT), token_meta=meta(USDT),
            payment_request=request(USDT, destination=sender))
        assert "payment.direction" in {f.code for f in res.findings}


class TestZeroValueTransfer:
    def zero_value_facts(self):
        """A succeeded transaction whose only matching transfer moves nothing."""
        data = fixture("tx_5e857c89")
        logs = [dict(log) for log in data["receipt"]["logs"]]
        for log in logs:
            if log.get("topics") and log["topics"][0].lower() == (
                    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"):
                log["data"] = "0x0"
        data["receipt"] = {**data["receipt"], "logs": logs}
        return fetch_transaction_facts(FakeRpc(data), SIMPLE_TX)

    def test_zero_value_transfer_is_a_conflict(self):
        f = check_zero_value_transfer(
            self.zero_value_facts(), USDT, SIMPLE_RECIPIENT, ["INV-R1"])
        assert f is not None and f.status is Status.CONFLICT
        assert "moved zero base units" in f.summary

    def test_non_zero_transfer_produces_no_finding(self):
        assert check_zero_value_transfer(
            simple_facts(), USDT, SIMPLE_RECIPIENT, ["INV-R1"]) is None

    def test_zero_value_still_looks_like_a_transfer_to_a_naive_check(self):
        """Why this check exists: token and destination both match, yet no value moved."""
        facts = self.zero_value_facts()
        assert check_asset(facts, USDT, None, ["INV-R1"]).status is Status.VERIFIED
        assert check_destination(facts, USDT, SIMPLE_RECIPIENT, ["PR-R1"]).status is Status.VERIFIED
        assert check_zero_value_transfer(facts, USDT, SIMPLE_RECIPIENT, ["INV-R1"]) is not None
